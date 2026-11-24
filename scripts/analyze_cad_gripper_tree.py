#!/usr/bin/env python3
"""Compare reduced damping with tree integration followed by inertial closure.

This local calculation is not DART or an acceptance substitute. It includes
every split body's CAD inertia. Comparing two integration orders exposes an
assumption hidden by condensing the closed mechanism before applying damping.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import ResolvedRobot,canonical_hash,load_robot_json
from uchuva_gazebo.robot_kinematics import forward_kinematics,transform_point,rotate_vector
from analyze_cad_gripper_coupling import analyze,convolve,polynomial_roots


def transpose(matrix):return [list(row) for row in zip(*matrix)]
def multiply(a,b):return [[sum(x*y for x,y in zip(row,column)) for column in zip(*b)] for row in a]
def add(a,b,scale=1):return [[x+scale*y for x,y in zip(ar,br)] for ar,br in zip(a,b)]
def scale(a,value):return [[value*x for x in row] for row in a]
def identity(size):return [[float(i==j) for j in range(size)] for i in range(size)]


def observed_mode(rows):
    """Descriptive one-step fits, not acceptance or a global plant model."""
    windows=[]
    for start,end in ((.0001,.0006),(.001,.0025),(.01,.0799)):
        selected=[r for r in rows if start-1e-12<=r['sim_time']<=end+1e-12 and
                  r.get('status')=='active']
        if len(selected)<3:raise ValueError('Insufficient every-step diagnostic samples')
        if max(abs(b['sim_time']-a['sim_time']-.0001) for a,b in zip(selected,selected[1:]))>1e-10:
            raise ValueError('Diagnostic observer missed a native step')
        velocities=[r['measured_velocity_rad_s'] for r in selected]
        x,y=velocities[:-1],velocities[1:];mx=sum(x)/len(x);my=sum(y)/len(y)
        slope=sum((a-mx)*(b-my) for a,b in zip(x,y))/sum((a-mx)**2 for a in x)
        intercept=my-slope*mx
        residual=math.sqrt(sum((b-slope*a-intercept)**2 for a,b in zip(x,y))/len(x))
        windows.append({'start_s':start,'end_s':end,'samples':len(selected),
            'velocity_lag_one_slope':slope,'velocity_intercept_rad_s':intercept,
            'fit_rmse_rad_s':residual,'sign_changes':sum(a*b<0 for a,b in zip(x,y)),
            'maximum_abs_velocity_rad_s':max(abs(v) for v in velocities),
            'maximum_requested_target_rad':max(abs(r['requested_target_position_rad']) for r in selected)})
    return {'model':'v[n+1]=slope*v[n]+intercept, descriptive local least-squares fit',
        'step_s':.0001,'windows':windows,
        'interpretation':'Alternating every-step growth at zero target indicates a high-frequency numerical mode; saturation and finite constraint projection prevent treating the fitted slope as one global linear pole.'}


def inverse(matrix):
    size=len(matrix);aug=[row[:]+unit for row,unit in zip(matrix,identity(size))]
    for col in range(size):
        pivot=max(range(col,size),key=lambda row:abs(aug[row][col]))
        if abs(aug[pivot][col])<1e-20:raise ValueError('Singular inertia/projection matrix')
        aug[col],aug[pivot]=aug[pivot],aug[col]
        divisor=aug[col][col];aug[col]=[v/divisor for v in aug[col]]
        for row in range(size):
            if row!=col:
                factor=aug[row][col];aug[row]=[x-factor*y for x,y in zip(aug[row],aug[col])]
    return [row[size:] for row in aug]


def quaternion_product(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return [w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z]


def tree_mass_matrix(robot,epsilon=1e-6):
    data=robot.to_dict();names=[j['name'] for j in data['joints'] if j['name'].startswith('gripper_')]
    poses=forward_kinematics(robot);bodies=[b for b in data['links'] if b['name'].startswith('gripper_')]
    zero={j['name']:0. for j in data['joints'] if j['type']!='fixed'}
    pairs=[(forward_kinematics(robot,{**zero,name:epsilon}),forward_kinematics(robot,{**zero,name:-epsilon})) for name in names]
    matrix=[[0.]*len(names) for _ in names]
    for body in bodies:
        name=body['name'];inertia=body['inertial'];orientation=poses[name]['quaternion_xyzw']
        conjugate=[-orientation[0],-orientation[1],-orientation[2],orientation[3]]
        translation=[];rotation=[]
        for positive,negative in pairs:
            cp=transform_point(positive[name],inertia['com_m']);cm=transform_point(negative[name],inertia['com_m'])
            translation.append([(x-y)/(2*epsilon) for x,y in zip(cp,cm)])
            qp,qm=positive[name]['quaternion_xyzw'],negative[name]['quaternion_xyzw']
            if sum(x*y for x,y in zip(qp,qm))<0:qm=[-v for v in qm]
            derivative=[(x-y)/(2*epsilon) for x,y in zip(qp,qm)]
            omega_world=[2*v for v in quaternion_product(derivative,conjugate)[:3]]
            rotation.append(rotate_vector(conjugate,omega_world))
        xx,yy,zz,xy,xz,yz=inertia['tensor_kg_m2'];tensor=[[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]]
        for i in range(len(names)):
            for j in range(len(names)):
                linear=inertia['mass_kg']*sum(x*y for x,y in zip(translation[i],translation[j]))
                angular=sum(rotation[i][r]*tensor[r][s]*rotation[j][s] for r in range(3) for s in range(3))
                matrix[i][j]+=linear+angular
    return names,matrix


def projected_poles(mass,damping,stiffness,explicit,basis,step,projection_metric):
    """Free tree implicit damping, then exact velocity projection in a metric."""
    left=multiply(inverse(multiply(multiply(transpose(basis),projection_metric),basis)),
                  multiply(transpose(basis),projection_metric))
    free_inverse=inverse(add(mass,damping,step))
    velocity=multiply(multiply(multiply(left,free_inverse),add(mass,explicit,-step)),basis)
    position=scale(multiply(multiply(multiply(left,free_inverse),stiffness),basis),-step)
    middle=add(add(identity(2),velocity),position,step)
    # det(lambda² I - lambda (I+Bv+h Bq) + Bv) = 0.
    entries=[[[velocity[i][j],-middle[i][j],float(i==j)] for j in range(2)] for i in range(2)]
    first=convolve(entries[0][0],entries[1][1]);second=convolve(entries[0][1],entries[1][0])
    poles=polynomial_roots(list(reversed([a-b for a,b in zip(first,second)])))
    return {'velocity_map':velocity,'position_map':position,
        'poles':[{'real':v.real,'imaginary':v.imag,'modulus':abs(v)} for v in poles],
        'spectral_radius':max(abs(v) for v in poles)}


def analyze_tree(data,topology,candidate_damping=.012):
    robot=ResolvedRobot(data,canonical_hash(data));reduced=analyze(data,topology)
    names,mass=tree_mass_matrix(robot);_,repeat=tree_mass_matrix(robot,5e-7)
    convergence=max(abs(a-b) for ar,br in zip(mass,repeat) for a,b in zip(ar,br))/max(abs(v) for row in mass for v in row)
    if convergence>1e-6:raise ValueError('Finite difference inertia did not converge')
    size=len(names);basis=[[0.,0.] for _ in names]
    for col,side in enumerate(('left','right')):
        for row in reduced['joint_damping_contributions'][side]:
            basis[names.index(row['joint'])][col]=row['coordinate_derivative']
    condensed=multiply(multiply(transpose(basis),mass),basis)
    old=reduced['reduced_inertias_kg_m2']
    discrepancy=max(abs(condensed[i][i]-old[i])/old[i] for i in range(2))
    if discrepancy>1e-6:raise ValueError('Independent tree/closed inertia disagreement')
    joints={j['name']:j for j in data['joints']}
    damping=[[joints[names[i]].get('damping',0) if i==j else 0. for j in range(size)] for i in range(size)]
    gear=data['gear_couplings'][0];motor=data['control']['gripper'][gear['driver']]
    driver,follower=[names.index(gear[key]) for key in ('driver','follower')]
    gear_vector=[0.]*size;gear_vector[driver]=-gear['ratio'];gear_vector[follower]=1
    stiffness=[[gear['stiffness_nm_rad']*a*b for b in gear_vector] for a in gear_vector]
    stiffness[driver][driver]+=motor['p_gain'];step=gear['maximum_step_s']
    candidates={}
    for label,coefficient in (('original',gear['damping_nms_rad']),('candidate',candidate_damping)):
        explicit=[[coefficient*a*b for b in gear_vector] for a in gear_vector]
        explicit[driver][driver]+=motor['d_gain']
        candidates[label]={'gear_damping_nms_rad':coefficient,
            'mass_metric_projection':projected_poles(mass,damping,stiffness,explicit,basis,step,mass),
            'augmented_mass_metric_projection':projected_poles(mass,damping,stiffness,explicit,basis,step,add(mass,damping,step))}
    return {'scope':__doc__,'source_robot_spec_sha256':robot.sha256,'coordinate_order':names,
        'tree_mass_matrix_kg_m2':mass,'closed_velocity_basis':basis,'condensed_mass_matrix':condensed,
        'inertia_finite_difference_relative_change':convergence,'closed_inertia_relative_discrepancy':discrepancy,
        'native_joint_damping_diagonal':[damping[i][i] for i in range(size)],'candidates':candidates,
        'assumptions':['Linearization about CAD q0, no contact and no velocity/effort saturation.',
            'Closed velocity basis comes from the exact CAD four-bar, while each open-tree body is differentiated independently.',
            'Mass-metric projection is a hypothesis about an integration order, not a reproduction of finite-iteration DART PGS.',
            'The comparison with augmented mass is mathematical; only native observations can admit a candidate.'],
        'equation':'vfree=(M+h D)^-1[(M-h De) v-h K q]; vnext=Pmetric vfree; Pmetric=T(T^t metric T)^-1 T^t metric.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','mechanisms-report','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--native-force-records',type=Path)
    args=parser.parse_args();topology=json.loads(args.mechanisms_report.read_text())['topology_evidence']
    result=analyze_tree(load_robot_json(args.profile),topology)
    result['source_files_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (args.profile,args.mechanisms_report,Path(__file__))}
    if args.native_force_records:
        result['native_mode']=observed_mode([json.loads(line) for line in args.native_force_records.read_text().splitlines()])
        result['source_files_sha256'][str(args.native_force_records)]=hashlib.sha256(args.native_force_records.read_bytes()).hexdigest()
    with args.output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps(result['candidates'],indent=2))


if __name__=='__main__':main()
