#!/usr/bin/env python3
"""Add one explicit optional base-feedback revision; never run native physics."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[Path(__file__).resolve(),ROOT/'src/uchuva_gazebo/robot_spec.py',
         ROOT/'src/uchuva_gazebo/robot_drive_control.py',ROOT/'configs/robots/robot_spec.schema.json']
BYTES={p:p.read_bytes() for p in SOURCES}
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile,verify_robot_assets


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh candidate directory')
    config_bytes=args.config.read_bytes();config=read(args.config)
    profile=ROOT/config['source_profile'];assets=ROOT/config['source_asset_root']
    profile_digest=sha(profile);source=resolve_robot_profile(profile)
    if source.sha256!=config['source_robot_spec_sha256']:raise ValueError('Source RobotSpec differs')
    verified=verify_robot_assets(source,assets);old=source.to_dict();new=copy.deepcopy(old)
    if 'base_feedback' in old['control']['drive']:raise ValueError('This revision only introduces an absent optional controller')
    if 'native_harvest' in old['capabilities']:raise ValueError('Diagnostic candidate cannot inherit harvest eligibility')
    evidence=copy.deepcopy(config['provenance'])
    evidence['source']+='; settings SHA256 '+hashlib.sha256(config_bytes).hexdigest()
    new['control']['drive']['base_feedback']=config['base_feedback']
    added=[]
    for key in config['base_feedback']:
        path='/control/drive/base_feedback/'+key
        if path in new['parameter_metadata']:raise ValueError('Unexpected pre-existing feedback metadata')
        new['parameter_metadata'][path]={**evidence,'update_class':'runtime'};added.append(path)
    new['provenance']={**evidence,'source':old['provenance']['source']+'; '+evidence['source']}
    robot=resolve_robot_profile(new)
    reverse=robot.to_dict();del reverse['control']['drive']['base_feedback']
    for path in added:del reverse['parameter_metadata'][path]
    reverse['provenance']=old['provenance']
    if reverse!=old:raise ValueError('Feedback revision changed unrelated physical inputs')
    args.output.mkdir(parents=True);shutil.copytree(assets,args.output/'assets')
    if verify_robot_assets(robot,args.output/'assets')!=verified:raise ValueError('Candidate CAD assets differ')
    write(args.output/'profile.json',robot.to_dict())
    (args.output/'revision_config.json').write_bytes(config_bytes)
    snapshots=args.output/'source_snapshot';snapshots.mkdir()
    for path,content in BYTES.items():
        if path.read_bytes()!=content:raise ValueError('Preparation source changed')
        (snapshots/path.name).write_bytes(content)
    if sha(profile)!=profile_digest or args.config.read_bytes()!=config_bytes:raise ValueError('Frozen input changed')
    report={'status':'PREPARED_NOT_NATIVE_VALIDATED','source_robot_spec_sha256':source.sha256,
        'robot_spec_sha256':robot.sha256,'source_profile_sha256':profile_digest,
        'config_sha256':hashlib.sha256(config_bytes).hexdigest(),'asset_root':'assets',
        'allowed_changes':['control.drive.base_feedback','feedback provenance metadata','profile provenance'],
        'all_other_inputs_identical':True,'required_new_observation_contract':config['required_new_observation_contract'],
        'known_prior_failures_preserved':config['provenance']['uncertainty'],
        'native_validation':'NO EJECUTADO','native_harvest_eligible':False,
        'source_files_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(b).hexdigest() for p,b in BYTES.items()}}
    write(args.output/'derivation.json',report)
    print(json.dumps({'status':report['status'],'robot_spec_sha256':robot.sha256},indent=2))


if __name__=='__main__':main()
