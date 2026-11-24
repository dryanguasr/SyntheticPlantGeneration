#!/usr/bin/env python3
"""Resolve existing drive parameters with explicit estimated provenance."""
from __future__ import annotations
import argparse, hashlib, json, math, cmath, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile


def drive_revision(profile, revision, revision_source, revision_hash):
    base=resolve_robot_profile(profile);before=base.to_dict()
    if base.sha256!=revision['base_robot_spec_sha256']:raise ValueError('Drive revision belongs to another source profile')
    permitted={'wheel_effort_limit_nm','wheel_velocity_p_gain','wheel_velocity_i_gain','wheel_integral_effort_limit_nm'}
    if not set(revision['candidate_parameters'])<=permitted:raise ValueError('Undeclared drive parameter update')
    evidence={'status':'estimado','source':revision_source,'revision':revision_hash,
        'method':revision['derivation']['gain_selection'],'uncertainty':revision['derivation']['hardware_caveat']}
    for name in revision['candidate_parameters']:
        if name not in before['parameters']:raise ValueError('Parameter has no existing resolved bindings: '+name)
    robot=resolve_robot_profile(before,{'/parameters/'+name:{'value':value,'provenance':evidence}
        for name,value in revision['candidate_parameters'].items()})
    after=robot.to_dict()
    for key in ('links','frames','physics','collision_policy','closures','gear_couplings'):
        if before.get(key)!=after.get(key):raise ValueError('Drive revision altered physical geometry/mechanism: '+key)
    for key in ('arm','gripper'):
        if before['control'].get(key)!=after['control'].get(key):raise ValueError('Drive revision altered another controller')
    return base,robot


def wheel_pi_analysis(robot):
    data=robot.to_dict();links={r['name']:r for r in data['links']};dt=data['physics']['maximum_step_s'];rows=[]
    for joint in data['joints']:
        if joint['group']!='drive':continue
        # This CAD family places the joint frame at the wheel origin with an
        # identity child pose; reject a changed frame rather than misusing Iyy.
        if joint['axis']!=[0,1,0] or joint['child_pose']!={'xyz_m':[0,0,0],'quaternion_xyzw':[0,0,0,1]}:
            raise ValueError('Wheel inertia analysis requires the declared Y-axis joint frame')
        inertia=links[joint['child']]['inertial'];com=inertia['com_m']
        effective=inertia['tensor_kg_m2'][1]+inertia['mass_kg']*(com[0]**2+com[2]**2)
        gains=data['control']['drive']['joints'][joint['name']];p,ki=gains['p_gain'],gains['i_gain']
        # Both common Euler orderings: integral updated after or before torque.
        cases=[]
        for integrate_first in (False,True):
            a=1-dt*p/effective-(dt*dt*ki/effective if integrate_first else 0)
            b=-dt*ki/effective;c=dt;d=1
            trace=a+d;det=a*d-b*c;root=cmath.sqrt(trace*trace-4*det)
            eigenvalues=((trace+root)/2,(trace-root)/2)
            cases.append({'integral_updated_first':integrate_first,
                'eigenvalues':[{'real':z.real,'imaginary':z.imag} for z in eigenvalues],
                'spectral_radius':max(abs(z) for z in eigenvalues),
                'locally_schur_stable':max(abs(z) for z in eigenvalues)<1})
        rows.append({'joint':joint['name'],'axis_inertia_kg_m2':effective,'dt_p_over_inertia':dt*p/effective,
            'dt_s':dt,'p_gain':p,'i_gain':ki,'linear_free_wheel_checks':cases})
    return {'scope':'Local unsaturated free-wheel velocity PI analysis only; not proof for contacts, skid, saturation, suspension or the coupled CAD robot',
        'wheel_inertia_method':'I_COM_yy + mass*(COM_x^2+COM_z^2); CAD tensor and joint frame, minimum effective inertia before contact adds load',
        'rows':rows,'all_local_checks_passed':all(c['locally_schur_stable'] for r in rows for c in r['linear_free_wheel_checks'])}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--revision',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    revision=json.loads(args.revision.read_text());digest=hashlib.sha256(args.revision.read_bytes()).hexdigest()
    base,robot=drive_revision(args.profile,revision,args.revision.as_posix(),digest)
    analysis=wheel_pi_analysis(robot)
    if not analysis['all_local_checks_passed']:raise ValueError('Local discrete free-wheel PI check failed')
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'profile.json').write_text(json.dumps(robot.to_dict(),indent=2)+'\n')
    report={'status':'PREPARED_NOT_NATIVE_VALIDATED','source_robot_spec_sha256':base.sha256,'robot_spec_sha256':robot.sha256,
        'revision_sha256':digest,'geometry_inertia_mechanisms_unchanged':True,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'analysis':analysis}
    (args.output/'derivation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
