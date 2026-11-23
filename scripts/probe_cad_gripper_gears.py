#!/usr/bin/env python3
"""Two native CAD four-bars, one effort-limited motor, passive gear coupling.

The finite torsional stiffness/damping are explicit engineering probe values.
This is not an ideal gear constraint, tooth contact, or hardware calibration.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import probe_cad_gripper_loop as single
from probe_cad_suspension_loop import node, dump, sha
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.closed_loops import adapt_loop_joint
from uchuva_gazebo.robot_kinematics import transform_point


def world(config, coupled):
    root = ET.fromstring(single.world(config['positive'], True))
    model = root.find('world/model')
    for plugin in model.findall('plugin'):
        model.remove(plugin)
    for side in ('positive', 'negative'):
        other = ET.fromstring(single.world(config[side], True)).find('world/model')
        source = model if side == 'positive' else other
        for link in source.findall('link'):
            if link.get('name') == 'housing':
                continue
            link.set('name', side+'_'+link.get('name'))
            if side == 'negative':
                model.append(link)
        for joint in source.findall('joint'):
            if joint.get('name') == 'anchor':
                continue
            joint.set('name', side+'_'+joint.get('name'))
            for tag in ('parent','child'):
                if joint.findtext(tag) != 'housing':
                    joint.find(tag).text = side+'_'+joint.findtext(tag)
            if side == 'negative':
                model.append(joint)
        adapt_loop_joint(model, side+'_gripper_closure')
    root.find('world/physics/max_step_size').text = str(config['step_s'])
    if config.get('solver'):
        node(node(node(root.find('world/physics'),'dart'),'solver'),'solver_type',config['solver'])
    model.find('pose').text = '0 0 1 ' + ' '.join(str(x) for x in config.get('model_rotation_rpy',[0,0,0]))
    # One real motor on the CAD servo-driven negative-X gear only.
    controller = node(model,'plugin',filename='gz-sim-joint-position-controller-system',
        name='gz::sim::systems::JointPositionController')
    for tag,value in (('joint_name','negative_drive_pivot'),('initial_position',0),
        ('topic','/probe/gripper_drive_reference'),('use_velocity_commands','false'),
        ('p_gain',.2),('i_gain',0),('d_gain',.01),('cmd_min',-.02),('cmd_max',.02)):
        node(controller,tag,value)
    publisher = node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for tag,value in (('publish_link_pose','true'),('publish_model_pose','false'),
        ('use_pose_vector_msg','true'),('static_publisher','false'),('update_frequency',100),('topic','/probe/gear_poses')):
        node(publisher,tag,value)
    observer = node(model,'plugin',filename='libUchuvaRobotTelemetrySystem.so',name='uchuva::RobotTelemetrySystem')
    node(observer,'robot_spec_sha256',config['fixture_sha256']);node(observer,'topic','/probe/gear_joints')
    for side in ('positive','negative'):
        for name in ('rocker_pivot','drive_pivot','crank_coupler','gripper_closure'):
            row = node(observer,'joint',name=side+'_'+name)
            node(row,'effort_limit', .02 if side=='negative' and name=='drive_pivot' else 0)
    if coupled:
        gear = node(model,'plugin',filename='libUchuvaGearCouplingSystem.so',name='uchuva::GearCouplingSystem')
        for tag,value in config['coupling'].items():
            node(gear,tag,value)
        node(gear,'robot_spec_sha256',config['fixture_sha256']);node(gear,'topic','/probe/gear_reactions')
    ET.indent(root,space='  ')
    return ET.tostring(root,encoding='unicode')+'\n'


def run_case(output, plugins, case):
    config=json.loads((output/'fixture.json').read_text())
    protocol=json.loads((output/'protocol.json').read_text())
    directory=output/case;directory.mkdir();coupled=case=='coupled'
    sdf=directory/'probe.sdf';sdf.write_text(world(config,coupled))
    check=subprocess.run(['gz','sdf','-k',str(sdf)],capture_output=True,text=True)
    (directory/'sdf_check.log').write_text(check.stdout+check.stderr)
    os.environ['GZ_PARTITION']='uchuva-gears-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    transport=Node();poses=[];joints=[];reactions=[];errors=[];commands=[];lock=threading.Lock()
    command=transport.advertise('/probe/gripper_drive_reference',Double)
    def observe_poses(message):
        stamps=[p.header.stamp.sec+p.header.stamp.nsec*1e-9 for p in message.pose]
        if not stamps or max(stamps)-min(stamps)>1e-9:
            errors.append('Missing/inconsistent pose timestamp');return
        with lock:
            poses.append({'sim_time':stamps[0],'poses':{p.name.rsplit('::',1)[-1]:{
                'xyz_m':[p.position.x,p.position.y,p.position.z],
                'quaternion_xyzw':[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]} for p in message.pose}})
    def observe_joints(message):
        row=json.loads(message.data)
        if row['robot_spec_sha256'] != config['fixture_sha256']:
            errors.append('Wrong fixture hash');return
        t=row['sim_time'];target=0 if t<.5 else .1 if t<1.2 else -.1
        msg=Double();msg.data=target;command.publish(msg)
        with lock:joints.append(row);commands.append({'sim_time':t,'position_rad':target})
    def observe_reactions(message):
        row=json.loads(message.data)
        if row['robot_spec_sha256'] != config['fixture_sha256']:
            errors.append('Wrong coupling hash');return
        with lock:reactions.append(row)
    for msg,topic,callback in ((Pose_V,'/probe/gear_poses',observe_poses),
        (StringMsg,'/probe/gear_joints',observe_joints),(StringMsg,'/probe/gear_reactions',observe_reactions)):
        if not transport.subscribe(msg,topic,callback):raise RuntimeError('Native subscription failed')
    with (directory/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-s','-r','--iterations',
            str(round(2/config['step_s'])),str(sdf)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
            errors.append('native_timeout')
    time.sleep(.15)
    for topic in ('/probe/gear_poses','/probe/gear_joints','/probe/gear_reactions'):transport.unsubscribe(topic)
    for name,rows in (('poses',poses),('joints',joints),('reactions',reactions),('commands',commands)):
        (directory/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in rows))
    names=[side+'_'+name for side in ('positive','negative') for name in
           ('rocker_pivot','drive_pivot','crank_coupler','gripper_closure')]
    observed=[row for row in joints if row['sim_time']>=protocol['observe_from_s'] and all(
        any(j['name']==name and j['position_available'] and j['velocity_available'] and j['wrench_available']
            for j in row['joints']) for name in names)]
    error=[];positions={side:[] for side in ('positive','negative')}
    for row in observed:
        q={j['name']:j['position'] for j in row['joints']}
        error.append(abs(q['positive_drive_pivot']-config['coupling']['ratio']*q['negative_drive_pivot']))
        for side in positions:positions[side].append(q[side+'_drive_pivot'])
    residuals={side:[] for side in ('positive','negative')};welds=[];weld_angles=[]
    for row in poses:
        if row['sim_time']<protocol['observe_from_s']:continue
        for side in residuals:
            points=config[side]['axis_points_cad_m'];offset=[d-a for a,d in zip(points['A'],points['D'])]
            rocker=row['poses'][side+'_short_rocker'];coupler=row['poses'][side+'_coupler']
            residuals[side].append(math.dist(transform_point(rocker,offset),coupler['xyz_m']))
            aux=row['poses'][side+'_short_rocker__closure_'+side+'_gripper_closure']
            welds.append(math.dist(rocker['xyz_m'],aux['xyz_m']))
            dot=abs(sum(a*b for a,b in zip(rocker['quaternion_xyzw'],aux['quaternion_xyzw'])))
            weld_angles.append(2*math.acos(min(1.,dot)))
    excursions={side:max(values)-min(values) if values else None for side,values in positions.items()}
    maxima={side:max(values,default=None) for side,values in residuals.items()}
    reaction_rows=[r for r in reactions if r['sim_time']>=protocol['observe_from_s']]
    balance=max((abs(r['constraint_power_w']+r['elastic_energy_rate_w']+r['dissipation_w'])
                 for r in reaction_rows),default=None)
    torque=max((abs(r['follower_constraint_torque_nm']) for r in reaction_rows),default=None)
    motor_commands=[abs(j['force_command']) for row in observed for j in row['joints']
                    if j['name']=='negative_drive_pivot' and j['force_command_available']]
    follower_commands=[abs(j['force_command']) for row in observed for j in row['joints']
                       if j['name']=='positive_drive_pivot' and j['force_command_available']]
    separate_motor=(bool(motor_commands) and max(motor_commands)<=protocol['maximum_motor_command_nm']+1e-12
                    and max(follower_commands,default=0)<=1e-12)
    log_text=(directory/'native.log').read_text(errors='replace')
    physical=(code==0 and check.returncode==0 and not errors and
        'already has a parent' not in log_text and 'GearCouplingSystem:' not in log_text and
        len(observed)>=protocol['minimum_samples'] and all(
            value is not None and value<=protocol['maximum_closure_residual_m'] for value in maxima.values()) and
        bool(welds) and max(welds)<=protocol['maximum_closure_residual_m'] and
        max(weld_angles)<=protocol['maximum_auxiliary_rotation_residual_rad'] and
        excursions['negative'] is not None and excursions['negative']>=protocol['minimum_drive_excursion_rad'])
    gear_pass=(bool(error) and max(error)<=protocol['maximum_gear_error_rad'] and
        excursions['positive'] is not None and excursions['positive']>=protocol['minimum_drive_excursion_rad'] and
        len(reaction_rows)>=protocol['minimum_samples'] and balance is not None and balance<1e-10 and
        torque is not None and torque>1e-5 and separate_motor and
        all(r.get('application')=='internal_link_torque_pairs' for r in reaction_rows))
    negative_pass=bool(error) and max(error)>protocol['minimum_disconnected_error_rad'] and not reactions
    result={'status':'PASS' if physical and (gear_pass if coupled else negative_pass) else 'FAIL',
        'case':case,'native_exit_code':code,'sdf_check_code':check.returncode,'errors':errors,
        'all_eight_joint_observations':len(observed),'physical_loops_pass':physical,
        'maximum_pin_residuals_m':maxima,'maximum_auxiliary_translation_residual_m':max(welds,default=None),
        'maximum_auxiliary_rotation_residual_rad':max(weld_angles,default=None),
        'maximum_gear_error_rad':max(error,default=None),'drive_excursions_rad':excursions,
        'passive_coupling_torque_observed_max_nm':torque,'constraint_power_balance_residual_w':balance,
        'maximum_motor_joint_force_command_nm':max(motor_commands,default=None),
        'maximum_follower_joint_force_command_nm':max(follower_commands,default=None),
        'single_motor_separate_from_passive_link_reactions':separate_motor,
        'coupled_gear_criteria_pass':gear_pass if coupled else None,
        'disconnected_negative_control_pass':negative_pass if not coupled else None,
        'files_sha256':{p.name:sha(p) for p in directory.iterdir() if p.is_file()}}
    dump(directory/'result.json',result);print(case,result['status'],max(error,default=None),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--plugin-dir',type=Path,required=True)
    parser.add_argument('--positive-fixture',type=Path,default=REPO/'outputs/real_harvester_validation/gripper_loop_02/fixture.json')
    parser.add_argument('--inventory',type=Path,default=REPO/'outputs/real_harvester_cad/inventory_full_01/cad_inventory.json')
    parser.add_argument('--motion-inventory',type=Path,default=REPO/'outputs/real_harvester_cad/inventory_motion_01/cad_inventory.json')
    parser.add_argument('--case',choices=['coupled','disconnected_control'])
    parser.add_argument('--model-rotation-rpy',type=float,nargs=3,default=[0,0,0])
    parser.add_argument('--solver',choices=['dantzig','pgs'],default='dantzig')
    args=parser.parse_args();output=args.output.resolve();plugins=args.plugin_dir.resolve()
    if args.case:run_case(output,plugins,args.case);return 0
    positive=json.loads(args.positive_fixture.read_text());negative=deepcopy(positive)
    inventory=json.loads(args.inventory.read_text(encoding='utf-8-sig'))
    doc=next(d for d in inventory['documents'] if d['source_path']=='gripper/Gripper ensamble.iam')
    rows={r['name']:r for r in doc['relations']}
    refs={'A':'Coincidencia:9','B':'Coincidencia:7','C':'Coincidencia:23','D':'Coincidencia:13'}
    negative['axis_evidence']={}
    for label,name in refs.items():
        geometry=rows[name]['EntityOne'];point=geometry['BasePoint_m'];axis=geometry['AxisVector']
        if abs(abs(axis[1])-1)>1e-8 or abs(axis[0])+abs(axis[2])>1e-8:raise ValueError('Nonparallel CAD hinge')
        negative['axis_points_cad_m'][label]=[point[0],0,point[2]]
        negative['axis_evidence'][label]={'constraint':name,'entity':'EntityOne','geometry':geometry}
    motion=json.loads(args.motion_inventory.read_text(encoding='utf-8-sig'))
    motion_doc=next(d for d in motion['documents'] if d['source_path']==doc['source_path'])
    relation=next(r for r in motion_doc['relations'] if r['name'].startswith('Rotaci'))
    if motion_doc['sha256']!=doc['sha256'] or relation['parameters']['Ratio']['si_value']!=1 or relation['ForwardDirection'] is not False:
        raise ValueError('CAD gear evidence differs from declared 1:1 reverse relation')
    config={'positive':positive,'negative':negative,'step_s':.0001,
        'model_rotation_rpy':args.model_rotation_rpy,
        'solver':args.solver,
        'coupling':{'driver':'negative_drive_pivot','follower':'positive_drive_pivot','ratio':-1,'offset':0,
            'stiffness_nm_rad':100,'damping_nms_rad':.03,'maximum_step_s':.0001},
        'parameter_status':'finite_torsional_compliance_engineering_heuristic_not_measured_hardware',
        'gear_evidence':relation,'motion_inventory_sha256':sha(args.motion_inventory),
        'inventory_sha256':sha(args.inventory),'fixture_source_sha256':sha(args.positive_fixture),
        'axis_sign_convention':'Both Gazebo hinges use common CAD +Y; reverse external gears use q_positive=-q_negative.'}
    config['fixture_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True,exist_ok=False);dump(output/'fixture.json',config)
    dump(output/'protocol.json',{'observe_from_s':.2,'minimum_samples':100,'maximum_closure_residual_m':.0005,
        'maximum_auxiliary_rotation_residual_rad':.001,'maximum_gear_error_rad':.001,
        'maximum_motor_command_nm':.02,
        'minimum_drive_excursion_rad':.02,'minimum_disconnected_error_rad':.005,
        'scope':'Both CAD loops retain original .5mm pin criterion; added strict .001rad coupling criterion frozen before execution.'})
    frozen=output/'plugins';frozen.mkdir();build=json.loads((plugins/'build_provenance.json').read_text())
    for name in ('RobotTelemetrySystem','ClosedLoopSystem','GearCouplingSystem'):
        library='libUchuva'+name+'.so'
        if sha(plugins/library)!=build['libraries_sha256'][library] or sha(REPO/'gazebo/harvest_system'/(name+'.cc'))!=build['source_sha256'][name+'.cc']:
            raise ValueError('Build source/binary identity mismatch')
        shutil_path=frozen/library;shutil_path.write_bytes((plugins/library).read_bytes())
    (frozen/'build_provenance.json').write_bytes((plugins/'build_provenance.json').read_bytes())
    for case in ('coupled','disconnected_control'):
        subprocess.run([sys.executable,__file__,'--output',str(output),'--plugin-dir',str(frozen),'--case',case],check=True)
    cases={case:json.loads((output/case/'result.json').read_text()) for case in ('coupled','disconnected_control')}
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    dump(output/'summary.json',{'status':'PASS' if all(r['status']=='PASS' for r in cases.values()) else 'FAIL',
        'script_sha256':sha(__file__),'fixture_sha256':sha(output/'fixture.json'),
        'build_provenance_sha256':sha(frozen/'build_provenance.json'),'cases':cases})
    return 0


if __name__=='__main__':raise SystemExit(main())
