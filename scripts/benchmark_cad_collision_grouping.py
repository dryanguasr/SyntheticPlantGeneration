#!/usr/bin/env python3
"""Paired short native performance observation; no mobility/contact admission.

Both representations retain the complete robot, controls, gravity, ground,
initial pose and 100 us step. Only collision grouping/provenance may differ.
No state writer or command publisher is used: configured zero references hold.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
CODE_PATHS=[Path(__file__).resolve(), ROOT/'scripts/probe_cad_mobility.py',
            *sorted((ROOT/'src/uchuva_gazebo').glob('*.py')), ROOT/'configs/robots/robot_spec.schema.json']
CODE_BYTES={p:p.read_bytes() for p in CODE_PATHS}
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_sdf import resolved_robot_contract
from probe_cad_mobility import world, protocol


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def jsonlines(path,rows):Path(path).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))


def verify_pair(source, grouped, manifest):
    if source.sha256!=manifest['source_robot_spec_sha256'] or grouped.sha256!=manifest['robot_spec_sha256']:
        raise ValueError('Grouping manifest belongs to a different frozen profile')
    a,b=source.to_dict(),grouped.to_dict()
    reverse=copy.deepcopy(b);reverse['provenance']=a['provenance']
    for original,changed in zip(a['links'],reverse['links']):
        if original['name']!=changed['name']:raise ValueError('Link order changed')
        if original['name']=='arm_wrist_roll' or original['name'].startswith('gripper'):
            if changed!=original:raise ValueError('A protected link changed')
        original_primitives=[r for r in original['collisions'] if r['geometry']['type']!='mesh']
        changed_primitives=[r for r in changed['collisions'] if r['geometry']['type']!='mesh']
        if original_primitives!=changed_primitives:raise ValueError('A primitive changed')
        changed['collisions']=original['collisions']
    if reverse!=a:raise ValueError('Paired benchmark would change other physical parameters')
    if b.get('physics',{}).get('collision_detector')!='bullet':
        raise ValueError('This preregistered comparison requires Bullet')


def prepare_case(label, robot, asset_root, out, plugin_dir, build, config):
    out.mkdir()
    assets=verify_robot_assets(robot,asset_root)
    for uri,digest in assets.items():
        target=out/uri;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(asset_root/uri,target)
        if sha(target)!=digest:raise ValueError('Asset changed while snapshotting')
    plugins=out/'plugins';plugins.mkdir()
    for name,digest in build['libraries_sha256'].items():
        if Path(name).name!=name or sha(plugin_dir/name)!=digest:raise ValueError('Unverified native library')
        shutil.copyfile(plugin_dir/name,plugins/name)
    shutil.copyfile(plugin_dir/'build_provenance.json',plugins/'build_provenance.json')
    write(out/'robot_resolved.json',robot.to_dict())
    sdf=out/'world.sdf';sdf.write_text(world(robot,config))
    check=subprocess.run(['gz','sdf','-k',str(sdf)],capture_output=True,text=True)
    (out/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise ValueError('Native SDF rejected '+label)
    write(out/'provenance.json',{'robot_spec_sha256':robot.sha256,'assets_sha256':assets,
          'libraries_sha256':build['libraries_sha256'],'build_provenance_sha256':sha(plugins/'build_provenance.json'),
          'world_sha256':sha(sdf)})


def run_case(label, robot, out, iterations, wall_timeout):
    os.environ['GZ_PARTITION']='cad-grouping-benchmark-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(out/'plugins')
    os.environ['GZ_SIM_RESOURCE_PATH']=str(out)
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.world_stats_pb2 import WorldStatistics
    node=Node();raw={'model_poses':[],'link_poses':[],'joints':[],'force_control':[],'stats':[]};errors=[]
    started=time.monotonic();contract=resolved_robot_contract(robot)
    def receive_pose(kind):
        def callback(message):
            raw[kind].append({'wall_since_start':time.monotonic()-started,
                'protobuf_base64':base64.b64encode(message.SerializeToString()).decode(),
                'poses':[{'name':p.name,'sim_time':p.header.stamp.sec+p.header.stamp.nsec*1e-9,
                          'pose':[p.position.x,p.position.y,p.position.z,p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]}
                         for p in message.pose]})
        return callback
    def receive_json(kind):
        def callback(message):
            try:
                row=json.loads(message.data)
                if row.get('robot_spec_sha256')!=robot.sha256:raise ValueError('Wrong observed RobotSpec')
                raw[kind].append({'wall_since_start':time.monotonic()-started,'message':row})
            except Exception as error:errors.append(str(error))
        return callback
    callbacks=[];topics=[]
    def subscribe(cls,topic,callback):
        callbacks.append(callback);topics.append(topic)
        if not node.subscribe(cls,topic,callback):raise ValueError('Subscription failed '+topic)
    subscribe(Pose_V,'/probe/cad_model_pose',receive_pose('model_poses'))
    subscribe(Pose_V,contract['topics']['link_poses'],receive_pose('link_poses'))
    subscribe(StringMsg,contract['topics_robot_telemetry'],receive_json('joints'))
    for topic in contract['topics'].get('position_force_states',{}).values():
        subscribe(StringMsg,topic,receive_json('force_control'))
    def stats(message):
        raw['stats'].append({'wall_since_start':time.monotonic()-started,'iterations':message.iterations,
                            'sim_time':message.sim_time.sec+message.sim_time.nsec*1e-9})
    subscribe(WorldStatistics,'/world/cad_mobility_probe/stats',stats)
    started=time.monotonic()
    with (out/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-s','-r','--iterations',str(iterations),str(out/'world.sdf')],
                                 cwd=out,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=wall_timeout)
        except subprocess.TimeoutExpired:
            errors.append('native_timeout');os.killpg(process.pid,signal.SIGINT)
            try:code=process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
    wall=time.monotonic()-started
    write(out/'native_completion.json',{'native_exit_code':code,'wall_seconds':wall,'errors':list(errors),'native_pid':process.pid})
    for topic in topics:node.unsubscribe(topic)
    for kind,rows in raw.items():jsonlines(out/(kind+'.jsonl'),rows)
    samples=raw['joints'];window=None
    if len(samples)>1:
        first,last=samples[0],samples[-1]
        delta_sim=last['message']['sim_time']-first['message']['sim_time']
        delta_wall=last['wall_since_start']-first['wall_since_start']
        window={'first_sim_time':first['message']['sim_time'],'last_sim_time':last['message']['sim_time'],
                'simulation_span_s':delta_sim,'wall_span_s':delta_wall,'observed_rtf':delta_sim/delta_wall}
    metrics={}
    for sample in samples:
        for joint in sample['message']['joints']:
            row=metrics.setdefault(joint['name'],{'max_abs_velocity_window':0.,'max_abs_force_command_window':0.})
            for key in row:
                value=joint.get(key)
                if value is not None:row[key]=max(row[key],abs(value))
    result={'status':'PERFORMANCE_OBSERVATION_ONLY','case':label,'robot_spec_sha256':robot.sha256,
            'native_exit_code':code,'native_wall_seconds_including_load':wall,'errors':errors,
            'command_publishers_used':False,'requested_iterations':iterations,'observation_window':window,
            'sample_counts':{k:len(v) for k,v in raw.items()},'joint_window_metrics':metrics,
            'native_contact_validation':'PENDING','mobility_acceptance':'NOT_EVALUATED',
            'raw_files_sha256':{p.name:sha(p) for p in out.glob('*.jsonl')}}
    write(out/'result.json',result)
    print(json.dumps({'case':label,'wall':wall,'window':window,'errors':errors}),flush=True)
    return result


def main():
    # A fresh process per case isolates gz-transport's shared singleton and its
    # discovery partition; neither run can accidentally observe its neighbor.
    if len(sys.argv)==5 and sys.argv[1]=='--internal-case':
        out=Path(sys.argv[2]);robot=resolve_robot_profile(out/'robot_resolved.json')
        result=run_case(sys.argv[3],robot,out,1000,float(sys.argv[4]))
        return int(bool(result['errors']) or result['native_exit_code']!=0)
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-profile','source-assets','grouped-profile','grouped-assets','grouping-manifest','plugin-dir','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--start-height',type=float,default=.298218017078388)
    parser.add_argument('--wall-timeout',type=float,default=120)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh output path')
    source=resolve_robot_profile(args.source_profile);grouped=resolve_robot_profile(args.grouped_profile)
    manifest=read(args.grouping_manifest);verify_pair(source,grouped,manifest)
    config=protocol(args.start_height,.0001);config['physics']=source.to_dict()['physics']
    build=read(args.plugin_dir/'build_provenance.json')
    for name,digest in build['source_sha256'].items():
        if Path(name).name!=name or sha(ROOT/'gazebo/harvest_system'/name)!=digest:
            raise ValueError('Native source differs from frozen build '+name)
    output=args.output.resolve();output.mkdir()
    write(output/'preregistered_protocol.json',{'scope':'1000-step representation/performance comparison, not acceptance',
        'iterations':1000,'step_s':.0001,'duration_s':.1,'wall_timeout_per_case_s':args.wall_timeout,
        'start_xyzyaw':config['start_xyzyaw'],'physics':config['physics'],'ground_contact':config['ground_contact'],
        'source_robot_spec_sha256':source.sha256,'grouped_robot_spec_sha256':grouped.sha256,
        'grouping_manifest_sha256':sha(args.grouping_manifest),'all_parameters_except_collision_representation_identical':True,
        'no_command_publishers':True,'native_contact_and_full_mobility_acceptance':'PENDING'})
    cases=(('original',source,args.source_assets),('grouped',grouped,args.grouped_assets))
    for label,robot,assets in cases:prepare_case(label,robot,assets,output/label,args.plugin_dir,build,config)
    snapshots=output/'source_snapshot';snapshots.mkdir()
    for path,content in CODE_BYTES.items():
        if path.read_bytes()!=content:raise ValueError('Execution source changed during preparation')
        target=snapshots/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
    results=[]
    for label,robot,_ in cases:
        child=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--internal-case',str(output/label),label,str(args.wall_timeout)],capture_output=True,text=True)
        (output/label/'runner.log').write_text(child.stdout+child.stderr)
        if not (output/label/'result.json').is_file():raise RuntimeError('Benchmark child failed: '+child.stderr)
        result=read(output/label/'result.json');results.append(result)
        print(json.dumps({'case':label,'wall':result['native_wall_seconds_including_load'],
                          'window':result['observation_window'],'errors':result['errors']}),flush=True)
    if any(p.read_bytes()!=content for p,content in CODE_BYTES.items()):
        raise ValueError('Execution source changed during benchmark')
    write(output/'result.json',{'status':'PERFORMANCE_OBSERVATION_ONLY','cases':results,
        'source_files_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(b).hexdigest() for p,b in CODE_BYTES.items()},
        'global_native_acceptance':'NOT_EVALUATED'})
    return int(any(r['errors'] or r['native_exit_code']!=0 for r in results))


if __name__=='__main__':raise SystemExit(main())
