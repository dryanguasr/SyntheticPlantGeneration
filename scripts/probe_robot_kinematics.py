#!/usr/bin/env python3
"""Compare resolved FK with native Gazebo link poses at measured joint states.

Run with WSL system Python. This isolated fixture fixes the base, removes
collisions and uses zero gravity. It validates the articulated SDF transform
contract, not collision safety, payload capacity or agreement with hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_kinematics import forward_kinematics, compose_poses
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract
from uchuva_gazebo.robot_mechanism_validation import audit_mechanism_sample, audit_passive_gear_commands


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def node(parent, tag, text=None, **attributes):
    child = ET.SubElement(parent, tag, attributes)
    if text is not None:
        child.text = str(text)
    return child


def protocol(robot, continue_after_tracking_failure=False, max_step_size=.001):
    if not math.isfinite(max_step_size) or not 0 < max_step_size <= .001:
        raise ValueError('Explicit integrator step must be finite, positive and no larger than the original 1 ms')
    data = robot.to_dict()
    physics = data.get('physics', {})
    if max_step_size > physics.get('maximum_step_s', .001):
        raise ValueError('Requested integrator step exceeds the explicit profile physics contract')
    movable = [j for j in data['joints'] if j['type'] != 'fixed']
    if not movable or not robot.joint_names:
        raise ValueError('The probe requires movable arm joints')
    if any(not j['limits']['lower'] <= 0 <= j['limits']['upper'] for j in movable):
        raise ValueError('Zero posture is outside a declared joint limit; no implicit reference remapping')
    if set(robot.joint_names) != set(data['control']['arm']):
        raise ValueError('Each arm joint requires its declared force PID controller')
    passive_mechanisms = any(j['group'] == 'passive' for j in movable)
    zero = {j['name']: 0.0 for j in movable if not passive_mechanisms or j['group'] == 'arm'}
    cases = [{'name':'zero','target':zero}]
    for joint in movable:
        if joint['group'] != 'arm':
            continue
        for sign, label in ((1,'positive'),(-1,'negative')):
            room = joint['limits']['upper'] if sign > 0 else -joint['limits']['lower']
            displacement = min(.1, room*.4)
            if displacement < .01:
                raise ValueError(f'{joint["name"]}: insufficient declared range for both diagnostic directions')
            target = dict(zero)
            target[joint['name']] = sign*displacement
            cases.append({'name':joint['name']+'_'+label,'target':target})
    return {
        'schema_version':'native-fk-probe/1.0','cases':cases,
        'position_tolerance_m':1e-5,'orientation_tolerance_rad':1e-4,
        'target_tolerance_rad':.01,'steady_velocity_tolerance_rad_s':.01,
        'minimum_steady_samples':20,'minimum_steady_duration_s':.2,
        'phase_sim_timeout_s':12,'phase_wall_timeout_s':60,
        'initial_wall_timeout_s':20,'max_step_size_s':max_step_size,
        'integrator_revision':'original 1 ms' if max_step_size == .001 else 'explicit smaller step for force-coupled CAD mechanisms; acceptance tolerances unchanged',
        'physics_solver_type':physics.get('solver_type'),
        'physics_collision_detector':physics.get('collision_detector', 'ode'),
        'pose_publish_rate_hz':100,'matched_timestamp_tolerance_ns':0,
        'mechanism_tolerances':{'suspension_position_m':.001,'gripper_position_m':.0005,
                                'closure_orientation_rad':.001,'gear_coordinate_rad':.001},
        'mechanism_scope':'Independent native body/auxiliary poses and observed gear coordinates; FK tree consistency alone cannot prove a closed mechanism.',
        'minimum_evaluated_samples_per_case':20,
        'continue_after_tracking_failure':bool(continue_after_tracking_failure),
        'tracking_joint_names':list(zero),
        'tracking_scope':('Only the five commanded arm joints have position targets. Passive mechanism coordinates are measured for every-link FK and all-moving-joint velocity stability, never commanded to zero.'
                          if passive_mechanisms else 'Historical fixture: all movable coordinates have zero reference except the individual arm displacement.'),
        'base_start_xyz_yaw':[.3,-.2,.7,.35],
        'pose_semantics':'PosePublisher Pose.header stamp; frame_id is model. JointStatePublisher Model.header stamp. Exact nanosecond join, no interpolation.',
        'criterion':'All native links agree with FK(measured q) throughout each observed phase; additionally target reached and stable.',
        'scope':'SDF/FK kinematic consistency only. Base fixed to world; zero gravity; all collisions and sensors removed. No hardware accuracy, self-collision, dynamics or harvest acceptance.',
    }


def make_world(robot, criteria, with_observer):
    model = resolved_robot_model(robot, tuple(criteria['base_start_xyz_yaw']))
    removed = {'collisions':0,'sensors':0,'plugins':[]}
    for link in model.findall('link'):
        for kind in ('collision','sensor'):
            for item in list(link.findall(kind)):
                link.remove(item)
                removed['collisions' if kind == 'collision' else 'sensors'] += 1
    for plugin in list(model.findall('plugin')):
        name = plugin.attrib.get('name','')
        if name.endswith(('JointController','PosePublisher')) or ('RobotTelemetrySystem' in name and not with_observer):
            model.remove(plugin)
            removed['plugins'].append(name)
        elif name.endswith('JointStatePublisher'):
            node(plugin,'update_rate',criteria['pose_publish_rate_hz'])
    anchor = node(model,'joint',name='diagnostic_world_anchor',type='fixed')
    node(anchor,'parent','world')
    node(anchor,'child',robot.to_dict()['root_link'])
    publisher = node(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
    for tag,value in {'publish_link_pose':'true','publish_model_pose':'false','use_pose_vector_msg':'true',
                      'static_publisher':'false','update_frequency':criteria['pose_publish_rate_hz'],
                      'topic':'/probe/fk_link_poses'}.items():
        node(publisher,tag,value)
    sdf = ET.Element('sdf',version='1.10')
    world = node(sdf,'world',name='fk_probe')
    node(world,'gravity','0 0 0')
    physics = node(world,'physics',name='1ms',type='ignored')
    node(physics,'max_step_size',criteria['max_step_size_s'])
    node(physics,'real_time_factor',1)
    if criteria.get('physics_solver_type'):
        dart=node(physics,'dart')
        node(node(dart,'solver'),'solver_type',criteria['physics_solver_type'])
        node(dart,'collision_detector',criteria['physics_collision_detector'])
    node(world,'plugin',filename='gz-sim-physics-system',name='gz::sim::systems::Physics')
    world.append(model)
    return sdf, removed


def quaternion_distance(first, second):
    dot = abs(sum(a*b for a,b in zip(first,second)))
    norms = math.sqrt(sum(a*a for a in first)*sum(b*b for b in second))
    if not norms or not math.isfinite(norms):
        raise ValueError('Invalid observed quaternion')
    return 2*math.acos(min(1,max(-1,dot/norms)))


def compare_sample(robot, joint_row, pose_row):
    data = robot.to_dict()
    expected_names = {j['name'] for j in data['joints'] if j['type'] != 'fixed'}
    if set(joint_row['positions']) != expected_names:
        raise ValueError('Incomplete or unexpected native joint state')
    expected_links = {link['name'] for link in data['links']}
    if set(pose_row['links']) != expected_links:
        raise ValueError('Incomplete or unexpected native link pose set')
    fk = forward_kinematics(robot, joint_row['positions'], base_pose=joint_row['model_pose'], check_limits=False)
    errors = {}
    for name in sorted(expected_links):
        observed = compose_poses(joint_row['model_pose'],pose_row['links'][name])
        predicted = fk[name]
        errors[name] = {
            'position_error_m':math.dist(observed['xyz_m'],predicted['xyz_m']),
            'orientation_error_rad':quaternion_distance(observed['quaternion_xyzw'],predicted['quaternion_xyzw']),
        }
    return errors


def native_probe(robot, output, criteria, plugins):
    # Imports are deliberately inside preflight: Windows pure preparation can
    # record NO EJECUTADO without pretending Gazebo bindings are available.
    from gz.transport13 import Node
    from gz.msgs10.pose_v_pb2 import Pose_V
    from gz.msgs10.model_pb2 import Model
    from gz.msgs10.double_pb2 import Double
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from google.protobuf.json_format import MessageToDict

    data = robot.to_dict()
    contract = resolved_robot_contract(robot)
    os.environ['GZ_PARTITION'] = 'uchuva-fk-'+uuid.uuid4().hex
    if plugins:
        os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(plugins)+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH','')
    transport = Node()
    condition = threading.Condition()
    pose_rows, joint_rows, errors = {}, {}, []
    telemetry_audits = []
    raw_pose = (output/'native_pose_messages.jsonl').open('w')
    raw_joint = (output/'native_joint_messages.jsonl').open('w')
    raw_telemetry = (output/'native_robot_telemetry.jsonl').open('w')

    def ns(header):
        return int(header.stamp.sec)*1_000_000_000+int(header.stamp.nsec)

    def pose(p):
        values = [p.position.x,p.position.y,p.position.z,p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]
        if not all(math.isfinite(x) for x in values):
            raise ValueError('Nonfinite native pose')
        return {'xyz_m':values[:3],'quaternion_xyzw':values[3:]}

    def on_pose(message):
        try:
            stamps = {ns(p.header) for p in message.pose}
            if len(stamps) != 1:
                raise ValueError('Mixed or empty native pose timestamps')
            links = {}
            for p in message.pose:
                header = {r.key:list(r.value) for r in p.header.data}
                if header.get('frame_id') != [data['model_name']]:
                    raise ValueError('Unexpected native parent frame: '+str(header))
                prefix = data['model_name']+'::'
                if not p.name.startswith(prefix):
                    raise ValueError('Native pose from unexpected model')
                name = p.name[len(prefix):]
                if name in links:
                    raise ValueError('Duplicate native link pose')
                links[name] = pose(p)
            stamp = stamps.pop()
            with condition:
                raw_pose.write(json.dumps(MessageToDict(message,preserving_proto_field_name=True))+'\n');raw_pose.flush()
                pose_rows[stamp] = {'links':links}
                condition.notify_all()
        except Exception as error:
            with condition:errors.append(repr(error));condition.notify_all()

    def on_joint(message):
        try:
            if message.name != data['model_name']:
                raise ValueError('Native joint message model mismatch')
            positions, velocities = {}, {}
            for joint in message.joint:
                if not joint.HasField('axis1'):
                    raise ValueError('Native joint lacks axis1')
                if joint.name in positions:
                    raise ValueError('Duplicate native joint')
                positions[joint.name] = joint.axis1.position
                velocities[joint.name] = joint.axis1.velocity
            if not all(math.isfinite(v) for v in list(positions.values())+list(velocities.values())):
                raise ValueError('Nonfinite native joint state')
            with condition:
                raw_joint.write(json.dumps(MessageToDict(message,preserving_proto_field_name=True))+'\n');raw_joint.flush()
                joint_rows[ns(message.header)] = {'positions':positions,'velocities':velocities,'model_pose':pose(message.pose)}
                condition.notify_all()
        except Exception as error:
            with condition:errors.append(repr(error));condition.notify_all()

    def on_telemetry(message):
        try:
            row = json.loads(message.data)
            checked = audit_passive_gear_commands(robot,row)
            with condition:
                raw_telemetry.write(json.dumps(row,allow_nan=False)+'\n');raw_telemetry.flush()
                telemetry_audits.append(checked)
                if not checked['passed']:
                    errors.extend(checked['failures'])
                condition.notify_all()
        except Exception as error:
            with condition:errors.append(repr(error));condition.notify_all()

    pose_topic = '/probe/fk_link_poses'
    joint_topic = contract['topics']['joint_states']
    if not transport.subscribe(Pose_V,pose_topic,on_pose) or not transport.subscribe(Model,joint_topic,on_joint):
        raise RuntimeError('Native subscriptions failed')
    if data.get('gear_couplings') and not transport.subscribe(StringMsg,contract['topics_robot_telemetry'],on_telemetry):
        raise RuntimeError('Native gear motor observation subscription failed')
    publishers = {name:transport.advertise(topic,Double) for name,topic in contract['topics']['joint_commands'].items()}
    log = (output/'native.log').open('w')
    process = subprocess.Popen(['gz','sim','--force-version','8','-s','-r',str(output/'probe.sdf')],
                               stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    results = []
    try:
        deadline = time.monotonic()+criteria['initial_wall_timeout_s']
        with condition:
            while not set(pose_rows).intersection(joint_rows):
                if errors:raise RuntimeError(errors[-1])
                if process.poll() is not None:raise RuntimeError('Gazebo exited before observation')
                if time.monotonic()>deadline:raise TimeoutError('No synchronized native observations')
                condition.wait(.05)
        for case in criteria['cases']:
            with condition:begin = max(set(pose_rows).intersection(joint_rows))
            wall_start = time.monotonic()
            last_sent = 0.0
            last_evaluated = begin
            accepted = []
            evaluated = []
            failure = None
            target_error = None
            speed = None
            while True:
                now = time.monotonic()
                if now-last_sent >= .1:
                    for name,publisher in publishers.items():publisher.publish(Double(data=case['target'][name]))
                    last_sent = now
                with condition:
                    if errors:raise RuntimeError(errors[-1])
                    stamps = sorted(t for t in set(pose_rows).intersection(joint_rows) if t>last_evaluated)
                    samples = [(t,joint_rows[t],pose_rows[t]) for t in stamps]
                for stamp,joints,poses in samples:
                    link_errors = compare_sample(robot,joints,poses)
                    mechanism = audit_mechanism_sample(robot,joints['positions'],poses['links'])
                    row = {'stamp_ns':stamp,'joint_positions':joints['positions'],'link_errors':link_errors,
                           'observed_mechanism':mechanism}
                    evaluated.append(row)
                    position_error = max(x['position_error_m'] for x in link_errors.values())
                    rotation_error = max(x['orientation_error_rad'] for x in link_errors.values())
                    if position_error>criteria['position_tolerance_m'] or rotation_error>criteria['orientation_tolerance_rad']:
                        failure = 'native_fk_mismatch'
                    if not mechanism['passed']:
                        failure = 'native_mechanism_constraint_violation'
                    target_error = max(abs(joints['positions'][name]-value) for name,value in case['target'].items())
                    speed = max(abs(v) for v in joints['velocities'].values())
                    if target_error<=criteria['target_tolerance_rad'] and speed<=criteria['steady_velocity_tolerance_rad_s']:
                        accepted.append(stamp)
                    else:accepted=[]
                    last_evaluated = stamp
                stable = len(accepted)>=criteria['minimum_steady_samples'] and (accepted[-1]-accepted[0])*1e-9>=criteria['minimum_steady_duration_s']
                enough = len(evaluated)>=criteria['minimum_evaluated_samples_per_case']
                if failure or (stable and enough):break
                if process.poll() is not None:
                    failure='native_exit_during_case';break
                if now-wall_start>criteria['phase_wall_timeout_s'] or (last_evaluated-begin)*1e-9>criteria['phase_sim_timeout_s']:
                    failure='tracking_not_settled_within_protocol' if enough else 'observation_timeout';break
                with condition:condition.wait(.025)
            kinematic_consistent = enough and all(
                error['position_error_m'] <= criteria['position_tolerance_m'] and
                error['orientation_error_rad'] <= criteria['orientation_tolerance_rad']
                for sample in evaluated for error in sample['link_errors'].values())
            result = {'name':case['name'],'status':'FAIL' if failure else 'PASS','reason':failure,
                      'target':case['target'],'samples':len(evaluated),'steady_samples':len(accepted),
                      'wall_elapsed_s':time.monotonic()-wall_start,
                      'kinematic_consistency_status':'PASS' if kinematic_consistent else 'FAIL',
                      'mechanism_constraint_status':'PASS' if enough and all(row['observed_mechanism']['passed'] for row in evaluated) else 'FAIL',
                      'target_reached':target_error is not None and target_error<=criteria['target_tolerance_rad'],
                      'target_stable':stable,
                      'last_target_error_rad':target_error,'last_max_joint_speed_rad_s':speed,
                      'max_position_error_m':max((x['position_error_m'] for row in evaluated for x in row['link_errors'].values()),default=None),
                      'max_orientation_error_rad':max((x['orientation_error_rad'] for row in evaluated for x in row['link_errors'].values()),default=None)}
            dump(output/(case['name']+'_result.json'),result)
            (output/(case['name']+'_comparisons.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in evaluated))
            results.append(result)
            print(case['name'],result['status'],flush=True)
            if failure and not (criteria.get('continue_after_tracking_failure') and failure=='tracking_not_settled_within_protocol'):
                break
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGINT)
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        transport.unsubscribe(pose_topic);transport.unsubscribe(joint_topic)
        if data.get('gear_couplings'):transport.unsubscribe(contract['topics_robot_telemetry'])
        raw_pose.close();raw_joint.close();raw_telemetry.close();log.close()
    result_by_name = {case['name']:case for case in results}
    for case in criteria['cases']:
        if case['name'] not in result_by_name:
            results.append({'name':case['name'],'status':'NO EJECUTADO','reason':'Earlier diagnostic failure'})
    follower_commands_passed = not data.get('gear_couplings') or bool(telemetry_audits) and all(row['passed'] for row in telemetry_audits)
    return {'status':'PASS' if all(x['status']=='PASS' for x in results) and follower_commands_passed else 'FAIL','cases':results,
            'kinematic_consistency_status':'PASS' if all(x.get('kinematic_consistency_status')=='PASS' for x in results) else 'FAIL',
            'tracking_status':'PASS' if all(x.get('target_reached') and x.get('target_stable') for x in results) else 'FAIL',
            'mechanism_constraint_status':'PASS' if all(x.get('mechanism_constraint_status')=='PASS' for x in results) else 'FAIL',
            'passive_follower_motor_commands_status':'PASS' if follower_commands_passed else 'FAIL',
            'passive_follower_audited_samples':len(telemetry_audits),
            'callback_errors':errors,'partition':os.environ['GZ_PARTITION'],
            'raw_pose_sha256':digest(output/'native_pose_messages.jsonl'),
            'raw_joint_sha256':digest(output/'native_joint_messages.jsonl'),
            'raw_robot_telemetry_sha256':digest(output/'native_robot_telemetry.jsonl')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True)
    parser.add_argument('--asset-root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plugin-dir',type=Path)
    parser.add_argument('--max-step-size',type=float,default=.001,
                        help='Explicit integrator revision; original acceptance tolerances remain unchanged')
    parser.add_argument('--continue-after-tracking-failure',action='store_true',
                        help='Continue all postures after a tracking timeout; preserve FAIL and unchanged tolerances')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    launched = False
    try:
        robot = resolve_robot_profile(args.profile)
        asset_root = (args.asset_root or REPO).resolve()
        assets = verify_robot_assets(robot,asset_root)
        criteria = protocol(robot,args.continue_after_tracking_failure,args.max_step_size)
        dump(output/'protocol.json',criteria)
        dump(output/'robot_resolved.json',robot.to_dict())
        plugins = args.plugin_dir.resolve() if args.plugin_dir else None
        required = ['libUchuvaRobotTelemetrySystem.so'] if plugins else []
        for key, name in (('closures', 'ClosedLoopSystem'), ('gear_couplings', 'GearCouplingSystem')):
            if robot.to_dict().get(key):
                if not plugins:
                    raise ValueError('Mechanism diagnostic requires explicit frozen plugin directory')
                required.append('libUchuva'+name+'.so')
        if any(settings.get('reference_mode') == 'ramped_position'
               for group in ('arm', 'gripper')
               for settings in robot.to_dict()['control'].get(group, {}).values()):
            if not plugins:
                raise ValueError('Ramped force controller requires an explicit frozen plugin directory')
            required.append('libUchuvaJointPositionForceSystem.so')
        library_hashes = {}
        if plugins:
            build = json.loads((plugins/'build_provenance.json').read_text())
            if (build.get('source_sha256',{}).get('ObservationSchedule.hh') !=
                    digest(REPO/'gazebo/harvest_system/ObservationSchedule.hh')):
                raise ValueError('Native observation schedule differs from its build')
            if ('libUchuvaJointPositionForceSystem.so' in required and
                    build.get('source_sha256', {}).get('PositionForceController.hh') !=
                    digest(REPO/'gazebo/harvest_system/PositionForceController.hh')):
                raise ValueError('Ramped force-controller helper differs from its native build')
            frozen = output/'plugins'
            frozen.mkdir()
            for name in required:
                library = plugins/name
                actual = digest(library)
                source_name = name.removeprefix('libUchuva').removesuffix('.so')+'.cc'
                if (build.get('libraries_sha256',{}).get(name) != actual or
                    build.get('source_sha256',{}).get(source_name) != digest(REPO/'gazebo/harvest_system'/source_name)):
                    raise ValueError('Requested plugin differs from build/source provenance: '+name)
                shutil.copyfile(library,frozen/name)
                if digest(frozen/name) != actual:
                    raise ValueError('Native plugin changed during snapshot')
                library_hashes[name] = actual
            shutil.copyfile(plugins/'build_provenance.json',frozen/'build_provenance.json')
            plugins = frozen
        sdf, removed = make_world(robot,criteria,plugins is not None)
        # Asset hashes were checked against the immutable profile; only fixture
        # URI resolution changes, never geometry scale or source mesh bytes.
        for uri in sdf.findall('.//mesh/uri'):
            uri.text = str((asset_root/uri.text).resolve())
        ET.indent(sdf)
        ET.ElementTree(sdf).write(output/'probe.sdf',encoding='unicode',xml_declaration=True)
        provenance = {'profile_sha256':robot.sha256,'assets_sha256':assets,'diagnostic_derivation':removed,
                      'script_sha256':digest(__file__),'protocol_sha256':digest(output/'protocol.json'),
                      'sdf_sha256':digest(output/'probe.sdf'),
                      'source_sha256':{name:digest(REPO/'src/uchuva_gazebo'/name) for name in ('robot_spec.py','robot_kinematics.py','robot_sdf.py','robot_mechanism_validation.py')},
                      'primary_pose_api_source':'https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/pose_publisher/PosePublisher.cc'}
        if plugins:
            provenance['observer_sha256']=digest(plugins/'libUchuvaRobotTelemetrySystem.so')
            provenance['native_libraries_sha256']=library_hashes
            provenance['native_build_provenance_sha256']=digest(plugins/'build_provenance.json')
        dump(output/'provenance.json',provenance)
        if not shutil.which('gz'):
            raise RuntimeError('Gazebo CLI unavailable; execute with WSL system Python and native bindings')
        check = subprocess.run(['gz','sdf','-k',str(output/'probe.sdf')],capture_output=True,text=True,timeout=20)
        (output/'sdf_check.log').write_text(check.stdout+check.stderr)
        if check.returncode:raise RuntimeError('Native SDF validation failed')
        provenance['gazebo_versions'] = subprocess.check_output(['gz','sim','--versions'],text=True).strip()
        dump(output/'provenance.json',provenance)
        # Check imports before claiming a native run was attempted.
        import gz.transport13  # noqa: F401
        launched = True
        result = native_probe(robot,output,criteria,plugins)
    except Exception as error:
        result = {'status':'FAIL' if launched else 'NO EJECUTADO','reason':repr(error)}
    result['scope']='Native SDF/FK consistency diagnostic; not hardware, collision or harvest validation.'
    dump(output/'summary.json',result)
    print(json.dumps({'output':str(output),'status':result['status'],'reason':result.get('reason')}),flush=True)
    return 0 if result['status']=='PASS' else (1 if launched else 2)


if __name__ == '__main__':
    raise SystemExit(main())
