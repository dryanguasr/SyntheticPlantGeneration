#!/usr/bin/env python3
"""Audit only the isolated gripper bench from independent native observations.

This does not admit a full robot, a different CAD revision, harvesting, contact
grasp, or latch. All closed-link comparisons use measured poses, never FK.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_mechanism_validation import audit_mechanism_sample,audit_passive_gear_commands
from uchuva_gazebo.robot_control_validation import evaluate_position_force_control


def read_rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(directory):
    data=json.loads((directory/'profile.json').read_text());robot=resolve_robot_profile(data)
    result=json.loads((directory/'result.json').read_text());protocol=json.loads((directory/'protocol.json').read_text())
    errors=[]
    if result.get('status')!='OBSERVED' or result.get('native_exit_code')!=0 or result.get('errors'):
        errors.append('Native acquisition did not complete successfully')
    if protocol.get('no_contact_diagnostic'):
        errors.append('Collision-free negative control cannot admit the CAD bench')
    if result.get('native_observed_collision_detectors')!=[protocol['collision_detector']]:
        errors.append('Native detector identity does not match the frozen protocol')
    for filename,digest in result['files_sha256'].items():
        if sha(directory/filename)!=digest:errors.append('Evidence hash changed: '+filename)
    expected_joints={j['name'] for j in data['joints'] if j['name'].startswith('gripper_')}
    expected_links={l['name'] for l in data['links'] if l['name'].startswith('gripper_')}|{'arm_wrist_roll'}
    records=read_rows(directory/'joints.jsonl');observed={}
    limits={j['name']:j['limits'] for j in data['joints'] if j['name'] in expected_joints}
    velocity_max=0.
    for row in records:
        key=round(row['commanded_before_step_time']*1e9)
        if key in observed:errors.append('Duplicate native physics step')
        observed[key]=row
        if row['robot_spec_sha256']!=robot.sha256:errors.append('Wrong native robot hash')
        if {j['name'] for j in row['joints']}!=expected_joints or len(row['joints'])!=len(expected_joints):
            errors.append('Incomplete/duplicate native gripper joints')
        if row['sim_time']!=row['measured_after_step_time'] or abs(row['sim_time']-row['commanded_before_step_time']-protocol['step_s'])>1e-12:
            errors.append('Native step timestamp disagreement')
        for joint in row['joints']:
            if not joint.get('position_available') or not joint.get('velocity_available'):
                errors.append('Native coordinates missing');continue
            values=[joint['position'],joint['velocity'],joint['max_abs_velocity_window']]
            if not all(type(v) in (int,float) and math.isfinite(v) for v in values):
                errors.append('Nonfinite native coordinate');continue
            peak=joint['max_abs_velocity_window'];velocity_max=max(velocity_max,peak)
            bound=limits[joint['name']]
            if peak>bound['velocity']:errors.append('Native velocity limit: '+joint['name'])
            if not bound['lower']<=joint['position']<=bound['upper']:errors.append('Native coordinate limit: '+joint['name'])
        passive=audit_passive_gear_commands(robot,row)
        errors.extend(passive['failures'])
    # Deliberately restrict the analysis domain to the physically retained bench
    # closures. The original whole-robot identity is still checked above.
    mechanism_data={**data,'closures':[c for c in data['closures'] if c['body'] in expected_links]}
    view=SimpleNamespace(to_dict=lambda:mechanism_data)
    maxima={};times=[];gear_max=0.
    for message in read_rows(directory/'poses.jsonl'):
        poses={};stamps=set()
        for row in message['pose']:
            header=row['header'];stamp=header['stamp'];stamps.add(int(stamp.get('sec',0))*10**9+int(stamp.get('nsec',0)))
            if not any(item['key']=='frame_id' and item['value']==[data['model_name']] for item in header['data']):
                errors.append('Wrong native pose frame')
            name=row['name'].removeprefix(data['model_name']+'::')
            if name in poses:errors.append('Duplicate native link pose')
            poses[name]={'xyz_m':[float(row['position'].get(key,0)) for key in 'xyz'],
                'quaternion_xyzw':[float(row['orientation'].get(key,0)) for key in 'xyzw']}
        if len(stamps)!=1 or set(poses)!=expected_links:
            errors.append('Native pose timestamp/coverage disagreement');continue
        stamp=stamps.pop();state=observed.get(stamp)
        if state is None:errors.append('No native joint observation for exact pose step');continue
        sample=audit_mechanism_sample(view,{j['name']:j['position'] for j in state['joints']},poses)
        errors.extend(sample['failures']);times.append(stamp*1e-9)
        for closure in sample['closures']:
            peak=maxima.setdefault(closure['name'],{'position_error_m':0.,'orientation_error_rad':0.})
            for key in peak:peak[key]=max(peak[key],closure[key])
        gear_max=max(gear_max,max(abs(g['coordinate_error_rad']) for g in sample['gears']))
    if len(times)<20 or any(b<=a or b-a>.020000000001 for a,b in zip(times,times[1:])):
        errors.append('Insufficient/nonmonotonic measured pose coverage')
    if not times or times[0]>.020000000001 or protocol['duration_s']-times[-1]>.020000000001:
        errors.append('Incomplete bench interval')
    force=[]
    if times:
        manifest={'robot_config':data,'robot_spec_sha256':robot.sha256,'robot_task':{'acceptance':{
            'max_telemetry_gap_s':.02,'joint_position_tolerance_rad':.01,
            'joint_velocity_tolerance_rad_s':0,'effort_tolerance_nm':1e-6,'orientation_state_max_age_s':.02}}}
        force=evaluate_position_force_control(manifest,read_rows(directory/'force_control.jsonl'),records,
            [{'ready':True,'sim_time':times[0]},{'ready':True,'sim_time':times[-1]}])
        if any(not row['passed'] for row in force):errors.append('Independent force-controller audit failed')
    driver=next(iter(data['control']['gripper']))
    last=next(j for j in records[-1]['joints'] if j['name']==driver)
    if abs(last['position']-protocol['open_reference_rad'])>.01:errors.append('Driver target residual exceeds original .01 rad')
    return {'status':'PASS' if not errors else 'FAIL','scope':__doc__,
        'not_full_robot_or_harvest_acceptance':True,'errors':sorted(set(errors)),
        'source_robot_spec_sha256':robot.sha256,'native_link_pose_samples':len(times),
        'maximum_native_velocity_rad_s':velocity_max,'closure_maxima':maxima,'maximum_native_gear_error_rad':gear_max,
        'independent_force_audit':force,'final_driver_position_rad':last['position'],
        'evidence_result_sha256':sha(directory/'result.json'),'audit_script_sha256':sha(Path(__file__)),
        'consumed_source_sha256':{name:sha(ROOT/'src/uchuva_gazebo'/name) for name in (
            'robot_control_validation.py','robot_mechanism_validation.py','robot_kinematics.py',
            'robot_spec.py','robot_validation.py')},
        'consumed_evidence_sha256':{name:sha(directory/name) for name in (
            'profile.json','protocol.json','result.json','joints.jsonl','poses.jsonl','force_control.jsonl')}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report=audit(args.directory)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps(report,indent=2));return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
