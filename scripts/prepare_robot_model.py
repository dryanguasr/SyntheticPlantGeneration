#!/usr/bin/env python3
"""Resolve and export one robot revision; does not launch Gazebo or interpret CAD.

Example: python scripts/prepare_robot_model.py --profile proxy_v1 --output outputs/robot_proxy
Overrides are JSON-pointer records with value and explicit provenance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.robot_spec import (
    PROFILE_DIRECTORY, load_robot_json, resolve_robot_profile, verify_robot_assets,
)
from uchuva_gazebo.robot_sdf import resolved_robot_contract, resolved_robot_model


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


def prepare(profile, output, *, overrides=None, asset_root=None):
    """Fresh output only. A blocked profile still receives an explicit report."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(profile)
    if not source.exists() and source.name == str(profile):
        source = PROFILE_DIRECTORY/(str(profile).removesuffix('.json')+'.json')
    report = {
        'schema_version': 'robot-preparation/1.0',
        'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'NO EJECUTADO',
        'scope': 'Static configuration/description preparation only; no CAD extraction or native dynamics executed.',
        'profile_source': str(source.resolve()),
        'static_preparation_passed': False,
        'checks': [],
        'evidence_status': {
            'cad_correspondence': 'NO OBSERVADO',
            'physical_prototype_correspondence': 'NO OBSERVADO',
            'native_sdf_validation': 'NO EJECUTADO',
            'native_fk_and_contacts': 'NO EJECUTADO',
            'actuator_effort_and_saturation': 'NO EJECUTADO',
            'harvest_mission': 'NO EJECUTADO',
        },
        'files_sha256': {},
        'implementation_files_sha256': {name: sha(REPO/name) for name in (
            'src/uchuva_gazebo/robot_spec.py', 'src/uchuva_gazebo/robot_kinematics.py',
            'src/uchuva_gazebo/robot_sdf.py', 'configs/robots/robot_spec.schema.json',
            'scripts/prepare_robot_model.py')},
    }
    try:
        raw = load_robot_json(source)
        report['source_profile_sha256'] = sha(source)
        report['missing_evidence'] = raw.get('missing_evidence', [])
        robot = resolve_robot_profile(raw, overrides)
        report['checks'].append({'name': 'resolved_schema_physics_topology_provenance', 'status': 'PASS'})
        meshes = [visual['geometry'] for link in robot.links for visual in link['visuals'] if visual['geometry']['type'] == 'mesh']
        if meshes and asset_root is None:
            raise ValueError('Mesh assets require an explicit --asset-root; no implicit download or unverified export')
        verified = verify_robot_assets(robot, asset_root) if meshes else {}
        report['checks'].append({'name': 'mesh_hashes_and_frozen_bindings', 'status': 'PASS', 'mesh_count': len(verified)})
        model = resolved_robot_model(robot)
        root = ET.Element('sdf', version='1.9')
        root.append(model)
        ET.indent(root, space='  ')
        xml = ET.tostring(root, encoding='unicode')+'\n'
        ET.fromstring(xml)
        contract = resolved_robot_contract(robot)
        write_json(output/'robot_resolved.json', robot.to_dict())
        write_json(output/'robot_contract.json', contract)
        (output/'model.sdf').write_text(xml, encoding='utf-8')
        for uri in verified:
            destination = output/uri
            if destination.exists():
                raise ValueError('Asset URI would overwrite a generated robot artifact')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(asset_root)/uri, destination)
            if sha(destination) != verified[uri]:
                raise ValueError('Mesh changed while copying into robot package')
        report['robot_spec_sha256'] = robot.sha256
        report['profile_id'] = robot.profile_id
        report['checks'].append({'name': 'canonical_sdf_and_contract_export', 'status': 'PASS'})
        report['static_preparation_passed'] = True
        report['files_sha256'] = {path.relative_to(output).as_posix(): sha(path) for path in sorted(output.rglob('*')) if path.is_file()}
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['blocker'] = f'{type(error).__name__}: {error}'
        report['checks'].append({'name': 'preparation_blocker', 'status': 'FAIL', 'detail': report['blocker']})
    write_json(output/'preparation_report.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, help='Profile alias or canonical JSON path')
    parser.add_argument('--overrides', type=Path, help='Explicit value/provenance override map')
    parser.add_argument('--asset-root', type=Path, help='Local directory containing admitted meshes')
    parser.add_argument('--output', type=Path, required=True, help='New output directory; never overwritten')
    args = parser.parse_args(argv)
    overrides = load_robot_json(args.overrides) if args.overrides else None
    report = prepare(args.profile, args.output, overrides=overrides, asset_root=args.asset_root)
    print(json.dumps({'output': str(args.output.resolve()), 'static_preparation_passed': report['static_preparation_passed'],
                      'status': report['status'], 'blocker': report.get('blocker')}, ensure_ascii=False))
    return 0 if report['static_preparation_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
