#!/usr/bin/env python3
"""Sample unchanged CAD meshes against frozen V8 at preflight cut candidates.

Static snapshots only: no trajectory, contact, gripper opening or native pass.
All target fruit bodies remain obstacles and no collision pair is exempted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile,verify_robot_assets
from uchuva_gazebo.robot_motion import ResolvedMotionConfig,resolved_world_clearance
from uchuva_gazebo.harvest_clearance import rigid_cylinders,_CylinderIndex


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','asset-root','preflight','plant-package','acceptance-lock','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--per-target',type=int,default=3);args=parser.parse_args()
    if args.per_target<1:parser.error('At least one candidate per target is required')
    robot=resolve_robot_profile(args.profile);verify_robot_assets(robot,args.asset_root)
    preflight=json.loads(args.preflight.read_text());manifest_path=args.plant_package/'manifest.json'
    manifest=json.loads(manifest_path.read_text());lock=json.loads(args.acceptance_lock.read_text())
    if preflight['protocol']['robot_spec_sha256']!=robot.sha256 or preflight['protocol']['manifest_sha256']!=sha(manifest_path):
        raise ValueError('Preflight robot/plant identity does not match supplied artifacts')
    args.output.mkdir(parents=True,exist_ok=False)
    data=robot.to_dict();names=list(robot.joint_names);bounds={j['name']:j['limits'] for j in data['joints'] if j['name'] in names}
    auxiliary={j['name']:0. for j in data['joints'] if j.get('group') in ('passive','gripper')}
    protocol={'scope':__doc__,'robot_spec_sha256':robot.sha256,'per_target':args.per_target,
        'joint_margin_rad':lock['joint_margin_rad'],'clearance_m':lock['motion_clearance_m'],
        'clearance_report_cap_m':lock['motion_clearance_m'],
        'distance_reporting':'Distances at or above the frozen clearance threshold are capped; every potentially failing pair still uses exact declared triangles/primitives.',
        'auxiliary_joint_positions':auxiliary,'auxiliary_state_scope':'Explicit nominal CAD q0, not observed suspension or open gripper state.',
        'collision_exemption_changes':[],'target_body_exemptions':[],
        'source_sha256':{str(p):sha(p) for p in (args.profile,args.preflight,manifest_path,
            args.plant_package/'harvest.sdf',args.acceptance_lock,Path(__file__))}}
    code_paths=[Path(__file__),*[ROOT/'src/uchuva_gazebo'/name for name in
        ('robot_spec.py','robot_kinematics.py','robot_motion.py','robot_mesh_geometry.py','harvest_clearance.py')]]
    code_bytes={path:path.read_bytes() for path in code_paths}
    protocol['analysis_source_sha256']={path.relative_to(ROOT).as_posix():hashlib.sha256(value).hexdigest()
        for path,value in code_bytes.items()}
    for path,value in code_bytes.items():
        destination=args.output/'source_snapshot'/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(value)
    dump(args.output/'protocol.json',protocol)
    tree=ET.parse(args.plant_package/'harvest.sdf');plant_names={p['model_name'] for p in manifest['plants']}
    models=[m for m in tree.findall('world/model') if m.get('name') in plant_names]
    cylinders=_CylinderIndex(rigid_cylinders({'models':models,'plants':manifest['plants']},args.plant_package))
    task={'orientation_mode':'position_direction','target_direction':[0,0,1],'tool_axis':[0,1,0],
        'orientation_tolerance_rad':preflight['protocol']['direction_tolerance_rad'],'tool_frame':'cut_point',
        'auxiliary_joint_positions':auxiliary}
    config=ResolvedMotionConfig(robot,task,asset_root=args.asset_root)
    results=[]
    for target in preflight['targets']:
        margins=[]
        for index,candidate in enumerate(target['candidates']):
            per_joint={name:min(q-bounds[name]['lower'],bounds[name]['upper']-q) for name,q in candidate['joint_positions_rad'].items()}
            margins.append({'candidate_index':index,'minimum_joint_margin_rad':min(per_joint.values()),
                'joint_margins_rad':per_joint,'kinematic_tolerances_passed':candidate['within_kinematic_tolerances']})
        eligible=[row for row in margins if row['kinematic_tolerances_passed'] and row['minimum_joint_margin_rad']>=lock['joint_margin_rad']]
        eligible.sort(key=lambda row:row['minimum_joint_margin_rad'],reverse=True)
        checks=[]
        for entry in eligible[:args.per_target]:
            candidate=target['candidates'][entry['candidate_index']]
            values=[candidate['joint_positions_rad'][name] for name in names]
            started=time.monotonic()
            clearance=resolved_world_clearance(values,candidate['base_xyzyaw'],cylinders,manifest['fruits'],None,config,
                report_cap=lock['motion_clearance_m'])
            checks.append({**entry,'base_xyzyaw':candidate['base_xyzyaw'],
                'joint_positions_rad':candidate['joint_positions_rad'],'clearance':clearance,
                'static_clearance_passed':clearance['robot_clearance_m']>=lock['motion_clearance_m'],
                'analysis_wall_seconds':time.monotonic()-started})
            with (args.output/'candidate_observations.jsonl').open('a') as stream:
                stream.write(json.dumps({'fruit_id':target['fruit_id'],**checks[-1]},allow_nan=False)+'\n')
            print(json.dumps({'target':target['fruit_id'],'candidate':entry['candidate_index'],
                'clearance_m':clearance['robot_clearance_m'],'limiting':clearance['limiting_robot_pair']}),flush=True)
        results.append({'fruit_id':target['fruit_id'],'all_candidate_margins':margins,
            'kinematic_and_margin_candidate_count':len(eligible),'static_checked_candidates':checks,
            'any_sampled_static_candidate_passed':any(row['static_clearance_passed'] for row in checks),
            'continuous_route_and_native_admission':'NOT_EXECUTED'})
        dump(args.output/'target_results.json',results)
    if any(path.read_bytes()!=value for path,value in code_bytes.items()):
        raise ValueError('Analysis source changed during the audit; results cannot be admitted')
    dump(args.output/'summary.json',{'status':'STATIC_PREFLIGHT_ONLY','protocol':protocol,'plant_cylinder_count':len(cylinders),
        'targets':results,'all_targets_have_sampled_static_candidate':all(t['any_sampled_static_candidate_passed'] for t in results)})


if __name__=='__main__':main()
