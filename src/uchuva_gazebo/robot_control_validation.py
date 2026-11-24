"""Audit ramped references against independently observed native force commands."""
from __future__ import annotations

import math
import bisect

from .robot_validation import acceptance_config


def evaluate_base_drive_control(manifest, commands, pose_samples):
    """Independently check reference limits and rates against native pose logs.

    This is not a physical tracking/traction test. It deliberately does not
    certify tire friction or copy a controller's claimed measured yaw rate.
    """
    drive = manifest['robot_config']['control']['drive']
    config = drive.get('base_feedback', {})
    if not config.get('enabled'):
        return []
    errors = []
    observed = {}
    for sample in pose_samples:
        pose = sample.get('robot_pose', sample.get('pose'))
        if pose is None:
            continue
        stamp = sample.get('sim_time')
        if (type(stamp) not in (int, float) or not math.isfinite(stamp) or
                not isinstance(pose, (list, tuple)) or len(pose) != 7 or
                any(type(v) not in (int, float) or not math.isfinite(v) for v in pose) or
                abs(sum(v*v for v in pose[3:])-1) > 1e-6):
            errors.append('Invalid native base pose'); continue
        key = round(stamp, 9)
        if key in observed and observed[key] != list(pose):
            errors.append('Conflicting native poses at one timestamp')
        observed[key] = list(pose)
    times = sorted(observed); unwrapped = []
    for stamp in times:
        x, y, z, w = observed[stamp][3:]
        angle = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
        if unwrapped:
            previous = unwrapped[-1]
            angle = previous+math.atan2(math.sin(angle-previous), math.cos(angle-previous))
        unwrapped.append(angle)
    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Nonfinite drive-reference value')
        return value
    def close(actual, expected, label):
        if abs(number(actual)-number(expected)) > 1e-9:
            raise ValueError(label+' differs from independently reconstructed value')
    def clamp(value, bound):return max(-bound, min(bound, value))
    records = [row for row in commands if 'drive_reference' in row]
    expected_records = [row for row in commands if row.get('kind') == 'base_velocity' or 'wheel_velocity_references_rad_s' in row]
    if len(records) != len(expected_records):
        errors.append('Missing feedback trace for a wheel command')
    previous_time, previous_v, previous_w = 0., 0., 0.
    active = 0
    for index, command in enumerate(records):
        row = command['drive_reference']
        try:
            if row.get('schema_version') != 'native-base-drive-reference/1.0' or row.get('feedback_enabled') is not True:
                raise ValueError('Wrong drive-reference contract')
            if row.get('observation_source') != 'native_model_pose_ideal' or 'rejected_request_error' in row:
                raise ValueError('Invalid or rejected feedback observation')
            stamp = number(row['sim_time']); dt = stamp-previous_time
            if dt < 0:raise ValueError('Drive reference clock regressed')
            close(command['sim_time'], stamp, 'Command time')
            target_v = clamp(number(row['requested_linear_m_s']), drive['max_linear_velocity'])
            target_w = clamp(number(row['requested_angular_rad_s']), drive['max_angular_velocity'])
            close(row['target_linear_m_s'], target_v, 'Linear target')
            close(row['target_angular_rad_s'], target_w, 'Angular target')
            correction = 0.
            if target_v == 0 and target_w == 0:
                if row['feedback_status'] != 'zero_twist_braking' or row['zero_twist_feedback_bypass'] is not True:
                    raise ValueError('Zero-twist stop must bypass feedback')
            else:
                active += 1
                if row['feedback_status'] != 'active' or row['zero_twist_feedback_bypass']:
                    raise ValueError('Moving reference lacks active feedback')
                when = number(row['observation_time']); age = stamp-when
                if age < -1e-9 or age > config['max_observation_age_s']+1e-12:
                    raise ValueError('Native yaw observation is future or stale')
                key = round(when, 9)
                if key not in observed:raise ValueError('No native pose at the claimed observation time')
                end = bisect.bisect_left(times, key)
                beginning = when-config['window_s']
                if not times or times[0] > beginning+1e-9:raise ValueError('Incomplete native yaw observation window')
                left = max(0, bisect.bisect_right(times, beginning)-1)
                right = min(left+1, len(times)-1)
                if left == right:raise ValueError('Yaw-rate window has no bracketing native poses')
                fraction = clamp((beginning-times[left])/(times[right]-times[left]), 1.)
                fraction = max(0., fraction)
                start_yaw = unwrapped[left]+fraction*(unwrapped[right]-unwrapped[left])
                rate = (unwrapped[end]-start_yaw)/config['window_s']
                close(row['observed_yaw_rate_rad_s'], rate, 'Observed yaw rate')
                close(row['observation_age_s'], max(0., age), 'Observation age')
                close(row['observation_window_start'], beginning, 'Observation window')
                correction = config['p_gain']*(target_w-rate)
            close(row['feedback_correction_rad_s'], correction, 'Feedback correction')
            corrected = target_w+correction; desired = clamp(corrected, drive['max_angular_velocity'])
            if row['angular_feedback_clipped'] is not (desired != corrected):
                raise ValueError('Feedback clipping flag differs')
            close(row['compensated_angular_before_limit_rad_s'], corrected, 'Raw compensated reference')
            close(row['compensated_angular_rad_s'], desired, 'Bounded compensated reference')
            close(row['ramp_dt_s'], dt, 'Ramp interval')
            v = previous_v+clamp(target_v-previous_v, drive['max_linear_acceleration']*dt)
            w = previous_w+clamp(desired-previous_w, drive['max_angular_acceleration']*dt)
            close(row['linear_m_s'], v, 'Linear ramp'); close(row['angular_rad_s'], w, 'Angular ramp')
            close(command['linear_m_s'], v, 'Published linear reference')
            close(command['angular_rad_s'], w, 'Published angular reference')
            expected_names = set(drive['left_joints']) | set(drive['right_joints'])
            if set(row['wheel_velocity_references_rad_s']) != expected_names or set(command['wheel_velocity_references_rad_s']) != expected_names:
                raise ValueError('Wheel command coverage differs')
            for side, sign in (('left_joints', -1), ('right_joints', 1)):
                omega = (v+sign*w*drive['wheel_separation_m']/2)/drive['wheel_radius_m']
                for name in drive[side]:
                    expected = clamp(omega*drive['joint_signs'][name], drive['joints'][name]['command_velocity'])
                    close(row['wheel_velocity_references_rad_s'][name], expected, 'Wheel trace '+name)
                    close(command['wheel_velocity_references_rad_s'][name], expected, 'Published wheel '+name)
            previous_time, previous_v, previous_w = stamp, v, w
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as error:
            errors.append({'sample': index, 'error': str(error)})
    return [{'name': 'native_base_feedback_reference_verified', 'passed': bool(records) and not errors,
             'samples': len(records), 'active_feedback_samples': active, 'errors': errors,
             'scope': 'Reference arithmetic, limits and ideal-native pose rates only; physical effort/tracking are separate checks.'}]


def evaluate_position_force_control(manifest, records, native_records, samples, *,
                                    control_groups=('arm', 'gripper')):
    """Audit all ramped motors by default; isolated benches declare their scope.

    A subset is written into the result and cannot establish full-robot
    admission. The harvest auditor always uses the default complete scope.
    """
    if (not isinstance(control_groups, (tuple, list)) or not control_groups or
            len(set(control_groups)) != len(control_groups) or
            not set(control_groups) <= {'arm', 'gripper'}):
        raise ValueError('Explicit nonempty arm/gripper controller scope required')
    data = manifest['robot_config']
    controls = {name: settings for group in control_groups
                for name, settings in data['control'].get(group, {}).items()
                if settings.get('reference_mode') == 'ramped_position'}
    if not controls:
        if set(control_groups) != {'arm', 'gripper'}:
            raise ValueError('Isolated scope contains no ramped controllers')
        return []
    limits = acceptance_config(manifest['robot_task'])
    ready = [row for row in samples if row.get('ready') is True]
    check = {'name': 'native_ramped_force_control_observed', 'passed': False,
             'errors': [], 'joints': {}, 'required_control_groups': list(control_groups),
             'full_robot_controller_scope': set(control_groups) == {'arm', 'gripper'}}
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
            if not isinstance(row, dict) or not finite(row.get('sim_time')) or row['sim_time'] < 0:
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
                if (stamp >= start or name in previous or
                        not finite(row.get('force_command_nm')) or row['force_command_nm'] != 0):
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
