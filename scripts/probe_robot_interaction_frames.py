#!/usr/bin/env python3
"""Native interaction-frame/axis diagnostic; not a harvest mission.

Run with WSL system Python after build_harvest_plugin.sh. The original native
5-case execution is preserved under outputs/real_robot_interaction_frame_probe_02.
"""
import argparse
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

REPO=Path(__file__).resolve().parents[1]
BUILD=REPO/'outputs/real_harvester_plugin_build'
CASES={
 'offsets_correct':(0,False,'.2 0 .01 0 0 0','.2 0 0 0 0 0',None),
 'axis_reversed':(math.pi,False,'.2 0 .01 0 0 3.141592653589793','.2 0 0 0 0 0','cut_orientation_out_of_range'),
 'axis_bidirectional':(math.pi,True,'.2 0 .01 0 0 3.141592653589793','.2 0 0 0 0 0',None),
 'wrong_cut_origin':(0,False,'0 0 0 0 0 0','.2 0 0 0 0 0','cut_point_out_of_range'),
 'wrong_grasp_origin':(0,False,'.2 0 .01 0 0 0','0 0 0 0 0 0','fruit_outside_capture_radius'),
}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def world(case):
 angle,bidirectional,cut,grasp,_=CASES[case]
 return f'''<sdf version="1.9"><world name="interaction_probe">
 <gravity>0 0 0</gravity><physics name="1ms" type="ignored"><max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor></physics>
 <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
 <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
 <model name="plant"><static>true</static><link name="plant_link"/></model>
 <model name="harvester"><static>true</static><pose>0 0 1 0 0 0</pose><link name="tool_link"/></model>
 <model name="fruit"><pose>.2 0 1 0 0 0</pose><link name="fruit_link"><inertial><mass>.006</mass><inertia><ixx>.000001</ixx><iyy>.000001</iyy><izz>.000001</izz><ixy>0</ixy><ixz>0</ixz><iyz>0</iyz></inertia></inertial></link></model>
 <plugin filename="UchuvaHarvestSystem" name="uchuva::HarvestSystem">
 <robot_model>harvester</robot_model><tool_link>tool_link</tool_link>
 <tcp_pose>.1 .02 .03 0 0 0</tcp_pose><cut_pose>{cut}</cut_pose><grasp_pose>{grasp}</grasp_pose>
 <tool_cut_axis>1 0 0</tool_cut_axis><cut_axis_tolerance>.05</cut_axis_tolerance><cut_axis_bidirectional>{str(bidirectional).lower()}</cut_axis_bidirectional>
 <cut_tolerance>.02</cut_tolerance><capture_radius>.05</capture_radius><max_relative_speed>.12</max_relative_speed><stable_time>.2</stable_time>
 <fruit id="fixture_fruit"><model>fruit</model><link>fruit_link</link><parent_model>plant</parent_model><parent_link>plant_link</parent_link><cut_point>0 0 .01</cut_point><cut_axis>1 0 0</cut_axis></fruit>
 </plugin></world></sdf>'''


def child(case,destination):
 from gz.transport13 import Node
 from gz.msgs10.stringmsg_pb2 import StringMsg
 destination.mkdir(exist_ok=False)
 sdf=destination/'world.sdf';sdf.write_text(world(case))
 checked=subprocess.run(['gz','sdf','-k',str(sdf)],capture_output=True,text=True,timeout=15)
 (destination/'sdf_check.log').write_text(checked.stdout+checked.stderr)
 if checked.returncode:raise RuntimeError('Invalid probe SDF')
 node=Node();states=[];events=[];condition=threading.Condition()
 streams=[(destination/'states.jsonl').open('w'),(destination/'events.jsonl').open('w')]
 def state_callback(msg):
  data=json.loads(msg.data)
  with condition:states.append(data);streams[0].write(json.dumps(data)+'\n');streams[0].flush();condition.notify_all()
 def event_callback(msg):
  data=json.loads(msg.data)
  with condition:events.append(data);streams[1].write(json.dumps(data)+'\n');streams[1].flush();condition.notify_all()
 if not node.subscribe(StringMsg,'/harvest/state',state_callback) or not node.subscribe(StringMsg,'/harvest/events',event_callback):raise RuntimeError('Subscribe failed')
 publisher=node.advertise('/harvest/command',StringMsg)
 log=(destination/'server.log').open('w')
 process=subprocess.Popen(['gz','sim','--force-version','8','-s','-r','-v','3',str(sdf)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 result={'case':case,'scope':'Synthetic fixed-frame guard diagnostic, zero gravity; not a dynamic robot or crop harvest validation','passed':False,'sdf_sha256':sha(sdf),'partition':os.environ['GZ_PARTITION']}
 def wait(predicate,timeout=12):
  deadline=time.monotonic()+timeout
  with condition:
   while not predicate():
    if process.poll() is not None:raise RuntimeError('Gazebo exited')
    if states and states[-1].get('status')=='error':raise RuntimeError(str(states[-1]))
    if time.monotonic()>deadline:raise TimeoutError('Probe timeout')
    condition.wait(.05)
 try:
  wait(lambda:states and states[-1].get('ready') and states[-1]['sim_time']>1)
  initial=states[-1]
  assert initial['schema_version']==2,initial
  assert math.dist(initial['tool_pose'][:3],[.1,.02,1.03])<1e-7,initial
  before=len(events);publisher.publish(StringMsg(data='arm fixture_fruit'))
  wait(lambda:any(row.get('action')=='arm' and row.get('phase')=='ack' for row in events[before:]))
  ack=next(row for row in events[before:] if row.get('action')=='arm' and row.get('phase')=='ack')
  expected=CASES[case][-1]
  result.update(initial_sample=initial,arm_ack=ack,expected_rejection=expected)
  if expected:
   assert ack.get('accepted') is False and ack.get('reason')==expected,ack
   assert states[-1]['fruits'][0]['state']=='ATTACHED',states[-1]
  else:
   assert ack.get('accepted') is True,ack
   wait(lambda:states[-1]['fruits'][0].get('stable_seconds',0)>=.25)
   publisher.publish(StringMsg(data='cut fixture_fruit'))
   wait(lambda:states[-1]['fruits'][0]['state']=='HELD')
   held=states[-1];result['held_sample']=held
   assert math.dist(held['fruits'][0]['position'],[.2,0,1])<1e-6,held
   assert math.dist(initial['cut_pose'][:3],[.2,0,1.01])<1e-7
   assert math.dist(initial['grasp_pose'][:3],[.2,0,1])<1e-7
  result['passed']=True
 except Exception as error:result['error']=repr(error)
 finally:
  if process.poll() is None:os.killpg(process.pid,signal.SIGINT)
  try:process.wait(timeout=8)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGTERM);process.wait(timeout=5)
  node.unsubscribe('/harvest/state');node.unsubscribe('/harvest/events')
  for stream in streams:stream.close()
  log.close()
  result.update(state_count=len(states),event_count=len(events),server_returncode=process.returncode)
  (destination/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
 print(json.dumps({'case':case,'passed':result['passed'],'error':result.get('error')}),flush=True)
 return 0 if result['passed'] else 1


def main():
 global BUILD
 parser=argparse.ArgumentParser();parser.add_argument('--case',choices=CASES);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--plugin-dir',type=Path,default=BUILD);args=parser.parse_args();BUILD=args.plugin_dir.resolve()
 if args.case:return child(args.case,args.output)
 args.output.mkdir(parents=True,exist_ok=False)
 (args.output/'protocol.json').write_text(json.dumps({'scope':'Synthetic zero-gravity fixed-frame and cut-axis guard diagnostic; not dynamic robot or harvest acceptance','pose_tolerance_m':1e-7,'held_position_tolerance_m':1e-6,'capture_radius_m':.05,'cut_tolerance_m':.02,'axis_tolerance_rad':.05,'stable_time_s':.2,'cases':{name:{'expected_rejection':value[-1],'bidirectional':value[1]} for name,value in CASES.items()}},indent=2))
 try:
  provenance=json.loads((BUILD/'build_provenance.json').read_text())
  for name,digest in provenance['source_sha256'].items():
   if sha(REPO/'gazebo/harvest_system'/name)!=digest:raise RuntimeError('Stale plugin source: '+name)
  if sha(BUILD/'libUchuvaHarvestSystem.so')!=provenance['library_sha256']:raise RuntimeError('Stale plugin library')
 except Exception as error:
  summary={'status':'NO EJECUTADO','passed':False,'reason':repr(error),'script_sha256':sha(Path(__file__))}
  (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
  print(json.dumps(summary));return 2
 results=[]
 for case in CASES:
  env=os.environ.copy();env['GZ_PARTITION']='frame_probe_'+case+'_'+str(time.time_ns());env['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(BUILD)
  try:
   run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--case',case,'--output',str(args.output/case),'--plugin-dir',str(BUILD)],env=env,timeout=35)
   result=json.loads((args.output/case/'result.json').read_text());results.append({'case':case,'passed':result['passed'],'code':run.returncode})
  except Exception as error:
   results.append({'case':case,'passed':False,'error':repr(error)})
 summary={'status':'PASS' if all(r['passed'] for r in results) else 'FAIL','passed':all(r['passed'] for r in results),'cases':results,'build_provenance':provenance,'script_sha256':sha(Path(__file__)),'protocol_sha256':sha(args.output/'protocol.json')}
 (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
 print(json.dumps(summary['cases']))
 return 0 if summary['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
