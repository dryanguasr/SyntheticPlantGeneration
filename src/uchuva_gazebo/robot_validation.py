"""Independent acceptance of resolved-robot telemetry, with explicit tolerances.

Joint force commands and simulated transmitted wrench are different evidence.
Neither is a measured real motor torque. Missing evidence never becomes zero.
"""
from __future__ import annotations

import math

from .robot_kinematics import rotate_vector
from .robot_spec import resolve_robot_profile


ACCEPTANCE_FIELDS = ('max_telemetry_gap_s', 'joint_position_tolerance_rad',
                     'joint_velocity_tolerance_rad_s', 'effort_tolerance_nm',
                     'orientation_state_max_age_s')


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def acceptance_config(task):
    values = task.get('acceptance', {})
    for name in ACCEPTANCE_FIELDS:
        if not _finite(values.get(name)) or values[name] < 0:
            raise ValueError(f'Native robot acceptance requires a preregistered finite {name}')
    if values['max_telemetry_gap_s'] <= 0 or values['orientation_state_max_age_s'] <= 0:
        raise ValueError('Robot telemetry coverage intervals must be positive')
    return {name: values[name] for name in ACCEPTANCE_FIELDS}


def evaluate_native_mechanisms(manifest, records, pose_records, samples):
    """Join native observations; a correct FK tree is not a closure observation."""
    from .robot_mechanism_validation import audit_mechanism_sample, audit_passive_gear_commands
    robot = resolve_robot_profile(manifest['robot_config'])
    limits = acceptance_config(manifest['robot_task'])
    ready = [s for s in samples if s.get('ready') is True]
    if not ready:
        return [{'name': 'native_mechanisms_observed', 'passed': False, 'errors': ['No ready interval']}]
    start, finish = ready[0]['sim_time'], ready[-1]['sim_time']
    errors, maxima, observed_times = [], {}, []
    poses, valid_records = [], []
    for name, incoming, selected in (('link pose', pose_records, poses), ('joint state', records, valid_records)):
        for row in incoming:
            stamp = row.get('sim_time') if isinstance(row, dict) else None
            if not _finite(stamp):
                if len(errors) < 20:
                    errors.append('Invalid native '+name+' timestamp')
                continue
            if name == 'joint state' or stamp >= start:
                selected.append(row)
    records = valid_records
    joint_steps, previous = {}, None
    for row in records:
        before, after = row.get('commanded_before_step_time'), row.get('measured_after_step_time')
        if (not _finite(before) or not _finite(after) or after != row['sim_time'] or
                not 0 <= after-before <= limits['max_telemetry_gap_s']):
            if len(errors) < 20:
                errors.append('Invalid native joint physics-step timestamps')
            continue
        key = round(before*1_000_000_000)
        if key in joint_steps:
            if len(errors) < 20:
                errors.append('Duplicate native joint physics-step timestamp')
            continue
        joint_steps[key] = row
    expected = {link['name'] for link in robot.links}
    for row in poses:
        try:
            stamp = row['sim_time']
            if not _finite(stamp) or (previous is not None and stamp <= previous):
                raise ValueError('Non-increasing native mechanism timestamps')
            if (row.get('schema_version') != 'native-robot-link-poses/1.0' or
                    row.get('robot_spec_sha256') != robot.sha256 or
                    row.get('frame_id') != robot.data['model_name'] or set(row['links']) != expected):
                raise ValueError('Native mechanism pose identity/frame/links mismatch')
            # PosePublisher stamps UpdateInfo.simTime. The native observer's
            # post-step value is labelled simTime+dt, with simTime preserved
            # as commanded_before_step_time. Join the exact same iteration,
            # rather than accepting a nearby sample from a previous step.
            observed = joint_steps.get(round(stamp*1_000_000_000))
            if observed is None:
                raise ValueError('No native mechanism joint state from the exact physics step')
            positions = {j['name']: j['position'] for j in observed['joints'] if j.get('position_available')}
            report = audit_mechanism_sample(robot, positions, row['links'])
            for closure in report['closures']:
                metric = maxima.setdefault(closure['name'], {'maximum_position_error_m': 0, 'maximum_orientation_error_rad': 0})
                metric['maximum_position_error_m'] = max(metric['maximum_position_error_m'], closure['position_error_m'])
                metric['maximum_orientation_error_rad'] = max(metric['maximum_orientation_error_rad'], closure['orientation_error_rad'])
            for gear in report['gears']:
                metric = maxima.setdefault(gear['name'], {'maximum_coordinate_error_rad': 0})
                metric['maximum_coordinate_error_rad'] = max(metric['maximum_coordinate_error_rad'], abs(gear['coordinate_error_rad']))
            if not report['passed']:
                raise ValueError('; '.join(report['failures']))
            observed_times.append(stamp)
            previous = stamp
        except (KeyError, TypeError, ValueError) as error:
            if len(errors) < 20:
                errors.append(str(error))
    for row in records:
        if row.get('sim_time', -math.inf) < start:
            continue
        try:
            report = audit_passive_gear_commands(robot, row)
            if not report['passed']:
                raise ValueError('; '.join(report['failures']))
        except (KeyError, TypeError, ValueError) as error:
            if len(errors) < 20:
                errors.append(str(error))
    gap = max((b-a for a,b in zip(observed_times, observed_times[1:])), default=math.inf)
    coverage = (len(observed_times) >= 20 and observed_times[0]-start <= limits['max_telemetry_gap_s']
                and finish-observed_times[-1] <= limits['max_telemetry_gap_s'] and gap <= limits['max_telemetry_gap_s'])
    return [{'name': 'native_mechanisms_observed', 'passed': not errors and coverage,
             'errors': errors, 'sample_count': len(observed_times), 'complete_coverage': coverage,
             'maximum_observation_gap_s': gap if math.isfinite(gap) else None, 'metrics': maxima,
             'timestamp_join': 'PosePublisher stamp equals observer commanded_before_step_time; both contain post-Physics values of the same iteration',
             'source': 'native link poses, joint coordinates and actuator commands; no FK substitution'}]


def evaluate_robot_telemetry(manifest, records, samples, events):
    """Recompute limits, availability, coverage and cutting-axis alignment."""
    robot = resolve_robot_profile(manifest['robot_config'])
    task = manifest['robot_task']
    limits = acceptance_config(task)
    data = robot.to_dict()
    joints = {j['name']: j for j in data['joints'] if j['type'] != 'fixed'}
    errors, checks = [], []
    metrics = {name: {'max_abs_force_command': 0, 'max_abs_velocity': 0,
                      'saturated_steps': 0, 'wrench_samples': 0,
                      'observed_window_count': 0} for name in joints}
    ready = [s for s in samples if s.get('ready') is True]
    if not ready:
        raise ValueError('No ready harvest interval for robot observation')
    start, finish = ready[0]['sim_time'], ready[-1]['sim_time']
    # Initial components can be unavailable before Physics has stepped. The
    # complete mission interval still has to be covered, including its ends.
    records = [r for r in records if not _finite(r.get('sim_time')) or r['sim_time'] >= start]
    previous_time, previous_iteration = None, None
    maximum_gap = 0
    observed_times = []
    for index, row in enumerate(records):
        try:
            stamp = row['sim_time']
            if not _finite(stamp):
                raise ValueError('invalid simulation timestamp')
            if row.get('schema_version') != 'robot-telemetry/1.0' or row.get('robot_spec_sha256') != robot.sha256:
                raise ValueError('wrong robot identity or telemetry schema')
            if row.get('reset_count') != 0 or type(row.get('sample_count')) is not int or row['sample_count'] < 1:
                raise ValueError('reset or unobserved physics window')
            iteration = row.get('iteration')
            if type(iteration) is not int or (previous_iteration is not None and iteration <= previous_iteration):
                raise ValueError('non-increasing iteration')
            if previous_time is not None:
                if stamp <= previous_time:
                    raise ValueError('non-increasing simulation time')
                maximum_gap = max(maximum_gap, stamp-previous_time)
            before, after = row.get('commanded_before_step_time'), row.get('measured_after_step_time')
            if not _finite(before) or not _finite(after) or after != stamp or not 0 <= after-before <= limits['max_telemetry_gap_s']:
                raise ValueError('command and observation do not cover the same physics step')
            if row.get('wrench_semantics') != 'simulated_transmitted_joint_frame_not_motor_torque':
                raise ValueError('ambiguous wrench semantics')
            observed = {j['name']: j for j in row['joints']}
            if set(observed) != set(joints) or len(observed) != len(row['joints']):
                raise ValueError('missing, duplicate or unexpected observed joints')
            observed_times.append(stamp)
            # Describe available raw windows before checking acceptance. A
            # rejected speed peak must remain visible in the reported maximum,
            # including joints after the first one that fails in this sample.
            for name, actual in observed.items():
                metric = metrics[name]
                metric['observed_window_count'] += 1
                for source, target in (('max_abs_force_command_window', 'max_abs_force_command'),
                                       ('max_abs_velocity_window', 'max_abs_velocity')):
                    value = actual.get(source)
                    if _finite(value) and value >= 0:
                        metric[target] = max(metric[target], value)
                saturated = actual.get('saturated_steps')
                if type(saturated) is int and 0 <= saturated <= row['sample_count']:
                    metric['saturated_steps'] += saturated
                wrench = actual.get('transmitted_wrench')
                if (actual.get('wrench_available') is True and isinstance(wrench, dict)
                        and all(isinstance(wrench.get(k), list) and len(wrench[k]) == 3
                                and all(_finite(v) for v in wrench[k]) for k in ('force', 'torque'))):
                    metric['wrench_samples'] += 1
            for name, joint in joints.items():
                actual, bound = observed[name], joint['limits']
                for key in ('position', 'velocity'):
                    if actual.get(key+'_available') is not True or not _finite(actual.get(key)):
                        raise ValueError(f'{name}: unavailable {key}')
                if not bound['lower']-limits['joint_position_tolerance_rad'] <= actual['position'] <= bound['upper']+limits['joint_position_tolerance_rad']:
                    raise ValueError(f'{name}: position limit exceeded')
                velocity = actual.get('max_abs_velocity_window')
                if not _finite(velocity) or velocity < abs(actual['velocity'])-1e-9 or velocity > bound['velocity']+limits['joint_velocity_tolerance_rad_s']:
                    raise ValueError(f'{name}: unavailable or excessive observed velocity')
                effort = actual.get('max_abs_force_command_window')
                if joint['group'] != 'passive':
                    if actual.get('force_command_available') is not True or not _finite(actual.get('force_command')):
                        raise ValueError(f'{name}: commanded effort unavailable')
                    if not _finite(effort) or effort < abs(actual['force_command'])-1e-9 or effort > bound['effort']+limits['effort_tolerance_nm']:
                        raise ValueError(f'{name}: effort window missing or joint effort limit exceeded')
                    gains = data['control']['arm'].get(name) or data['control']['drive'].get('joints', {}).get(name) or data['control'].get('gripper', {}).get(name)
                    if gains is None or not gains['cmd_min']-limits['effort_tolerance_nm'] <= actual['force_command'] <= gains['cmd_max']+limits['effort_tolerance_nm']:
                        raise ValueError(f'{name}: command violates effective controller bounds')
                    if effort > max(abs(gains['cmd_min']), abs(gains['cmd_max']))+limits['effort_tolerance_nm']:
                        raise ValueError(f'{name}: effort window violates controller bounds')
                if actual.get('wrench_available') is not True:
                    raise ValueError(f'{name}: transmitted wrench unavailable')
                wrench = actual.get('transmitted_wrench')
                if not isinstance(wrench, dict) or any(not isinstance(wrench.get(k), list) or len(wrench[k]) != 3 or not all(_finite(v) for v in wrench[k]) for k in ('force', 'torque')):
                    raise ValueError(f'{name}: malformed transmitted wrench')
                saturated = actual.get('saturated_steps')
                if type(saturated) is not int or not 0 <= saturated <= row['sample_count']:
                    raise ValueError(f'{name}: invalid saturation window')
            previous_time, previous_iteration = stamp, iteration
        except (KeyError, TypeError, ValueError) as error:
            if len(errors) < 20:
                errors.append({'sample': index, 'error': str(error)})
    checks.append({'name': 'resolved_robot_observed_limits_and_wrench', 'passed': bool(records) and not errors,
                   'errors': errors, 'robot_spec_sha256': robot.sha256, 'joint_metrics': metrics,
                   'note': 'Metrics describe available raw windows, including rejected samples; they do not imply acceptance. Force command is controller output; transmitted wrench is simulated joint-frame reaction, not motor torque.'})
    coverage = bool(records) and not errors and records[0]['sim_time']-start <= limits['max_telemetry_gap_s'] and finish-records[-1]['sim_time'] <= limits['max_telemetry_gap_s'] and maximum_gap <= limits['max_telemetry_gap_s']
    checks.append({'name': 'resolved_robot_telemetry_covers_mission', 'passed': coverage,
                   'maximum_gap_s': max((b-a for a, b in zip(observed_times, observed_times[1:])), default=None),
                   'maximum_validated_sample_gap_s': maximum_gap,
                   'sample_count': len(records), 'identity_valid_observed_samples': len(observed_times),
                   'criteria': limits,
                   'note': 'Raw transport coverage and acceptance are distinct: rejected physical samples still fail complete validated coverage.'})
    targets = {t['id']: t for t in manifest['mission']['targets']}
    orientation_errors, observed_angles = [], []
    cuts = [event for event in events if event.get('phase') == 'ack' and event.get('action') == 'cut' and event.get('accepted') is True]
    for event in cuts:
        prior = [s for s in ready if s['sim_time'] <= event['sim_time']]
        try:
            if not prior or event['sim_time']-prior[-1]['sim_time'] > limits['orientation_state_max_age_s']:
                raise ValueError('cut has no fresh preceding observed pose')
            sample = prior[-1]
            if sample.get('schema_version') != 2 or sample.get('orientation_guard_enabled') is not True:
                raise ValueError('resolved interaction frames/orientation guard were not active')
            fruit = next(f for f in sample['fruits'] if f['id'] == event['id'])
            desired = rotate_vector(fruit['pose'][3:], targets[event['id']]['cut_axis_world'])
            actual = rotate_vector(sample['cut_pose'][3:], task['tool_axis'])
            cosine = max(-1.0, min(1.0, sum(a*b for a, b in zip(actual, desired))))
            angle = math.acos(abs(cosine) if task['cut_axis_bidirectional'] else cosine)
            observed_angles.append(angle)
            if angle > task['orientation_tolerance_rad']:
                raise ValueError('observed cut axis exceeds preregistered tolerance')
        except (KeyError, TypeError, ValueError, StopIteration) as error:
            orientation_errors.append({'id': event['id'], 'error': str(error)})
    checks.append({'name': 'resolved_cut_orientation_observed', 'passed': not orientation_errors,
                   'accepted_cuts': len(cuts), 'maximum_axis_error_rad': max(observed_angles, default=None),
                   'errors': orientation_errors, 'scope': 'No cutting claim when accepted_cuts is zero.'})
    return checks
