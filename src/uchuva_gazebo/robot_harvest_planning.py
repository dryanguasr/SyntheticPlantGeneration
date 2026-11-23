"""Bounded CAD pickup search with full base poses and a common carry posture.

The caller supplies candidate robot poses, never revised plant positions.
Infeasibility is retained per target; this is a sampled screen, not a proof
of continuous collision freedom or successful native contact dynamics.
"""
from __future__ import annotations

import math

from .robot_kinematics import (pose_from_rpy, inverse_pose, transform_point,
                               rotate_vector)


def plan_resolved_harvest(bundle, config, *, samples=81, clearance_m=.004,
                          pickup_standoff_m=.5):
    from .harvest_clearance import (rigid_cylinders, audit_joint_segment,
                                   EXTRACTION_OFFSETS)
    task = config.task
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
    cylinders, fruits = rigid_cylinders(bundle), bundle['fruits']
    if not fruits or len({f['id'] for f in fruits}) != len(fruits):
        raise ValueError('Resolved planning requires nonempty unique fruit identities')
    targets = {}
    for fruit in fruits:
        cut = fruit['cut_point_world_m']
        axis = [b-a for a, b in zip(fruit['pedicel_start_world_m'], fruit['pedicel_end_world_m'])]
        length = math.sqrt(sum(v*v for v in axis))
        if length < 1e-12:
            raise ValueError('Morphological pedicel direction cannot be zero')
        axis = [v/length for v in axis]
        candidates = task.get('pickup_base_candidates', {}).get(fruit['id'],
            [[cut[0]-pickup_standoff_m, cut[1], height, 0]])
        rejected, accepted = [], None
        for base in candidates:
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
                c = config.for_direction(rotate_vector(inverse['quaternion_xyzw'], world_direction))
                record = {'base_pose': list(base), 'direction_sign': sign}
                try:
                    qcut = list(c.solve(local_cut, seed=carry))
                    qpre = list(c.solve(local_pre, seed=qcut))
                except ValueError as error:
                    rejected.append({**record, 'reason': str(error)})
                    continue
                _, cut_pose = c.world_shapes(qcut, base)
                held = {**fruit, 'held_offset_in_tool_m':
                        transform_point(inverse_pose(cut_pose), fruit['center_world_m'])}
                approach = []
                for first, second, a, b in (('carry', 'preapproach', carry, qpre),
                                             ('preapproach', 'cut', qpre, qcut)):
                    row = audit_joint_segment(a, b, base, cylinders, fruits, config=c,
                        samples=samples, clearance_m=clearance_m, stop_on_failure=True)
                    row.update({'from': first, 'to': second, 'held': False})
                    approach.append(row)
                    if not row['passed']:
                        break
                if not all(row['passed'] for row in approach):
                    rejected.append({**record, 'reason': 'approach_collision_or_margin', 'segments': approach})
                    continue
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
                        row = audit_joint_segment(a, b, base, cylinders, fruits, held=held, config=c,
                            samples=samples, clearance_m=clearance_m, stop_on_failure=True)
                        row.update({'from': first, 'to': second, 'held': True})
                        extraction.append(row)
                        if not row['passed']:
                            break
                    if not all(row['passed'] for row in extraction):
                        rejected.append({**record, 'offset_m': list(offset),
                            'reason': 'extraction_collision_or_margin', 'segments': extraction})
                        continue
                    segments = approach+extraction
                    accepted = {'pickup_base_pose': list(base), 'cut_axis_world': world_direction,
                        'joint_waypoints': {'carry': carry, 'preapproach': qpre, 'cut': qcut, 'extraction_0': qout},
                        'tcp_waypoints_world_m': {name: transform_point(pose, point) for name, point in
                            [('carry', carry_local), ('preapproach', local_pre), ('cut', local_cut), ('extraction_0', local_out)]},
                        'sequence': ['carry', 'preapproach', 'cut', 'extraction_0', 'carry'],
                        'extraction_offset_m': list(offset),
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
