#!/usr/bin/env python3
"""Native force-actuated prismatic guard fixture, not CAD grip-contact validation.

The fruit starts attached through HarvestSystem, transfers only after observed
jaw closure, and falls under gravity after observed reopening and release.
No pose/velocity writer, teleportation or switched gravity is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def read(path):return json.loads(Path(path).read_text())
def node(parent,tag,value=None,**attrs):
    result=ET.SubElement(parent,tag,attrs)
    if value is not None:result.text=str(value)
    return result


def protocol():
    return {'schema_version':'native-prismatic-jaw-guard-probe/1.0','dt_s':.0001,
        'duration_s':12.,'wall_timeout_s':100.,'gravity_m_s2':[0,0,-9.81],
        'scope':'Ideal latch state-machine guard only; simplified native actuator fixture, no CAD geometry or physical pad-contact claim',
        'jaw':{'joint_name':'jaw','joint_type':'prismatic','open_position':.005507998450615,
               'closed_position':0.,'position_tolerance':.0002,'max_speed':.001,'stable_time':.2},
        'actuator':{'p_gain':1000.,'i_gain':0.,'d_gain':1.,'i_min':0.,'i_max':0.,
            'cmd_min':-2.,'cmd_max':2.,'command_velocity':.005,'lower_limit':0.,'upper_limit':.006,
            'initial_position':0.},
        'fixture_mass_kg':.01,'fixture_inertia_kg_m2':1e-6,
        'fixture_parameters_status':'engineering_heuristic_for_plugin_contract_only',
        'expected_acknowledgments':[
            ['far','arm',False,'cut_point_out_of_range'],
            ['near','arm',False,'jaw_not_open'],
            ['near','arm',True,'armed_no_second_constraint_created'],
            ['near','cut',False,'jaw_not_closed'],
            ['near','cut',True,'plant_constraint_removal_requested'],
            ['near','release',False,'jaw_not_open'],
            ['near','release',True,'tool_constraint_removal_requested']],
        'minimum_free_fall_m':.02,'maximum_force_N':2.,
        'retention_position_error_m':.001}


def world(config,identity):
    sdf=ET.Element('sdf',version='1.10'); w=node(sdf,'world',name='jaw_guard_probe')
    node(w,'gravity','0 0 -9.81'); physics=node(w,'physics',name='step',type='ignored')
    node(physics,'max_step_size',config['dt_s']);node(physics,'real_time_factor',1)
    dart=node(physics,'dart');node(node(dart,'solver'),'solver_type','pgs');node(dart,'collision_detector','bullet')
    node(w,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    def link(model,name,pose=None):
        item=node(model,'link',name=name)
        if pose:node(item,'pose',pose)
        inertial=node(item,'inertial');node(inertial,'mass',config['fixture_mass_kg'])
        tensor=node(inertial,'inertia')
        for key in ('ixx','iyy','izz','ixy','ixz','iyz'):
            node(tensor,key,config['fixture_inertia_kg_m2'] if key in ('ixx','iyy','izz') else 0)
        return item
    ground=node(w,'model',name='ground');node(ground,'static','true')
    floor=link(ground,'floor','0 0 -.05 0 0 0');c=node(floor,'collision',name='floor')
    node(node(node(c,'geometry'),'box'),'size','3 3 .1')
    anchor=node(w,'model',name='plant');node(anchor,'static','true');link(anchor,'support')
    robot=node(w,'model',name='fixture');node(robot,'pose','0 0 .3 0 0 0')
    link(robot,'tool');link(robot,'jaw_link','.1 0 0 0 0 0')
    fixed=node(robot,'joint',name='fixture_mount',type='fixed');node(fixed,'parent','world');node(fixed,'child','tool')
    joint=node(robot,'joint',name='jaw',type='prismatic');node(joint,'parent','tool');node(joint,'child','jaw_link')
    axis=node(joint,'axis');node(axis,'xyz','1 0 0');limit=node(axis,'limit')
    for key,value in (('lower',0),('upper',.006),('effort',2),('velocity',.01)):node(limit,key,value)
    control=node(robot,'plugin',filename='libUchuvaJointPositionForceSystem.so',name='uchuva::JointPositionForceSystem')
    for key,value in {'joint_name':'jaw','topic':'/probe/jaw','state_topic':'/probe/force','robot_spec_sha256':identity,
                      'publish_rate':100,**config['actuator']}.items():node(control,key,value)
    observer=node(robot,'plugin',filename='libUchuvaRobotTelemetrySystem.so',name='uchuva::RobotTelemetrySystem')
    for key,value in (('robot_spec_sha256',identity),('topic','/probe/joints'),('publish_rate',10000)):node(observer,key,value)
    node(node(observer,'joint',name='jaw'),'effort_limit',2)
    for name,x in (('near',0),('far',.2)):
        fruit=node(w,'model',name=name);node(fruit,'pose',f'{x} 0 .3 0 0 0')
        body=link(fruit,'body');coll=node(body,'collision',name='fruit')
        node(node(node(coll,'geometry'),'sphere'),'radius',.008)
    harvest=node(w,'plugin',filename='libUchuvaHarvestSystem.so',name='uchuva::HarvestSystem')
    for key,value in (('robot_model','fixture'),('tool_link','tool'),('tcp_pose','0 0 0 0 0 0'),
            ('cut_pose','0 0 0 0 0 0'),('grasp_pose','0 0 0 0 0 0'),('cut_tolerance',.002),
            ('capture_radius',.03),('max_relative_speed',.02),('stable_time',.1),
            ('attachment_tolerance',.001),('command_topic','/probe/command'),
            ('event_topic','/probe/events'),('state_topic','/probe/state')):node(harvest,key,value)
    jaw=node(harvest,'jaw_guard')
    for key,value in config['jaw'].items():node(jaw,key,value)
    for name in ('near','far'):
        item=node(harvest,'fruit',id=name)
        for key,value in (('model',name),('link','body'),('parent_model','plant'),('parent_link','support'),('cut_point','0 0 0')):node(item,key,value)
    ET.indent(sdf,space='  ');return ET.tostring(sdf,encoding='unicode')+'\n'


def audit(run):
    config=read(run/'protocol.json');completion=read(run/'native_completion.json')
    records={name:[json.loads(line) for line in (run/(name+'.jsonl')).read_text().splitlines()] for name in ('states','events','joints','forces')}
    checks=[]
    def check(name,passed,**facts):checks.append({'name':name,'passed':bool(passed),**facts})
    check('native_completed',completion['native_exit_code']==0 and not completion['errors'],errors=completion['errors'])
    ack=[[e['id'],e['action'],e['accepted'],e['reason']] for e in records['events'] if e['phase']=='ack']
    check('native_state_machine_and_negative_guards',ack==config['expected_acknowledgments'],observed=ack)
    observed_by_iteration={row['iteration']:row for row in records['joints']};guard_errors=[]
    for event in records['events']:
        if event['phase']!='ack':continue
        guard=event['jaw_guard'];joint=observed_by_iteration.get(guard['observation_iteration'])
        if joint is None:guard_errors.append('Missing exact native jaw iteration');continue
        raw=joint['joints'][0]
        if abs(guard['position_m']-raw['position'])>1e-10 or abs(guard['velocity_m_s']-raw['velocity'])>1e-10:
            guard_errors.append('Guard state differs from independent native observation')
        if event['accepted']:
            opened=event['action'] in ('arm','release');target=config['jaw']['open_position' if opened else 'closed_position']
            if (not guard['available'] or abs(raw['position']-target)>config['jaw']['position_tolerance'] or
                abs(raw['velocity'])>config['jaw']['max_speed'] or
                guard['open_stable_seconds' if opened else 'closed_stable_seconds']+1e-10<config['jaw']['stable_time']):
                guard_errors.append('Accepted transition without observed settled jaw')
    check('accepted_guard_matches_native_joint_iteration',not guard_errors,errors=guard_errors)
    force_max=max((abs(r['joints'][0]['force_command']) for r in records['joints'] if r['joints'][0]['force_command_available']),default=math.inf)
    unit_ok=bool(records['forces']) and all(r.get('joint_type')=='prismatic' and r.get('position_unit')=='m' and r.get('force_unit')=='N' for r in records['forces'])
    check('native_force_and_prismatic_units',force_max<=config['maximum_force_N']+1e-12 and unit_ok,max_force_N=force_max if math.isfinite(force_max) else None)
    near=[(r,next(f for f in r['fruits'] if f['id']=='near')) for r in records['states'] if r['fruits']]
    held=[f for _,f in near if f['state']=='HELD'];released=[f for _,f in near if f['state']=='RELEASED']
    residuals=[f['constraint_error_m'] for f in held if f['constraint_error_m'] is not None]
    # The same creation iteration has no post-constraint residual yet; native
    # Physics must apply it in the next step before a residual is meaningful.
    check('ideal_retention_observed',bool(residuals) and all(f['joint_parent']=='tool' and f['joint_present'] for f in held) and
          len(held)-len(residuals)<=1 and max(residuals,default=math.inf)<=config['retention_position_error_m'])
    drop=max((.3-f['position'][2] for f in released),default=0.)
    check('opened_release_and_gravity_fall',bool(released) and all(not f['joint_present'] and f['joint_parent']=='none' for f in released) and drop>=config['minimum_free_fall_m'],maximum_fall_m=drop)
    provenance=read(run/'provenance.json')
    integrity=all(sha(run/path)==digest for path,digest in provenance['frozen_files_sha256'].items())
    check('frozen_fixture_and_native_binaries_unchanged',integrity)
    return {'status':'PASS' if all(row['passed'] for row in checks) else 'FAIL','scope':config['scope'],
        'checks':checks,'native_rerun':False,'source_auditor_sha256':sha(__file__),
        'raw_sha256':{name+'.jsonl':sha(run/(name+'.jsonl')) for name in records}}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plugin-dir',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--audit-run',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Fresh output path required')
    if args.audit_run:
        result=audit(args.audit_run.resolve());dump(args.output,result);print(json.dumps(result,indent=2));return int(result['status']!='PASS')
    if args.plugin_dir is None:parser.error('--plugin-dir required for native run')
    output=args.output.resolve();output.mkdir(parents=True);config=protocol();dump(output/'protocol.json',config)
    identity=sha(output/'protocol.json');build=read(args.plugin_dir/'build_provenance.json')
    for name,digest in build['source_sha256'].items():
        if sha(ROOT/'gazebo/harvest_system'/name)!=digest:raise ValueError('Native source/build mismatch: '+name)
    plugins=output/'plugins';plugins.mkdir()
    for name,digest in build['libraries_sha256'].items():
        if sha(args.plugin_dir/name)!=digest:raise ValueError('Native binary mismatch: '+name)
        shutil.copyfile(args.plugin_dir/name,plugins/name)
    shutil.copyfile(args.plugin_dir/'build_provenance.json',plugins/'build_provenance.json')
    (output/'runner_source.py').write_bytes(Path(__file__).read_bytes())
    (output/'world.sdf').write_text(world(config,identity))
    frozen={p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}
    dump(output/'provenance.json',{'frozen_files_sha256':frozen,'source_sha256':build['source_sha256'],'identity':identity})
    validation=subprocess.run(['gz','sdf','-k',str(output/'world.sdf')],capture_output=True,text=True)
    (output/'sdf_check.log').write_text(validation.stdout+validation.stderr)
    if validation.returncode:raise ValueError('Native SDF invalid')
    os.environ['GZ_PARTITION']='jaw-guard-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    transport=Node();lock=threading.Lock();records={name:[] for name in ('states','events','joints','forces')};errors=[]
    callbacks=[]
    for name,topic in (('states','state'),('events','events'),('joints','joints'),('forces','force')):
        def receive(message,key=name):
            try:
                row=json.loads(message.data)
                with lock:records[key].append(row)
            except Exception as error:errors.append(str(error))
        callbacks.append(receive)
        if not transport.subscribe(StringMsg,'/probe/'+topic,receive):raise RuntimeError('Subscribe failed')
    commands=transport.advertise('/probe/command',StringMsg);jaw=transport.advertise('/probe/jaw',Double)
    start=time.monotonic()
    with (output/'native.log').open('w') as logfile:
        process=subprocess.Popen(['gz','sim','--force-version','8','-s','-r','--iterations',str(round(config['duration_s']/config['dt_s'])),str(output/'world.sdf')],stdout=logfile,stderr=subprocess.STDOUT,cwd=output,start_new_session=True)
        def wait(predicate):
            while time.monotonic()-start<config['wall_timeout_s']:
                with lock:
                    if predicate():return
                if process.poll() is not None:raise RuntimeError('Native process exited before transitions completed')
                time.sleep(.005)
            raise TimeoutError('Fixture computational wall timeout')
        def state():return records['states'][-1] if records['states'] else {}
        def send(command):
            with lock:before=len(records['events'])
            message=StringMsg();message.data=command;commands.publish(message)
            wait(lambda:any(row['phase']=='ack' for row in records['events'][before:]))
        def target(value,opened):
            message=Double();message.data=value;jaw.publish(message)
            wait(lambda:state().get('jaw_guard',{}).get('open_ready' if opened else 'closed_ready',False))
        try:
            wait(lambda:state().get('ready') and state().get('jaw_guard',{}).get('closed_ready'))
            send('arm far');send('arm near')
            target(config['jaw']['open_position'],True);send('arm near');send('cut near')
            target(0.,False);send('cut near')
            wait(lambda:any(f['id']=='near' and f['state']=='HELD' for f in state().get('fruits',[])))
            send('release near');target(config['jaw']['open_position'],True);send('release near')
            code=process.wait(timeout=max(.1,config['wall_timeout_s']-(time.monotonic()-start)))
        except Exception as error:
            errors.append(type(error).__name__+': '+str(error))
            if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
    dump(output/'native_completion.json',{'native_exit_code':code,'native_wall_seconds':time.monotonic()-start,'errors':errors})
    for topic in ('state','events','joints','force'):transport.unsubscribe('/probe/'+topic)
    for name,values in records.items():(output/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in values))
    result=audit(output);dump(output/'result.json',result);print(json.dumps(result,indent=2));return int(result['status']!='PASS')


if __name__=='__main__':raise SystemExit(main())
