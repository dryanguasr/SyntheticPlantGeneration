"""Bounded CAD pickup search with full base poses and a common carry posture.

The caller supplies candidate robot poses, never revised plant positions.
Infeasibility is retained per target; this is a sampled screen, not a proof
of continuous collision freedom or successful native contact dynamics.
"""
from __future__ import annotations

import math

from .robot_kinematics import (pose_from_rpy, inverse_pose, transform_point,
                               rotate_vector, compose_poses, solve_ik)
from .robot_crop_collision_policy import WRIST_OPTION
from .robot_motion import resolved_world_clearance


PREAPPROACH_OFFSETS = ((-.10, 0., .10), (-.08, 0., .04), (-.08, 0., 0.),
                      (-.06, -.05, .02), (-.06, .05, .02),
                      (0., -.07, .03), (0., .07, .03), (0., 0., .075))


def _position_joints(config, point, seed):
    solved = solve_ik(config.robot, point, tool_frame=config.frame, seed=seed,
                      orientation_mode='position_only',
                      auxiliary_joint_positions=getattr(config, 'aux_positions', {}))
    if not solved.success:
        raise ValueError(f'Position-only IK failed: {solved.reason}')
    values = solved.joint_positions
    return [values[name] for name in config.robot.joint_names] if isinstance(values, dict) else list(values)


def _preapproach_candidates(config, point, seed, carry, expanded):
    """Keep the exact cutter direction for the cut; vary waypoints outside its guard."""
    offsets = PREAPPROACH_OFFSETS if expanded else PREAPPROACH_OFFSETS[:1]
    horizontal = math.hypot(*point[:2])
    if expanded and horizontal > 0:
        radial = [-value/horizontal for value in point[:2]]
        offsets = ((*[.09*value for value in radial], .06),
                   (*[.07*value for value in radial], .02), *offsets)
    failures = []
    for offset in offsets:
        target = [a+b for a, b in zip(point, offset)]
        for directed in ((True, False) if expanded else (True,)):
            try:
                joints = list(config.solve(target, seed=seed)) if directed else _position_joints(config, target, seed)
                yield joints, target, None
            except ValueError as error:
                failures.append(str(error))
    if expanded:
        for fraction in (.20, .35, .55, .75):
            waypoint = [a+(b-a)*fraction for a, b in zip(seed, carry)]
            target = config.fk(waypoint)['position_m']
            if math.dist(point, target) >= .055:
                yield waypoint, target, None
    if failures:
        yield None, None, failures[0]


def _lift_candidates(config, outgoing, carry):
    start = config.fk(outgoing)['position_m']
    end = config.fk(carry)['position_m']
    center = [(a+b)/2 for a,b in zip(start, end)]
    for height in (.08, .15, .22):
        point = [center[0], center[1], max(start[2], end[2]) + height]
        try:
            yield _position_joints(config, point, outgoing), point
        except ValueError:
            continue


def audit_jaw_transition(joints, base, cylinders, fruits, config, *, joint_name,
                         start_m, end_m, held=None, samples=81, clearance_m=.004):
    """Sample a prismatic jaw stroke with the arm and other auxiliaries fixed.

    The 1 mm increment is an engineering sampling resolution, not a guarantee
    of continuous clearance. The requested density is retained when finer;
    an odd count includes the stroke midpoint even for a two-sample request.
    Every posture uses the existing geometric audit and contact policy.
    """
    from .harvest_clearance import audit_joint_segment

    if type(samples) is not int or not 2 <= samples <= 10001:
        raise ValueError('Jaw transition requires between 2 and 10001 requested samples')
    if type(clearance_m) not in (int, float) or not math.isfinite(clearance_m) or clearance_m <= 0:
        raise ValueError('Jaw transition requires positive finite clearance')
    joint = next((row for row in config.robot.joints if row['name'] == joint_name), None)
    if joint is None or joint.get('group') != 'gripper' or joint.get('type') != 'prismatic':
        raise ValueError('Jaw transition requires a declared prismatic gripper joint')
    if joint_name not in config.aux_positions:
        raise ValueError('Jaw transition requires an explicit auxiliary joint state')
    for value in (start_m, end_m):
        if (type(value) not in (int, float) or not math.isfinite(value) or
                not joint['limits']['lower'] <= value <= joint['limits']['upper']):
            raise ValueError('Jaw transition endpoints must be finite and within joint limits')
    count = max(samples, 3, math.ceil(abs(end_m-start_m)/.001) + 1)
    count += (count-1) % 2
    if count > 10001:
        raise ValueError('Jaw transition exceeds the bounded sampling budget')
    result = None
    previous_tcp = None
    for index in range(count):
        fraction = index/(count-1)
        position = (1-fraction)*start_m + fraction*end_m
        observed = {**config.aux_positions, joint_name: position}
        motion = config.for_observed_joints(observed)
        row = audit_joint_segment(joints, joints, base, cylinders, fruits,
            held=held, config=motion, samples=2, clearance_m=clearance_m,
            stop_on_failure=True, report_cap=clearance_m)
        if result is None:
            result = {**row, 'samples': 0, 'requested_samples': 2*count,
                'auxiliary_joint': joint_name, 'auxiliary_start_m': start_m,
                'auxiliary_end_m': end_m, 'auxiliary_samples': 0,
                'auxiliary_requested_samples': count,
                'maximum_auxiliary_sample_step_m': abs(end_m-start_m)/(count-1),
                'method': 'sampled_prismatic_jaw_with_fixed_arm',
                'continuous_clearance_certified': False}
        result['samples'] += row['samples']
        result['auxiliary_samples'] += 1
        result['minimum_joint_margin_rad'] = min(result['minimum_joint_margin_rad'], row['minimum_joint_margin_rad'])
        for key, detail in (
                ('minimum_robot_clearance_m', 'limiting_robot_pair'),
                ('minimum_held_clearance_m', 'limiting_held_obstacle'),
                ('minimum_held_robot_clearance_m', 'limiting_held_robot_link')):
            if row[key] is not None and (result[key] is None or row[key] < result[key]):
                result[key] = row[key]
                if detail in row:
                    result[detail] = row[detail]
                result[detail+'_auxiliary_sample'] = index
        tcp = motion.fk(joints)['position_m']
        if previous_tcp is not None:
            result['maximum_tcp_sample_step_m'] = max(result['maximum_tcp_sample_step_m'], math.dist(previous_tcp, tcp))
        previous_tcp = tcp
        if not row['passed']:
            result.update(passed=False, failed_auxiliary_fraction=fraction,
                          failed_auxiliary_position_m=position)
            for key in ('first_failure_only', 'first_failure_scope', 'unobserved_fields_at_failure'):
                if key in row:
                    result[key] = row[key]
            break
    return result


def plan_resolved_harvest(bundle, config, *, samples=81, clearance_m=.004,
                          pickup_standoff_m=.5, target_ids=None):
    from .harvest_clearance import (_CylinderIndex, planned_crop_obstacles, audit_joint_segment,
                                   EXTRACTION_OFFSETS)
    task = config.task
    fixture = task.get('demo_fixture')
    expanded = bool(fixture and fixture.get(WRIST_OPTION))
    if type(samples) is not int or samples < 2:
        raise ValueError('At least two segment samples are required')
    if not math.isfinite(clearance_m) or clearance_m <= 0:
        raise ValueError('Positive finite clearance is required')
    if not math.isfinite(pickup_standoff_m) or pickup_standoff_m <= .12:
        raise ValueError('Pickup standoff must exceed .12 m')
    height = task.get('planning_base_height_m')
    if type(height) not in (int, float) or not math.isfinite(height) or height <= 0:
        raise ValueError('Resolved pickup requires explicit positive planning_base_height_m')
    carry = list(task.get('carry_joints_rad',
                        [config.robot.data['arm_home_positions'][n] for n in config.robot.joint_names]))
    carry_local = config.fk(carry)['position_m']
    cylinders, fruits = _CylinderIndex(planned_crop_obstacles(bundle)), bundle['fruits']
    occupied = fruits + bundle.get('static_fruit_obstacles', [])
    if not fruits or len({f['id'] for f in fruits}) != len(fruits):
        raise ValueError('Resolved planning requires nonempty unique fruit identities')
    targets = {}
    for fruit in fruits:
        if target_ids is not None and fruit['id'] not in target_ids:
            continue
        cut = fruit['cut_point_world_m']
        axis = [b-a for a, b in zip(fruit['pedicel_start_world_m'], fruit['pedicel_end_world_m'])]
        length = math.sqrt(sum(v*v for v in axis))
        if length < 1e-12:
            raise ValueError('Morphological pedicel direction cannot be zero')
        axis = [v/length for v in axis]
        candidates = task.get('pickup_base_candidates', {}).get(fruit['id'],
            [[cut[0]-pickup_standoff_m, cut[1], height, 0]])
        rejected, accepted = [], None
        for candidate in candidates:
            base = candidate['base_pose'] if isinstance(candidate, dict) else candidate
            seed = candidate['q'] if isinstance(candidate, dict) else carry
            if len(base) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in base):
                raise ValueError('Pickup candidate must contain finite x,y,z,yaw')
            if abs(base[2]-height) > 1e-12:
                raise ValueError('Pickup candidate cannot change the declared ground height')
            pose = pose_from_rpy(base[:3], [0, 0, base[3]])
            inverse = inverse_pose(pose)
            local_cut = transform_point(inverse, cut)
            for sign in ((1, -1) if task.get('cut_axis_bidirectional') else (1,)):
                world_direction = [sign*v for v in axis]
                if isinstance(candidate, dict) and math.dist(world_direction, candidate['cut_axis_world']) > 1e-10:
                    continue
                c = config.for_direction(rotate_vector(inverse['quaternion_xyzw'], world_direction))
                if fixture:
                    c = c.for_target_cut(fruit['id'])
                    jaw = fixture['gripper']
                    c = c.for_observed_joints({**c.aux_positions, jaw['joint']: jaw['closed_position_m']})
                record = {'base_pose': list(base), 'direction_sign': sign}
                try:
                    qcut = list(c.solve(local_cut, seed=seed))
                except ValueError as error:
                    rejected.append({**record, 'reason': str(error)})
                    continue
                _, cut_pose = c.world_shapes(qcut, base)
                held = {**fruit, 'held_offset_in_tool_m':
                        transform_point(inverse_pose(cut_pose), fruit['center_world_m']),
                        'held_pose_in_tool': compose_poses(inverse_pose(cut_pose),
                            pose_from_rpy(fruit['center_world_m'], [0, 0, 0]))}
                opened = c
                if fixture:
                    opened = c.for_observed_joints({**c.aux_positions, jaw['joint']: jaw['open_position_m']})

                def segment(first, second, a, b, *, carrying=False, motion=c):
                    payload = held if carrying else None
                    if expanded and a != b:
                        joint_margin = min(min(x-lo, hi-x, y-lo, hi-y)
                                           for x, y, (lo, hi) in zip(a, b, motion.joint_limits))
                        if joint_margin < fixture['minimum_joint_margin_rad']:
                            return {'from': first, 'to': second, 'held': carrying, 'passed': False,
                                    'reason': 'joint_margin', 'minimum_joint_margin_rad': joint_margin}
                        # Reject an obstructed segment before walking hundreds
                        # of small steps. Every passing segment is still sampled
                        # at the original density and joint increment.
                        for fraction in (1., .5, .25, .75):
                            trial = [x+(y-x)*fraction for x, y in zip(a, b)]
                            state = resolved_world_clearance(trial, base, cylinders, occupied, payload, motion,
                                report_cap=clearance_m, reject_on_first_failure=True)
                            if any(state.get(key, clearance_m) is not None and
                                   state.get(key, clearance_m) < clearance_m for key in
                                   ('robot_clearance_m', 'held_clearance_m', 'held_robot_clearance_m')):
                                return {'from': first, 'to': second, 'held': carrying, 'passed': False,
                                        'reason': 'early_segment_clearance_failure', 'fraction': fraction,
                                        'clearance': state, 'clearance_threshold_m': clearance_m}
                    row = audit_joint_segment(a, b, base, cylinders, occupied,
                        held=payload, config=motion, samples=2 if a == b else samples,
                        clearance_m=clearance_m, stop_on_failure=True,
                        report_cap=clearance_m if fixture else .5)
                    row.update({'from': first, 'to': second, 'held': carrying})
                    if fixture and row['minimum_joint_margin_rad'] < fixture['minimum_joint_margin_rad']:
                        row.update(passed=False, reason='joint_margin')
                    return row

                if fixture:
                    closure = audit_jaw_transition(qcut, base, cylinders, occupied, c,
                        joint_name=jaw['joint'], start_m=jaw['open_position_m'],
                        end_m=jaw['closed_position_m'], samples=samples, clearance_m=clearance_m)
                    closure.update({'from': 'cut_open', 'to': 'cut_closed', 'held': False})
                    if not closure['passed']:
                        rejected.append({**record, 'reason': 'jaw_closure_collision_or_margin', 'segments': [closure]})
                        continue
                approach = None
                for qpre, local_pre, error in _preapproach_candidates(c, local_cut, qcut, carry, expanded):
                    if error:
                        rejected.append({**record, 'reason': error})
                        continue
                    ingress = [segment('carry', 'preapproach', carry, qpre, motion=opened)]
                    if ingress[0]['passed']:
                        ingress.append(segment('preapproach', 'cut', qpre, qcut, motion=opened))
                    if all(row['passed'] for row in ingress):
                        approach = [*ingress, closure] if fixture else ingress
                        break
                    rejected.append({**record, 'reason': 'approach_collision_or_margin', 'segments': ingress})
                if approach is None:
                    continue
                offsets = EXTRACTION_OFFSETS
                if expanded:
                    offsets = (tuple(a-b for a, b in zip(local_pre, local_cut)), *offsets)
                for offset in offsets:
                    local_out = [v+d for v, d in zip(local_cut, offset)]
                    try:
                        qout = qpre if expanded and offset == offsets[0] else list(c.solve(local_out, seed=qcut))
                    except ValueError as error:
                        if not expanded:
                            rejected.append({**record, 'offset_m': list(offset), 'reason': str(error)})
                            continue
                        try:
                            qout = _position_joints(c, local_out, qcut)
                        except ValueError as fallback_error:
                            rejected.append({**record, 'offset_m': list(offset), 'reason': str(fallback_error)})
                            continue
                    extraction = []
                    extraction.append(segment('cut', 'extraction_0', qcut, qout, carrying=True))
                    qlift = lift_point = None
                    if extraction[0]['passed']:
                        transfer = segment('extraction_0', 'carry', qout, carry, carrying=True)
                        extraction.append(transfer)
                        if expanded and not transfer['passed']:
                            for candidate_lift, point in _lift_candidates(c, qout, carry):
                                beginning = segment('extraction_0', 'extraction_1', qout, candidate_lift, carrying=True)
                                if not beginning['passed']:
                                    continue
                                end = segment('extraction_1', 'carry', candidate_lift, carry, carrying=True)
                                if end['passed']:
                                    qlift, lift_point = candidate_lift, point
                                    extraction = [extraction[0], beginning, end]
                                    break
                    if not all(row['passed'] for row in extraction):
                        rejected.append({**record, 'offset_m': list(offset),
                            'reason': 'extraction_collision_or_margin', 'segments': extraction})
                        continue
                    deposit = None
                    deposit_lift = None
                    deposit_segments = []
                    if fixture:
                        for release in onboard_release_joints(c, held, carry, fixture['bin']):
                            transfer = segment('carry', 'above_basket', carry, release, carrying=True)
                            transfer_segments = [transfer]
                            lift_used = None
                            if expanded and not transfer['passed']:
                                for lift, _ in _lift_candidates(c, carry, release):
                                    start = segment('carry', 'deposit_lift', carry, lift, carrying=True)
                                    if not start['passed']:
                                        continue
                                    end = segment('deposit_lift', 'above_basket', lift, release, carrying=True)
                                    if end['passed']:
                                        lift_used, transfer_segments = lift, [start, end]
                                        break
                            if not all(part['passed'] for part in transfer_segments):
                                continue
                            clear_open = audit_jaw_transition(release, base, cylinders, occupied, c,
                                joint_name=jaw['joint'], start_m=jaw['closed_position_m'],
                                end_m=jaw['open_position_m'], held=held, samples=samples,
                                clearance_m=clearance_m)
                            clear_open.update({'from': 'above_basket_closed', 'to': 'above_basket_open', 'held': True})
                            if not clear_open['passed']:
                                rejected.append({**record, 'reason': 'jaw_opening_collision_or_margin',
                                    'deposit_joints': list(release), 'segments': [clear_open]})
                                continue
                            # The attached world fruit has already been removed from its crop pose.
                            # The separate return audit below uses the released tray volume.
                            deposit, deposit_lift = release, lift_used
                            deposit_segments = [*transfer_segments, clear_open]
                            break
                        if deposit is None:
                            rejected.append({**record, 'reason': 'no_safe_onboard_deposit_pose'})
                            # Each withdrawal returns to the same carry pose.
                            # This transfer depends only on the current cut
                            # attachment, so another withdrawal cannot fix it.
                            break
                    segments = approach+extraction+deposit_segments
                    joints = {'carry': carry, 'preapproach': qpre, 'cut': qcut, 'extraction_0': qout}
                    waypoints = {'carry': carry_local, 'preapproach': local_pre, 'cut': local_cut, 'extraction_0': local_out}
                    sequence = ['carry', 'preapproach', 'cut', 'extraction_0']
                    if qlift is not None:
                        joints['extraction_1'] = qlift
                        waypoints['extraction_1'] = lift_point
                        sequence.append('extraction_1')
                    accepted = {'pickup_base_pose': list(base), 'cut_axis_world': world_direction,
                        'joint_waypoints': joints,
                        'tcp_waypoints_world_m': {name: transform_point(pose, point) for name, point in waypoints.items()},
                        'sequence': [*sequence, 'carry'],
                        'extraction_offset_m': list(offset),
                        **({'deposit_joints': deposit} if fixture else {}),
                        **({'deposit_sequence': [deposit_lift, deposit]} if deposit_lift is not None else {}),
                        'audit': {'passed': True, 'segments': segments, 'rejected_candidates': rejected,
                            'minimum_robot_clearance_m': min(r['minimum_robot_clearance_m'] for r in segments),
                            'minimum_held_clearance_m': min(r['minimum_held_clearance_m'] for r in extraction),
                            'minimum_held_robot_clearance_m': min(r['minimum_held_robot_clearance_m'] for r in extraction)}}
                    break
                if accepted:
                    break
            if accepted:
                break
        targets[fruit['id']] = accepted or {'audit': {'passed': False, 'rejected_candidates': rejected},
                                           'status': 'FAIL', 'cause': 'bounded_search_found_no_safe_path'}
    return {'targets': targets, 'audit': {'schema_version': 'resolved-harvest-planning/1.0',
        'passed': all(t['audit']['passed'] for t in targets.values()), 'target_count': len(targets),
        'robot_spec_sha256': config.robot.sha256, 'clearance_threshold_m': clearance_m,
        'carry_joints_rad': carry, 'carry_tcp_base_m': carry_local,
        'planning_base_height_m': height, 'gazebo_validation': 'NO EJECUTADO',
        'method': 'full_SE3_base_bounded_IK_shared_primitives_sampled_joint_paths',
        'limitations': ['No continuous collision certificate', 'Passive planning state must be checked against native motion',
                        'Base travel and physical fruit contact require native audit']}}


def onboard_release_joints(config, fruit, carry, basket):
    """Solve for the latched fruit above the aperture, with position-only IK."""
    lo, hi = basket['inner_min_m'], basket['inner_max_m']
    x, y = [(a+b)/2 for a,b in zip(lo[:2], hi[:2])]
    horizontal_centers = [(x, y)]
    heights = (.06, .12, .20, .28)
    if getattr(config, 'task', {}).get('demo_fixture', {}).get(WRIST_OPTION):
        heights = (*heights, .34, .42, .50)
        radius = fruit['radius_m']
        horizontal_centers.extend((x+dx, y+dy) for dx, dy in ((-.04, 0.), (.04, 0.), (0., -.04), (0., .04))
                                  if lo[0]+radius <= x+dx <= hi[0]-radius and
                                  lo[1]+radius <= y+dy <= hi[1]-radius)
    offset = fruit['held_offset_in_tool_m']
    poses = (carry, [0., -.7, .9, .2, 0.], [0., .7, -.9, -.2, 0.])
    targets = ([cx, cy, hi[2]+fruit['radius_m']+height]
               for cx, cy in horizontal_centers for height in heights)
    for center in targets:
        for seed in poses:
            q = list(seed)
            for _ in range(8):
                motion = config.fk(q)
                point = rotate_vector(motion['quaternion_xyzw'], offset)
                if math.dist([a+b for a,b in zip(motion['position_m'], point)], center) <= .002:
                    yield q
                    break
                try:
                    q = _position_joints(config, [a-b for a,b in zip(center, point)], q)
                except ValueError:
                    break


def audited_drive_route(start, route, config, cylinders, fruits, clearance_m):
    """Check stowed robot at in-place turns and along each approach leg."""
    from .harvest_clearance import _CylinderIndex
    if not isinstance(cylinders, _CylinderIndex):
        cylinders = _CylinderIndex(cylinders)
    task = config.task
    carry = list(task.get('carry_joints_rad',
                             [config.robot.data['arm_home_positions'][n] for n in config.robot.joint_names]))
    height = task['planning_base_height_m']
    samples = 0
    for goal in route:
        x, y, yaw = start
        distance = math.dist(start[:2], goal[:2])
        heading = math.atan2(goal[1]-y, goal[0]-x) if distance > 1e-9 else yaw
        before_turn = math.remainder(heading-yaw, math.tau)
        after_turn = math.remainder(goal[2]-heading, math.tau)
        pre, travel, post = (max(1, math.ceil(abs(before_turn)/.06)),
                             max(1, math.ceil(distance/.025)),
                             max(1, math.ceil(abs(after_turn)/.06)))
        poses = [(x, y, yaw+before_turn*i/pre) for i in range(pre+1)]
        poses.extend((x+(goal[0]-x)*i/travel, y+(goal[1]-y)*i/travel, heading) for i in range(1, travel+1))
        poses.extend((goal[0], goal[1], heading+after_turn*i/post) for i in range(1, post+1))
        for px, py, yaw in poses:
            base = [px, py, height, yaw]
            row = resolved_world_clearance(carry, base, cylinders, fruits, None, config,
                                           report_cap=clearance_m, reject_on_first_failure=True)
            samples += 1
            if row['robot_clearance_m'] < clearance_m:
                return {'passed': False, 'pose': base, 'samples': samples, 'clearance': row}
        start = goal
    return {'passed': True, 'samples': samples, 'planned_base_geometry_only': True,
            'sample_intervals_m_rad': [.025, .06], 'clearance_m': clearance_m}
