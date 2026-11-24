#!/usr/bin/env python3
"""Identify native contacts in every CAD gripper collision without changing physics.

This is a short causal diagnostic, not a harvesting acceptance test. The first
interval holds CAD q0; the following interval ramps only the existing driver
PID to an explicitly bounded opening. All passive coordinates remain physical.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import json
import math
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from probe_cad_gripper_contact import build_world,REPO
from probe_cad_suspension_loop import dump,sha,node
from uchuva_gazebo.robot_spec import load_robot_json,ResolvedRobot,canonical_hash,verify_robot_assets,validate_robot_spec


def diagnostic_profile(source,disable_contacts=False,collision_detector=None,reference_mode=None,gear_damping=None):
    """A separately hashed diagnostic description, never an admission bypass."""
    data=copy.deepcopy(source);removed=[]
    if disable_contacts:
        for link in data['links']:
            if link['name']=='arm_wrist_roll' or link['name'].startswith('gripper_'):
                removed.extend({'link':link['name'],'collision':shape['name']} for shape in link['collisions'])
                link['collisions']=[]
        data['profile_id']+='_no_gripper_contacts_diagnostic'
        data['capabilities']=[value for value in data['capabilities'] if value!='native_harvest']
    if collision_detector is not None:
        data.setdefault('physics',{})['collision_detector']=collision_detector
        data['profile_id']+='_'+collision_detector+'_detector_diagnostic'
    if reference_mode is not None:
        for control in data['control']['gripper'].values():control['reference_mode']=reference_mode
        data['profile_id']+='_'+reference_mode+'_diagnostic'
    if gear_damping is not None:
        for gear in data['gear_couplings']:gear['damping_nms_rad']=gear_damping
        data['profile_id']+='_gear_damping_'+str(gear_damping).replace('.','p')
    if disable_contacts or collision_detector is not None or reference_mode is not None or gear_damping is not None:
        data['provenance']={'status':'estimado','source':'Source RobotSpec SHA256 '+canonical_hash(source),
            'revision':'isolated_gripper_contact_diagnostic_v1',
            'method':'Controlled diagnostic only; collision removal='+str(disable_contacts)+
                     '; collision detector='+str(collision_detector)+'; reference mode='+str(reference_mode)+
                     '; explicit gear damping='+str(gear_damping)+
                     '. No mass, joint, motor gain or friction change. Not harvesting acceptance.'}
    return data,removed


def instrument_contacts(root):
    model=root.find('world/model')
    sensors=[]
    for link in model.findall('link'):
        for sensor in list(link.findall('sensor')):
            link.remove(sensor)
        for collision in link.findall('collision'):
            name=link.get('name')+'__'+collision.get('name')
            topic='/probe/gripper_all_contacts/'+name
            sensor=node(link,'sensor',name='observe_'+name,type='contact')
            node(sensor,'always_on','true');node(sensor,'update_rate',100)
            contact=node(sensor,'contact');node(contact,'collision',collision.get('name'))
            node(contact,'topic',topic)
            sensors.append({'link':link.get('name'),'collision':collision.get('name'),'topic':topic})
    return sensors


def magnitude(vector):
    return math.sqrt(sum(float(vector.get(name,0))**2 for name in ('x','y','z')))


def native_collision_detectors(log):
    clean=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',log)
    return re.findall(r'Using \[([^]]+)\] collision detector',clean)


def run(output):
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    from gz.msgs10.contacts_pb2 import Contacts
    from gz.msgs10.pose_v_pb2 import Pose_V
    from google.protobuf.json_format import MessageToDict
    protocol=json.loads((output/'protocol.json').read_text())
    data=json.loads((output/'profile.json').read_text())
    provenance=json.loads((output/'provenance.json').read_text())
    sensors=json.loads((output/'contact_sensors.json').read_text())
    transport=Node();mutex=threading.Lock();records={name:[] for name in ('joints','gear','poses','commands','force_control')}
    pairs={};errors=[];raw_messages=0
    last_command_time=-math.inf
    driver=next(iter(data['control']['gripper']))
    publisher=transport.advertise(data['namespace']+'/gripper/'+driver+'/cmd_pos',Double)
    if not publisher:raise RuntimeError('Cannot advertise the single driver')
    contact_file=gzip.open(output/'contacts.jsonl.gz','wt',encoding='utf-8',compresslevel=1)

    def on_joints(message):
        nonlocal last_command_time
        try:
            row=json.loads(message.data)
            if row['robot_spec_sha256']!=provenance['canonical_robot_sha256']:
                raise ValueError('Native joint observation belongs to a different profile')
            stamp=row['sim_time']
            reference=min(protocol['open_reference_rad'],max(0,stamp-protocol['initial_hold_s'])*protocol['command_ramp_rad_s'])
            publish_command=stamp-last_command_time+1e-12>=.01
            if publish_command:
                command=Double();command.data=reference
                if not publisher.publish(command):raise RuntimeError('Driver publication failed')
                last_command_time=stamp
            with mutex:
                records['joints'].append(row)
                if publish_command:
                    records['commands'].append({'sim_time':stamp,'joint':driver,'position_rad':reference,
                        'kind':'gripper_position','phase':'q0_hold' if stamp<protocol['initial_hold_s'] else 'open',
                        'passive_joints_commanded':False})
        except (ValueError,KeyError,TypeError,RuntimeError) as error:
            errors.append(str(error))

    def on_gear(message):
        with mutex:records['gear'].append(json.loads(message.data))

    def on_force_control(message):
        row=json.loads(message.data)
        if row.get('robot_spec_sha256')!=provenance['canonical_robot_sha256']:
            errors.append('Native force controller has a different profile hash')
        with mutex:records['force_control'].append(row)

    def on_poses(message):
        row=MessageToDict(message,preserving_proto_field_name=True)
        with mutex:records['poses'].append(row)

    def on_contact(message,source):
        nonlocal raw_messages
        row=MessageToDict(message,preserving_proto_field_name=True)
        with mutex:
            raw_messages+=1
            contact_file.write(json.dumps({'source':source,'native_message':row},allow_nan=False)+'\n')
            for contact in row.get('contact',[]):
                names=tuple(sorted(contact.get(key,{}).get('name','') for key in ('collision1','collision2')))
                timestamp=contact.get('time',row.get('header',{}).get('stamp',{}))
                stamp=float(timestamp.get('sec',0))+1e-9*float(timestamp.get('nsec',0))
                depth=max(contact.get('depth',[]),default=0)
                forces=[magnitude(value.get('force',{})) for wrench in contact.get('wrench',[])
                        for key,value in wrench.items() if key.endswith('wrench') and isinstance(value,dict)]
                item=pairs.setdefault(names,{'collisions':list(names),'observed_records':0,'maximum_depth_m':0,
                    'maximum_reported_force_norm_n':0,'first_sim_time':stamp,'last_sim_time':stamp,
                    'point_min_m':[math.inf]*3,'point_max_m':[-math.inf]*3,'sensor_sources':set(),
                    'records_during_q0_hold':0})
                item['observed_records']+=1;item['maximum_depth_m']=max(item['maximum_depth_m'],depth)
                item['maximum_reported_force_norm_n']=max(item['maximum_reported_force_norm_n'],max(forces,default=0))
                item['last_sim_time']=max(item['last_sim_time'],stamp);item['sensor_sources'].add(source)
                if stamp<protocol['initial_hold_s']:item['records_during_q0_hold']+=1
                for point in contact.get('position',[]):
                    for index,key in enumerate(('x','y','z')):
                        value=float(point.get(key,0));item['point_min_m'][index]=min(item['point_min_m'][index],value)
                        item['point_max_m'][index]=max(item['point_max_m'][index],value)

    subscriptions=[(StringMsg,data['namespace']+'/robot_telemetry',on_joints),
                   (StringMsg,data['namespace']+'/gear_couplings/'+data['gear_couplings'][0]['name'],on_gear),
                   (Pose_V,'/probe/cad_gripper_poses',on_poses)]
    if data['control']['gripper'][driver].get('reference_mode')=='ramped_position':
        subscriptions.append((StringMsg,data['namespace']+'/gripper/'+driver+'/force_control_state/v1',on_force_control))
    for sensor in sensors:
        source=sensor['link']+'::'+sensor['collision']
        subscriptions.append((Contacts,sensor['topic'],lambda message,source=source:on_contact(message,source)))
    for message_type,topic,callback in subscriptions:
        if not transport.subscribe(message_type,topic,callback):raise RuntimeError('Subscription failed: '+topic)
    with (output/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-v','4','-s','-r','--iterations',
            str(round(protocol['duration_s']/protocol['step_s'])+protocol.get('final_observation_guard_steps',0)),str(output/'probe.sdf')],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=200)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
            errors.append('native_timeout')
    time.sleep(.2)
    for _,topic,_ in subscriptions:transport.unsubscribe(topic)
    with mutex:contact_file.close()
    for name,rows in records.items():
        (output/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in rows))
    statistics={}
    for row in records['joints']:
        for joint in row['joints']:
            item=statistics.setdefault(joint['name'],{'minimum_position':math.inf,'maximum_position':-math.inf,
                'maximum_abs_velocity':0,'maximum_velocity_window':0,'maximum_motor_command_window':0})
            if joint['position_available']:
                item['minimum_position']=min(item['minimum_position'],joint['position'])
                item['maximum_position']=max(item['maximum_position'],joint['position'])
            if joint['velocity_available']:item['maximum_abs_velocity']=max(item['maximum_abs_velocity'],abs(joint['velocity']))
            for source,target in (('max_abs_velocity_window','maximum_velocity_window'),
                                  ('max_abs_force_command_window','maximum_motor_command_window')):
                if isinstance(joint.get(source),(int,float)):item[target]=max(item[target],joint[source])
    for row in pairs.values():row['sensor_sources']=sorted(row['sensor_sources'])
    native_log=(output/'native.log').read_text(errors='replace')
    active_detectors=native_collision_detectors(native_log)
    detector_confirmed=bool(active_detectors) and active_detectors[-1]==protocol['collision_detector']
    if not detector_confirmed:errors.append('Requested collision detector was not confirmed by native startup')
    if data['control']['gripper'][driver].get('reference_mode')=='ramped_position' and not records['force_control']:
        errors.append('No native ramped force controller observation received')
    complete=bool(records['joints']) and records['joints'][-1]['sim_time']>=protocol['duration_s']-.02 and not errors and code==0
    result={'status':'OBSERVED' if complete else 'FAIL','not_acceptance_pass':True,'native_exit_code':code,
        'scope':__doc__,'errors':errors,'raw_contact_messages':raw_messages,
        'contact_pair_counts_include_both_sensors':True,
        'requested_collision_detector':protocol['collision_detector'],'native_observed_collision_detectors':active_detectors,
        'contact_pairs':sorted(pairs.values(),key=lambda row:row['maximum_depth_m'],reverse=True),
        'force_controller_observation_count':len(records['force_control']),
        'force_controller_window_maxima':{key:max((row.get(key,0) for row in records['force_control']),default=None)
            for key in ('max_abs_velocity_window','max_abs_force_command_window',
                        'max_abs_unsaturated_force_window','max_abs_reference_rate_window','rejected_commands')},
        'joint_statistics':statistics,'maximum_gear_error_rad':max((abs(row['error_rad']) for row in records['gear']),default=None),
        'last_observed_joints':records['joints'][-1] if records['joints'] else None,
        'files_sha256':{path.name:sha(path) for path in output.iterdir() if path.is_file()}}
    dump(output/'result.json',result)
    print(json.dumps({'status':result['status'],'pairs':len(pairs),'raw_messages':raw_messages,
        'largest_contacts':result['contact_pairs'][:6]},allow_nan=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','asset-root','plugin-dir','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--open-reference-rad',type=float,default=.04)
    parser.add_argument('--no-contact-diagnostic',action='store_true')
    parser.add_argument('--collision-detector',choices=('ode','fcl','bullet','dart'))
    parser.add_argument('--reference-mode',choices=('ramped_position',))
    parser.add_argument('--observation-rate',type=float,default=100)
    parser.add_argument('--duration-s',type=float,default=1.2)
    parser.add_argument('--gear-damping',type=float)
    args=parser.parse_args()
    if not math.isfinite(args.open_reference_rad) or not 0<=args.open_reference_rad<=.04:
        parser.error('Diagnostic opening must lie in [0,.04] rad')
    if not math.isfinite(args.observation_rate) or not 0<args.observation_rate<=10000:
        parser.error('Observation rate must lie in (0,10000] Hz')
    if not math.isfinite(args.duration_s) or not .05<=args.duration_s<=1.2:
        parser.error('Diagnostic duration must lie in [.05,1.2] s')
    if args.gear_damping is not None and (not math.isfinite(args.gear_damping) or args.gear_damping<0):
        parser.error('Gear damping must be finite and nonnegative')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    original=load_robot_json(args.profile)
    data,removed=diagnostic_profile(original,args.no_contact_diagnostic,args.collision_detector,args.reference_mode,args.gear_damping)
    validate_robot_spec(data)
    robot=ResolvedRobot(data,canonical_hash(data));verify_robot_assets(robot,args.asset_root)
    root=build_world(robot,args.asset_root.resolve(),False)
    detector=data.get('physics',{}).get('collision_detector','ode')
    root.find('world/physics/dart/collision_detector').text=detector
    for plugin in root.findall('world/model/plugin'):
        if plugin.get('name') in ('uchuva::RobotTelemetrySystem','uchuva::GearCouplingSystem','uchuva::JointPositionForceSystem'):
            rate=plugin.find('publish_rate')
            if rate is None:node(plugin,'publish_rate',args.observation_rate)
            else:rate.text=str(args.observation_rate)
    sensors=instrument_contacts(root);ET.indent(root,space='  ')
    (output/'probe.sdf').write_text(ET.tostring(root,encoding='unicode')+'\n')
    dump(output/'profile.json',data);dump(output/'source_profile.json',original);dump(output/'contact_sensors.json',sensors)
    dump(output/'protocol.json',{'duration_s':args.duration_s,'step_s':.0001,'initial_hold_s':.2,'command_ramp_rad_s':.2,
        'observation_rate_hz':args.observation_rate,'outer_command_rate_hz':100,
        'final_observation_guard_steps':1,
        'open_reference_rad':args.open_reference_rad,'solver':'pgs','geometry_changes':removed,
        'collision_detector':detector,'no_contact_diagnostic':args.no_contact_diagnostic,
        'reference_mode':args.reference_mode or 'original_position_pid',
        'gear_damping_revision':{'from':[g['damping_nms_rad'] for g in original['gear_couplings']],
            'to':[g['damping_nms_rad'] for g in data['gear_couplings']],
            'rationale':'Explicit diagnostic parameter; candidate 0.012 is motivated by the preregistered full-tree inertia/projection analysis, not a changed acceptance threshold.'} if args.gear_damping is not None else None,
        'control_gain_changes':[],'mass_changes':[],'friction_changes':[],'collision_exclusion_changes':[],
        'contact_recording':'Every delivered message from every gripper collision sensor, lossless gzip JSONL; both sensor endpoints may report the same pair.',
        'frozen_diagnostic_thresholds':{'gripper_closure_m':.0005,'gear_relation_rad':.001,'joint_velocity_limit_rad_s':1},
        'scope':__doc__})
    plugins=output/'plugins';plugins.mkdir();source=args.plugin_dir.resolve()
    build=json.loads((source/'build_provenance.json').read_text())
    systems=['RobotTelemetrySystem','ClosedLoopSystem','GearCouplingSystem']
    if any(control.get('reference_mode')=='ramped_position' for control in data['control']['gripper'].values()):
        systems.append('JointPositionForceSystem')
        header='PositionForceController.hh'
        if sha(REPO/'gazebo/harvest_system'/header)!=build['source_sha256'][header]:
            raise ValueError('Stale controller helper '+header)
    for name in systems:
        library='libUchuva'+name+'.so'
        if sha(source/library)!=build['libraries_sha256'][library] or sha(REPO/'gazebo/harvest_system'/(name+'.cc'))!=build['source_sha256'][name+'.cc']:
            raise ValueError('Stale plugin '+name)
        shutil.copyfile(source/library,plugins/library)
    shutil.copyfile(source/'build_provenance.json',plugins/'build_provenance.json')
    for script in (Path(__file__),REPO/'scripts/probe_cad_gripper_contact.py'):
        shutil.copyfile(script,output/script.name)
    dump(output/'provenance.json',{'canonical_robot_sha256':robot.sha256,'source_robot_spec_sha256':canonical_hash(original),
        'source_profile_sha256':sha(args.profile),
        'asset_root':str(args.asset_root.resolve()),'build_provenance_sha256':sha(source/'build_provenance.json'),
        'script_sha256':sha(__file__),'fixture_builder_sha256':sha(REPO/'scripts/probe_cad_gripper_contact.py')})
    check=subprocess.run(['gz','sdf','-k',str(output/'probe.sdf')],capture_output=True,text=True)
    (output/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise RuntimeError('Invalid SDF')
    os.environ['GZ_PARTITION']='cad-all-contacts-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)
    run(output)


if __name__=='__main__':main()
