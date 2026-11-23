"""Verify the frozen V8 source files, plant poses and interaction thresholds."""
import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(config, lock, *, root=REPO, manifest=None, reference=None):
    errors = []
    if config['plants'] != lock['plants']:
        errors.append('plant_configuration_changed')
    if config['interaction'] != lock['interaction']:
        errors.append('interaction_thresholds_changed')
    observed = {}
    for name, expected in lock['files_sha256'].items():
        path = root/name
        observed[name] = digest(path) if path.is_file() else None
        if observed[name] != expected:
            errors.append('plant_source_changed:'+name)
    if manifest is not None:
        actual = {f['id']: f for f in manifest['fruits']}
        if set(actual) != set(lock['plants']['target_ids']):
            errors.append('target_identities_changed')
        if reference is None:
            errors.append('missing_frozen_geometry_reference')
        else:
            original = {f['id']: f for f in reference['fruits']}
            fields = ('center_world_m', 'cut_point_world_m', 'pedicel_start_world_m',
                      'pedicel_end_world_m', 'radius_m')
            for name in actual.keys() & original.keys():
                if any(actual[name].get(k) != original[name].get(k) for k in fields):
                    errors.append('target_geometry_changed:'+name)
        if manifest['interaction'] != lock['interaction']:
            errors.append('manifest_interaction_thresholds_changed')
    return {'status': 'PASS' if not errors else 'FAIL', 'errors': errors,
            'source_hashes_observed': observed, 'target_count': len(lock['plants']['target_ids']),
            'scope': 'V8 plant/configuration integrity only; no native robot validation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=REPO/'configs/harvest_pilot_v8.json')
    parser.add_argument('--lock', type=Path, default=REPO/'configs/robots/cad_v8_acceptance_lock.json')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--reference', type=Path, default=REPO/'outputs/harvest_pilot_v8_c4_gui/manifest.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    lock = read(args.lock)
    result = verify(read(args.config), lock,
                    manifest=read(args.manifest) if args.manifest else None,
                    reference=read(args.reference) if args.manifest else None)
    result.update(lock_sha256=digest(args.lock), configuration_sha256=digest(args.config))
    if args.manifest:
        result.update(manifest_sha256=digest(args.manifest), reference_sha256=digest(args.reference))
        if result['reference_sha256'] != lock['frozen_manifest']['sha256']:
            result['errors'].append('frozen_manifest_reference_changed')
            result['status'] = 'FAIL'
    content = json.dumps(result, indent=2, ensure_ascii=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(content)
    print(content)
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
