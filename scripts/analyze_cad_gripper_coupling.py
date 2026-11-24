#!/usr/bin/env python3
"""Linearized CAD gear/PID screen including DART's implicit joint damping.

This is a contact-free ideal-closure calculation, not native acceptance. It
keeps current gains unchanged and reports both the incomplete undamped screen
and the complete reduced damping model so a retune cannot hide an omission.
"""
import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import ResolvedRobot,canonical_hash,load_robot_json
from uchuva_gazebo.robot_kinematics import forward_kinematics
from cad_mechanisms import gripper_reduced_dynamics


def polynomial_roots(coefficients):
    """Four distinct poles, with checked residuals; no numerical dependency."""
    coefficients=[value/coefficients[0] for value in coefficients]
    size=len(coefficients)-1
    radius=1+max(abs(value) for value in coefficients[1:])
    roots=[radius*cmath.exp(1j*(.21+2*math.pi*i/size)) for i in range(size)]
    def evaluate(value):
        result=coefficients[0]
        for coefficient in coefficients[1:]:result=result*value+coefficient
        return result
    for _ in range(400):
        updated=[];changes=[]
        for i,value in enumerate(roots):
            denominator=math.prod(value-other for j,other in enumerate(roots) if j!=i)
            if abs(denominator)<1e-30:raise ValueError('Unresolved repeated pole')
            change=evaluate(value)/denominator
            updated.append(value-change);changes.append(abs(change))
        roots=updated
        if max(changes)<1e-12:break
    if max(abs(evaluate(value)) for value in roots)>1e-9:
        raise ValueError('Pole root residual did not converge')
    return sorted(roots,key=lambda value:(value.real,value.imag))


def convolve(a,b):
    result=[0.]*(len(a)+len(b)-1)
    for i,x in enumerate(a):
        for j,y in enumerate(b):result[i+j]+=x*y
    return result


def coupled_screen(inertia,implicit_damping,gear_k,gear_c,motor_p,motor_d,step):
    values=[*inertia,*implicit_damping,gear_k,gear_c,motor_p,motor_d,step]
    if not all(type(value) in (int,float) and math.isfinite(value) for value in values):
        raise ValueError('Finite dynamics are required')
    if min(inertia)<=0 or step<=0 or min(implicit_damping)<0 or min(gear_k,gear_c,motor_p,motor_d)<0:
        raise ValueError('Positive masses/step and nonnegative gains are required')
    explicit=[[gear_c+motor_d,gear_c],[gear_c,gear_c]]
    stiffness=[[gear_k+motor_p,gear_k],[gear_k,gear_k]]
    # (M+h Di) q[n+1] + (-2M-h Di+h De+h²K) q[n]
    #                   + (M-h De) q[n-1] = 0.
    entries=[]
    for i in range(2):
        row=[]
        for j in range(2):
            mass=inertia[i] if i==j else 0
            damping=implicit_damping[i] if i==j else 0
            row.append([mass-step*explicit[i][j],
                -2*mass-step*damping+step*explicit[i][j]+step**2*stiffness[i][j],
                mass+step*damping])
        entries.append(row)
    a=convolve(entries[0][0],entries[1][1]);b=convolve(entries[0][1],entries[1][0])
    coefficients=list(reversed([x-y for x,y in zip(a,b)]))
    roots=polynomial_roots(coefficients)
    margin=[[((4*inertia[i]+2*step*implicit_damping[i]) if i==j else 0)
             -2*step*explicit[i][j]-step**2*stiffness[i][j] for j in range(2)] for i in range(2)]
    discriminant=math.sqrt((margin[0][0]-margin[1][1])**2+4*margin[0][1]**2)
    return {'implicit_damping_diagonal_nms_rad':implicit_damping,'explicit_damping_matrix_nms_rad':explicit,
        'stiffness_matrix_nm_rad':stiffness,'step_s':step,
        'poles':[{'real':value.real,'imaginary':value.imag,'modulus':abs(value)} for value in roots],
        'spectral_radius':max(abs(value) for value in roots),
        'linearly_stable_in_this_reduced_model':max(abs(value) for value in roots)<1,
        'minus_one_stability_margin_matrix':margin,
        'minus_one_margin_eigenvalues':[(margin[0][0]+margin[1][1]+sign*discriminant)/2 for sign in (-1,1)]}


def analyze(data,topology):
    robot=ResolvedRobot(data,canonical_hash(data));poses=forward_kinematics(robot)
    gear=data['gear_couplings'][0];gains=data['control']['gripper'][gear['driver']]
    joints={row['name']:row for row in data['joints']}
    reduced=gripper_reduced_dynamics(data['links'],poses,topology,joints[gear['driver']]['axis'],
        gear['maximum_step_s'],gear['stiffness_nm_rad'],gear['damping_nms_rad'])
    contributions={};damping=[]
    for side in ('left','right'):
        short,jaw=reduced[side]['short_angular_ratio'],reduced[side]['jaw_angular_ratio']
        derivatives={'gripper_'+side+'_short_pivot':short,'gripper_'+side+'_jaw_pivot':jaw-1,
            'gripper_'+side+'_short_closure_pin':short-jaw,
            gear['driver'] if side=='left' else gear['follower']:1}
        contributions[side]=[{ 'joint':name,'coordinate_derivative':rate,
            'native_implicit_damping':joints[name].get('damping',0),
            'reduced_damping':joints[name].get('damping',0)*rate*rate} for name,rate in derivatives.items()]
        damping.append(sum(row['reduced_damping'] for row in contributions[side]))
    masses=[reduced[side]['effective_inertia_kg_m2'] for side in ('left','right')]
    def screen(di):return coupled_screen(masses,di,gear['stiffness_nm_rad'],gear['damping_nms_rad'],
        gains['p_gain'],gains['d_gain'],gear['maximum_step_s'])
    return {'scope':__doc__,'source_robot_spec_sha256':robot.sha256,'gains_changed':False,
        'reduced_inertias_kg_m2':masses,'joint_damping_contributions':contributions,
        'without_native_implicit_damping':screen([0,0]),'with_native_implicit_damping':screen(damping),
        'equation':'(M+h Di) v[n+1] = (M-h De) v[n] - h K q[n]; q[n+1] = q[n]+h v[n+1]. Di comes from native joint damping; De includes gear damping and motor derivative gain.',
        'limitations':['Ideal exact four-bar closure at q0 only; PGS projection and split-link compliance are omitted.',
            'Contact/friction, command saturation, changing Jacobian and finite publication step are omitted.',
            'The motor derivative differentiates position error, so a staircase reference also produces a bounded derivative kick.',
            'A stable pole calculation does not establish native mechanism acceptance or hardware calibration.'],
        'primary_sources':[
            'https://dartsim.github.io/tutorials_pendulum.html',
            'https://raw.githubusercontent.com/dartsim/dart/v6.13.2/dart/dynamics/detail/GenericJoint.hpp',
            'https://raw.githubusercontent.com/gazebosim/gz-sim/gz-sim8/src/systems/joint_position_controller/JointPositionController.cc',
            'https://raw.githubusercontent.com/gazebosim/gz-math/gz-math7/src/PID.cc']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('profile','mechanisms-report','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    report=analyze(load_robot_json(args.profile),json.loads(args.mechanisms_report.read_text())['topology_evidence'])
    report['source_files_sha256']={str(path):hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in (args.profile,args.mechanisms_report,Path(__file__))}
    with args.output.open('x',encoding='utf-8') as handle:json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({name:report[name]['spectral_radius'] for name in
        ('without_native_implicit_damping','with_native_implicit_damping')}))


if __name__=='__main__':main()
