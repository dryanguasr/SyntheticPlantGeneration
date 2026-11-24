"""Bounded CAD pickup search with full base poses and a common carry posture.

The caller supplies candidate robot poses, never revised plant positions.
Infeasibility is retained per target; this is a sampled screen, not a proof
of continuous collision freedom or successful native contact dynamics.
"""
from __future__ import annotations

import math

from .robot_kinematics import (pose_from_rpy, inverse_pose, transform_point,
                               rotate_vector, compose_poses, solve_ik)


def plan_resolved_harvest(bundle, config, *, samples=81, clearance_m=.004,
                          pickup_standoff_m=.5, target_ids=None):
    from .harvest_clearance import (planned_crop_obstacles, audit_joint_segment,
                                   EXTRACTION_OFFSETS)
    task = config.task
    fixture = task.get('demo_fixture')
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
    cylinders, fruits = planned_crop_obstacles(bundle), bundle['fruits']
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
            local_pre = [local_cut[0]-.10, local_cut[1], local_cut[2]+.10]
            for sign in ((1, -1) if task.get('cut_axis_bidirectional') else (1,)):
                world_direction = [sign*v for v in axis]
                if isinstance(candidate, dict) and math.dist(world_direction, candidate['cut_axis_world']) > 1e-10:
                    continue
                c = config.for_direction(rotate_vector(inverse['quaternion_xyzw'], world_direction))
                if fixture:
                    c = c.for_target_cut(fruit['id'])
                record = {'base_pose': list(base), 'direction_sign': sign}
                try:
                    qcut = list(c.solve(local_cut, seed=seed))
                    qpre = list(c.solve(local_pre, seed=qcut))
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
                    jaw = fixture['gripper']
                    opened = c.for_observed_joints({**c.aux_positions, jaw['joint']: jaw['open_position_m']})

                def segment(first, second, a, b, *, carrying=False, motion=c):
                    row = audit_joint_segment(a, b, base, cylinders, occupied,
                        held=held if carrying else None, config=motion, samples=samples,
                        clearance_m=clearance_m, stop_on_failure=True,
                        report_cap=clearance_m if fixture else .5)
                    row.update({'from': first, 'to': second, 'held': carrying})
                    if fixture and row['minimum_joint_margin_rad'] < fixture['minimum_joint_margin_rad']:
                        row.update(passed=False, reason='joint_margin')
                    return row

                approach = []
                for first, second, a, b in (('carry', 'preapproach', carry, qpre),
                                             ('preapproach', 'cut', qpre, qcut)):
                    row = segment(first, second, a, b, motion=opened)
                    approach.append(row)
                    if not row['passed']:
                        break
                if not all(row['passed'] for row in approach):
                    rejected.append({**record, 'reason': 'approach_collision_or_margin', 'segments': approach})
                    continue
                if fixture:
                    closure = segment('cut_open', 'cut_closed', qcut, qcut)
                    if not closure['passed']:
                        rejected.append({**record, 'reason': 'closed_cut_geometry', 'segments': [closure]})
                        continue
                    approach.append(closure)
                for offset in EXTRACTION_OFFSETS:
                    local_out = [v+d for v, d in zip(local_cut, offset)]
                    try:
                        qout = list(c.solve(local_out, seed=qcut))
                    except ValueError as error:
                        rejected.append({**record, 'offset_m': list(offset), 'reason': str(error)})
                        continue
                    extraction = []
                    for first, second, a, b in (('cut', 'extraction_0', qcut, qout),
                                                ('extraction_0', 'carry', qout, carry)):
                        row = segment(first, second, a, b, carrying=True)
                        extraction.append(row)
                        if not row['passed']:
                            break
                    if not all(row['passed'] for row in extraction):
                        rejected.append({**record, 'offset_m': list(offset),
                            'reason': 'extraction_collision_or_margin', 'segments': extraction})
                        continue
                    deposit = None
                    deposit_segments = []
                    if fixture:
                        for release in onboard_release_joints(c, held, carry, fixture['bin']):
                            transfer = segment('carry', 'above_basket', carry, release, carrying=True)
                            if not transfer['passed']:
                                continue
                            clear_open = segment('above_basket_closed', 'above_basket_open', release, release,
                                                 carrying=True, motion=opened)
                            if not clear_open['passed']:
                                continue
                            # The attached world fruit has already been removed from its crop pose.
                            # The separate return audit below uses the released tray volume.
                            deposit, deposit_segments = release, [transfer, clear_open]
                            break
                        if deposit is None:
                            rejected.append({**record, 'reason': 'no_safe_onboard_deposit_pose'})
                            continue
                    segments = approach+extraction+deposit_segments
                    accepted = {'pickup_base_pose': list(base), 'cut_axis_world': world_direction,
                        'joint_waypoints': {'carry': carry, 'preapproach': qpre, 'cut': qcut, 'extraction_0': qout},
                        'tcp_waypoints_world_m': {name: transform_point(pose, point) for name, point in
                            [('carry', carry_local), ('preapproach', local_pre), ('cut', local_cut), ('extraction_0', local_out)]},
                        'sequence': ['carry', 'preapproach', 'cut', 'extraction_0', 'carry'],
                        'extraction_offset_m': list(offset),
                        **({'deposit_joints': deposit} if fixture else {}),
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
    offset = fruit['held_offset_in_tool_m']
    poses = (carry, [0., -.7, .9, .2, 0.], [0., .7, -.9, -.2, 0.])
    for height in (.06, .12, .20, .28):
        center = [x, y, hi[2]+fruit['radius_m']+height]
        for seed in poses:
            q = list(seed)
            for _ in range(8):
                motion = config.fk(q)
                point = rotate_vector(motion['quaternion_xyzw'], offset)
                if math.dist([a+b for a,b in zip(motion['position_m'], point)], center) <= .002:
                    yield q
                    break
                solved = solve_ik(config.robot, [a-b for a,b in zip(center, point)],
                                  tool_frame=config.frame, seed=q, orientation_mode='position_only')
                if not solved.success:
                    break
                q = [solved.joint_positions[name] for name in config.robot.joint_names]


def audited_drive_route(start, route, config, cylinders, fruits, clearance_m):
    """Check stowed robot at in-place turns and along each approach leg."""
    from .harvest_clearance import _CylinderIndex
    from .robot_motion import resolved_world_clearance
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
            row = resolved_world_clearance(carry, base, cylinders, fruits, None, config, report_cap=clearance_m)
            samples += 1
            if row['robot_clearance_m'] < clearance_m:
                return {'passed': False, 'pose': base, 'samples': samples, 'clearance': row}
        start = goal
    return {'passed': True, 'samples': samples, 'planned_base_geometry_only': True,
            'sample_intervals_m_rad': [.025, .06], 'clearance_m': clearance_m}
