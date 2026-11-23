"""Audit ramped references against independently observed native force commands."""
from __future__ import annotations

import math

from .robot_validation import acceptance_config


def evaluate_position_force_control(manifest, records, native_records, samples):
    data = manifest['robot_config']
    controls = {name: settings for group in ('arm', 'gripper')
                for name, settings in data['control'].get(group, {}).items()
                if settings.get('reference_mode') == 'ramped_position'}
    if not controls:
        return []
    limits = acceptance_config(manifest['robot_task'])
    ready = [row for row in samples if row.get('ready') is True]
    check = {'name': 'native_ramped_force_control_observed', 'passed': False,
             'errors': [], 'joints': {}}
    if not ready:
        check['errors'].append('No ready interval')
        return [check]
    start, end = ready[0]['sim_time'], ready[-1]['sim_time']
    finite = lambda value: type(value) in (int, float) and math.isfinite(value)
    native = {}
    for row in native_records:
        stamp = row.get('commanded_before_step_time')
        if finite(stamp):
            key = round(stamp*1e9)
            if key in native:
                check['errors'].append('Duplicate native command timestamp')
            native[key] = row
    joints = {j['name']: j for j in data['joints']}
    previous, times = {}, {name: [] for name in controls}
    check['initialization_samples'] = 0
    fields = ('sim_time', 'requested_target_position_rad', 'limited_reference_rad',
              'measured_position_rad', 'measured_velocity_rad_s',
              'unsaturated_force_nm', 'force_command_nm', 'command_velocity_rad_s')
    for index, row in enumerate(records):
        try:
            if not isinstance(row, dict) or not finite(row.get('sim_time')):
                raise ValueError('Missing or nonfinite controller timestamp')
            name, stamp = row.get('joint_name'), row['sim_time']
            if (row.get('schema_version') != 'joint-position-force/1.0' or
                    row.get('robot_spec_sha256') != manifest['robot_spec_sha256'] or
                    row.get('sample_phase') != 'pre_physics' or name not in controls):
                raise ValueError('Wrong controller schema, robot, phase or joint')
            if row.get('status') == 'waiting_for_native_state':
                # Gazebo has no joint state on its first PreUpdate. Keep this
                # explicit initialization observation; it can never count as
                # ready coverage or excuse losing native state later.
                if stamp >= start or name in previous or row.get('force_command_nm') != 0:
                    raise ValueError('Missing native state outside initial zero-force startup')
                check['initialization_samples'] += 1
                continue
            if row.get('status') != 'active' or any(not finite(row.get(key)) for key in fields):
                raise ValueError('Inactive or nonfinite force-controller observation')
            settings, joint = controls[name], joints[name]
            reference, command = row['limited_reference_rad'], row['force_command_nm']
            if row['command_velocity_rad_s'] != settings['command_velocity']:
                raise ValueError('Controller uses a different reference speed limit')
            for field in ('requested_target_position_rad', 'limited_reference_rad'):
                if not joint['limits']['lower']-1e-9 <= row[field] <= joint['limits']['upper']+1e-9:
                    raise ValueError('Command or reference outside declared joint limits')
            if name in previous:
                old_time, old_reference = previous[name]
                if stamp <= old_time:
                    raise ValueError('Nonmonotonic or duplicate controller timestamp')
                if abs(reference-old_reference) > settings['command_velocity']*(stamp-old_time)+1e-9:
                    raise ValueError('Internal reference exceeds its declared slew limit')
            previous[name] = (stamp, reference)
            clipped = min(settings['cmd_max'], max(settings['cmd_min'], row['unsaturated_force_nm']))
            if abs(clipped-command) > limits['effort_tolerance_nm']:
                raise ValueError('Reported limited effort differs from clipped request')
            if type(row.get('saturated')) is not bool:
                raise ValueError('Missing saturation observation')
            if row['saturated'] != (row['unsaturated_force_nm'] < settings['cmd_min'] or
                                    row['unsaturated_force_nm'] > settings['cmd_max']):
                raise ValueError('Saturation flag disagrees with the reported effort request')
            if not start <= stamp <= end:
                continue
            window_fields = ('max_abs_velocity_window', 'max_abs_force_command_window',
                             'max_abs_unsaturated_force_window', 'max_abs_reference_rate_window')
            if any(not finite(row.get(key)) or row[key] < 0 for key in window_fields):
                raise ValueError('Missing native per-step maxima')
            counters = ('window_steps', 'invalid_state_steps_window', 'saturated_steps_window',
                        'saturated_steps_total', 'rejected_commands', 'command_sequence')
            if any(type(row.get(key)) is not int or row[key] < 0 for key in counters):
                raise ValueError('Missing or invalid native controller counters')
            if (row['window_steps'] < 1 or row['invalid_state_steps_window'] != 0 or
                    row['saturated_steps_window'] > row['window_steps'] or
                    row['saturated_steps_total'] < row['saturated_steps_window'] or
                    row['rejected_commands'] > row['command_sequence']):
                raise ValueError('Invalid native controller window')
            if row['max_abs_velocity_window'] > joint['limits']['velocity']+limits['joint_velocity_tolerance_rad_s']:
                raise ValueError('Native per-step velocity exceeds the declared joint limit')
            if row['max_abs_force_command_window'] > max(abs(settings['cmd_min']), abs(settings['cmd_max']))+limits['effort_tolerance_nm']:
                raise ValueError('Native per-step effort exceeds the controller limit')
            if row['max_abs_reference_rate_window'] > settings['command_velocity']+1e-9:
                raise ValueError('Native per-step reference exceeds its slew limit')
            for maximum, instant in zip(window_fields, ('measured_velocity_rad_s', 'force_command_nm',
                                                       'unsaturated_force_nm', 'command_velocity_rad_s')):
                # The last item is a configured bound, not an instantaneous
                # reference rate, so it is checked above instead.
                if maximum != 'max_abs_reference_rate_window' and row[maximum]+1e-9 < abs(row[instant]):
                    raise ValueError('Native maximum is below its reported instantaneous value')
            times[name].append(stamp)
            observed = native.get(round(stamp*1e9))
            if observed is None:
                raise ValueError('No independent force observation from the same physics step')
            value = next((j for j in observed['joints'] if j['name'] == name), None)
            if (value is None or not value.get('force_command_available') or
                    not finite(value.get('force_command')) or
                    abs(value['force_command']-command) > limits['effort_tolerance_nm']):
                raise ValueError('Native JointForceCmd differs from the force-controller observation')
        except (KeyError, TypeError, ValueError) as error:
            if len(check['errors']) < 20:
                check['errors'].append({'sample': index, 'error': str(error)})
    for name, stamps in times.items():
        gaps = ([stamps[0]-start, end-stamps[-1]]+
                [b-a for a, b in zip(stamps, stamps[1:])]) if stamps else []
        maximum_gap = max(gaps, default=None)
        check['joints'][name] = {'samples': len(stamps), 'maximum_gap_s': maximum_gap}
        if len(stamps) < 20 or maximum_gap > limits['max_telemetry_gap_s']:
            check['errors'].append(name+': incomplete native controller coverage')
    check['passed'] = not check['errors']
    return [check]
