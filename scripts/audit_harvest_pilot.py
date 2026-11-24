#!/usr/bin/env python3
"""Recompute acceptance from raw native telemetry; never trust a prior PASS label."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from uchuva_gazebo.harvest_pilot import load_verified_package, sha256_file
from uchuva_gazebo.harvest_validation import evaluate_harvest_run


NATIVE_SOURCE_FILES = ('HarvestSystem.cc', 'CMakeLists.txt')


def native_source_files(manifest):
    """Frozen historical packages retain their original two-source contract."""
    files = manifest.get('source', {}).get('files_sha256', {})
    if 'robot_spec_sha256' in manifest or 'gazebo/harvest_system/RobotTelemetrySystem.cc' in files:
        extra = tuple(name for name in ('ClosedLoopSystem.cc', 'GearCouplingSystem.cc', 'JointPositionForceSystem.cc', 'PositionForceController.hh', 'ObservationSchedule.hh', 'JawStateGuard.hh')
                      if 'gazebo/harvest_system/'+name in files)
        return (*NATIVE_SOURCE_FILES, 'RobotTelemetrySystem.cc', *extra)
    return NATIVE_SOURCE_FILES


def native_library_files(manifest):
    sources = native_source_files(manifest)
    return tuple('libUchuva'+name.removesuffix('.cc')+'.so'
                 for name in sources if name.endswith('.cc'))


def command_event_consistency(commands, events):
    """Match ordered acknowledgements to recorded commands, independently."""
    interactions = [c for c in commands if c.get('kind') == 'interaction']
    acks = [e for e in events if e.get('phase') == 'ack']
    errors = []
    prior_seq, prior_time = 0, -math.inf
    for event in events:
        seq, stamp = event.get('seq'), event.get('sim_time')
        if (type(seq) is not int or seq <= prior_seq or type(stamp) not in (int, float)
                or not math.isfinite(stamp) or stamp < prior_time):
            errors.append('invalid_event_sequence_or_time')
            break
        prior_seq, prior_time = seq, stamp
    if not interactions or len(interactions) != len(acks):
        errors.append('command_ack_count_mismatch')
    for index, (command, event) in enumerate(zip(interactions, acks)):
        expected = event.get('action', '') + (' ' + event['id'] if event.get('id') else '')
        stamp = command.get('sim_time')
        valid_time = (type(stamp) in (int, float) and math.isfinite(stamp)
                      and type(event.get('sim_time')) in (int, float)
                      and 0 <= event['sim_time'] - stamp <= 3)
        if command.get('command') != expected or not valid_time:
            errors.append(f'command_ack_mismatch:{index}')
    return {'name': 'commands_match_event_acknowledgements', 'passed': not errors,
            'command_count': len(interactions), 'ack_count': len(acks), 'errors': errors}


def json_safe(value):
    """Keep unavailable diagnostic magnitudes as null, never JSON Infinity.

    Acceptance is computed before this conversion. Missing measurements retain
    a failed check; null must never be interpreted as a zero residual.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def strict_json_loads(text):
    def reject(constant):
        raise ValueError(f'Nonstandard JSON numeric constant: {constant}')
    return json.loads(text, parse_constant=reject)


def read_jsonl(path):
    records = [strict_json_loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f'JSONL records must be objects: {path}')
    return records


def valid_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def plugin_record_matches(manifest, metadata):
    """Check the recorded build against the frozen source contract, offline."""
    record = metadata.get('plugin_build', {})
    sources = record.get('source_sha256', {})
    expected = manifest.get('source', {}).get('files_sha256', {})
    names = native_source_files(manifest)
    libraries = record.get('libraries_sha256', {})
    robot_provenance = ('robot_spec_sha256' not in manifest or (
        metadata.get('robot_spec_sha256') == manifest['robot_spec_sha256']
        and all(valid_digest(libraries.get(name)) for name in native_library_files(manifest))
        and libraries.get('libUchuvaHarvestSystem.so') == record.get('library_sha256')))
    return (robot_provenance and set(sources) == set(names)
            and all(valid_digest(sources[name]) and sources[name] == expected.get('gazebo/harvest_system/' + name)
                    for name in names)
            and valid_digest(record.get('library_sha256'))
            and record.get('library_sha256') == metadata.get('plugin_sha256')
            and valid_digest(record.get('provenance_sha256')))


def _audit(package, run):
    manifest = load_verified_package(package)
    run = Path(run)
    metadata = strict_json_loads((run / 'run.json').read_text(encoding='utf-8'))
    if metadata['manifest_sha256'] != sha256_file(Path(package) / 'manifest.json'):
        raise ValueError('Run belongs to a different or modified manifest')
    outcome = strict_json_loads((run / 'outcome.json').read_text(encoding='utf-8'))
    samples = read_jsonl(run / 'telemetry.jsonl')
    events = read_jsonl(run / 'events.jsonl')
    commands = read_jsonl(run / 'commands.jsonl')
    mesh_vertices = None
    fixture = manifest.get('robot_task', {}).get('demo_fixture')
    if fixture:
        from uchuva_gazebo.harvest_basket import load_fruit_vertices
        mesh_vertices = load_fruit_vertices(manifest, package)
    report = evaluate_harvest_run(manifest, samples, events, metadata['target_ids'],
                                 mode=metadata['mode'], execution_error=outcome['error'],
                                 fruit_mesh_vertices=mesh_vertices)
    report['checks'] += [
        {'name': 'native_execution_recorded', 'passed': metadata.get('native_executed') is True},
        {'name': 'harmonic_explicitly_selected', 'passed': metadata.get('forced_gazebo_major') == 8},
        {'name': 'native_plugin_provenance', 'passed': plugin_record_matches(manifest, metadata)},
        {'name': 'command_evidence_available', 'passed': bool(commands)},
        command_event_consistency(commands, events),
    ]
    if fixture and metadata['mode'] == 'harvest':
        per_deposit = {row['name'].removesuffix(':settled_in_bin'): row['passed']
                       for row in report['checks'] if row['name'].endswith(':settled_in_bin')}
        report['deposited_fruit_ids'] = [identifier for identifier, passed in per_deposit.items() if passed]
        report['deposited_by_plant'] = {p['id']: sum(identifier.startswith(p['id']+':') and passed
            for identifier, passed in per_deposit.items()) for p in manifest['plants']}
        report['mission_complete_nine'] = len(per_deposit) == 9 and all(
            count == 3 for count in report['deposited_by_plant'].values())
        report['perception_mode'] = fixture['perception_mode']
        report['checks'] += audit_demonstration_gates(run, commands, events, metadata['target_ids'], manifest)
    if 'robot_spec_sha256' in manifest:
        from uchuva_gazebo.robot_validation import evaluate_robot_telemetry
        report['checks'] += evaluate_robot_telemetry(manifest, read_jsonl(run / 'robot_telemetry.jsonl'), samples, events)
        from uchuva_gazebo.robot_control_validation import evaluate_base_drive_control
        report['checks'] += evaluate_base_drive_control(manifest, commands, samples)
        if manifest['robot']['topics'].get('position_force_states'):
            from uchuva_gazebo.robot_control_validation import evaluate_position_force_control
            report['checks'] += evaluate_position_force_control(manifest,
                read_jsonl(run/'force_control.jsonl'), read_jsonl(run/'robot_telemetry.jsonl'), samples)
            report['robot_control_validation_source_sha256'] = sha256_file(REPO / 'src/uchuva_gazebo/robot_control_validation.py')
        if manifest['robot_config'].get('closures') or manifest['robot_config'].get('gear_couplings'):
            from uchuva_gazebo.robot_validation import evaluate_native_mechanisms
            report['checks'] += evaluate_native_mechanisms(manifest,
                read_jsonl(run/'robot_telemetry.jsonl'), read_jsonl(run/'robot_poses.jsonl'), samples)
        report['checks'].append({'name': 'run_effective_robot_frozen', 'passed':
            metadata.get('robot_effective_sha256') == sha256_file(run / 'robot_effective.json')
            == manifest['files_sha256'][manifest['robot_effective_file']]})
        report['robot_validation_source_sha256'] = sha256_file(REPO / 'src/uchuva_gazebo/robot_validation.py')
    for check in report['checks']:
        check.setdefault('status', 'PASS' if check['passed'] else 'FAIL')
    report['passed'] = all(check['passed'] for check in report['checks'])
    report['status'] = ('NO EJECUTADO' if metadata.get('native_executed') is not True
                        else 'PASS' if report['passed'] else 'FAIL')
    report['manifest_sha256'] = metadata['manifest_sha256']
    report['audited_target_ids'] = metadata['target_ids']
    report['auditor_sha256'] = sha256_file(Path(__file__))
    report['validation_source_sha256'] = sha256_file(REPO / 'src/uchuva_gazebo/harvest_validation.py')
    if not report['passed']:
        report['physical_validation'] = 'failed_or_unobserved'
    report['evidence_files_sha256'] = {name: sha256_file(run / name) for name in (
        'run.json', 'outcome.json', 'telemetry.jsonl', 'events.jsonl', 'commands.jsonl', 'server.log')}
    if 'robot_spec_sha256' in manifest:
        report['robot_spec_sha256'] = manifest['robot_spec_sha256']
        report['evidence_files_sha256'].update({name: sha256_file(run / name) for name in ('robot_telemetry.jsonl', 'robot_effective.json')})
        if 'link_poses' in manifest['robot']['topics']:
            report['evidence_files_sha256']['robot_poses.jsonl'] = sha256_file(run/'robot_poses.jsonl')
        if manifest['robot']['topics'].get('position_force_states'):
            report['evidence_files_sha256']['force_control.jsonl'] = sha256_file(run/'force_control.jsonl')
    return report


def audit_demonstration_gates(run, commands, events, target_ids, manifest):
    from uchuva_gazebo.harvest_perception import checked_rgb_frames, target_gate
    from harvest_perception_capture import visibility_from_labels
    import cv2

    rows = []
    fixture = manifest['robot_task']['demo_fixture']
    fruits = {f['id']: f for f in manifest['fruits']}
    for identifier in target_ids:
        seen = [item for item in commands if item.get('kind') == 'perception_confirmation' and item['id'] == identifier]
        actions = {item['action']: item for item in events if item.get('phase') == 'ack'
                   and item.get('id') == identifier and item.get('accepted') is True}
        gated = False
        error = None
        if len(seen) == 1 and 'arm' in actions:
            entry = seen[0]
            directory = (run / entry['capture_directory']).resolve()
            try:
                if not directory.is_relative_to(run.resolve()) or entry['mode'] != fixture['perception_mode']:
                    raise ValueError('Wrong perception mode or evidence directory')
                source = manifest['source']['files_sha256']
                capture = strict_json_loads((directory/'capture_report.json').read_text(encoding='utf-8'))
                observer = manifest['perception_observers'][fruits[identifier]['plant_id']]
                if (capture['status'] != 'CAPTURED_EXACT_NATIVE_PAIRS' or capture['errors'] or
                        capture['capture_script_sha256'] != source['scripts/harvest_perception_capture.py'] or
                        capture['perception_module_sha256'] != source['src/uchuva_gazebo/harvest_perception.py'] or
                        strict_json_loads((directory/'private/observer.json').read_text(encoding='utf-8')) != observer):
                    raise ValueError('Camera capture, observer or capture source differs')
                public = checked_rgb_frames(directory/'public')['frames']
                visibility = strict_json_loads((directory/'private/visibility.json').read_text(encoding='utf-8'))['frames']
                if len(public) != 3 or len(visibility) != 3:
                    raise ValueError('Expected three exact native camera pairs')
                gated = entry['sim_time'] < actions['arm']['sim_time']
                for rgb, labels in zip(public, visibility):
                    if any(rgb[k] != labels[k] for k in ('frame_id', 'stamp_ns', 'image_sha256')):
                        raise ValueError('Camera IDs/timestamps/hashes differ')
                    file = (directory/'private'/labels['label_filename']).resolve()
                    if not file.is_relative_to(directory/'private') or sha256_file(file) != labels['label_png_sha256']:
                        raise ValueError('Verified native labels are unavailable')
                    image = cv2.imread(str(file), cv2.IMREAD_COLOR)
                    if image is None or image.shape != (observer['height'], observer['width'], 3):
                        raise ValueError('Malformed native panoptic frame')
                    rebuilt = visibility_from_labels(image[:, :, ::-1].tobytes(), rgb['width'], rgb['height'],
                                                     rgb['width']*3, observer['target_label_map'])
                    if rebuilt != labels['targets']:
                        raise ValueError('Stored visibility differs from the native label pixels')
                    decision = target_gate(None, labels, mode=entry['mode'], now_ns=round(entry['sim_time']*1e9),
                                           maximum_age_ns=1_000_000_000, minimum_visible_pixels=16, minimum_box_iou=.5)
                    gated = gated and any(t['id'] == identifier and t['eligible'] for t in decision['targets'])
            except (KeyError, ValueError, OSError, TypeError) as exc:
                error = str(exc)
                gated = False
        rows.append({'name': f'{identifier}:observed_camera_confirmation', 'passed': gated, 'error': error})
        for action, position in (('arm', 'open'), ('cut', 'closed'), ('release', 'open')):
            event = actions.get(action, {})
            guard = event.get('jaw_guard') or {}
            expected = fixture['gripper']
            q, velocity = guard.get('position_m'), guard.get('velocity_m_s')
            ok = (guard.get('available') is True and guard.get(f'{position}_ready') is True and
                  type(q) in (float, int) and type(velocity) in (float, int) and
                  abs(q-expected[f'{position}_position_m']) <= expected['position_tolerance_m'] and
                  abs(velocity) <= expected['maximum_speed_m_s'])
            rows.append({'name': f'{identifier}:native_jaw_{action}', 'passed': ok})
    return rows


def audit(package, run):
    """Return a serializable failed report for incomplete or malformed evidence."""
    try:
        return json_safe(_audit(package, run))
    except Exception as error:
        # Auditing must fail closed even when a run was interrupted mid-write.
        return {'schema_version': 'harvest-acceptance/1.0', 'passed': False,
                'status': 'NO OBSERVADO' if isinstance(error, FileNotFoundError) else 'FAIL',
                'checks': [{'name': 'evidence_integrity', 'passed': False}],
                'error': f'{type(error).__name__}: {error}',
                'physical_validation': 'failed_or_unobserved'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    report = audit(args.package, args.run)
    if args.run.is_dir():
        try:
            (args.run / 'audit.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        except OSError as error:
            report['passed'] = False
            report['physical_validation'] = 'failed_or_unobserved'
            report['audit_write_error'] = str(error)
    print(json.dumps(report, indent=2, allow_nan=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
