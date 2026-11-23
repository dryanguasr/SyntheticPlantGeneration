#!/usr/bin/env python3
"""Position/direction preflight within unchanged CAD joint windows.

Base XY/yaw are free, base height is fixed, and no plant coordinate changes.
This is not collision, native dynamics, continuous path or hardware acceptance.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import (forward_kinematics,compose_poses,rotate_vector,
    axis_quaternion,pose_from_rpy,_solve_linear)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def angle_z(axis):return math.acos(max(-1,min(1,axis[2])))


class CutChain:
    def __init__(self,robot):
        self.robot=robot;self.data=robot.to_dict();self.names=list(robot.joint_names)
        self.joints=[next(j for j in self.data['joints'] if j['name']==name) for name in self.names]
        self.mount=forward_kinematics(robot)[self.joints[0]['parent']]
        self.frame=next(f for f in self.data['frames'] if f['name']=='cut_point')
        if self.frame['parent']!=self.joints[-1]['child'] or any(b['parent']!=a['child'] for a,b in zip(self.joints,self.joints[1:])):
            raise ValueError('Expected consecutive CAD arm chain ending at cut frame')
        self.bounds=[(j['limits']['lower'],j['limits']['upper']) for j in self.joints]
    def evaluate(self,q):
        pose=self.mount
        for joint,value in zip(self.joints,q):
            motion={'xyz_m':[0,0,0],'quaternion_xyzw':axis_quaternion(joint['axis'],value+joint['zero_offset'])}
            pose=compose_poses(compose_poses(compose_poses(pose,joint['origin']),motion),joint['child_pose'])
        cut=compose_poses(pose,self.frame['pose']);axis=rotate_vector(cut['quaternion_xyzw'],[0,1,0])
        return cut,axis


def orientation_enclosure(chain,subdivisions=32):
    """Analytic angular Lipschitz boxes for this verified parallel-axis chain.

    Roundoff is padded by 1e-10 rad. This proves only orientation exclusion
    within this numeric RobotSpec and a level base; it is no hardware theorem.
    """
    joints=chain.joints;unit=[0,0,0,1]
    if len(joints)!=5 or chain.mount['quaternion_xyzw']!=unit or joints[0]['axis']!=[0.,0.,1.]:
        return {'status':'NOT_APPLICABLE','reason':'Arm mount/yaw structural conditions differ'}
    if any(j['origin']['quaternion_xyzw']!=unit or j['child_pose']['quaternion_xyzw']!=unit or j['zero_offset']!=0 for j in joints):
        return {'status':'NOT_APPLICABLE','reason':'Nonidentity fixed rotation or offset'}
    if not joints[1]['axis']==joints[2]['axis']==joints[3]['axis']:
        return {'status':'NOT_APPLICABLE','reason':'Three pitch axes are not identical'}
    a,b=joints[1]['axis'],joints[4]['axis']
    initial=rotate_vector(chain.frame['pose']['quaternion_xyzw'],[0,1,0])
    sum_bounds=[sum(chain.bounds[i][j] for i in (1,2,3)) for j in (0,1)]
    roll_bounds=chain.bounds[4];lower=math.pi;upper=0;witnesses=[]
    da=(sum_bounds[1]-sum_bounds[0])/subdivisions;db=(roll_bounds[1]-roll_bounds[0])/subdivisions
    radius=(da+db)/2+1e-10
    for i in range(subdivisions):
        for j in range(subdivisions):
            pitch=sum_bounds[0]+(i+.5)*da;roll=roll_bounds[0]+(j+.5)*db
            direction=rotate_vector(axis_quaternion(a,pitch),rotate_vector(axis_quaternion(b,roll),initial))
            theta=angle_z(direction);lo=max(0,theta-radius);hi=min(math.pi,theta+radius)
            lower=min(lower,lo);upper=max(upper,hi)
            witnesses.append({'pitch_sum_rad':pitch,'roll_rad':roll,'theta_center_rad':theta,
                              'theta_lower_rad':lo,'theta_upper_rad':hi})
    return {'status':'ENCLOSED','method':'Parallel pitch axes commute; yaw about world Z preserves vertical direction. Each composed rotation is 1-Lipschitz in spherical angle; each box radius is half-width(sum pitch)+half-width(roll).',
        'floating_point_padding_rad':1e-10,'pitch_sum_interval_rad':sum_bounds,'roll_interval_rad':list(roll_bounds),
        'subdivisions_per_axis':subdivisions,'boxes':witnesses,'theta_from_vertical_interval_rad':[lower,upper],
        'axis_vertical_interval':[math.cos(upper),math.cos(lower)],
        'scope':'Numeric profile bounds and level base only; provisional commissioning windows, not measured hardware stops.',
        'numerical_method':'Ordinary double precision with conservative angular padding, not formally verified interval arithmetic.'}


def optimize(chain,seed,height,theta,allowed_direction_error=0):
    q=list(seed);bounds=chain.bounds
    def features(q):
        pose,axis=chain.evaluate(q)
        angle=angle_z(axis)
        angular_residual=max(0,abs(angle-theta)-allowed_direction_error)
        return [pose['xyz_m'][2],.3*angular_residual]
    goal=[height,0]
    for _ in range(100):
        current=features(q);error=[a-b for a,b in zip(goal,current)]
        if abs(error[0])<1e-6 and abs(error[1])<3e-6:break
        columns=[]
        for index,(lo,hi) in enumerate(bounds):
            plus,minus=q.copy(),q.copy();plus[index]=min(hi,q[index]+1e-5);minus[index]=max(lo,q[index]-1e-5)
            fp,fm=features(plus),features(minus)
            columns.append([(a-b)/(plus[index]-minus[index]) for a,b in zip(fp,fm)])
        normal=[[sum(a*b for a,b in zip(columns[i],columns[j]))+(.003**2 if i==j else 0) for j in range(5)] for i in range(5)]
        step=_solve_linear(normal,[sum(a*b for a,b in zip(column,error)) for column in columns])
        if step is None:break
        cap=min(1,.15/max(max(map(abs,step)),1e-12));old=sum(v*v for v in error)
        for factor in (1,.5,.25,.125,.03125):
            candidate=[max(lo,min(hi,x+cap*factor*delta)) for x,delta,(lo,hi) in zip(q,step,bounds)]
            if sum((a-b)**2 for a,b in zip(goal,features(candidate)))<old-1e-18:
                q=candidate;break
        else:break
    return q


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','manifest','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    robot=resolve_robot_profile(args.profile);chain=CutChain(robot)
    manifest=json.loads(args.manifest.read_text());ground=.296218017078388
    protocol={'scope':__doc__,'robot_spec_sha256':robot.sha256,'profile_file_sha256':sha(args.profile),
        'manifest_sha256':sha(args.manifest),'script_sha256':sha(Path(__file__)),'seed':20261123,
        'base_height_m':ground,'base_xy_yaw_free':True,'cut_axis_bidirectional':True,
        'position_tolerance_m':1e-5,'direction_tolerance_rad':.03,'arm_joint_bounds':dict(zip(chain.names,chain.bounds)),
        'plant_target_ids':[f['id'] for f in manifest['fruits']],'plant_mutations':[],
        'collision_checks':'NOT_EXECUTED; no collision exemptions or trajectory acceptance'}
    protocol['joint_window_scope']='Unchanged provisional commissioning window; no global CAD or prototype impossibility claim.'
    dump(args.output/'protocol.json',protocol);dump(args.output/'profile.json',robot.to_dict())
    (args.output/'preflight_source.py').write_bytes(Path(__file__).read_bytes())
    rng=random.Random(protocol['seed']);seeds=[[0]*5]+[list(v) for v in itertools.product(*chain.bounds)]
    seeds += [[rng.uniform(lo,hi) for lo,hi in chain.bounds] for _ in range(300)]
    errors=[]
    for q in seeds[:33]:
        exact=forward_kinematics(robot,q)['cut_point'];fast,_=chain.evaluate(q)
        errors.append(math.dist(exact['xyz_m'],fast['xyz_m']))
        errors.append(max(abs(a-b) for a,b in zip(exact['quaternion_xyzw'],fast['quaternion_xyzw'])))
    if max(errors)>1e-12:raise ValueError('Reduced arm chain differs from the canonical full FK')
    sampled=[(q,*chain.evaluate(q)) for q in seeds]
    enclosure=orientation_enclosure(chain);dump(args.output/'orientation_enclosure.json',enclosure)
    sampled_range={'sample_count':len(sampled),'height_world_range_m':[ground+min(s[1]['xyz_m'][2] for s in sampled),ground+max(s[1]['xyz_m'][2] for s in sampled)],
        'axis_vertical_range':[min(s[2][2] for s in sampled),max(s[2][2] for s in sampled)],
        'full_fk_check_max_error':max(errors),'sampled_not_global_height_bound':True}
    results=[]
    for fruit in manifest['fruits']:
        delta=[b-a for a,b in zip(fruit['pedicel_start_world_m'],fruit['pedicel_end_world_m'])]
        norm=math.sqrt(sum(v*v for v in delta));direction=[v/norm for v in delta]
        target=fruit['cut_point_world_m'];candidates=[];sign_bounds=[]
        for sign in (1,-1):
            desired=[sign*v for v in direction];theta=angle_z(desired);height=target[2]-ground
            if enclosure['status']=='ENCLOSED':
                lo,hi=enclosure['theta_from_vertical_interval_rad'];lower=max(0,lo-theta,theta-hi)
                sign_bounds.append({'axis_sign':sign,'orientation_error_lower_bound_rad':lower,
                    'necessary_added_total_joint_range_lower_bound_rad':max(0,lower-protocol['direction_tolerance_rad']),
                    'range_extension_scope':'Necessary L1 sum of angular departures beyond current non-yaw windows only; not sufficient for position, collisions or mechanical feasibility.',
                    'orientation_excluded':lower>protocol['direction_tolerance_rad']})
            ranked=sorted(sampled,key=lambda item:(item[1]['xyz_m'][2]-height)**2+(.3*(angle_z(item[2])-theta))**2)[:10]
            for tolerance in (0,protocol['direction_tolerance_rad']-1e-6):
                for q0,_,_ in ranked:
                    q=optimize(chain,q0,height,theta,tolerance);pose,axis=chain.evaluate(q)
                    yaw=math.atan2(desired[1],desired[0])-math.atan2(axis[1],axis[0]);c,s=math.cos(yaw),math.sin(yaw)
                    x,y,z=pose['xyz_m'];base=[target[0]-c*x+s*y,target[1]-s*x-c*y,ground,yaw]
                    position_error=abs(z+ground-target[2]);direction_error=abs(angle_z(axis)-theta)
                    world=forward_kinematics(robot,q,base_pose=pose_from_rpy(base[:3],[0,0,yaw]))['cut_point']
                    world_axis=rotate_vector(world['quaternion_xyzw'],[0,1,0])
                    exact_position=math.dist(world['xyz_m'],target)
                    exact_direction=math.acos(max(-1,min(1,sum(a*b for a,b in zip(world_axis,desired)))))
                    if abs(exact_position-position_error)>1e-10 or abs(exact_direction-direction_error)>1e-7:
                        raise ValueError('Candidate residual disagrees with independent full-world canonical FK')
                    candidates.append({'axis_sign':sign,'search_angular_slack_rad':tolerance,
                        'base_xyzyaw':base,'joint_positions_rad':dict(zip(chain.names,q)),
                        'position_error_m':position_error,'direction_error_rad':direction_error,
                        'canonical_world_fk_position_error_m':exact_position,'canonical_world_fk_direction_error_rad':exact_direction,
                        'within_kinematic_tolerances':position_error<=protocol['position_tolerance_m'] and direction_error<=protocol['direction_tolerance_rad'],
                        'collision_and_native_acceptance':'NOT_EXECUTED'})
        candidates.sort(key=lambda row:row['position_error_m']**2+(.3*row['direction_error_rad'])**2)
        result={'fruit_id':fruit['id'],'cut_point_world_m':target,'pedicel_axis_world':direction,
            'orientation_bounds':sign_bounds,'candidates':candidates,
            'status':'KINEMATIC_CANDIDATE_FOUND' if any(c['within_kinematic_tolerances'] for c in candidates) else
                     ('ORIENTATION_EXCLUDED_WITHIN_PROFILE_WINDOWS' if sign_bounds and all(b['orientation_excluded'] for b in sign_bounds) else 'NO_CANDIDATE_IN_SAMPLED_SEARCH')}
        results.append(result);dump(args.output/'target_results.json',results)
        print(json.dumps({'target':fruit['id'],'status':result['status'],'best_position_m':candidates[0]['position_error_m'],
            'best_direction_rad':candidates[0]['direction_error_rad']}),flush=True)
    dump(args.output/'summary.json',{'status':'PREFLIGHT_ONLY','protocol':protocol,'sampled_workspace':sampled_range,
        'orientation_enclosure_sha256':sha(args.output/'orientation_enclosure.json'),'targets':results,
        'target_ids_and_plant_geometry_preserved':True,'native_executed':False})


if __name__=='__main__':main()
