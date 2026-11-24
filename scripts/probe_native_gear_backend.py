#!/usr/bin/env python3
"""Prepare/run reciprocal native-gear and mesh-support diagnostic fixtures.

Preparation never starts Gazebo. Use a separate --run CASE process for each
case under Linux/WSL, with the already installed gz transport Python modules.
All fixtures, plugin hashes and criteria are recorded before execution.
These engineered fixtures do not admit a CAD robot or its small-pad contacts.
"""
import argparse,hashlib,json,math,os,shutil,signal,subprocess,time,uuid
from pathlib import Path
import xml.etree.ElementTree as ET
DEFAULT_ENGINE='/usr/lib/x86_64-linux-gnu/gz-physics-7/engine-plugins/libgz-physics7-bullet-featherstone-plugin.so'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def e(p,t,v=None,**a):
 r=ET.SubElement(p,t,a)
 if v is not None:r.text=str(v)
 return r
def inertial(link,mass,ix,iy,iz):
 i=e(link,'inertial');e(i,'mass',mass);t=e(i,'inertia')
 for k,v in [('ixx',ix),('iyy',iy),('izz',iz),('ixy',0),('ixz',0),('iyz',0)]:e(t,k,v)
def posepub(model,topic,model_only=False):
 p=e(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
 for k,v in [('publish_link_pose',str(not model_only).lower()),('publish_model_pose',str(model_only).lower()),('publish_visual_pose','false'),('publish_collision_pose','false'),('use_pose_vector_msg','true'),('update_frequency',-1),('topic',topic)]:e(p,k,v)
def base(gravity='0 0 0'):
 root=ET.Element('sdf',version='1.11');w=e(root,'world',name='backend_capability');e(w,'gravity',gravity)
 p=e(w,'physics',name='step',type='ignored');e(p,'max_step_size',.0001);e(p,'real_time_factor',1)
 e(w,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
 return root,w
def rotor(coupled,driven):
 root,w=base();m=e(w,'model',name='rotors');e(m,'pose','0 0 1 0 0 0');housing=e(m,'link',name='housing');inertial(housing,1,.01,.01,.01)
 fixed=e(m,'joint',name='anchor',type='fixed');e(fixed,'parent','world');e(fixed,'child','housing')
 for name,mass,x in [('leader',.04,-.03),('follower',.06,.03)]:
  link=e(m,'link',name=name);e(link,'pose',f'{x} 0 0 0 0 0');inertial(link,mass,mass*(.0003+.000004)/12,mass*(.0003+.000004)/12,.5*mass*.0001)
  v=e(link,'visual',name='solid');g=e(e(v,'geometry'),'cylinder');e(g,'radius',.01);e(g,'length',.002)
  j=e(m,'joint',name=name+'_joint',type='revolute');e(j,'parent','housing');e(j,'child',name);e(j,'pose','0 0 0 0 0 0',relative_to=name)
  axis=e(j,'axis');e(axis,'xyz','0 0 1');lim=e(axis,'limit')
  for k,v in [('lower',-1),('upper',1),('effort',.02),('velocity',1)]:e(lim,k,v)
  if name=='follower' and coupled:
   mimic=e(axis,'mimic',joint='leader_joint',axis='axis');e(mimic,'multiplier',-1);e(mimic,'offset',0);e(mimic,'reference',0)
 p=e(w,'plugin',filename='gz-sim-apply-link-wrench-system',name='gz::sim::systems::ApplyLinkWrench');e(p,'verbose','false');load=e(p,'persistent');e(load,'entity_name','rotors::'+driven);e(load,'entity_type','link');e(load,'torque','0 0 0.00002')
 obs=e(m,'plugin',filename='libUchuvaRobotTelemetrySystem.so',name='uchuva::RobotTelemetrySystem');e(obs,'robot_spec_sha256','0'*64);e(obs,'topic','/fixture/joints');e(obs,'publish_rate',10000)
 for n in ('leader','follower'):e(e(obs,'joint',name=n+'_joint'),'effort_limit',0)
 posepub(m,'/fixture/poses');return root
def meshbox():
 # Exact closed box 20x20x10mm, flat face normals; no inflation in source.
 vertices=[(x*.01,y*.01,z*.005) for x,y,z in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
 faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
 out=['# exact source box in SI, outward triangles and matching normals']
 for i,f in enumerate(faces):
  a,b,c=[vertices[n] for n in f];u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)];n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in n));n=[x/length for x in n]
  for p in (a,b,c):out.append('v '+' '.join(map(str,p)))
  for _ in range(3):out.append('vn '+' '.join(map(str,n)))
  out.append('f '+' '.join(f'{k}//{k}' for k in range(i*3+1,i*3+4)))
 return '\n'.join(out)+'\n'
def margin():
 root,w=base('0 0 -9.81')
 for name,x in [('mesh',-.1),('primitive',.1)]:
  floor=e(w,'model',name=name+'_floor');e(floor,'static','true');e(floor,'pose',f'{x} 0 .005 0 0 0');link=e(floor,'link',name='body');g=e(e(link,'collision',name='surface'),'geometry')
  if name=='mesh':e(e(g,'mesh'),'uri','box.obj')
  else:e(e(g,'box'),'size','.02 .02 .01')
  ball=e(w,'model',name=name+'_ball');e(ball,'pose',f'{x} 0 .04 0 0 0');link=e(ball,'link',name='body');inertial(link,.001,4e-10,4e-10,4e-10);e(e(e(link,'collision',name='sphere'),'geometry'),'sphere')
  link.find('collision/geometry/sphere').append(ET.Element('radius'));link.find('collision/geometry/sphere/radius').text='.001'
  posepub(ball,'/fixture/'+name+'_poses',True)
 return root
def prepare(output, plugin_dir, engine):
 OUT=output.resolve();ENGINE=engine
 if OUT.exists():raise ValueError("Use a fresh output directory")
 OUT.mkdir(parents=True)
 if (OUT/'protocol.json').exists():raise ValueError('Preserve previous protocol')
 source=plugin_dir.resolve();plugins=OUT/'plugins';plugins.mkdir()
 build=read(source/'build_provenance.json')
 for name,digest in build['libraries_sha256'].items():
  if sha(source/name)!=digest:raise ValueError('Library differs from supplied build provenance')
  shutil.copyfile(source/name,plugins/name)
 shutil.copyfile(source/'build_provenance.json',plugins/'build_provenance.json')
 (OUT/'box.obj').write_text(meshbox(),encoding='utf-8');cases={}
 for label,coupled,driven in [('leader_coupled',True,'leader'),('follower_coupled',True,'follower'),('follower_disconnected',False,'follower')]:
  cases[label]={'duration_s':.1,'coupled':coupled,'loaded_body':driven,'kind':'reciprocity'}
  p=OUT/label;p.mkdir();r=rotor(coupled,driven);ET.indent(r,space='  ');(p/'world.sdf').write_text(ET.tostring(r,encoding='unicode')+'\n',encoding='utf-8')
 cases['mesh_margin']={'duration_s':.3,'kind':'geometry_fidelity'};p=OUT/'mesh_margin';p.mkdir();r=margin();ET.indent(r,space='  ');(p/'world.sdf').write_text(ET.tostring(r,encoding='unicode')+'\n',encoding='utf-8')
 write(OUT/'protocol.json',{'status':'PREREGISTERED_NOT_EXECUTED','scope':'Backend capability fixtures, not robot migration or admission','dt_s':.0001,'cases':cases,'native_wall_timeout_s':60,
  'transmission':'Native SDF mimic multiplier−1, no GearCouplingSystem, no motor controller or JointVelocityCmd on either rotor; external constant2e−5Nm torque only on the declared body.',
  'fixture_mass_properties':'Engineered two-solid-cylinder test masses.04/.06kg,radius.01m,length.002m, axial inertias2e−6/3e−6kgm²; not hardware estimates.',
  'criteria':{'gear_position_error_rad':.001,'minimum_backdriven_excursion_rad':.005,'motor_command_bound_nm':1e-12,'rotor_velocity_bound_rad_s':1.03,'mesh_vs_primitive_support_difference_m':.0001},
  'negative_control':'Disconnected leader stays|q|<1e−9 while externally loaded follower moves>.005rad. Coupled must backdrive both ways withqsum≤.001 and no motorcommand.',
  'geometry_control':'Identical source20x20x10mm box as triangles or nativebox;1mm spheres settle nominalz=.011. More than.1mm relative support offset is a backend geometry-fidelity failure, not a relaxed robot threshold.',
  'native_engine_path':ENGINE,'helper_sha256':sha(__file__),'libraries_sha256':build['libraries_sha256'],
  'inputs_sha256':{str(p.relative_to(OUT)):sha(p) for p in [OUT/'box.obj',*[OUT/n/'world.sdf' for n in cases]]}})
 print('prepared')
def run(output, label):
 OUT=output.resolve();ENGINE=read(OUT/"protocol.json")["native_engine_path"]
 protocol=read(OUT/'protocol.json');config=protocol['cases'][label];case=OUT/label
 if (case/'result.json').exists():raise ValueError('Preserve completed case')
 if sha(__file__)!=protocol['helper_sha256']:raise ValueError('Helper changed')
 for rel,digest in protocol['inputs_sha256'].items():
  if sha(OUT/rel.replace(chr(92), chr(47)))!=digest:raise ValueError('Fixture changed')
 for name,digest in protocol['libraries_sha256'].items():
  if sha(OUT/'plugins'/name)!=digest:raise ValueError('Plugin changed')
 check=subprocess.run(['gz','sdf','-k',str(case/'world.sdf')],capture_output=True,text=True);(case/'sdf_check.log').write_text(check.stdout+check.stderr)
 if check.returncode:raise ValueError('Invalid fixtureSDF')
 engine_info=subprocess.check_output(['gz','plugin','--info','--plugin',ENGINE],text=True);(case/'engine_interfaces.txt').write_text(engine_info)
 os.environ['GZ_PARTITION']='gear-backend-'+uuid.uuid4().hex;os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(OUT/'plugins');os.environ['GZ_SIM_RESOURCE_PATH']=str(OUT)
 from gz.transport13 import Node
 from gz.msgs10.stringmsg_pb2 import StringMsg
 from gz.msgs10.pose_v_pb2 import Pose_V
 node=Node();observed={'joints':[],'poses':[]};callbacks=[];errors=[]
 def joints(msg):
  try:observed['joints'].append(json.loads(msg.data))
  except Exception as exc:errors.append(str(exc))
 def poses(msg):observed['poses'].append({'poses':[{'name':p.name,'time_s':p.header.stamp.sec+p.header.stamp.nsec*1e-9,'xyz_m':[p.position.x,p.position.y,p.position.z],'q_xyzw':[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]} for p in msg.pose]})
 subscriptions=[(StringMsg,'/fixture/joints',joints),(Pose_V,'/fixture/poses',poses)] if config['kind']=='reciprocity' else [(Pose_V,'/fixture/mesh_poses',poses),(Pose_V,'/fixture/primitive_poses',poses)]
 for kind,topic,callback in subscriptions:
  callbacks.append(callback)
  if not node.subscribe(kind,topic,callback):raise ValueError('Cannot subscribe')
 started=time.monotonic()
 with (case/'native.log').open('w') as log:
  process=subprocess.Popen(['gz','sim','--force-version','8','--physics-engine',ENGINE,'-s','-r','--iterations',str(round(config['duration_s']/protocol['dt_s'])),str(case/'world.sdf')],cwd=case,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  try:code=process.wait(timeout=protocol['native_wall_timeout_s'])
  except subprocess.TimeoutExpired:
   errors.append('native_timeout');os.killpg(process.pid,signal.SIGINT)
   try:code=process.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait()
 for _,topic,_ in subscriptions:node.unsubscribe(topic)
 for name,rows in observed.items():(case/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in rows))
 result={'status':'DIAGNOSTIC_ONLY','case':label,'native_exit_code':code,'errors':errors,'wall_seconds':time.monotonic()-started,'engine_sha256':sha(ENGINE),'helper_sha256':sha(__file__),'observations':{n:len(r) for n,r in observed.items()},'files_sha256':{p.name:sha(p) for p in case.iterdir() if p.is_file()}}
 write(case/'result.json',result);print(json.dumps(result))
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--output',type=Path,required=True)
 p.add_argument('--plugin-dir',type=Path)
 p.add_argument('--engine',default=DEFAULT_ENGINE)
 p.add_argument('--run',choices=('leader_coupled','follower_coupled','follower_disconnected','mesh_margin'))
 args=p.parse_args()
 if args.run:
  run(args.output,args.run)
 elif args.plugin_dir is None:
  p.error('--plugin-dir is required for preparation')
 else:
  prepare(args.output,args.plugin_dir,args.engine)

if __name__=='__main__': main()
