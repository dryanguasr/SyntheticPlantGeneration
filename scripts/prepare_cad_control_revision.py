#!/usr/bin/env python3
"""Apply a documented arm controller revision without changing CAD geometry."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile


def revised_profile(source, revision):
    robot = resolve_robot_profile(source)
    if robot.sha256 != revision['base_robot_spec_sha256']:
        raise ValueError('Control revision does not match its immutable input profile')
    data = robot.to_dict()
    original = copy.deepcopy(data)
    if set(revision['arm']) != set(robot.joint_names):
        raise ValueError('Revision must explicitly cover exactly the arm joints')
    provenance = {'status': 'estimado', 'source': revision['revision_id'],
                  'revision': revision['revision_id'],
                  'method': revision['derivation']['gain_selection']+' '+revision['derivation']['hardware_caveat']}
    for name, settings in revision['arm'].items():
        joint_index = next(i for i, row in enumerate(data['joints']) if row['name'] == name)
        actuator_index = next(i for i, row in enumerate(data['actuators']) if row['joint'] == name)
        key = name+'_simulation_effort_nm'
        data['parameters'][key] = settings['effort_limit_nm']
        data['parameter_metadata']['/parameters/'+key] = {**provenance, 'update_class': 'model_regeneration'}
        effort_paths = [f'/joints/{joint_index}/limits/effort',
                        f'/control/arm/{name}/cmd_min', f'/control/arm/{name}/cmd_max',
                        f'/actuators/{actuator_index}/continuous_effort', f'/actuators/{actuator_index}/peak_effort']
        data['derived_values'] = [row for row in data['derived_values'] if row['path'] not in effort_paths]
        for path in effort_paths:
            expression = {'parameter': key}
            if path.endswith('cmd_min'):
                expression = {'op': 'mul', 'args': [-1, expression]}
            data['derived_values'].append({'path': path, 'expression': expression})
        for gain in ('p_gain', 'i_gain', 'd_gain'):
            data['control']['arm'][name][gain] = settings[gain]
            data['parameter_metadata'][f'/control/arm/{name}/{gain}'] = {**provenance, 'update_class': 'runtime'}
        data['actuators'][actuator_index]['status'] = 'estimado'
    data['profile_id'] += '_'+revision['revision_id']
    data['provenance'] = {**provenance, 'source': original['provenance']['source']+'; '+revision['revision_id']}
    resolved = resolve_robot_profile(data)
    final = resolved.to_dict()
    for key in ('links', 'frames', 'collision_policy', 'arm_home_positions', 'capabilities'):
        if final[key] != original[key]:
            raise AssertionError('Unintended geometry/semantic change: '+key)
    for before, after in zip(original['joints'], final['joints']):
        allowed = copy.deepcopy(after)
        if before['name'] in revision['arm']:
            allowed['limits']['effort'] = before['limits']['effort']
        if before != allowed:
            raise AssertionError('Unintended joint geometry, range or velocity change')
    if final['control']['drive'] != original['control']['drive']:
        raise AssertionError('Unintended drive change')
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--revision', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    revision = json.loads(args.revision.read_text(encoding='utf-8'))
    robot = revised_profile(args.profile, revision)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'profile.json').write_text(json.dumps(robot.to_dict(), indent=2)+'\n', encoding='utf-8')
    evidence = {'robot_spec_sha256': robot.sha256, 'base_robot_spec_sha256': revision['base_robot_spec_sha256'],
                'source_files_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in (args.profile, args.revision, Path(__file__))},
                'geometry_contacts_joint_ranges_velocity_unchanged': True,
                'acceptance_unchanged': True, 'hardware_validation': False}
    (args.output/'derivation.json').write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
