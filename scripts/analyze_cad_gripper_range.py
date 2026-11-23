#!/usr/bin/env python3
"""Trace each CAD four-bar on its saved assembly branch, without dynamics.

The output is a kinematic operating-envelope proposal, not mechanical-stop,
collision, servo calibration or grasp-force validation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_kinematics import (axis_quaternion, rotate_vector, compose_poses,
                                          pose_identity, transform_point)
from prepare_cad_robot import from_matrix


def dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def subtract(a,b):
    return [x-y for x,y in zip(a,b)]


def cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def signed_angle(a,b,axis):
    return math.atan2(dot(axis,cross(a,b)),dot(a,b))


def trace_four_bar(points, axis, end, intervals=1000):
    a,b,c0,d0 = [points[key] for key in 'ABCD']
    short_length, jaw_length = math.dist(a,d0), math.dist(c0,d0)
    previous = d0
    records = []
    for index in range(intervals+1):
        q = end*index/intervals
        crank = rotate_vector(axis_quaternion(axis,q),subtract(c0,b))
        c = [x+y for x,y in zip(b,crank)]
        distance = math.dist(a,c)
        if distance < 1e-12 or not abs(short_length-jaw_length) <= distance <= short_length+jaw_length:
            return {'status':'KINEMATIC_BRANCH_UNREACHABLE','failed_driver_rad':q,'records':records}
        unit = [v/distance for v in subtract(c,a)]
        along = (short_length**2-jaw_length**2+distance**2)/(2*distance)
        height = math.sqrt(max(0,short_length**2-along**2))
        perpendicular = cross(axis,unit)
        middle = [x+along*y for x,y in zip(a,unit)]
        choices = [[x+sign*height*y for x,y in zip(middle,perpendicular)] for sign in (-1,1)]
        d = min(choices,key=lambda point:math.dist(point,previous))
        short_angle = signed_angle(subtract(d0,a),subtract(d,a),axis)
        jaw_angle = signed_angle(subtract(d0,c0),subtract(d,c),axis)
        records.append({'driver_rad':q,'short_rad':short_angle,'jaw_joint_rad':jaw_angle-q,
                        'closure_pin_rad':short_angle-jaw_angle,'jaw_absolute_rad':jaw_angle,
                        'point_d_m':d,'circle_intersection_height_m':height})
        previous = d
    fields = ('short_rad','jaw_joint_rad','closure_pin_rad')
    extrema = {name:{'minimum':min(row[name] for row in records),'maximum':max(row[name] for row in records),
                      'maximum_absolute_velocity_ratio_to_driver':max(abs((b[name]-a[name])/(b['driver_rad']-a['driver_rad']))
                          for a,b in zip(records,records[1:]))} for name in fields}
    return {'status':'KINEMATIC_BRANCH_TRACED','extrema':extrema,'records':records}


def _matrix(pose):
    axes=[rotate_vector(pose['quaternion_xyzw'],[int(i==j) for i in range(3)]) for j in range(3)]
    return [v for i in range(3) for v in [*(axes[j][i] for j in range(3)),pose['xyz_m'][i]]]+[0,0,0,1]


def prepare_brep_motion(inventory, driver_end=.1, intervals=20):
    document=next(row for row in inventory['documents'] if row['source_path']=='gripper/Gripper ensamble.iam')
    documents={row['id']:row for row in inventory['documents']}
    occurrences={row['name']:row for row in inventory['occurrences']
                 if row['root_document_id']==document['id'] and row['parent_id']==document['id']}
    relations={row['name']:row for row in document['relations']}
    axis=[0,1,0]
    traces,points,bounds={}, {}, {}
    roles={'Gripper y engranaje:1':('fixed',None),
           'Eslabon L:1':('right','jaw'),'Eslabon L:2':('left','jaw'),
           'Eslabon 1:1':('right','short'),'Eslabon 1:2':('left','short'),
           'Engranaje recto2:1':('right','gear'),'Engranaje recto1:1':('left','gear')}
    for side,sign,references in (
        ('left',1,[('Coincidencia:9','EntityOne'),('Coincidencia:7','EntityOne'),('Coincidencia:23','EntityOne'),('Coincidencia:13','EntityOne')]),
        ('right',-1,[('Coincidencia:10','EntityOne'),('Coincidencia:1','EntityTwo'),('Coincidencia:22','EntityOne'),('Coincidencia:15','EntityOne')])):
        points[side]={key:[relations[name][entity]['BasePoint_m'][0],0,relations[name][entity]['BasePoint_m'][2]]
                      for key,(name,entity) in zip('ABCD',references)}
        trace=trace_four_bar(points[side],axis,sign*driver_end,intervals)
        if trace['status']!='KINEMATIC_BRANCH_TRACED':
            raise ValueError('Requested BRep envelope crosses an unreachable four-bar configuration')
        traces[side]=trace
        a,b,c,d=[points[side][key] for key in 'ABCD']
        base,crank=subtract(b,a),subtract(c,b)
        cosine=2*dot(base,crank);sine=2*dot(base,cross(axis,crank));constant=dot(base,base)+dot(crank,crank)
        low,high=sorted((0,sign*driver_end))
        critical=[low,high]+[math.atan2(sine,cosine)+k*math.pi for k in range(-2,3)
                             if low<=math.atan2(sine,cosine)+k*math.pi<=high]
        squared=[constant+cosine*math.cos(q)+sine*math.sin(q) for q in critical]
        short,jaw=math.dist(a,d),math.dist(c,d)
        max_cosine=max(abs((short*short+jaw*jaw-value)/(2*short*jaw)) for value in squared)
        sine_lower=math.sqrt(1-max_cosine*max_cosine)
        crank_length=math.sqrt(dot(crank,crank))
        bounds[side]={'minimum_bar_sine':sine_lower,'short_angular_ratio_upper':crank_length/(short*sine_lower),
                      'jaw_absolute_angular_ratio_upper':crank_length/(jaw*sine_lower),'crank_length_m':crank_length,
                      'method':'Exact extrema of |B-A+R(q)(C0-B)|^2 over the whole interval; inverse 2x2 pin-velocity Jacobian bounded using the minimum angle sine.'}
    samples=[]
    velocity_bounds={}
    for index in range(intervals+1):
        transforms={}
        for name,(side,role) in roles.items():
            occurrence=occurrences[name]
            original=from_matrix(occurrence['transform_root_m'])
            movement=pose_identity()
            if side!='fixed':
                item=traces[side]['records'][index]
                p=points[side]
                if role=='gear':
                    center,target,angle=p['B'],p['B'],item['driver_rad']
                elif role=='short':
                    center,target,angle=p['A'],p['A'],item['short_rad']
                else:
                    center=p['C']
                    rotated=rotate_vector(axis_quaternion(axis,item['driver_rad']),subtract(p['C'],p['B']))
                    target=[x+y for x,y in zip(p['B'],rotated)]
                    angle=item['jaw_absolute_rad']
                rotation=axis_quaternion(axis,angle)
                turned=rotate_vector(rotation,center)
                movement={'xyz_m':[a-b for a,b in zip(target,turned)],'quaternion_xyzw':rotation}
                if index==0:
                    geometry=documents[occurrence['document_id']]['bounds_m']
                    corners=[[geometry['max' if mask>>dimension&1 else 'min'][dimension] for dimension in range(3)] for mask in range(8)]
                    radius=max(math.dist(transform_point(original,corner),center) for corner in corners)
                    rate=1 if role=='gear' else bounds[side]['short_angular_ratio_upper'] if role=='short' else bounds[side]['jaw_absolute_angular_ratio_upper']
                    velocity_bounds[name]=rate*radius+(bounds[side]['crank_length_m'] if role=='jaw' else 0)
            else:
                velocity_bounds[name]=0
            transformed=compose_poses(movement,original)
            if index==0 and math.dist(transformed['xyz_m'],original['xyz_m'])>1e-10:
                raise AssertionError('Saved CAD pose changed at zero')
            transforms[name]=_matrix(transformed)
        samples.append({'driver_rad':driver_end*index/intervals,'occurrence_transforms_m':transforms})
    return {'schema_version':'cad-gripper-brep-envelope-input/1.0','assembly_sha256':document['sha256'],
            'driver_interval_rad':[0,driver_end],'sampling_interval_rad':abs(driver_end)/intervals,
            'point_speed_bounds_m_per_driver_rad':velocity_bounds,'four_bar_global_derivative_bounds':bounds,
            'continuous_clearance_rule':'For each sampled gap subtract (speed_bound_A+speed_bound_B)*sampling_interval/2; a positive remainder certifies separation between samples for this exact rigid four-bar path. It is not a 4-mm external-clearance acceptance.',
            'samples':samples}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--mechanisms-report',type=Path,required=True)
    parser.add_argument('--driver-end',type=float,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--motion-inventory',type=Path)
    parser.add_argument('--brep-motion-output',type=Path)
    args=parser.parse_args()
    profile=json.loads(args.profile.read_text(encoding='utf-8-sig'))
    report=json.loads(args.mechanisms_report.read_text(encoding='utf-8-sig'))
    axis=next(row['axis'] for row in profile['joints'] if row['name']=='gripper_left_driver')
    result={'scope':__doc__,'driver_end_rad':args.driver_end,'intervals':1000,
            'source_files_sha256':{str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in (args.profile,args.mechanisms_report,Path(__file__))},'sides':{}}
    for side,sign in (('left',1),('right',-1)):
        points=next(row['points_base_m'] for row in report['topology_evidence'] if row['name']=='gripper_'+side)
        result['sides'][side]=trace_four_bar(points,axis,sign*args.driver_end)
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,allow_nan=False)
        handle.write('\n')
    if args.brep_motion_output:
        if not args.motion_inventory:
            raise ValueError('BRep motion preparation requires its explicit native inventory')
        motion=prepare_brep_motion(json.loads(args.motion_inventory.read_text(encoding='utf-8-sig')),args.driver_end)
        motion['source_inventory_sha256']=hashlib.sha256(args.motion_inventory.read_bytes()).hexdigest()
        with args.brep_motion_output.open('x',encoding='utf-8') as handle:
            json.dump(motion,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({side:{k:v for k,v in row.items() if k!='records'} for side,row in result['sides'].items()},indent=2))


if __name__=='__main__':
    main()
