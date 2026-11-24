"""Screen the locked V8 catalog and freeze the feasible CAD demonstration routes."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
import math
from pathlib import Path
import sys

from prepare_harvest_pilot import source_metadata
from screen_cad_v8_demo import ROOT, read
from verify_cad_v8_acceptance import verify

sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.harvest_basket import DEMO_FIXTURE_SCHEMA, validated_demonstration
from uchuva_gazebo.harvest_clearance import _CylinderIndex, planned_crop_obstacles
from uchuva_gazebo.harvest_pilot import sha256_file, write_package
from uchuva_gazebo.harvest_plants import DEFAULT_PLANT_CONFIG, build_harvest_plants
from uchuva_gazebo.robot_harvest_planning import plan_resolved_harvest
from uchuva_gazebo.robot_motion import ResolvedMotionConfig, resolved_world_clearance
from uchuva_gazebo.robot_spec import resolve_robot_profile


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def build_config(base, robot, robot_directory, derivation, lock, screen, *, rgb_comparison, ideal_cut_segment,
                 ignore_finger_blade_crop_contacts=False, ignore_wrist_housing_crop_contacts=False):
    config = deepcopy(base)
    config['world_name'] = 'uchuva_cad_v8_demonstration'
    config['robot_profile'] = str(robot_directory/'profile.json')
    config['robot_asset_root'] = str(robot_directory/'assets')
    height = screen['height_m']
    config['robot_start_xyzyaw'] = [-1.47, -.8, height, 0.]
    config['aisle_x_m'] = -1.47
    config['video_observer'] = {'pose': [-4.8, -2.9, 2.7, 0., .320, .829], 'width': 1280,
                               'height': 720, 'fps': 10, 'horizontal_fov_rad': 1.1,
                               'topic': '/harvest/video_observer/image'}
    if ignore_wrist_housing_crop_contacts:
        # Put all three stations and the connecting aisle in one native view.
        config['video_observer'].update(pose=[-4.4, 1.8, 2.45, 0., .409, 0.], horizontal_fov_rad=1.47)
    jaw = derivation['gripper']
    if robot.sha256 != derivation['robot_spec_sha256']:
        raise ValueError('Profile differs from recorded CAD derivation')
    bin_spec = {**derivation['bin'], 'frame': 'robot_base'}
    aux = {j['name']: 0. for j in robot.joints if j['group'] in ('passive', 'gripper')}
    config['robot_task'] = {'orientation_mode': 'position_direction', 'target_direction': [0, 0, 1],
        'tool_frame': 'cut_point', 'tool_axis': [0, 1, 0], 'orientation_tolerance_rad': .03,
        'target_direction_source': 'pedicel_axis', 'cut_axis_bidirectional': True,
        'planning_base_height_m': height, 'auxiliary_joint_positions': aux,
        'acceptance': {'max_telemetry_gap_s': .1, 'joint_position_tolerance_rad': .01,
                       'joint_velocity_tolerance_rad_s': .03, 'effort_tolerance_nm': 1e-8,
                       'orientation_state_max_age_s': .1},
        'demo_fixture': {'schema_version': DEMO_FIXTURE_SCHEMA, 'robot_spec_sha256': robot.sha256,
            'scope': 'CAD-based demonstration with ideal cut and latch and native prismatic jaw',
            'frozen_v8_reference_sha256': screen['reference_sha256'], 'motion_clearance_m': lock['motion_clearance_m'],
            'minimum_joint_margin_rad': lock['joint_margin_rad'],
            'gripper': {**jaw, 'maximum_observed_speed_m_s': .0055}, 'bin': bin_spec,
            'ideal_cut_blade_shapes': ['gripper_left_jaw/part_109_bounds', 'gripper_right_jaw/part_110_bounds',
                                       'gripper_left_jaw/part_113_bounds', 'gripper_right_jaw/part_114_bounds'],
            'perception_mode': 'gazebo_instance_visibility', 'rgb_comparison_sha256': sha256_file(rgb_comparison),
            'camera_by_plant': {f'plant_{i:03}': [-1.12, y-.22, .88, 0., .13, .19]
                                for i, (_, y, _) in enumerate(base['plants']['positions_m'])}}}
    config['plants'].update(explicit_targets_allow_partial=True, max_dynamic_fruits_per_plant=3,
                            fruit_collision_representation='closed_v8_calyx_mesh',
                            ideal_cut_segment_m=ideal_cut_segment)
    if ignore_finger_blade_crop_contacts:
        config['robot_task']['demo_fixture']['ignore_finger_blade_crop_contacts'] = True
    if ignore_wrist_housing_crop_contacts:
        config['robot_task']['demo_fixture']['ignore_wrist_housing_crop_contacts'] = True
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('robot-directory', 'cut-screen', 'rgb-comparison', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--candidates-per-target', type=int, default=4)
    parser.add_argument('--package', type=Path, help='Write a verified harvest bundle if a subset passes the preflight')
    parser.add_argument('--static-only', action='store_true')
    parser.add_argument('--ignore-finger-blade-crop-contacts', action='store_true',
                        help='Demonstration only: exempt the declared fingers, pads and blades from crop contacts')
    parser.add_argument('--ignore-wrist-housing-crop-contacts', action='store_true',
                        help='Also exempt the CAD wrist and gripper housing from crop contacts in this demonstration')
    parser.add_argument('--plant', action='append', choices=('plant_000', 'plant_001', 'plant_002'),
                        help='Restrict this candidate search to the named locked plant(s); all plants stay in the field')
    parser.add_argument('--ideal-cut-segment', type=float, default=.008,
                        help='Length of the target pedicel reserved for the explicitly idealized blade and pad interaction')
    args = parser.parse_args()
    if args.candidates_per_target < 1:
        parser.error('--candidates-per-target must be positive')
    if args.ignore_wrist_housing_crop_contacts and not args.ignore_finger_blade_crop_contacts:
        parser.error('--ignore-wrist-housing-crop-contacts requires --ignore-finger-blade-crop-contacts')
    lock = read(ROOT/'configs/robots/cad_v8_acceptance_lock.json')
    base = read(ROOT/'configs/harvest_pilot_v8.json')
    if verify(base, lock)['status'] != 'PASS':
        raise ValueError('Historical V8 source integrity check failed')
    robot = resolve_robot_profile(args.robot_directory/'profile.json')
    screen = read(args.cut_screen)
    if screen['reference_sha256'] != lock['frozen_manifest']['sha256'] or not screen['exact_calyx']:
        raise ValueError('Expected exact-surface screening evidence for the locked V8 scene')
    config = build_config(base, robot, args.robot_directory, read(args.robot_directory/'derivation.json'),
                          lock, screen, rgb_comparison=args.rgb_comparison, ideal_cut_segment=args.ideal_cut_segment,
                          ignore_finger_blade_crop_contacts=args.ignore_finger_blade_crop_contacts,
                          ignore_wrist_housing_crop_contacts=args.ignore_wrist_housing_crop_contacts)
    task = config['robot_task']
    fixture = validated_demonstration(robot, task)
    threshold = fixture['motion_clearance_m']
    from uchuva_gazebo.robot_crop_collision_policy import crop_collision_exclusions
    exempt_shapes = crop_collision_exclusions(robot, task)
    args.output.mkdir(parents=True, exist_ok=False)
    selection = {}
    for fruit in screen['targets']:
        poses = [row for row in fruit['poses'] if row['target_vs_tool_m'] >= threshold
                 or row.get('limiting_shape') in exempt_shapes]
        if args.ignore_wrist_housing_crop_contacts:
            # The old tool score includes the now-excluded shapes. Favor
            # stations farther out in the aisle for the P/D and chassis checks.
            poses.sort(key=lambda row: (row['base_pose'][0], abs(row['base_pose'][3])))
        selection[fruit['id']] = poses
    # Screening starts from the candidates' identical catalog geometry. To
    # avoid trimming reserve pedicels during the final audit, re-export only
    # the final subset and repeat planning from that exact package.
    possible = [f for f in screen['targets'] if selection[f['id']] and
                (not args.plant or f['plant_id'] in args.plant)]
    plants = deepcopy(config['plants'])
    plants['max_dynamic_fruits_per_plant'] = max(Counter(f['plant_id'] for f in possible).values(), default=1)
    # Screening can represent more reserve fruits than the final native scene.
    # The imported morphological sources are unaffected by this export budget.
    default_budget = DEFAULT_PLANT_CONFIG['reproductive_units_max']
    plants['reproductive_units_max'] = max(plants.get('reproductive_units_max', default_budget),
                                          plants['max_dynamic_fruits_per_plant'])
    plants['target_ids'] = [f['id'] for f in possible]
    report = {'status': 'NO EJECUTADO', 'scope': 'sampled CAD planning and route admission before native dynamics',
        'robot_spec_sha256': robot.sha256, 'tool_screen_robot_spec_sha256': screen['robot_spec_sha256'],
        'cut_screen_sha256': sha256_file(args.cut_screen), 'motion_clearance_m': threshold,
        'rgb_comparison_sha256': fixture['rgb_comparison_sha256'], 'tool_only_eligible_ids': plants['target_ids'],
        'checks': [], 'feasible_fruit_ids': [], 'native_executed': False}
    if exempt_shapes:
        report['ignored_crop_contact_shapes'] = sorted(exempt_shapes)
    report_path = args.output/'selection.json'
    write(report_path, report)
    if not possible:
        return 1
    print(f"Screening {len(possible)} frozen crop targets", flush=True)
    bundle = build_harvest_plants(plants, collision_screen=True)
    motion = ResolvedMotionConfig(robot, task, asset_root=args.robot_directory/'assets')
    for fruit in bundle['fruits']:
        geometry = fruit['collision_geometry']
        motion.mesh_repository.register_generated_obj(geometry, bundle['meshes'][geometry['uri']])
    cylinders = _CylinderIndex(planned_crop_obstacles(bundle))
    obstacles = bundle['fruits'] + bundle['static_fruit_obstacles']
    task['pickup_base_candidates'] = {}
    for fruit in bundle['fruits']:
        identifier = fruit['id']
        poses = selection[identifier][:args.candidates_per_target]
        candidates = []
        for pose in poses:
            state = resolved_world_clearance(pose['q'], pose['base_pose'], cylinders, obstacles, None,
                                             motion.for_target_cut(identifier), report_cap=threshold,
                                             reject_on_first_failure=True)
            passed = state['robot_clearance_m'] >= threshold
            report['checks'].append({'id': identifier, 'base_pose': pose['base_pose'], 'q': pose['q'],
                                     'scope': 'cut_pose_only',
                                     'passed': passed, 'clearance': state})
            print(f"{identifier} static={passed} clearance={state['robot_clearance_m']:.6g} "
                  f"limiting={state['limiting_robot_pair']}", flush=True)
            if passed:
                candidates.append(pose)
            write(report_path, report)
        task['pickup_base_candidates'][identifier] = candidates
    if args.static_only:
        report['status'] = 'STATIC_PREFLIGHT_ONLY'
        write(report_path, report)
        return 0
    motion = ResolvedMotionConfig(robot, task, mesh_repository=motion.mesh_repository)
    selected = []
    counts = Counter()
    for fruit in bundle['fruits']:
        identifier = fruit['id']
        if counts[fruit['plant_id']] == 3 or not task['pickup_base_candidates'][identifier]:
            continue
        plan = plan_resolved_harvest(bundle, motion, clearance_m=threshold, target_ids={identifier})['targets'][identifier]
        passed = plan['audit']['passed']
        report['checks'].append({'id': identifier, 'scope': 'pickup_and_deposit_paths', 'passed': passed, 'plan': plan})
        if passed:
            counts[fruit['plant_id']] += 1
            selected.append(identifier)
        report['feasible_fruit_ids'] = selected
        print(f'{identifier} path={passed}', flush=True)
        write(report_path, report)
    report['status'] = 'READY_FOR_PACKAGE' if len(selected) == 9 else 'INCOMPLETE_SELECTION'
    report['feasible_fruits_by_plant'] = dict(counts)
    if selected:
        config['plants']['target_ids'] = selected
        write(args.output/'config.json', config)
        if args.package:
            try:
                write_package(args.package, config, source_metadata())
            except ValueError as error:
                report['package_error'] = str(error)
    write(report_path, report)
    return int(not selected or 'package_error' in report)


if __name__ == '__main__':
    raise SystemExit(main())
