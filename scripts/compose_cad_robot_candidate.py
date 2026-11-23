#!/usr/bin/env python3
"""Compose frozen CAD/control revisions without inheriting a native PASS.

An unresolved damping selection produces only a blocked preparation report,
never an executable profile. This script never starts Gazebo.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = [Path(__file__).resolve(), ROOT/'src/uchuva_gazebo/robot_spec.py',
              ROOT/'configs/robots/robot_spec.schema.json']
CODE_BYTES = {path: path.read_bytes() for path in CODE_PATHS}
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets


DRIVE_PARAMETERS = {'wheel_effort_limit_nm': 6.5, 'wheel_velocity_p_gain': 30.,
                    'wheel_velocity_i_gain': 4., 'wheel_integral_effort_limit_nm': 5.5}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False)+'\n', encoding='utf-8')


def local_path(value):
    path = Path(value)
    if path.is_absolute() or '\\' in value or '..' in path.parts:
        raise ValueError('Integration inputs require portable repository-relative paths')
    resolved = (ROOT/path).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError('Integration input escapes the repository')
    return resolved


def verified_json(entry):
    path = local_path(entry['path'])
    if sha(path) != entry['sha256']:
        raise ValueError('Frozen integration evidence hash differs: '+entry['path'])
    return read(path)


def verify_drive_delta(base, reference, revisions):
    """Replay the exact recorded overrides, including their old provenance.

The original preparation code's prose formatting may evolve. The immutable
history, revision-file hashes and resulting complete profile must all agree.
No changed geometry, extra gain or changed binding can hide in this replay.
"""
    original, target = base.to_dict(), reference.to_dict()
    prefix = original.get('override_history', [])
    history = target.get('override_history', [])
    if history[:len(prefix)] != prefix:
        raise ValueError('Drive reference rewrites the source override history')
    remaining = history[len(prefix):]
    current, observed = base, []
    for revision, path, expected_hash in revisions:
        if revision['base_robot_spec_sha256'] != current.sha256:
            raise ValueError('Drive revision chain refers to a different intermediate profile')
        if not set(revision['candidate_parameters']) <= DRIVE_PARAMETERS.keys():
            raise ValueError('Drive revision attempts an unrelated parameter')
        for parameter, value in revision['candidate_parameters'].items():
            if not remaining:
                raise ValueError('Missing recorded drive override')
            event, remaining = remaining[0], remaining[1:]
            pointer = '/parameters/'+parameter
            if (event['path'] != pointer or event['value'] != value
                    or value != DRIVE_PARAMETERS[parameter]
                    or event['previous_value'] != current.data['parameters'][parameter]
                    or event['provenance']['source'] != path
                    or event['provenance']['revision'] != expected_hash):
                raise ValueError('Drive history differs from the frozen revision')
            current = resolve_robot_profile(current, {pointer: {
                'value': value, 'provenance': event['provenance']}})
            observed.append(copy.deepcopy(event))
    if remaining or current.to_dict() != target:
        raise ValueError('Drive reference contains changes outside the exact override replay')
    if {p: target['parameters'][p] for p in DRIVE_PARAMETERS} != DRIVE_PARAMETERS:
        raise ValueError('Final drive values do not match the declared finite PI hypothesis')
    return observed


def verify_conformance(entry, detector):
    report = verified_json(entry)
    root = local_path(entry['path']).parent
    cases = report.get('cases', {})
    if report.get('status') != 'PASS' or len(cases) != entry['expected_cases']:
        raise ValueError('Collision adapter conformance is incomplete')
    count = 0
    for name, row in cases.items():
        directory = (root/name).resolve()
        if not directory.is_relative_to(root):
            raise ValueError('Conformance case escapes its evidence directory')
        if (row.get('status') != 'PASS' or row.get('native_exit_code') != 0
                or not row.get('checks') or not all(row['checks'].values())):
            raise ValueError('Conformance case did not pass: '+name)
        files = row.get('files_sha256', {})
        if 'probe.sdf' not in files or 'native.log' not in files:
            raise ValueError('Conformance lacks raw provenance')
        for relative, digest in files.items():
            path = (directory/relative).resolve()
            if not path.is_relative_to(directory) or sha(path) != digest:
                raise ValueError('Conformance raw file hash differs: '+name+'/'+relative)
            count += 1
        world = ET.parse(directory/'probe.sdf').getroot()
        if world.findtext('.//physics/dart/collision_detector') != detector:
            raise ValueError('Conformance world uses another collision detector')
    return {'summary_sha256': entry['sha256'], 'cases': len(cases),
            'verified_raw_files': count, 'detector': detector,
            'scope': 'Adapter fixture support only; no integrated CAD validation transfer'}


def compose(cad, base, events, settings, evidence):
    before = cad.to_dict()
    if before['derived_values'] != base.to_dict()['derived_values']:
        raise ValueError('Revised CAD changed the drive parameter binding program')
    if 'native_harvest' in before['capabilities']:
        raise ValueError('This experimental integration must not inherit harvest eligibility')
    result = cad
    for event in events:
        result = resolve_robot_profile(result, {event['path']: {
            'value': event['value'], 'provenance': event['provenance']}})
    driven = result.to_dict()
    for key in ('links', 'frames', 'physics', 'collision_policy', 'closures', 'gear_couplings'):
        if before.get(key) != driven.get(key):
            raise ValueError('Drive integration changed CAD or mechanism state: '+key)
    data = copy.deepcopy(driven)
    detector = settings['collision_detector']
    if detector != 'bullet':
        raise ValueError('This integration revision is restricted to the verified Bullet adapter')
    data['physics']['collision_detector'] = detector
    data['parameter_metadata']['/physics/collision_detector'] = {
        **evidence, 'update_class': 'model_regeneration'}
    controls = settings['position_control']
    if (controls['groups'] != ['arm', 'gripper'] or controls['reference_mode'] != 'ramped_position'
            or controls['gripper_command_velocity_rad_s'] != .2):
        raise ValueError('Unapproved reference-ramp settings')
    for group in controls['groups']:
        for name, gains in data['control'].get(group, {}).items():
            gains['reference_mode'] = 'ramped_position'
            prefix = '/control/'+group+'/'+name
            data['parameter_metadata'][prefix+'/reference_mode'] = {
                **evidence, 'update_class': 'model_regeneration'}
            if group == 'gripper':
                gains['command_velocity'] = .2
                data['parameter_metadata'][prefix+'/command_velocity'] = {
                    **evidence, 'update_class': 'model_regeneration'}
    gear = settings['gear_coupling']
    damping = gear['damping_nms_rad']
    if (gear['selection_status'] != 'selected_for_full_validation'
            or type(damping) not in (int, float) or not math.isfinite(damping) or damping < 0):
        raise ValueError('Gripper damping has not been explicitly selected for full validation')
    matched = [(i, row) for i, row in enumerate(data['gear_couplings']) if row['name'] == gear['name']]
    if len(matched) != 1 or matched[0][1]['stiffness_nm_rad'] != gear['stiffness_nm_rad'] or gear['stiffness_nm_rad'] != 100:
        raise ValueError('Integration cannot change the fixed K100 gear topology')
    index, coupling = matched[0]
    coupling['damping_nms_rad'] = damping
    data['parameter_metadata'][f'/gear_couplings/{index}/damping_nms_rad'] = {
        **evidence, 'update_class': 'model_regeneration'}
    data['provenance']['source'] += '; '+evidence['source']
    data['provenance']['method'] += '; Combined experimental controls and detector; full native acceptance pending.'
    # Independently reverse the narrowly permitted integration fields.
    reverse = copy.deepcopy(data)
    reverse['physics'] = copy.deepcopy(driven['physics'])
    reverse['gear_couplings'] = copy.deepcopy(driven['gear_couplings'])
    for group in controls['groups']:
        for name, gains in reverse['control'].get(group, {}).items():
            prior = driven['control'][group][name]
            if 'reference_mode' in prior:
                gains['reference_mode'] = prior['reference_mode']
            else:
                gains.pop('reference_mode', None)
            if group == 'gripper':
                gains['command_velocity'] = prior['command_velocity']
    reverse['provenance'] = copy.deepcopy(driven['provenance'])
    reverse['parameter_metadata'] = copy.deepcopy(driven['parameter_metadata'])
    if reverse != driven:
        raise ValueError('Composition changed fields outside the frozen integration scope')
    resolved = resolve_robot_profile(data)
    if resolved.to_dict() != data:
        raise ValueError('Resolving integration changed undeclared derived values')
    return resolved


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a fresh output; existing evidence is immutable')
    config_bytes = args.config.read_bytes()
    settings, config_hash = read(args.config), hashlib.sha256(config_bytes).hexdigest()
    if (settings['drive_parameters'] != DRIVE_PARAMETERS or settings['native_harvest_eligible'] is not False
            or any(settings[k] for k in ('acceptance_changes', 'collision_exclusion_changes', 'plant_changes'))):
        raise ValueError('Integration configuration changes the authorized scope')
    profiles = {}
    input_hashes = {args.config.as_posix(): config_hash}
    for role, entry in settings['profiles'].items():
        path = local_path(entry['path'])
        robot = resolve_robot_profile(path)
        if robot.sha256 != entry['robot_spec_sha256']:
            raise ValueError('Frozen source profile differs: '+role)
        profiles[role] = robot
        input_hashes[entry['path']] = sha(path)
    revisions = [(verified_json(entry), entry['path'], entry['sha256'])
                 for entry in settings['drive_revisions']]
    events = verify_drive_delta(profiles['mechanism_base'], profiles['drive_reference'], revisions)
    conformance = [verify_conformance(row, settings['collision_detector']) for row in settings['collision_conformance']]
    velocity_entry = settings['position_control']['velocity_evidence']
    velocity = verified_json(velocity_entry)
    if velocity['gripper']['command_velocity_rad_s'] != .2:
        raise ValueError('Gripper ramp differs from its frozen estimation revision')
    asset_root = local_path(settings['profiles']['cad_revision']['asset_root'])
    verified_assets = verify_robot_assets(profiles['cad_revision'], asset_root)
    selection = settings['gear_coupling']
    pending = (selection['damping_nms_rad'] is None or selection['selection_status'] != 'selected_for_full_validation')
    if not pending:
        if not selection.get('selection_evidence'):
            raise ValueError('Selected damping requires frozen supporting evidence')
        verified_json(selection['selection_evidence'])
        if selection.get('supporting_analysis'):
            verified_json(selection['supporting_analysis'])
    args.output.mkdir(parents=True)
    report = {'schema_version': 'cad-integration-preparation/1.0',
        'status': 'BLOCKED_DAMPING_SELECTION_PENDING' if pending else 'PREPARED_NOT_NATIVE_VALIDATED',
        'config_sha256': config_hash, 'input_files_sha256': input_hashes,
        'declared_scope': settings['scope'], 'configuration_status': settings['status'],
        'source_robot_specs': {key: value.sha256 for key, value in profiles.items()},
        'drive_override_replay_exact': True, 'drive_events': events,
        'collision_conformance': conformance,
        'native_harvest_eligible': False, 'native_validation': 'NO EJECUTADO',
        'cad_operational_envelope_status': settings['profiles']['cad_revision']['operational_envelope_status'],
        'gripper_damping_selection': selection,
        'asset_root': None if pending else 'assets',
        'acceptance_masks_plants_unchanged': True,
        'all_source_cad_links_inertias_and_poses_preserved': True}
    if not pending:
        evidence = {'status': 'estimado', 'source': args.config.as_posix()+' SHA256 '+config_hash,
                    'revision': settings['revision_id'],
                    'method': settings['position_control']['provenance']+'; '+selection['provenance'],
                    'uncertainty': 'Simulation hypotheses only; no integrated native PASS or hardware calibration.'}
        robot = compose(profiles['cad_revision'], profiles['mechanism_base'], events, settings, evidence)
        shutil.copytree(asset_root, args.output/'assets')
        verify_robot_assets(robot, args.output/'assets')
        write(args.output/'profile.json', robot.to_dict())
        report['robot_spec_sha256'] = robot.sha256
        report['profile_file_sha256'] = sha(args.output/'profile.json')
        report['verified_asset_count'] = len(verified_assets)
    snapshots = args.output/'source_snapshot'
    snapshots.mkdir()
    for path, content in CODE_BYTES.items():
        if path.read_bytes() != content:
            raise ValueError('Execution source changed during composition: '+path.name)
        (snapshots/path.name).write_bytes(content)
    if args.config.read_bytes() != config_bytes:
        raise ValueError('Integration settings changed during preparation')
    report['source_code_sha256'] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(b).hexdigest()
                                    for p, b in CODE_BYTES.items()}
    (args.output/'integration_config.json').write_bytes(config_bytes)
    write(args.output/'integration_report.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'drive_override_replay_exact',
                      'native_harvest_eligible', 'native_validation')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()
