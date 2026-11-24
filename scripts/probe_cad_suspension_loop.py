#!/usr/bin/env python3
"""Test one CAD-derived suspension loop in native DART, without hiding failure.

Axes/eye coordinates come from the frozen CAD mapping. Lumped bodies, spring,
damping and stops are explicitly estimated probe parameters, not hardware data.
This tests native loop topology, not a calibrated suspension or contact model.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.robot_kinematics import transform_point


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def node(parent, tag, value=None, **attributes):
    child = ET.SubElement(parent, tag, attributes)
    if value is not None:
        child.text = str(value)
    return child


def numbers(values):
    return ' '.join(format(v, '.17g') for v in values)


def world(config, closed):
    sdf = ET.Element('sdf', version='1.10')
    world = node(sdf, 'world', name='suspension_loop_probe')
    node(world, 'gravity', '0 0 -9.81')
    physics = node(world, 'physics', name='step', type='ignored')
    node(physics, 'max_step_size', .001)
    node(physics, 'real_time_factor', 1)
    node(world, 'plugin', filename='gz-sim-physics-system', name='gz::sim::systems::Physics')
    model = node(world, 'model', name='suspension_probe')
    node(model, 'pose', '0 0 1 0 0 0')
    a, b, c = (config[k] for k in ('pivot_a_base_m', 'upper_eye_b_base_m', 'lower_eye_c_base_m'))
    direction = [v/config['eye_distance_m'] for v in [c[i]-b[i] for i in range(3)]]
    positions = {'chassis': [0,0,0], 'carrier': a, 'shock_upper': b, 'shock_lower': c}
    centers = {'chassis': [0,0,0], 'carrier': [(c[i]-a[i])/2 for i in range(3)],
               'shock_upper': [v*config['eye_distance_m']/4 for v in direction],
               'shock_lower': [-v*config['eye_distance_m']/4 for v in direction]}
    for name, position in positions.items():
        link = node(model, 'link', name=name)
        node(link, 'pose', numbers([*position,0,0,0]))
        inertial = node(link, 'inertial')
        node(inertial, 'pose', numbers([*centers[name],0,0,0]))
        node(inertial, 'mass', config['estimated_masses_kg'][name])
        tensor = node(inertial, 'inertia')
        for key in ('ixx', 'iyy', 'izz'):
            node(tensor, key, config['estimated_diagonal_inertia_kg_m2'][name])
    rows = [('anchor','fixed','world','chassis',[0,0,0], None),
            ('carrier_hinge','revolute','chassis','carrier',a,[0,1,0]),
            ('upper_eye','revolute','chassis','shock_upper',b,[0,1,0]),
            ('telescope','prismatic','shock_upper','shock_lower',b,direction)]
    if closed:
        rows.append(('lower_eye_closure','revolute','shock_lower','carrier',c,[0,1,0]))
    for name, kind, parent, child, point, direction in rows:
        joint = node(model, 'joint', name=name, type=kind)
        node(joint, 'parent', parent)
        node(joint, 'child', child)
        node(joint, 'pose', numbers([*point,0,0,0]), relative_to='__model__')
        if direction is not None:
            axis = node(joint, 'axis')
            node(axis, 'xyz', numbers(direction))
            limits = node(axis, 'limit')
            for key, value in (('lower', -.03 if kind == 'prismatic' else -.4),
                               ('upper', .03 if kind == 'prismatic' else .4), ('effort',1000), ('velocity',1)):
                node(limits, key, value)
            dynamics = node(axis, 'dynamics')
            node(dynamics, 'damping', config['estimated_damping_ns_m'] if kind == 'prismatic' else .2)
            node(dynamics, 'friction', 0)
            if kind == 'prismatic':
                node(dynamics, 'spring_reference', 0)
                node(dynamics, 'spring_stiffness', config['estimated_stiffness_n_m'])
    publisher = node(model, 'plugin', filename='gz-sim-pose-publisher-system', name='gz::sim::systems::PosePublisher')
    for tag, value in (('publish_link_pose','true'),('publish_model_pose','false'),('use_pose_vector_msg','true'),
                       ('static_publisher','false'),('update_frequency',100),('topic','/probe/suspension_poses')):
        node(publisher, tag, value)
    observer = node(model, 'plugin', filename='libUchuvaRobotTelemetrySystem.so', name='uchuva::RobotTelemetrySystem')
    node(observer, 'robot_spec_sha256', config['fixture_sha256'])
    node(observer, 'topic', '/probe/suspension_joints')
    for name, kind, *_ in rows:
        if kind != 'fixed':
            row = node(observer, 'joint', name=name)
            node(row, 'effort_limit', 0)
    ET.indent(sdf, space='  ')
    return ET.tostring(sdf, encoding='unicode')+'\n'


def run_case(output, plugins, case, world_builder=world):
    config = json.loads((output/'fixture.json').read_text())
    criteria = json.loads((output/'protocol.json').read_text())
    directory = output/case
    directory.mkdir()
    closed = case == 'closed_loop'
    sdf = directory/'probe.sdf'
    sdf.write_text(world_builder(config, closed))
    check = subprocess.run(['gz','sdf','-k',str(sdf)], capture_output=True,text=True)
    (directory/'sdf_check.log').write_text(check.stdout+check.stderr)
    os.environ['GZ_PARTITION'] = 'uchuva-cad-loop-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(plugins)+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    node_, poses, joints, errors, lock = Node(), [], [], [], threading.Lock()
    commands = []
    position_schedule = config.get('position_reference_schedule')
    command_publisher = node_.advertise(position_schedule['topic'], Double) if position_schedule else None
    def pose_callback(message):
        with lock:
            if not message.pose:
                errors.append('Empty pose vector')
                return
            # PosePublisher stamps each Pose, not the enclosing Pose_V header.
            stamps = [p.header.stamp.sec+p.header.stamp.nsec*1e-9 for p in message.pose]
            if max(stamps)-min(stamps) > 1e-9:
                errors.append('Pose vector contains inconsistent physics timestamps')
                return
            poses.append({'sim_time': stamps[0],
                'poses': {p.name.rsplit('::',1)[-1]: {'xyz_m':[p.position.x,p.position.y,p.position.z],
                    'quaternion_xyzw':[p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]} for p in message.pose}})
    def joint_callback(message):
        try:
            row = json.loads(message.data)
            if row['robot_spec_sha256'] != config['fixture_sha256']:
                raise ValueError('Wrong fixture hash')
            if position_schedule:
                target = next(step['position_rad'] for step in reversed(position_schedule['steps'])
                              if step['start_s'] <= row['sim_time'])
                message = Double(); message.data = target
                command_publisher.publish(message)
                commands.append({'sim_time': row['sim_time'], 'position_reference_rad': target})
            with lock:
                joints.append(row)
        except Exception as error:
            errors.append(str(error))
    if not node_.subscribe(Pose_V,'/probe/suspension_poses',pose_callback) or not node_.subscribe(StringMsg,'/probe/suspension_joints',joint_callback):
        raise RuntimeError('Native subscriptions failed')
    with (directory/'native.log').open('w') as log:
        process = subprocess.Popen(['gz','sim','--force-version','8','-s','-r','--iterations','2000',str(sdf)],
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:
                code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                code=process.wait(timeout=5)
            errors.append('native_timeout')
    time.sleep(.15)
    node_.unsubscribe('/probe/suspension_poses')
    node_.unsubscribe('/probe/suspension_joints')
    for name, records in (('poses',poses),('joints',joints),('commands',commands)):
        (directory/(name+'.jsonl')).write_text(''.join(json.dumps(row,allow_nan=False)+'\n' for row in records))
    offset = config.get('closure_parent_offset_m') or [c-a for a,c in zip(config['pivot_a_base_m'],config['lower_eye_c_base_m'])]
    residuals = []
    for row in poses:
        if row['sim_time'] < criteria['observe_from_s']:
            continue
        try:
            one = transform_point(row['poses'][config.get('closure_parent_link','carrier')],offset)
            two = transform_point(row['poses'][config.get('closure_child_link','shock_lower')],config.get('closure_child_offset_m',[0,0,0]))
            residuals.append(math.dist(one,two))
        except (KeyError,ValueError) as error:
            errors.append(str(error))
    names = config.get('open_joint_names',['carrier_hinge','upper_eye','telescope'])+([config.get('closure_joint_name','lower_eye_closure')] if closed else [])
    observed = [row for row in joints if row['sim_time'] >= criteria['observe_from_s'] and
                all(any(j['name']==name and j['position_available'] and j['velocity_available'] and j['wrench_available'] for j in row['joints']) for name in names)]
    excursions = {}
    for name in criteria.get('minimum_joint_excursion_rad', {}):
        values = [j['position'] for row in joints if row['sim_time'] >= criteria['observe_from_s']
                  for j in row['joints'] if j['name'] == name and j['position_available']
                  and isinstance(j['position'], (int, float)) and math.isfinite(j['position'])]
        excursions[name] = max(values)-min(values) if values else None
    motion_observed = all(excursions[name] is not None and excursions[name] >= minimum
                          for name, minimum in criteria.get('minimum_joint_excursion_rad', {}).items())
    log_text = re.sub(r'\x1b\[[0-9;]*m', '', (directory/'native.log').read_text(errors='replace'))
    log_text = ' '.join(log_text.split())
    rejected = 'already has a parent joint' in log_text or 'closed kinematic chain' in log_text
    supported = code==0 and check.returncode==0 and not errors and not rejected and len(observed)>=criteria['minimum_samples'] and motion_observed and bool(residuals) and max(residuals)<=criteria['maximum_closure_residual_m']
    result = {'status': 'PASS' if supported else 'FAIL', 'closed_loop_requested':closed,
        'native_topology_supported_and_observed':supported if closed else None,
        'native_exit_code':code, 'sdf_check_code':check.returncode, 'backend_rejected_joint':rejected,
        'all_joint_observation_count':len(observed),'pose_count':len(poses),
        'joint_excursions_rad':excursions,'required_motion_observed':motion_observed,
        'maximum_lower_eye_closure_residual_m':max(residuals,default=None),
        'final_lower_eye_closure_residual_m':residuals[-1] if residuals else None,'errors':errors,
        'interpretation': 'Closed-chain support requires every physical joint and bounded eye residual; process exit zero alone is insufficient.' if closed else 'Open-chain control is deliberately disconnected; its closure residual is not an acceptance failure of this control.',
        'files_sha256':{name:sha(directory/name) for name in ('probe.sdf','sdf_check.log','native.log','poses.jsonl','joints.jsonl','commands.jsonl')}}
    if not closed:
        result['status']='PASS' if code==0 and check.returncode==0 and not rejected and not errors and motion_observed and len(observed)>=criteria['minimum_samples'] else 'FAIL'
    dump(directory/'result.json',result)
    print(case,result['status'],result['maximum_lower_eye_closure_residual_m'],flush=True)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plugin-dir',type=Path,required=True)
    parser.add_argument('--mapping',type=Path,default=REPO/'configs/robots/cad_base_mapping.json')
    parser.add_argument('--case',choices=['closed_loop','open_control'])
    args=parser.parse_args()
    output,plugins=args.output.resolve(),args.plugin_dir.resolve()
    if args.case:
        return run_case(output,plugins,args.case)
    mapping=json.loads(args.mapping.read_text())
    source=next(row for row in mapping['suspension'] if row['name']=='front_right')
    a,b,c=[source[key]['axis_line_point_base_m'] for key in ('chassis_biela_hinge_axis_evidence','chassis_shock_eye_axis_evidence','biela_shock_eye_axis_evidence')]
    config={'scope':'CAD front-right suspension topology only; estimated lumped bodies, no hardware calibration',
        'mapping_sha256':sha(args.mapping),'pivot_a_base_m':a,'upper_eye_b_base_m':b,'lower_eye_c_base_m':c,
        'eye_distance_m':math.dist(b,c),'axes_base':[0,1,0],
        'estimated_masses_kg':{'chassis':1,'carrier':1,'shock_upper':.1,'shock_lower':.1},
        'estimated_diagonal_inertia_kg_m2':{'chassis':.01,'carrier':.01,'shock_upper':.001,'shock_lower':.001},
        'estimated_stiffness_n_m':1500,'estimated_damping_ns_m':25,
        'force_parameter_status':'manual_initial_guess_for_backend_probe_not_measured',
        'preload_n':0,'estimated_slider_travel_m':[-.03,.03],'estimated_pivot_limits_rad':[-.4,.4]}
    config['fixture_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True,exist_ok=False)
    dump(output/'fixture.json',config)
    dump(output/'protocol.json',{'observe_from_s':.2,'minimum_samples':100,'maximum_closure_residual_m':.001,
        'decision':'Native closed loop must instantiate and observe all four moving joints and retain its lower-eye coincidence under gravity. Missing closure or rejected joints means FAIL, regardless of simulator exit code.'})
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    (output/'cad_base_mapping.json').write_bytes(args.mapping.read_bytes())
    dump(output/'provenance.json',{'script_sha256':sha(__file__),'observer_sha256':sha(plugins/'libUchuvaRobotTelemetrySystem.so'),
        'build_provenance_sha256':sha(plugins/'build_provenance.json'),
        'primary_source':'https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7_7.8.0/dartsim/src/SDFFeatures.cc',
        'gazebo_versions':subprocess.check_output(['gz','sim','--versions'],text=True).strip()})
    for case in ('closed_loop','open_control'):
        subprocess.run([sys.executable,__file__,'--output',str(output),'--plugin-dir',str(plugins),'--case',case],check=True)
    results={case:json.loads((output/case/'result.json').read_text()) for case in ('closed_loop','open_control')}
    dump(output/'summary.json',{'native_closed_loop_supported':results['closed_loop']['native_topology_supported_and_observed'],
        'cases':results,'scope':'One CAD-derived suspension loop under explicit estimated loads; not the full robot or measured suspension.'})
    return 0


if __name__=='__main__':
    raise SystemExit(main())
