#!/usr/bin/env python3
"""Contrast frozen native contact messages with the declared CAD/cylinder geometry.

This read-only diagnostic writes a fresh report; it never changes the fixture,
acceptance thresholds or native evidence. A triangle point inside the finite
cylinder is an overlap witness, not a penetration-depth or contact-force model.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile,verify_robot_assets
from uchuva_gazebo.robot_kinematics import compose_poses,inverse_pose,transform_point,rotate_vector
from uchuva_gazebo.robot_mesh_geometry import read_collision_obj,segment_triangle_distance,point_triangle_distance


def rows(path):return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','asset-root','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();source=args.evidence;robot=resolve_robot_profile(source/'profile.json')
    verify_robot_assets(robot,args.asset_root);data=robot.to_dict()
    result=json.loads((source/'result.json').read_text())
    for name,digest in result['files_sha256'].items():
        if sha(source/name)!=digest:raise ValueError('Frozen evidence changed: '+name)
    native=rows(source/'poses.jsonl')[-1]
    states=rows(source/'states.jsonl');last=states[-1];fruit=next(f for f in last['fruits'] if f['id']=='contact_fixture')
    fruit_pose={'xyz_m':fruit['pose'][:3],'quaternion_xyzw':fruit['pose'][3:]};fruit_inverse=inverse_pose(fruit_pose)
    fixed_states=[(row['sim_time'],f['pose']) for row in states if row['sim_time']>1 for f in row.get('fruits',[])
        if f['id']=='contact_fixture' and f.get('pose')]
    drift=max(abs(a-b) for _,pose in fixed_states for a,b in zip(pose,fixed_states[0][1]))
    axis_start=[0,.0155,0];axis_end=[0,.0335,0];radius=.0018
    latest_contacts={};force_max={side:0. for side in ('left','right')}
    for row in rows(source/'contacts.jsonl'):
        if row['native_message'].get('contact'):latest_contacts[row['side']]=row
        for contact in row['native_message'].get('contact',[]):
            for wrench in contact.get('wrench',[]):
                for body in ('body_1_wrench','body_2_wrench'):
                    force=wrench.get(body,{}).get('force',{})
                    force_max[row['side']]=max(force_max[row['side']],math.sqrt(sum(force.get(k,0)**2 for k in 'xyz')))
    reports=[];inputs=[]
    for side,part in (('left','part_113_bounds'),('right','part_114_bounds')):
        link=next(link for link in data['links'] if link['name']=='gripper_'+side+'_jaw')
        shape=next(shape for shape in link['collisions'] if shape['name']==part);path=args.asset_root/shape['geometry']['uri']
        vertices,faces,_,_=read_collision_obj(path)
        pose=compose_poses(native['poses'][link['name']],shape['pose']);inverse=inverse_pose(pose)
        local=[transform_point(fruit_inverse,transform_point(pose,v)) for v in vertices]
        minimum=(math.inf,None,None,None)
        for face_index,face in enumerate(faces):
            a,b,c=[local[i] for i in face]
            for i in range(21):
                for j in range(21-i):
                    point=[a[k]+i/20*(b[k]-a[k])+j/20*(c[k]-a[k]) for k in range(3)]
                    radial=math.hypot(point[0],point[2])
                    if axis_start[1]<point[1]<axis_end[1] and radial<minimum[0]:
                        minimum=(radial,point,face_index,[1-(i+j)/20,i/20,j/20])
        capsule_lower_bound=min(segment_triangle_distance(axis_start,axis_end,*(local[i] for i in face)) for face in faces)-radius
        contact_points=[]
        for contact in latest_contacts[side]['native_message']['contact']:
            for point,normal,depth in zip(contact['position'],contact['normal'],contact['depth']):
                world=[point.get(k,0) for k in 'xyz'];padlocal=transform_point(inverse,world);framelocal=transform_point(fruit_inverse,world)
                contact_points.append({'native_depth_m':depth,'position_in_fruit_frame_m':framelocal,
                    'radial_distance_to_cylinder_axis_m':math.hypot(framelocal[0],framelocal[2]),
                    'distance_to_declared_pad_surface_m':min(point_triangle_distance(padlocal,*(vertices[i] for i in face)) for face in faces),
                    'normal_in_fruit_frame':rotate_vector(fruit_inverse['quaternion_xyzw'],[normal.get(k,0) for k in 'xyz'])})
        reports.append({'side':side,'mesh_sha256':sha(path),'faces':len(faces),
            'minimum_sampled_triangle_point_radius_m':minimum[0],'triangle_point_in_fruit_frame_m':minimum[1],
            'triangle_index':minimum[2],'barycentric_weights':minimum[3],
            'point_strictly_inside_finite_cylinder':minimum[0]<radius,
            'capsule_clearance_lower_bound_m':capsule_lower_bound,
            'maximum_native_contact_force_norm_n':force_max[side],
            'last_native_manifold_points':contact_points})
        inputs.append({'side':side,'vertices':vertices,'faces':faces,'world_pose':pose})
    report={'scope':__doc__,'robot_spec_sha256':robot.sha256,
        'native_pad_pose_time_s':native['sim_time'],'native_fruit_pose_time_s':last['sim_time'],
        'timestamp_difference_s':native['sim_time']-last['sim_time'],
        'temporal_limitation':'Diagnostic uses final samples with declared age; not exact-step mechanism admission.',
        'fixture_state':fruit['state'],'observed_fixed_pose_samples':len(fixed_states),
        'observed_fixed_pose_window_s':[fixed_states[0][0],fixed_states[-1][0]],'maximum_fixture_pose_component_change':drift,
        'cylinder_radius_m':radius,'cylinder_axis_endpoints_in_fruit_frame_m':[axis_start,axis_end],
        'pads':reports,'source_sha256':{str(p):sha(p) for p in (Path(__file__),source/'result.json',source/'profile.json',
            source/'states.jsonl',source/'poses.jsonl',source/'contacts.jsonl',source/'spawned_fruit.sdf',
            ROOT/'src/uchuva_gazebo/robot_mesh_geometry.py',ROOT/'src/uchuva_gazebo/robot_kinematics.py')}}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'geometry_comparison.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (args.output/'native_shape_inputs.json').write_text(json.dumps({'fruit_pose':fruit_pose,'cylinder_radius_m':radius,
        'cylinder_length_m':.018,'cylinder_center_in_fruit_frame_m':[0,.0245,0],'pads':inputs},indent=2)+'\n')
    cylinder_pose=compose_poses(fruit_pose,{'xyz_m':[0,.0245,0],
        'quaternion_xyzw':[math.sin(math.pi/4),0,0,math.cos(math.pi/4)]})
    with (args.output/'bullet_replay_input.txt').open('w') as handle:
        def line(values):handle.write(' '.join(str(value) for value in values)+'\n')
        line([radius,.018]);line(cylinder_pose['xyz_m']+cylinder_pose['quaternion_xyzw']);line([len(inputs)])
        for pad in inputs:
            line([pad['side'],len(pad['vertices']),len(pad['faces'])])
            line(pad['world_pose']['xyz_m']+pad['world_pose']['quaternion_xyzw'])
            for vertex in pad['vertices']:line(vertex)
            for face in pad['faces']:line(face)
    print(json.dumps({'report':str(args.output/'geometry_comparison.json'),'overlap_witnesses':[p['point_strictly_inside_finite_cylinder'] for p in reports]}))


if __name__=='__main__':main()
