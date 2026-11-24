#!/usr/bin/env python3
"""Native DART/ODE dynamic concave-mesh probe with void and wall witnesses.

A single watertight extruded U mesh moves downward under gravity on a physical
slider before reaching its bench stop. A falling sphere must enter its cavity,
while a wall witness and a convex-box control must stay above the upper edge.
An oblique orientation rotates geometry and gravity together, not coordinates
after simulation. No teleport or velocity/position command is used.
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
from uchuva_gazebo.robot_kinematics import rotate_vector
from probe_cad_suspension_loop import node,numbers,dump,sha

CASES=('hollow','wall','rotated_hollow','rotated_wall','convex_control',
       'mesh_hollow','mesh_wall','rotated_mesh_hollow','rotated_mesh_wall',
       'off_center_hollow','reversed_face_hollow','inverted_normal_hollow')


def obj_surface(vertices,faces):
    normals=[]
    for face in faces:
        a,b,c=[vertices[i] for i in face];u=[y-x for x,y in zip(a,b)];v=[y-x for x,y in zip(a,c)]
        normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length=math.sqrt(sum(x*x for x in normal));normals.append([x/length for x in normal])
    return '# Original project fixture, SI metres; explicit outward normals\n'+''.join(
        'v '+numbers(v)+'\n' for v in vertices)+''.join('vn '+numbers(n)+'\n' for n in normals)+''.join(
        'f '+' '.join(str(i+1)+'//'+str(n+1) for i in f)+'\n' for n,f in enumerate(faces))


def cube_mesh():
    vertices=[(x*.015,y*.015,z*.015) for x,y,z in
              [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    quads=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    return obj_surface(vertices,[(a,b,c) for a,b,c,d in quads]+[(a,c,d) for a,b,c,d in quads])


def u_mesh():
    polygon=[(-.1,0),(.1,0),(.1,.2),(.06,.2),(.06,.04),(-.06,.04),(-.06,.2),(-.1,.2)]
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    remaining=list(range(8));triangles=[]
    while len(remaining)>3:
        for i,b in enumerate(remaining):
            a,c=remaining[i-1],remaining[(i+1)%len(remaining)]
            if cross(polygon[a],polygon[b],polygon[c])<=0:continue
            if any(all(cross(polygon[x],polygon[y],polygon[p])>=-1e-15 for x,y in ((a,b),(b,c),(c,a)))
                   for p in remaining if p not in (a,b,c)):continue
            triangles.append((a,b,c));remaining.remove(b);break
        else:raise ValueError('U polygon triangulation failed')
    triangles.append(tuple(remaining))
    vertices=[(x,y,z) for y in (-.05,.05) for x,z in polygon]
    faces=list(triangles)+[tuple(i+8 for i in reversed(face)) for face in triangles]
    for i in range(8):
        j=(i+1)%8;faces.extend(((i,i+8,j+8),(i,j+8,j)))
    return obj_surface(vertices,faces)


def damaged_floor(text, reverse_winding=False, invert_normal=False):
    """Controlled malformed copy, never a repair of an original CAD artifact."""
    lines=text.splitlines();vertices=[];faces=[];normal_lines=[]
    for index,line in enumerate(lines):
        row=line.split()
        if row and row[0]=='v':vertices.append(list(map(float,row[1:])))
        elif row and row[0]=='vn':normal_lines.append(index)
        elif row and row[0]=='f':faces.append((index,row[1:]))
    # The target point (-.02,-1/60,.04) is strictly inside this inner-floor
    # triangle, farther than the witness radius from every edge.
    for index,face in faces:
        points=[vertices[int(token.split('/')[0])-1] for token in face]
        center=[sum(p[i] for p in points)/3 for i in range(3)]
        if abs(center[0]+.02)<1e-10 and abs(center[1]+1/60)<1e-10 and abs(center[2]-.04)<1e-10:
            if reverse_winding:lines[index]='f '+' '.join(reversed(face))
            if invert_normal:
                normal_index=int(face[0].split('//')[1])-1
                values=list(map(float,lines[normal_lines[normal_index]].split()[1:]))
                lines[normal_lines[normal_index]]='vn '+numbers([-v for v in values])
            return '\n'.join(lines)+'\n'
    raise ValueError('Controlled damaged triangle was not found')


def quaternion(rpy):
    r,p,y=[v/2 for v in rpy];cr,sr,cp,sp,cy,sy=math.cos(r),math.sin(r),math.cos(p),math.sin(p),math.cos(y),math.sin(y)
    return [sr*cp*cy-cr*sp*sy,cr*sp*cy+sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy]


def build_world(case, mesh, identity, detector='ode'):
    angles=[.3,.4,.2] if case.startswith('rotated') else [0,0,0]
    rotation=quaternion(angles);axis=rotate_vector(rotation,[0,0,1]);gravity=[-9.81*x for x in axis]
    root=ET.Element('sdf',version='1.10');world=node(root,'world',name='dynamic_concave_probe')
    node(world,'gravity',numbers(gravity));physics=node(world,'physics',name='1ms',type='ignored')
    node(physics,'max_step_size',.001);node(physics,'real_time_factor',1)
    dart=node(physics,'dart');node(node(dart,'solver'),'solver_type','pgs');node(dart,'collision_detector',detector)
    node(world,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    node(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
    x=.08 if case.endswith('wall') else -.02 if case in ('off_center_hollow','reversed_face_hollow','inverted_normal_hollow') else 0
    y=-1/60 if case in ('off_center_hollow','reversed_face_hollow','inverted_normal_hollow') else 0
    if case=='reversed_face_hollow':mesh=mesh.parent/'reversed_face_u.obj'
    if case=='inverted_normal_hollow':mesh=mesh.parent/'inverted_normal_u.obj'
    for name,local,mass,radius in (('mesh',[0,0,0],2,None),('sphere',[x,y,.35],.02,.015)):
        origin=rotate_vector(rotation,local);origin[2]+=.5
        model=node(world,'model',name=name);node(model,'static','false');node(model,'pose',numbers([*origin,*angles]))
        link=node(model,'link',name=name+'_link');inertial=node(link,'inertial');node(inertial,'mass',mass)
        tensor=node(inertial,'inertia')
        inertia=.01 if radius is None else mass*(2*.015)**2/6 if 'mesh_' in case else .4*mass*radius**2
        for k in ('ixx','iyy','izz'):node(tensor,k,inertia)
        collision=node(link,'collision',name=name+'_collision');geometry=node(collision,'geometry')
        if name=='sphere' and 'mesh_' in case:
            element=node(geometry,'mesh');node(element,'uri',str(mesh.parent/'cube.obj'));node(element,'scale','1 1 1')
        elif name=='sphere':node(node(geometry,'sphere'),'radius',radius)
        elif case=='convex_control':
            node(collision,'pose','0 0 .1 0 0 0');node(node(geometry,'box'),'size','.2 .1 .2')
        else:
            element=node(geometry,'mesh');node(element,'uri',str(mesh));node(element,'scale','1 1 1')
        surface=node(collision,'surface');node(node(surface,'contact'),'collide_bitmask',65535)
        friction=node(node(surface,'friction'),'ode');node(friction,'mu',.5);node(friction,'mu2',.5)
        joint=node(model,'joint',name=name+'_slider',type='prismatic');node(joint,'parent','world');node(joint,'child',name+'_link')
        joint_axis=node(joint,'axis');node(joint_axis,'xyz','0 0 1');limit=node(joint_axis,'limit')
        for tag,value in (('lower',-.05 if name=='mesh' else -.8),('upper',.1),('effort',1000),('velocity',10)):node(limit,tag,value)
        node(node(joint_axis,'dynamics'),'damping',.01)
        publisher=node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
        for tag,value in (('publish_link_pose','false'),('publish_model_pose','true'),('use_pose_vector_msg','true'),
            ('static_publisher','false'),('update_frequency',100),('topic','/probe/concave_poses')):node(publisher,tag,value)
        if name=='mesh':
            sensor=node(link,'sensor',name='mesh_contact',type='contact');node(sensor,'always_on','true')
            node(sensor,'update_rate',100);node(sensor,'topic','/probe/concave_contacts')
            contact=node(sensor,'contact');node(contact,'collision','mesh_collision')
            node(contact,'topic','/probe/concave_contacts')
            observer=node(model,'plugin',filename='libUchuvaRobotTelemetrySystem.so',name='uchuva::RobotTelemetrySystem')
            node(observer,'robot_spec_sha256',identity);node(observer,'topic','/probe/concave_joint')
            node(node(observer,'joint',name='mesh_slider'),'effort_limit',0)
    ET.indent(root,space='  ')
    return ET.tostring(root,encoding='unicode')+'\n',axis


def run_case(output,plugins,case):
    directory=output/case;directory.mkdir();protocol=json.loads((output/'protocol.json').read_text())
    identity=sha(output/'protocol.json');sdf,axis=build_world(case,output/'concave_u.obj',identity,protocol['collision_detector'])
    (directory/'probe.sdf').write_text(sdf)
    check=subprocess.run(['gz','sdf','-k',str(directory/'probe.sdf')],capture_output=True,text=True)
    (directory/'sdf_check.log').write_text(check.stdout+check.stderr)
    os.environ['GZ_PARTITION']='concave-'+uuid.uuid4().hex;os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH']=str(plugins)
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.contacts_pb2 import Contacts
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from google.protobuf.json_format import MessageToDict
    transport=Node();poses={};contact_rows=[];joints=[];mutex=threading.Lock();errors=[]
    def on_pose(msg):
        with mutex:
            for p in msg.pose:
                stamp=p.header.stamp.sec*1000000000+p.header.stamp.nsec
                poses.setdefault(stamp,{})[p.name.rsplit('::',1)[-1]]=[p.position.x,p.position.y,p.position.z]
    def on_contact(msg):
        with mutex:contact_rows.append(MessageToDict(msg,preserving_proto_field_name=True))
    def on_joint(msg):
        row=json.loads(msg.data)
        if row['robot_spec_sha256']!=identity:errors.append('Wrong identity');return
        with mutex:joints.append(row)
    topics=((Pose_V,'/probe/concave_poses',on_pose),(Contacts,'/probe/concave_contacts',on_contact),
            (StringMsg,'/probe/concave_joint',on_joint))
    for typ,topic,callback in topics:
        if not transport.subscribe(typ,topic,callback):raise RuntimeError('Subscribe failed')
    with (directory/'native.log').open('w') as log:
        process=subprocess.Popen(['gz','sim','--force-version','8','-v','4','-s','-r','--iterations','2000',str(directory/'probe.sdf')],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:code=process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);code=process.wait(timeout=5)
            errors.append('native_timeout')
    time.sleep(.15)
    for _,topic,_ in topics:transport.unsubscribe(topic)
    pose_rows=[{'sim_time':stamp*1e-9,'poses':row} for stamp,row in sorted(poses.items())]
    for name,rows in (('poses',pose_rows),('contacts',contact_rows),('joints',joints)):
        (directory/(name+'.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    heights=[]
    for row in pose_rows:
        if row['sim_time']<protocol['steady_start_s'] or len(row['poses'])!=2:continue
        heights.append(sum((s-m)*a for s,m,a in zip(row['poses']['sphere'],row['poses']['mesh'],axis)))
    complete=[r['joints'][0] for r in joints if r['joints'][0]['position_available'] and r['joints'][0]['velocity_available'] and r['joints'][0]['wrench_available']]
    expected=.215 if case.endswith('wall') or case=='convex_control' else .055
    q=[j['position'] for j in complete]
    contacts=sum(len(row.get('contact',[])) for row in contact_rows)
    clean_log=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',(directory/'native.log').read_text(errors='replace'))
    active_detectors=re.findall(r'Using \[([^]]+)\] collision detector',clean_log)
    checks={'native_exit':code==0 and check.returncode==0 and not errors,
        'collision_detector_confirmed':bool(active_detectors) and active_detectors[-1]==protocol['collision_detector'],
        'moving_dynamic_mesh':bool(q) and min(q)<-.045 and max(q)-min(q)>.03,
        'steady_pose_samples':len(heights)>=protocol['minimum_samples'],
        'physical_contact_observed':contacts>=protocol['minimum_contact_samples'],
        'wall_or_void_outcome':bool(heights) and max(abs(h-expected) for h in heights)<=protocol['height_tolerance_m']}
    result={'status':'PASS' if all(checks.values()) else 'FAIL','case':case,'checks':checks,'native_exit_code':code,
        'witness_geometry':'triangle_mesh_cube' if 'mesh_' in case else 'primitive_sphere',
        'expected_sphere_height_relative_mesh_m':expected,'final_relative_height_m':heights[-1] if heights else None,
        'maximum_relative_height_error_m':max((abs(h-expected) for h in heights),default=None),
        'minimum_dynamic_mesh_joint_position_m':min(q,default=None),'physical_contact_count':contacts,
        'complete_joint_samples':len(complete),'steady_pose_samples':len(heights),'errors':errors,
        'files_sha256':{p.name:sha(p) for p in directory.iterdir() if p.is_file()}}
    dump(directory/'result.json',result);print(case,result['status'],result['final_relative_height_m'],contacts,flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plugin-dir',type=Path,required=True);parser.add_argument('--case',choices=CASES)
    parser.add_argument('--only-cases',nargs='+',choices=CASES)
    parser.add_argument('--collision-detector',choices=('ode','fcl','bullet','dart'),default='ode');args=parser.parse_args()
    output=args.output.resolve();plugins=args.plugin_dir.resolve()
    if args.case:return run_case(output,plugins,args.case)
    output.mkdir(parents=True,exist_ok=False);(output/'concave_u.obj').write_text(u_mesh());(output/'cube.obj').write_text(cube_mesh())
    (output/'reversed_face_u.obj').write_text(damaged_floor(u_mesh(),reverse_winding=True))
    (output/'inverted_normal_u.obj').write_text(damaged_floor(u_mesh(),invert_normal=True))
    cases_to_run=args.only_cases or CASES[:9]
    dump(output/'protocol.json',{'steady_start_s':1.2,'minimum_samples':50,'minimum_contact_samples':5,
        'height_tolerance_m':.002,'sphere_radius_m':.015,'U_dimensions_m':[.2,.1,.2],
        'U_cavity_width_m':.12,'U_floor_top_m':.04,'wall_top_m':.2,'gravity_norm_m_s2':9.81,
        'dynamic_mass_kg':2,'dynamic_slider_stop_m':-.05,'step_s':.001,'solver':'pgs','collision_detector':args.collision_detector,
        'cases':cases_to_run,
        'scope':'Dynamic concave triangle mesh controls; malformed winding/normal cases intentionally test the limits of input integrity'})
    frozen=output/'plugins';frozen.mkdir()
    for name in ('libUchuvaRobotTelemetrySystem.so','build_provenance.json'):shutil.copyfile(plugins/name,frozen/name)
    build=json.loads((frozen/'build_provenance.json').read_text())
    if sha(frozen/'libUchuvaRobotTelemetrySystem.so')!=build['libraries_sha256']['libUchuvaRobotTelemetrySystem.so']:
        raise ValueError('Observer binary mismatch')
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    for case in cases_to_run:subprocess.run([sys.executable,__file__,'--output',str(output),'--plugin-dir',str(frozen),'--case',case],check=True)
    cases={case:json.loads((output/case/'result.json').read_text()) for case in cases_to_run}
    dump(output/'summary.json',{'status':'PASS' if all(r['status']=='PASS' for r in cases.values()) else 'FAIL',
        'cases':cases,'script_sha256':sha(__file__),'mesh_sha256':sha(output/'concave_u.obj'),'witness_mesh_sha256':sha(output/'cube.obj'),
        'build_provenance_sha256':sha(frozen/'build_provenance.json'),'scope':'Dynamic concave mesh with primitive and mesh witnesses in physical void, wall and oblique cases'})
    return 0


if __name__=='__main__':raise SystemExit(main())
