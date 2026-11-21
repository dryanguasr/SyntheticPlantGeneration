#!/usr/bin/env python3
"""Prepare the six-target harvest fixture using only Python's standard library."""
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
        'harvest_clearance.py', 'harvester_robot.py', 'harvest_validation.py')]
    paths += [REPO / 'src/uchuva_lsystem' / filename for filename in (
        'grammar.py', 'parameters.py', 'morphology.py', 'collisions.py', 'scene.py', 'blender_geometry.py', 'texture_assets.py')]
    paths += [REPO / 'scripts' / filename for filename in (
        'prepare_harvest_pilot.py', 'export_admitted_harvest_sources.py', 'screen_admitted_harvest_targets.py')]
    paths += [REPO / 'gazebo/harvest_system/HarvestSystem.cc', REPO / 'gazebo/harvest_system/CMakeLists.txt']
    return {'git_commit': git('rev-parse', 'HEAD'), 'git_branch': git('branch', '--show-current'),
            'working_tree_dirty': bool(git('status', '--porcelain')),
            'files_sha256': {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=REPO / 'configs/harvest_pilot_v1.json')
    parser.add_argument('--output', type=Path, default=REPO / 'outputs/harvest_pilot')
    parser.add_argument('--camera', action='store_true', help='Add RGB sensor; native run will require a rendering engine')
    args = parser.parse_args(argv)
    config = read_config(args.config)
    if args.camera:
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
