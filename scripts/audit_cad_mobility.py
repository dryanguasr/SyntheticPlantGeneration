#!/usr/bin/env python3
"""Re-audit immutable CAD mobility observations without running native physics."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    source=args.run_dir.resolve();output=args.output.resolve()
    if output.exists():raise ValueError('Use a fresh audit output directory')
    output.mkdir(parents=True)
    started=time.monotonic()
    names=('protocol.json','robot_resolved.json','profile_source.json','poses.jsonl','joints.jsonl',
           'link_poses.jsonl','commands.jsonl','native.log','provenance.json','world.sdf','runner_source.py')
    evidence={name:sha(source/name) for name in names}
    implementation=[ROOT/'scripts/probe_cad_mobility.py',Path(__file__),*sorted((ROOT/'src/uchuva_gazebo').glob('*.py'))]
    implementation_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in implementation}
    for path in implementation:
        destination=output/'source_snapshot'/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(path.read_bytes())
    sys.path.insert(0,str(ROOT/'src'))
    spec=importlib.util.spec_from_file_location('mobility_audit_runtime',ROOT/'scripts/probe_cad_mobility.py')
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    from uchuva_gazebo.robot_mesh_geometry import MeshRepository
    from uchuva_gazebo.robot_spec import resolve_robot_profile,verify_robot_assets
    robot=resolve_robot_profile(source/'robot_resolved.json')
    ramped=any(settings.get('reference_mode')=='ramped_position'
               for group in ('arm','gripper') for settings in robot.data['control'].get(group,{}).values())
    if ramped:evidence['force_control.jsonl']=sha(source/'force_control.jsonl')
    provenance=read(source/'provenance.json')
    if robot.sha256!=provenance['robot_spec_sha256']:raise ValueError('Observed package robot identity differs')
    if evidence['runner_source.py']!=provenance['runner_sha256']:raise ValueError('Frozen native runner hash differs')
    if evidence['world.sdf']!=provenance['sdf_sha256']:raise ValueError('Native world differs from its pre-launch hash')
    if evidence['profile_source.json']!=provenance['profile_source_sha256']:raise ValueError('Native profile source differs')
    assets=verify_robot_assets(robot,source)
    if assets!=provenance['assets_sha256']:raise ValueError('Native shared CAD asset identities differ')
    for name,digest in provenance['libraries_sha256'].items():
        if sha(source/'plugins'/name)!=digest:raise ValueError('Native library hash differs')
    geometries=[s['geometry'] for link in robot.links for s in link['collisions'] if s['geometry']['type']=='mesh']
    repo=MeshRepository(source,geometries) if geometries else None
    config=read(source/'protocol.json');poses=rows(source/'poses.jsonl');joints=rows(source/'joints.jsonl');links=rows(source/'link_poses.jsonl')
    native_world=ET.parse(source/'world.sdf')
    if config.get('physics'):
        actual_detector=native_world.findtext('world/physics/dart/collision_detector','ode')
        if actual_detector!=config['physics'].get('collision_detector','ode'):
            raise ValueError('Native collision detector differs from the frozen protocol')
        if native_world.findtext('world/physics/dart/solver/solver_type')!=config['physics'].get('solver_type'):
            raise ValueError('Native solver differs from the frozen protocol')
    expected=probe.protocol(config['start_xyzyaw'][2],config['dt_s'],config.get('experiment','full'))
    for key in ('acceptance','criteria','phases','duration_s','dt_s','start_xyzyaw','ground_contact'):
        if config[key]!=expected[key]:raise ValueError('Frozen mobility acceptance contract differs: '+key)
    if config.get('experiment')=='integrated_arm' and config.get('arm_targets_rad')!=probe.arm_phase_targets(robot,expected):
        raise ValueError('Frozen integrated arm targets differ from the resolved profile and protocol')
    errors=[];native_code=None;native_code_source=None
    if (source/'native_completion.json').is_file():
        completion=read(source/'native_completion.json')
        if completion['robot_spec_sha256']!=robot.sha256 or completion['protocol_sha256']!=evidence['protocol.json']:
            raise ValueError('Native completion belongs to another robot/protocol')
        native_code=completion['native_exit_code'];errors.extend(completion.get('errors',[]))
        native_code_source={'path':'native_completion.json','sha256':sha(source/'native_completion.json')}
    elif (source/'result.json').is_file():
        original=read(source/'result.json');native_code=original.get('native_exit_code')
        native_code_source={'path':'result.json','sha256':sha(source/'result.json')}
        for check in original.get('checks',[]):
            if check['name']=='native_exit_and_callbacks':errors.extend(check.get('errors',[]))
    elif (source/'progress.json').is_file():
        errors.extend(read(source/'progress.json').get('callback_errors',[]))
    if native_code is None:
        errors.append('Native return code was not persisted by the original wrapper; it remains unknown, not assumed zero')
    result=probe.evaluate(robot,config,poses,joints,errors,native_code,link_poses=links,mesh_repository=repo,
                          force_control=rows(source/'force_control.jsonl') if ramped else (),commands=rows(source/'commands.jsonl'))
    if any(sha(source/name)!=digest for name,digest in evidence.items()):raise ValueError('Raw observation changed during audit')
    if any(sha(ROOT/name)!=digest for name,digest in implementation_hashes.items()):raise ValueError('Implementation changed during audit')
    result.update(postprocessing_status='COMPLETED',native_exit_code=native_code,native_exit_code_source=native_code_source,
        native_rerun=False,acceptance_criteria_unchanged=True,evidence_files_sha256=evidence,
        implementation_files_sha256=implementation_hashes,source_snapshot='source_snapshot',elapsed_seconds=time.monotonic()-started,
        scope='Independent re-audit of the same native observations and frozen protocol. Unknown native return code prevents a global PASS.')
    (output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'elapsed_seconds':result['elapsed_seconds'],
        'failed_checks':[row['name'] for row in result['checks'] if not row['passed']],
        'result':str(output/'result.json')},indent=2))
    return int(result['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
