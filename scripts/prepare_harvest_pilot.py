#!/usr/bin/env python3
"""Prepare a manifest-driven harvest fixture using Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_gazebo.harvest_pilot import read_config, write_package


def source_metadata():
    def git(*args):
        result = subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else 'unavailable'
    paths = [REPO / 'src/uchuva_gazebo' / filename for filename in (
        'harvest_pilot.py', 'harvest_plants.py', 'harvest_visuals.py', 'harvest_collision_mesh.py',
        'harvest_clearance.py', 'harvester_robot.py', 'harvest_validation.py',
        'robot_spec.py', 'robot_kinematics.py', 'robot_sdf.py', 'robot_motion.py', 'robot_validation.py',
        'robot_collision_filters.py', 'robot_harvest_planning.py', 'robot_mesh_geometry.py',
        'robot_mechanism_validation.py', 'robot_control_validation.py', 'robot_drive_control.py')]
    paths += [REPO / 'src/uchuva_lsystem' / filename for filename in (
        'grammar.py', 'parameters.py', 'morphology.py', 'collisions.py', 'scene.py', 'blender_geometry.py', 'texture_assets.py')]
    paths += [REPO / 'scripts' / filename for filename in (
        'prepare_harvest_pilot.py', 'export_admitted_harvest_sources.py', 'screen_admitted_harvest_targets.py',
        'harvest_native_video.py', 'run_neo_flight.py', 'harvest_gripper_control.py')]
    paths += [REPO / 'gazebo/harvest_system' / name for name in ('HarvestSystem.cc', 'RobotTelemetrySystem.cc',
        'ClosedLoopSystem.cc', 'GearCouplingSystem.cc', 'JointPositionForceSystem.cc', 'PositionForceController.hh', 'ObservationSchedule.hh', 'CMakeLists.txt')]
    paths += [REPO / 'configs/robots/robot_spec.schema.json']
    return {'git_commit': git('rev-parse', 'HEAD'), 'git_branch': git('branch', '--show-current'),
            'working_tree_dirty': bool(git('status', '--porcelain')),
            'files_sha256': {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=REPO / 'configs/harvest_pilot_v1.json')
    parser.add_argument('--output', type=Path, default=REPO / 'outputs/harvest_pilot')
    parser.add_argument('--camera', action='store_true', help='Add RGB sensor; native run will require a rendering engine')
    parser.add_argument('--video-observer', action='store_true', help='Add a fixed native RGB camera observing the experiment')
    parser.add_argument('--robot-profile', type=Path, help='Canonical robot profile; robot_task must be explicit in the experiment configuration')
    args = parser.parse_args(argv)
    config = read_config(args.config)
    if args.video_observer:
        config['video_observer'] = {'pose': [-4, -4, 3, 0, .336, .937],
            'width': 1280, 'height': 720, 'fps': 15, 'horizontal_fov_rad': 1.25,
            'topic': '/harvest/video_observer/image'}
    if args.robot_profile:
        config['robot_profile'] = str(args.robot_profile.resolve())
    if args.camera:
        if 'robot_profile' in config:
            parser.error('--camera is a legacy proxy option; configure sensors in the robot profile')
        config['robot']['camera'] = True
    try:
        manifest = write_package(args.output, config, source_metadata())
    except (ValueError, FileExistsError) as error:
        parser.exit(2, f'Preparation failed: {error}. Choose a fresh output directory.\n')
    print(json.dumps({'package': str(args.output.resolve()), 'plants': len(manifest['plants']),
                      'dynamic_fruits': len(manifest['fruits']), 'arm_dof': manifest['robot']['arm_dof'],
                      'native_validation': 'pending_gazebo'}, indent=2))


if __name__ == '__main__':
    main()
