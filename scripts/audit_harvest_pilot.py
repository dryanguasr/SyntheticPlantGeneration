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
    return (set(sources) == set(NATIVE_SOURCE_FILES)
            and all(valid_digest(sources[name]) and sources[name] == expected.get('gazebo/harvest_system/' + name)
                    for name in NATIVE_SOURCE_FILES)
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
    report = evaluate_harvest_run(manifest, samples, events, metadata['target_ids'],
                                 mode=metadata['mode'], execution_error=outcome['error'])
    report['checks'] += [
        {'name': 'native_execution_recorded', 'passed': metadata.get('native_executed') is True},
        {'name': 'harmonic_explicitly_selected', 'passed': metadata.get('forced_gazebo_major') == 8},
        {'name': 'native_plugin_provenance', 'passed': plugin_record_matches(manifest, metadata)},
        {'name': 'command_evidence_available', 'passed': bool(commands)},
        command_event_consistency(commands, events),
    ]
    for check in report['checks']:
        check.setdefault('status', 'PASS' if check['passed'] else 'FAIL')
    report['passed'] = all(check['passed'] for check in report['checks'])
    report['status'] = ('NO EJECUTADO' if metadata.get('native_executed') is not True
                        else 'PASS' if report['passed'] else 'FAIL')
    report['auditor_sha256'] = sha256_file(Path(__file__))
    report['validation_source_sha256'] = sha256_file(REPO / 'src/uchuva_gazebo/harvest_validation.py')
    if not report['passed']:
        report['physical_validation'] = 'failed_or_unobserved'
    report['evidence_files_sha256'] = {name: sha256_file(run / name) for name in (
        'run.json', 'outcome.json', 'telemetry.jsonl', 'events.jsonl', 'commands.jsonl', 'server.log')}
    return report


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
