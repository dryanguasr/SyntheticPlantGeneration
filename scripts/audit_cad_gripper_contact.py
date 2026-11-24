#!/usr/bin/env python3
"""Audit an isolated native CAD pinza contact trial, without rerunning physics.

The full profile identity is preserved. Controller scope is explicitly gripper,
and a PASS never admits the full robot, crop grasp forces, or physical cutting.
Negative-depth Bullet manifold points are proximity, not surface contact.
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
from uchuva_gazebo.robot_validation import native_pose_joint_timestamp
from probe_cad_gripper_contact import nonseparating_pedicel_contact,verify_opening_clearance


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def stamp_seconds(header):
    stamp=header.get('stamp',{})
    return int(stamp.get('sec',0))+int(stamp.get('nsec',0))*1e-9


def audit(directory,legacy_timing_adapter=None):
    data=json.loads((directory/'profile.json').read_text());robot=resolve_robot_profile(data)
    original=json.loads((directory/'result.json').read_text())
    protocol=json.loads((directory/'protocol.json').read_text());errors=[]
    provenance=json.loads((directory/'provenance.json').read_text())
    for name,digest in provenance.get('consumed_audit_sources_sha256',{}).items():
        if sha(directory/'audit_sources'/name)!=digest:errors.append('Frozen audit source changed: '+name)
    build_path=directory/'plugins/build_provenance.json';build=json.loads(build_path.read_text())
    if sha(build_path)!=provenance['build_provenance_sha256']:errors.append('Frozen build provenance changed')
    for library in (directory/'plugins').glob('*.so'):
        if sha(library)!=build['libraries_sha256'].get(library.name):errors.append('Frozen native library changed: '+library.name)
    if legacy_timing_adapter is not None:
        if not isinstance(legacy_timing_adapter,dict) or legacy_timing_adapter.get('observer_source_sha256')!=build['source_sha256']['RobotTelemetrySystem.cc']:
            raise ValueError('Legacy clock adapter does not match the frozen observer source')
    # The original FAIL remains immutable. Only the known controller-scope
    # coverage error is re-evaluated; any other acquisition error still fails.
    if original.get('native_exit_code')!=0:errors.append('Native acquisition failed')
    errors.extend(error for error in original.get('errors',[]) if error!='Independent native force audit failed')
    for name,digest in original['files_sha256'].items():
        if sha(directory/name)!=digest:errors.append('Frozen evidence changed: '+name)
    if not protocol.get('contact_test'):errors.append('This is not a contact trial')
    if original.get('native_observed_collision_detectors')!=[protocol['collision_detector']]:
        errors.append('Native collision detector identity mismatch')
    frozen={'maximum_closure_residual_m':.0005,'maximum_gear_error_rad':.001,
        'maximum_latch_jump_m':.0005,'maximum_closure_rotation_residual_rad':.001,'step_s':.0001}
    if any(protocol.get(key)!=value for key,value in frozen.items()):errors.append('Frozen criteria changed')
    if protocol['fixture']['pedicel_radius_m']!=.0018:errors.append('Witness differs from V8 pedicel radius')
    verify_opening_clearance(data,protocol['open_reference_rad'],
        json.loads((directory/'opening_clearance_evidence.json').read_text()))
    native=rows(directory/'joints.jsonl');poses=rows(directory/'poses.jsonl');steps={}
    expected={j['name']:j['limits'] for j in data['joints'] if j['name'].startswith('gripper_')}
    expected_links={link['name'] for link in data['links'] if link['name'].startswith('gripper_')}|{'arm_wrist_roll'}
    velocity_max=0.
    for row in native:
        try:key=round(native_pose_joint_timestamp(row,legacy_timing_adapter)*1e9)
        except ValueError as error:errors.append(str(error));continue
        if key in steps:errors.append('Duplicate native physics step')
        steps[key]=row
        if row.get('robot_spec_sha256')!=robot.sha256:errors.append('Native profile identity mismatch')
        if {j['name'] for j in row['joints']}!=set(expected) or len(row['joints'])!=len(expected):
            errors.append('Incomplete or duplicated native joint coverage')
        if row['sim_time']!=row['measured_after_step_time'] or abs(row['sim_time']-row['commanded_before_step_time']-protocol['step_s'])>1e-12:
            errors.append('Native step timestamp disagreement')
        errors.extend(audit_passive_gear_commands(robot,row)['failures'])
        for joint in row['joints']:
            values=[joint.get(key) for key in ('position','velocity','max_abs_velocity_window')]
            if not joint.get('position_available') or not joint.get('velocity_available') or not all(type(v) in (int,float) and math.isfinite(v) for v in values):
                errors.append('Missing/nonfinite native joint observation');continue
            q,velocity,peak=values;bound=expected[joint['name']];velocity_max=max(velocity_max,abs(velocity),peak)
            if peak>bound['velocity'] or abs(velocity)>bound['velocity']:errors.append('Native velocity limit exceeded')
            if not bound['lower']<=q<=bound['upper']:errors.append('Native position limit exceeded')
    view=SimpleNamespace(to_dict=lambda:{**data,'closures':[c for c in data['closures'] if c['body'] in expected_links]})
    closure_maxima={};gear_max=0.;times=[];matched=0
    for row in poses:
        times.append(row['sim_time']);state=steps.get(round(row['sim_time']*1e9))
        if state is None:errors.append('Missing exact native pose/joint step');continue
        matched+=1
        if set(row['poses'])!=expected_links:errors.append('Incomplete native link coverage')
        sample=audit_mechanism_sample(view,{j['name']:j['position'] for j in state['joints']},row['poses'])
        errors.extend(sample['failures'])
        for closure in sample['closures']:
            maximum=closure_maxima.setdefault(closure['name'],{'position_error_m':0.,'orientation_error_rad':0.})
            for key in maximum:maximum[key]=max(maximum[key],closure[key])
        gear_max=max(gear_max,max(abs(g['coordinate_error_rad']) for g in sample['gears']))
    if not times or times[0]>.020000000001 or protocol['duration_s']-times[-1]>.020000000001 or any(b<=a or b-a>.020000000001 for a,b in zip(times,times[1:])):
        errors.append('Incomplete/nonmonotonic native pose interval')
    force=[]
    if times:
        manifest={'robot_config':data,'robot_spec_sha256':robot.sha256,'robot_task':{'acceptance':{
            'max_telemetry_gap_s':.02,'joint_position_tolerance_rad':.01,
            'joint_velocity_tolerance_rad_s':0,'effort_tolerance_nm':1e-6,'orientation_state_max_age_s':.02}}}
        force=evaluate_position_force_control(manifest,rows(directory/'force_control.jsonl'),native,
            [{'ready':True,'sim_time':times[0]},{'ready':True,'sim_time':times[-1]}],control_groups=('gripper',))
        if any(not check['passed'] for check in force):errors.append('Independent gripper force audit failed')
    driver=next(iter(data['control']['gripper']))
    for command in rows(directory/'commands.jsonl'):
        if command.get('joint')!=driver or command.get('passive_joints_commanded') is not False:
            errors.append('Unexpected/passive command writer')
    events=rows(directory/'events.jsonl')
    arm_times=[r['sim_time'] for r in events if r.get('action')=='arm' and r.get('accepted')]
    cut_times=[r['sim_time'] for r in events if r.get('action')=='cut' and r.get('accepted') and r.get('phase')=='result']
    contact_stats={side:{'points':0,'nonnegative_points':0,'minimum_depth_m':None,'maximum_depth_m':None,
        'nonseparating_times':[]} for side in ('left','right')}
    for row in rows(directory/'contacts.jsonl'):
        side=row['side'];stats=contact_stats[side]
        pad=data['model_name']+'::gripper_'+side+'_jaw::part_'+('113' if side=='left' else '114')+'_bounds'
        for contact in row['native_message'].get('contact',[]):
            names={contact.get(key,{}).get('name','') for key in ('collision1','collision2')}
            if names!={pad,'fruit_fixture::fruit_link::distal_pedicel'}:continue
            stamp=stamp_seconds(contact.get('header',row['native_message'].get('header',{})))
            for depth in contact.get('depth',[]):
                if type(depth) not in (int,float) or not math.isfinite(depth):errors.append('Nonfinite contact depth');continue
                stats['points']+=1;stats['nonnegative_points']+=int(depth>=0)
                stats['minimum_depth_m']=depth if stats['minimum_depth_m'] is None else min(stats['minimum_depth_m'],depth)
                stats['maximum_depth_m']=depth if stats['maximum_depth_m'] is None else max(stats['maximum_depth_m'],depth)
            if nonseparating_pedicel_contact(contact,pad):stats['nonseparating_times'].append(stamp)
    contacts_before_arm={side:bool(arm_times) and any(0<=arm_times[0]-t<=.1 for t in stats['nonseparating_times']) for side,stats in contact_stats.items()}
    if not all(contacts_before_arm.values()):errors.append('Both pads lack nonseparating native pedicel contact before ARM')
    for stats in contact_stats.values():
        stamps=stats.pop('nonseparating_times');stats['first_nonseparating_time_s']=min(stamps,default=None)
    if not arm_times or not cut_times or cut_times[0]-arm_times[0]<.25:errors.append('Missing original ARM/stability/CUT sequence')
    states=[(row['sim_time'],fruit) for row in rows(directory/'states.jsonl') for fruit in row.get('fruits',[]) if fruit['id']=='contact_fixture' and fruit.get('position') is not None]
    jumps=[math.dist(a[1]['position'],b[1]['position']) for a,b in zip(states,states[1:]) if a[1]['state']!='HELD' and b[1]['state']=='HELD']
    residuals=[fruit['constraint_error_m'] for _,fruit in states if fruit['state']=='HELD' and fruit.get('constraint_error_m') is not None]
    double=any(f.get('joint_present') and f.get('removal_pending') for _,f in states)
    latch_ok=bool(jumps) and max(jumps)<=.0005 and bool(residuals) and max(residuals)<=.0005 and not double
    if not latch_ok:errors.append('Ideal latch residual/jump/attachment criteria failed')
    evidence_names=set(original['files_sha256'])|{'result.json'}
    return {'status':'PASS' if not errors else 'FAIL','scope':__doc__,'errors':sorted(set(errors)),
        'source_robot_spec_sha256':robot.sha256,'original_result_status':original['status'],
        'original_result_preserved':True,'required_control_groups':['gripper'],'full_robot_admission':False,
        'independent_force_audit':force,'native_link_pose_samples':len(times),'exact_pose_joint_samples':matched,
        'joint_pose_timestamp_contract':'PosePublisher.header.stamp == RobotTelemetry.'+(legacy_timing_adapter['pose_joint_time_field'] if legacy_timing_adapter else 'measured_after_step_time'),
        'legacy_timing_adapter':legacy_timing_adapter,
        'joint_pose_coverage':'OBSERVED' if matched==len(times) and times else 'NOT_OBSERVED',
        'maximum_native_velocity_rad_s':velocity_max,'closure_maxima':closure_maxima,
        'maximum_native_gear_error_rad':gear_max if matched else None,
        'contact_stats':contact_stats,'contacts_before_arm':contacts_before_arm,
        'maximum_latch_transition_jump_m':max(jumps,default=None),'maximum_held_residual_m':max(residuals,default=None),
        'ideal_latch_compatibility_passed':latch_ok,'simultaneous_attachment_and_pending_removal':double,
        'bullet_depth_primary_sources':[
            'https://github.com/dartsim/dart/blob/v6.13.2/dart/collision/bullet/BulletCollisionDetector.cpp#L631',
            'https://github.com/gazebosim/gz-physics/blob/gz-physics7_7.8.0/dartsim/src/SimulationFeatures.cc#L262'],
        'audit_script_sha256':sha(Path(__file__)),
        'consumed_source_sha256':{name:sha(ROOT/name) for name in (
            'scripts/probe_cad_gripper_contact.py','scripts/admit_cad_gripper_envelope.py',
            'src/uchuva_gazebo/robot_control_validation.py','src/uchuva_gazebo/robot_mechanism_validation.py',
            'src/uchuva_gazebo/robot_kinematics.py','src/uchuva_gazebo/robot_spec.py','src/uchuva_gazebo/robot_validation.py')},
        'consumed_evidence_sha256':{name:sha(directory/name) for name in sorted(evidence_names)}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--legacy-timing-adapter',type=Path);args=parser.parse_args()
    adapter=json.loads(args.legacy_timing_adapter.read_text()) if args.legacy_timing_adapter else None
    report=audit(args.directory,adapter)
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({key:report[key] for key in ('status','errors','source_robot_spec_sha256','contact_stats')},indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
