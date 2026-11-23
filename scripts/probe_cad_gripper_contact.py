#!/usr/bin/env python3
"""Observe the real CAD gripper's opening and physical jaw contacts separately.

The wrist is fixed to a bench for this isolated mechanism test. All gripper
inertias, collisions, visuals, passive joints and gears come from the profile.
No moving joint is teleported or assigned a passive position command.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
from uchuva_gazebo.robot_spec import load_robot_json,ResolvedRobot,canonical_hash,verify_robot_assets
from uchuva_gazebo.robot_sdf import resolved_robot_model,pose_rpy
from uchuva_gazebo.robot_kinematics import compose_poses,rotate_vector,transform_point,forward_kinematics
from probe_cad_suspension_loop import node,dump,sha,numbers


def verify_opening_clearance(data,reference,evidence):
    """Bind the revised-CAD operating certificate to an actual profile mesh."""
    if evidence.get('status')!='PASS':raise ValueError('CAD operating envelope is not admitted')
    interval=evidence.get('interval_rad',[])
    if len(interval)!=2 or not all(type(v) in (int,float) and math.isfinite(v) for v in interval) or not interval[0]<=0<reference<=interval[1]:
        raise ValueError('CAD operating envelope does not cover the complete requested opening')
    cad_sha=evidence.get('cad_part_sha256','');visual_sha=evidence.get('visual_obj_sha256','').lower()
    if any(len(value)!=64 or any(c not in '0123456789abcdef' for c in value.lower()) for value in (cad_sha,visual_sha)):
        raise ValueError('Operating envelope lacks valid CAD / visual identity')
    bound={shape['geometry'].get('sha256','').lower() for link in data['links']
           for shape in link.get('visuals',[]) if shape['geometry']['type']=='mesh'}
    if visual_sha not in bound:raise ValueError('Admitted CAD mesh is absent from the actual profile')


def build_world(robot, asset_root, contact_test=False):
    data=robot.to_dict();root=ET.Element('sdf',version='1.10');world=node(root,'world',name='cad_gripper_bench')
    node(world,'gravity','0 0 -9.81');physics=node(world,'physics',name='100us',type='ignored')
    node(physics,'max_step_size',.0001);node(physics,'real_time_factor',1)
    dart=node(physics,'dart');node(dart,'collision_detector',data.get('physics',{}).get('collision_detector','ode'))
    node(node(dart,'solver'),'solver_type','pgs')
    node(world,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    node(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
    node(world,'plugin',filename='gz-sim-user-commands-system',name='gz::sim::systems::UserCommands')
    model=resolved_robot_model(robot)
    retained={l['name'] for l in data['links'] if l['name'].startswith('gripper_')}|{'arm_wrist_roll'}
    gripper_joints={j['name'] for j in data['joints'] if j['name'].startswith('gripper_')}
    for link in model.findall('link'):
        if link.get('name') not in retained:model.remove(link)
    for joint in model.findall('joint'):
        if joint.get('name') not in gripper_joints:model.remove(joint)
    for frame in model.findall('frame'):
        if frame.get('attached_to') not in retained:model.remove(frame)
    for plugin in model.findall('plugin'):
        name=plugin.get('name')
        if name=='uchuva::ClosedLoopSystem':
            for closure in plugin.findall('closure'):
                if closure.findtext('body') not in retained:plugin.remove(closure)
        elif name=='uchuva::GearCouplingSystem':pass
        elif name in ('gz::sim::systems::JointPositionController','uchuva::JointPositionForceSystem') and plugin.findtext('joint_name') in data['control'].get('gripper',{}):pass
        elif name=='uchuva::RobotTelemetrySystem':
            for joint in plugin.findall('joint'):
                if joint.get('name') not in gripper_joints:plugin.remove(joint)
        else:model.remove(plugin)
    anchor=node(model,'joint',name='isolated_wrist_bench',type='fixed')
    node(anchor,'parent','world');node(anchor,'child','arm_wrist_roll')
    for uri in model.findall('.//mesh/uri'):uri.text=str((asset_root/uri.text).resolve())
    publisher=node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for tag,value in (('publish_link_pose','true'),('publish_model_pose','false'),('use_pose_vector_msg','true'),
        ('static_publisher','false'),('update_frequency',100),('topic','/probe/cad_gripper_poses')):node(publisher,tag,value)
    for side in ('left','right'):
        link=model.find(f"link[@name='gripper_{side}_jaw']")
        sensor=node(link,'sensor',name=side+'_jaw_contact',type='contact')
        node(sensor,'always_on','true');node(sensor,'update_rate',100)
        node(sensor,'topic','/probe/cad_'+side+'_contacts')
        contact=node(sensor,'contact')
        node(contact,'collision','part_113_bounds' if side=='left' else 'part_114_bounds')
        node(contact,'topic','/probe/cad_'+side+'_contacts')
    if contact_test:
        plant=node(world,'model',name='plant_fixture');node(plant,'static','true');node(plant,'link',name='plant_link')
        harvest=node(world,'plugin',filename='libUchuvaHarvestSystem.so',name='uchuva::HarvestSystem')
        for tag,value in (('robot_model',data['model_name']),('tool_link','arm_wrist_roll'),
            ('tool_cut_axis','0 1 0'),('cut_axis_tolerance',.05),('cut_tolerance',.001),
            ('capture_radius',.05),('max_relative_speed',.12),('stable_time',.2)):
            node(harvest,tag,value)
        for tag,frame in (('tcp_pose','tcp'),('cut_pose','cut_point'),('grasp_pose','grasp_center')):
            node(harvest,tag,numbers(pose_rpy(next(f['pose'] for f in data['frames'] if f['name']==frame))))
        fruit=node(harvest,'fruit',id='contact_fixture')
        for tag,value in (('model','fruit_fixture'),('link','fruit_link'),('parent_model','plant_fixture'),
            ('parent_link','plant_link'),('cut_point','0 .033 0'),('cut_axis','0 1 0')):node(fruit,tag,value)
    world.append(model);ET.indent(root,space='  ')
    return root


def fruit_fixture(grasp, pedicel_radius_m=.0018):
    """Explicit bench witness: 32mm body below grasp, V8-sized 3.6mm pedicel."""
    pose={'xyz_m':transform_point(grasp,[0,-.03,0]),'quaternion_xyzw':grasp['quaternion_xyzw']}
    root=ET.Element('sdf',version='1.10');model=node(root,'model',name='fruit_fixture')
    node(model,'pose',numbers(pose_rpy(pose)));link=node(model,'link',name='fruit_link')
    inertial=node(link,'inertial');node(inertial,'mass',.006);tensor=node(inertial,'inertia')
    for name in ('ixx','iyy','izz'):node(tensor,name,.4*.006*.016**2)
    for name,kind,local in (('berry','sphere','0 0 0 0 0 0'),('distal_pedicel','cylinder','0 .0245 0 1.5707963267948966 0 0')):
        for tag in ('collision','visual'):
            shape=node(link,tag,name=name);node(shape,'pose',local);geometry=node(node(shape,'geometry'),kind)
            node(geometry,'radius',.016 if kind=='sphere' else pedicel_radius_m)
            if kind=='cylinder':node(geometry,'length',.018)
            if tag=='collision':
                surface=node(shape,'surface');node(node(surface,'contact'),'collide_bitmask',65535)
                friction=node(node(surface,'friction'),'ode');node(friction,'mu',.6);node(friction,'mu2',.6)
    ET.indent(root,space='  ')
    return ET.tostring(root,encoding='unicode')+'\n'


def jaw_gap(data, poses, pad_vertices=None):
    frame=next(r for r in data['frames'] if r['name']=='grasp_center')
    grasp=compose_poses(poses[frame['parent']],frame['pose'])
    axis=rotate_vector(grasp['quaternion_xyzw'],[1,0,0])
    projected={}
    for side,part in (('left','part_113_bounds'),('right','part_114_bounds')):
        link=next(l for l in data['links'] if l['name']==f'gripper_{side}_jaw')
        shape=next(s for s in link['collisions'] if s['name']==part)
        pose=compose_poses(poses[link['name']],shape['pose'])
        if shape['geometry']['type']=='mesh':
            projections=[sum((a-b)*d for a,b,d in zip(transform_point(pose,vertex),grasp['xyz_m'],axis))
                         for vertex in pad_vertices[side]]
            lo,hi=min(projections),max(projections);center=(lo+hi)/2;half=(hi-lo)/2
        else:
            center=sum((a-b)*d for a,b,d in zip(pose['xyz_m'],grasp['xyz_m'],axis))
            half=0
            for i,size in enumerate(shape['geometry']['size_m']):
                unit=[0,0,0];unit[i]=1
                direction=rotate_vector(pose['quaternion_xyzw'],unit)
                half+=abs(sum(a*b for a,b in zip(axis,direction)))*size/2
        projected[side]={'center_m':center,'half_extent_m':half,'inner_surface_m':center+(half if side=='left' else -half),
            'world_pose':pose,'collision':part}
    return {'gap_m':projected['right']['inner_surface_m']-projected['left']['inner_surface_m'],
            'grasp_pose':grasp,'pads':projected}


def run(output, plugins):
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    from gz.msgs10.contacts_pb2 import Contacts
    from gz.msgs10.entity_factory_pb2 import EntityFactory
    from gz.msgs10.boolean_pb2 import Boolean
    data=json.loads((output/'profile.json').read_text());protocol=json.loads((output/'protocol.json').read_text())
    pad_vertices={}
    mesh_shapes=[]
    for side,part in (('left','part_113_bounds'),('right','part_114_bounds')):
        link=next(l for l in data['links'] if l['name']==f'gripper_{side}_jaw')
        shape=next(s for s in link['collisions'] if s['name']==part)
        if shape['geometry']['type']=='mesh':mesh_shapes.append((side,shape))
    if mesh_shapes:
        from uchuva_gazebo.robot_mesh_geometry import MeshRepository
        repository=MeshRepository(json.loads((output/'provenance.json').read_text())['asset_root'],[s for _,s in mesh_shapes])
        for side,shape in mesh_shapes:
            geometry=shape['geometry'];pad_vertices[side]=repository.meshes[(geometry['uri'],geometry['sha256'])].vertices
    contact_test=protocol.get('contact_test',False)
    transport=Node();records={name:[] for name in ('poses','joints','gear','contacts','commands','states','events','transitions','force_control')};errors=[];mutex=threading.Lock()
    phase={'name':'opening','target':protocol['open_reference_rad'],'contact_times':{},'spawned':False,'armed':False,'cut':False,'held_since':None,
           'close_started':None,'close_initial_q':None,'open_stable_since':None,'contact_hold_reference':None}
    snapshots={}
    driver=next(iter(data['control']['gripper']));command=transport.advertise(data['namespace']+'/gripper/'+driver+'/cmd_pos',Double)
    def poses_callback(msg):
        stamps=[p.header.stamp.sec+p.header.stamp.nsec*1e-9 for p in msg.pose]
        if not stamps:return
        row={'sim_time':stamps[0],'poses':{p.name.rsplit('::',1)[-1]:{'xyz_m':[p.position.x,p.position.y,p.position.z],
            'quaternion_xyzw':[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]} for p in msg.pose}}
        row['jaw_geometry']=jaw_gap(data,row['poses'],pad_vertices)
        with mutex:records['poses'].append(row)
    def joints_callback(msg):
        row=json.loads(msg.data);t=row['sim_time']
        if contact_test:
            rate=protocol['actuator_command_ramp_rad_s']
            target=min(protocol['open_reference_rad'],rate*t) if phase['close_started'] is None else max(0,phase['close_initial_q']-rate*(t-phase['close_started']))
            if phase['contact_hold_reference'] is not None:target=phase['contact_hold_reference']
        else:target=next(step['position_rad'] for step in reversed(protocol['position_schedule']) if step['start_s']<=t)
        message=Double();message.data=target;command.publish(message)
        with mutex:records['joints'].append(row);records['commands'].append({'sim_time':t,'position_rad':target,
            'joint':driver,'kind':'gripper_position','phase':phase['name'],'passive_joints_commanded':False})
    def gear_callback(msg):
        with mutex:records['gear'].append(json.loads(msg.data))
    def force_callback(msg):
        with mutex:records['force_control'].append(json.loads(msg.data))
    def contacts_callback(msg,side):
        # Protobuf JSON preserves the native collision names, positions,
        # depths and contact wrenches without interpreting them as grasp force.
        from google.protobuf.json_format import MessageToDict
        row=MessageToDict(msg,preserving_proto_field_name=True)
        now=records['joints'][-1]['sim_time'] if records['joints'] else 0
        hits=[]
        for contact in row.get('contact',[]):
            names=[contact.get(k,{}).get('name','') for k in ('collision1','collision2')]
            if any('fruit_fixture' in name for name in names):hits.append(contact)
        with mutex:
            records['contacts'].append({'side':side,'observation_sim_time':now,'native_message':row,'fixture_contact':bool(hits)})
            if hits:phase['contact_times'][side]=now
    def state_callback(msg):
        with mutex:records['states'].append(json.loads(msg.data))
    def event_callback(msg):
        with mutex:records['events'].append(json.loads(msg.data))
    topics=[(Pose_V,'/probe/cad_gripper_poses',poses_callback),
            (StringMsg,data['namespace']+'/robot_telemetry',joints_callback),
            (StringMsg,data['namespace']+'/gear_couplings/'+data['gear_couplings'][0]['name'],gear_callback),
            (Contacts,'/probe/cad_left_contacts',lambda msg:contacts_callback(msg,'left')),
            (Contacts,'/probe/cad_right_contacts',lambda msg:contacts_callback(msg,'right')),
            (StringMsg,'/harvest/state',state_callback),(StringMsg,'/harvest/events',event_callback)]
    if data['control']['gripper'][driver].get('reference_mode')=='ramped_position':
        topics.append((StringMsg,data['namespace']+'/gripper/'+driver+'/force_control_state/v1',force_callback))
    for typ,topic,callback in topics:
        if not transport.subscribe(typ,topic,callback):raise RuntimeError('Subscription failed '+topic)
    harvest_command=transport.advertise('/harvest/command',StringMsg)
    with (output/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-v','4','-s','-r','--iterations',
            str(round(protocol['duration_s']/protocol['step_s'])+protocol['final_observation_guard_steps']),str(output/'probe.sdf')],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            if not contact_test:code=process.wait(timeout=300)
            else:
                deadline=time.monotonic()+300
                while process.poll() is None:
                    if time.monotonic()>deadline:raise subprocess.TimeoutExpired(process.args,300)
                    now=records['joints'][-1]['sim_time'] if records['joints'] else 0
                    latest=records['poses'][-1] if records['poses'] else None
                    moving=max((abs(j['velocity']) for j in records['joints'][-1]['joints'] if j['velocity_available']),default=math.inf) if records['joints'] else math.inf
                    if latest and now>.7 and latest['jaw_geometry']['gap_m']>2*protocol['fixture']['pedicel_radius_m'] and moving<.05:
                        if phase['open_stable_since'] is None:phase['open_stable_since']=now
                    else:phase['open_stable_since']=None
                    if phase['open_stable_since'] is not None and now-phase['open_stable_since']>=.15 and not phase['spawned']:
                        sdf_text=fruit_fixture(latest['jaw_geometry']['grasp_pose'],protocol['fixture']['pedicel_radius_m']);(output/'spawned_fruit.sdf').write_text(sdf_text)
                        ok,response=transport.request('/world/cad_gripper_bench/create',EntityFactory(sdf=sdf_text),EntityFactory,Boolean,5000)
                        if not ok or not response.data:raise RuntimeError('Initial fruit creation failed')
                        phase['spawned']=True;snapshots['open']={'joints':records['joints'][-1],'geometry':latest['jaw_geometry']}
                        records['transitions'].append({'sim_time':now,'phase':'created_fruit_after_opening','gap_m':latest['jaw_geometry']['gap_m']})
                    state=records['states'][-1] if records['states'] else {}
                    fruit=next((f for f in state.get('fruits',[]) if f['id']=='contact_fixture'),{})
                    if phase['spawned'] and state.get('ready') and phase['name']=='opening':
                        phase['name']='closing';phase['target']=0
                        phase['close_started']=now
                        phase['close_initial_q']=next(j['position'] for j in records['joints'][-1]['joints'] if j['name']==driver)
                        records['transitions'].append({'sim_time':now,'phase':'closing_on_pedicel'})
                    double_contact=all(side in phase['contact_times'] and now-phase['contact_times'][side]<.1 for side in ('left','right'))
                    if double_contact and not phase['armed']:
                        snapshots['contact']={'joints':records['joints'][-1],'geometry':latest['jaw_geometry'],'contact_times':dict(phase['contact_times'])}
                        harvest_command.publish(StringMsg(data='arm contact_fixture'));phase['armed']=True
                        phase['contact_hold_reference']=next(j['position'] for j in records['joints'][-1]['joints'] if j['name']==driver)
                        phase['name']='holding_after_two_contacts'
                        records['transitions'].append({'sim_time':now,'phase':'arm_after_both_native_contacts'})
                    if phase['armed'] and not phase['cut'] and fruit.get('stable_seconds',0)>=.25:
                        harvest_command.publish(StringMsg(data='cut contact_fixture'));phase['cut']=True
                        records['transitions'].append({'sim_time':now,'phase':'cut_after_stability_guard'})
                    if fruit.get('state')=='HELD':
                        if phase['held_since'] is None:phase['held_since']=now
                        if now-phase['held_since']>=.25 and 'held' not in snapshots:
                            snapshots['held']={'joints':records['joints'][-1],'geometry':latest['jaw_geometry'],'harvest_state':state}
                    if now>=protocol['duration_s']-.001:break
                    time.sleep(.02)
                code=process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
            errors.append('native_timeout')
        except Exception as error:
            errors.append(repr(error))
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            code=process.wait(timeout=8)
    time.sleep(.15)
    for _,topic,_ in topics:transport.unsubscribe(topic)
    for name,rows in records.items():(output/(name+'.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    plateaus=[]
    # The contact phase is event-driven; its commands do not follow the
    # separate opening-scan schedule. Do not label contact observations with
    # positions that were never commanded in that run.
    for step in ([] if contact_test else protocol['position_schedule']):
        end=next((s['start_s'] for s in protocol['position_schedule'] if s['start_s']>step['start_s']),protocol['duration_s'])
        qrows=[r for r in records['joints'] if end-.3<=r['sim_time']<end]
        prows=[r for r in records['poses'] if end-.3<=r['sim_time']<end]
        if not qrows or not prows:continue
        joint_positions={j['name']:j['position'] for j in qrows[-1]['joints'] if j['position_available']}
        plateaus.append({'command_rad':step['position_rad'],'sim_time':qrows[-1]['sim_time'],
            'all_gripper_positions_rad':joint_positions,'gap_min_m':min(r['jaw_geometry']['gap_m'] for r in prows),
            'gap_max_m':max(r['jaw_geometry']['gap_m'] for r in prows),'last_jaw_geometry':prows[-1]['jaw_geometry'],
            'max_abs_velocity_rad_s':max(abs(j['velocity']) for r in qrows for j in r['joints'] if j['velocity_available'])})
    gear_errors=[abs(r['error_rad']) for r in records['gear'] if r['sim_time']>=.2]
    closure_distances=[]
    for row in records['poses']:
        if row['sim_time']<.2:continue
        for closure in data['closures']:
            if closure['body'] in row['poses']:
                closure_distances.append(math.dist(row['poses'][closure['body']]['xyz_m'],row['poses'][closure['auxiliary']]['xyz_m']))
    mechanism_ok=(bool(gear_errors) and max(gear_errors)<=protocol['maximum_gear_error_rad'] and
                  bool(closure_distances) and max(closure_distances)<=protocol['maximum_closure_residual_m'])
    from types import SimpleNamespace
    from uchuva_gazebo.robot_mechanism_validation import audit_mechanism_sample,audit_passive_gear_commands
    bench_data={**data,'closures':[row for row in data['closures'] if row['body'].startswith('gripper_')]}
    view=SimpleNamespace(to_dict=lambda:bench_data)
    native_robot=ResolvedRobot(data,canonical_hash(data));native_steps={};mechanism_errors=[];orientation_max=0.
    for row in records['joints']:
        key=round(row['commanded_before_step_time']*1e9)
        if key in native_steps:mechanism_errors.append('Duplicate native physics step')
        native_steps[key]=row
        try:mechanism_errors.extend(audit_passive_gear_commands(native_robot,row)['failures'])
        except (KeyError,ValueError) as error:mechanism_errors.append(str(error))
    for row in records['poses']:
        state=native_steps.get(round(row['sim_time']*1e9))
        if state is None:mechanism_errors.append('Missing exact native joint/pose step');continue
        try:
            audit=audit_mechanism_sample(view,{j['name']:j['position'] for j in state['joints'] if j['position_available']},row['poses'])
            mechanism_errors.extend(audit['failures'])
            orientation_max=max(orientation_max,max(c['orientation_error_rad'] for c in audit['closures']))
        except (KeyError,ValueError) as error:mechanism_errors.append(str(error))
    mechanism_ok &= not mechanism_errors
    bounds={joint['name']:joint['limits'] for joint in data['joints'] if joint['name'].startswith('gripper_')}
    velocity_maxima={};position_ranges={};joint_limits_ok=bool(records['joints'])
    for row in records['joints']:
        for joint in row['joints']:
            name=joint['name']
            if not joint.get('position_available') or not joint.get('velocity_available'):
                joint_limits_ok=False;continue
            position,velocity=joint['position'],joint['velocity'];limit=bounds[name]
            if not math.isfinite(position) or not math.isfinite(velocity):
                joint_limits_ok=False;continue
            maximum=joint.get('max_abs_velocity_window')
            if not isinstance(maximum,(int,float)) or not math.isfinite(maximum):joint_limits_ok=False;continue
            velocity_maxima[name]=max(velocity_maxima.get(name,0),abs(velocity),maximum)
            previous=position_ranges.get(name,[position,position])
            position_ranges[name]=[min(previous[0],position),max(previous[1],position)]
            joint_limits_ok &= (limit['lower']-1e-9<=position<=limit['upper']+1e-9 and maximum<=limit['velocity']+1e-9)
    fruit_states=[(row['sim_time'],fruit) for row in records['states'] for fruit in row.get('fruits',[])
                  if fruit['id']=='contact_fixture' and fruit.get('position') is not None]
    transfer_jumps=[math.dist(a[1]['position'],b[1]['position']) for a,b in zip(fruit_states,fruit_states[1:])
                    if a[1]['state']!='HELD' and b[1]['state']=='HELD']
    held_errors=[f['constraint_error_m'] for _,f in fruit_states if f['state']=='HELD' and f.get('constraint_error_m') is not None]
    double_attachment=any(f.get('joint_present') and f.get('removal_pending') for _,f in fruit_states)
    latch_ok=(bool(transfer_jumps) and max(transfer_jumps)<=protocol['maximum_latch_jump_m'] and
              bool(held_errors) and max(held_errors)<=protocol['maximum_closure_residual_m'] and not double_attachment)
    native_log=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',(output/'native.log').read_text(errors='replace'))
    detectors=re.findall(r'Using \[([^]]+)\] collision detector',native_log)
    if detectors!=[protocol['collision_detector']]:errors.append('Native collision detector identity mismatch')
    from uchuva_gazebo.robot_control_validation import evaluate_position_force_control
    force_audit=[]
    if records['poses']:
        manifest={'robot_config':data,'robot_spec_sha256':canonical_hash(data),'robot_task':{'acceptance':{
            'max_telemetry_gap_s':.02,'joint_position_tolerance_rad':.01,
            'joint_velocity_tolerance_rad_s':0,'effort_tolerance_nm':1e-6,'orientation_state_max_age_s':.02}}}
        force_audit=evaluate_position_force_control(manifest,records['force_control'],records['joints'],
            [{'ready':True,'sim_time':records['poses'][0]['sim_time']},
             {'ready':True,'sim_time':records['poses'][-1]['sim_time']}])
        if any(not row['passed'] for row in force_audit):errors.append('Independent native force audit failed')
    if contact_test:
        passed=bool(snapshots.get('held')) and bool(snapshots.get('contact')) and not errors and code==0 and mechanism_ok and joint_limits_ok and latch_ok
    else:passed=code==0 and bool(plateaus) and not errors
    result={'status':('PASS' if contact_test else 'OBSERVED') if passed else 'FAIL','native_exit_code':code,'errors':errors,
        'scope':'Isolated CAD gripper; native pedicel contact and ideal latch compatibility only' if contact_test else 'Isolated CAD gripper opening scan, wrist physically fixed; no fruit, latch or whole-robot stability acceptance',
        'snapshots':snapshots,'contact_test':contact_test,
        'native_observed_collision_detectors':detectors,'independent_force_audit':force_audit,
        'mechanism_within_frozen_criteria':mechanism_ok,'maximum_gear_error_rad':max(gear_errors,default=None),
        'maximum_auxiliary_translation_residual_m':max(closure_distances,default=None),
        'maximum_auxiliary_rotation_residual_rad':orientation_max,'independent_mechanism_errors':sorted(set(mechanism_errors)),
        'joint_limits_within_declared_bounds':joint_limits_ok,
        'maximum_joint_velocities_rad_s':velocity_maxima,'joint_position_ranges_rad':position_ranges,
        'maximum_latch_transition_position_jump_m':max(transfer_jumps,default=None),
        'maximum_held_constraint_error_m':max(held_errors,default=None),
        'simultaneous_attachment_and_pending_removal_observed':double_attachment,
        'latch_compatibility_within_criteria':latch_ok if contact_test else None,
        'plateaus':plateaus,'sample_counts':{k:len(v) for k,v in records.items()},
        'files_sha256':{p.name:sha(p) for p in output.iterdir() if p.is_file()}}
    dump(output/'result.json',result);print(json.dumps({'status':result['status'],'plateaus':[
        {'command':r['command_rad'],'gap_m':[r['gap_min_m'],r['gap_max_m']],'velocity':r['max_abs_velocity_rad_s']} for r in plateaus]}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--asset-root',type=Path,required=True);parser.add_argument('--plugin-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--contact-test',action='store_true')
    parser.add_argument('--open-reference-rad',type=float,required=True,
        help='Explicit bench reference within declared profile limits; above .06 requires revised CAD clearance evidence')
    parser.add_argument('--opening-clearance-evidence',type=Path)
    args=parser.parse_args()
    if not math.isfinite(args.open_reference_rad) or args.open_reference_rad<=0:
        parser.error('Opening must be explicit, positive and finite')
    if args.open_reference_rad>.06 and args.opening_clearance_evidence is None:
        parser.error('Original CAD interferes above .07; opening above .06 requires explicit revised-CAD clearance evidence')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    data=load_robot_json(args.profile);robot=ResolvedRobot(data,canonical_hash(data));verify_robot_assets(robot,args.asset_root)
    driver=next(iter(data['control']['gripper']));bound=next(j['limits'] for j in data['joints'] if j['name']==driver)
    if args.open_reference_rad>bound['upper']:raise ValueError('Opening exceeds declared profile limits')
    if args.opening_clearance_evidence:
        clearance=json.loads(args.opening_clearance_evidence.read_text())
        if not isinstance(clearance,dict):raise ValueError('Clearance evidence must be a structured report')
        verify_opening_clearance(data,args.open_reference_rad,clearance)
        # Preserve the exact certificate; this probe does not recompute BRep.
        shutil.copyfile(args.opening_clearance_evidence,output/'opening_clearance_evidence.json')
    dump(output/'profile.json',data)
    dump(output/'protocol.json',{'duration_s':3.5 if args.contact_test else 5.3,'step_s':.0001,'solver':'pgs','maximum_closure_residual_m':.0005,
        'collision_detector':data.get('physics',{}).get('collision_detector','ode'),'final_observation_guard_steps':1,
        'maximum_gear_error_rad':.001,'maximum_latch_jump_m':.0005,
        'maximum_closure_rotation_residual_rad':.001,
        'actuator_command_ramp_rad_s':.2,'open_reference_rad':args.open_reference_rad,
        'opening_scope':'Explicit profile/CAD revision bench path, not a calibrated hardware range',
        'opening_clearance_evidence_sha256':sha(args.opening_clearance_evidence) if args.opening_clearance_evidence else None,
        'contact_hold_policy':'After native contact at both pads, hold the measured driver coordinate using the same single force controller; never command passive joints.',
        'position_schedule':[{'start_s':t,'position_rad':q} for t,q in
            [(0,0),(.5,args.open_reference_rad/2),(1.7,args.open_reference_rad),(2.9,args.open_reference_rad/2),(4.1,0)]],
        'contact_test':args.contact_test,'fixture':{'pedicel_radius_m':.0018,'berry_radius_m':.016,'mass_kg':.006,
            'berry_center_below_grasp_m':.03,'cut_plane_above_grasp_m':.003,
            'pedicel_dimension_source':'Frozen V8 target proxy radius 0.018 source units / 10 source units per metre = 0.0018 m; isolated collision witness only.',
            'parameter_status':'pedicel_radius_from_V8_proxy; other fixture values engineering_heuristic; not an actual detached crop pedicel'},
        'scope':'Two native pad contacts before arming; retain rigid latch semantics; no grasp-force or cutting-force validation' if args.contact_test else 'Opening scan; endpoint/settling evidence recorded without claiming contact or latch validation'})
    model=build_world(robot,args.asset_root.resolve(),args.contact_test);(output/'probe.sdf').write_text(ET.tostring(model,encoding='unicode')+'\n')
    check=subprocess.run(['gz','sdf','-k',str(output/'probe.sdf')],capture_output=True,text=True)
    (output/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise RuntimeError('Invalid SDF')
    plugins=output/'plugins';plugins.mkdir();source=args.plugin_dir.resolve();build=json.loads((source/'build_provenance.json').read_text())
    systems=['HarvestSystem','RobotTelemetrySystem','ClosedLoopSystem','GearCouplingSystem']
    if data['control']['gripper'][driver].get('reference_mode')=='ramped_position':
        systems.append('JointPositionForceSystem')
        if sha(REPO/'gazebo/harvest_system/PositionForceController.hh')!=build['source_sha256']['PositionForceController.hh']:
            raise ValueError('Stale force-controller helper')
    for name in systems:
        library='libUchuva'+name+'.so'
        if sha(source/library)!=build['libraries_sha256'][library] or sha(REPO/'gazebo/harvest_system'/(name+'.cc'))!=build['source_sha256'][name+'.cc']:
            raise ValueError('Stale plugin '+name)
        shutil.copyfile(source/library,plugins/library)
    shutil.copyfile(source/'build_provenance.json',plugins/'build_provenance.json')
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    dump(output/'provenance.json',{'script_sha256':sha(__file__),'profile_sha256':sha(args.profile),'canonical_robot_sha256':robot.sha256,
        'build_provenance_sha256':sha(source/'build_provenance.json'),'asset_root':str(args.asset_root.resolve())})
    os.environ['GZ_PARTITION']='cad-gripper-'+uuid.uuid4().hex;os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)
    run(output,plugins);return 0


if __name__=='__main__':raise SystemExit(main())
