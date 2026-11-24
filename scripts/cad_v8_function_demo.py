#!/usr/bin/env python3
"""Prepare/run a short native visual demonstration, never a harvest mission.

The fixed-gripper RobotSpec remains authoritative. The three frozen V8 plants
retain their geometry and world poses; only their three detachable fruit models
become explicitly static because this scene has no HarvestSystem or cut commands.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def element(parent, tag, value=None, **attributes):
    child = ET.SubElement(parent, tag, attributes)
    if value is not None:
        child.text = str(value)
    return child


def local_file(root, uri):
    if not isinstance(uri, str) or '\\' in uri or ':' in uri or PurePosixPath(uri).is_absolute() or '..' in PurePosixPath(uri).parts:
        raise ValueError('Asset must be a portable relative URI')
    path = (root/uri).resolve(strict=True)
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Asset escaped its explicit root')
    return path


def xml_value(node):
    return [node.tag, sorted(node.attrib.items()), (node.text or '').strip(),
            [xml_value(child) for child in node]]


def prepare(args):
    from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
    from uchuva_gazebo.robot_sdf import resolved_robot_contract
    from uchuva_gazebo.harvest_pilot import _video_observer
    import probe_cad_mobility as mobility

    output = args.output.resolve()
    if output.exists():
        raise ValueError('Use a fresh preparation directory')
    plants = args.plant_package.resolve()
    manifest = read(plants/'manifest.json')
    acceptance = read(args.acceptance_lock)
    if sha(plants/'manifest.json') != acceptance['frozen_manifest']['sha256']:
        raise ValueError('V8 manifest differs from its original selection lock')
    if [f['id'] for f in manifest['fruits']] != acceptance['plants']['target_ids']:
        raise ValueError('V8 target identities changed')
    for uri, digest in manifest['files_sha256'].items():
        if sha(local_file(plants, uri)) != digest:
            raise ValueError('Frozen V8 file changed: '+uri)
    robot = resolve_robot_profile(args.profile)
    data = robot.to_dict()
    if robot.sha256 != '100172ef1472a624c9e6288065bb82712b4b3ff53dbfab89c92dbb4b5e7d3059':
        raise ValueError('This demonstration requires the explicitly fixed q0 diagnostic profile')
    if data['control'].get('gripper') or any(j['type'] != 'fixed' for j in data['joints'] if j['name'].startswith('gripper_')):
        raise ValueError('Gripper must be physically fixed, with no controller')
    verify_robot_assets(robot, args.asset_root)
    build = read(args.plugin_dir/'build_provenance.json')
    for name in ('RobotTelemetrySystem.cc', 'ClosedLoopSystem.cc', 'JointPositionForceSystem.cc',
                 'PositionForceController.hh', 'ObservationSchedule.hh'):
        if sha(ROOT/'gazebo/harvest_system'/name) != build['source_sha256'][name]:
            raise ValueError('Stale native build source: '+name)
    protocol = {
        'schema_version': 'cad-v8-function-demo/1.0',
        'scope': 'Short native diagnostic visualization; no harvest or full-robot admission',
        'duration_s': 8., 'dt_s': .0001, 'guard_steps': 1, 'wall_timeout_s': 180,
        'start_xyzyaw': [-2., 1.3, .298218017078388, 0.],
        'physics': data['physics'], 'ground_contact': {'mu': .6, 'mu2': .6},
        'phases': [
            {'name': 'settle', 'start_s': 0., 'end_s': 1., 'shoulder_rad': 0., 'linear_m_s': 0.},
            {'name': 'arm_positive', 'start_s': 1., 'end_s': 2.5, 'shoulder_rad': .08, 'linear_m_s': 0.},
            {'name': 'arm_negative', 'start_s': 2.5, 'end_s': 4., 'shoulder_rad': -.08, 'linear_m_s': 0.},
            {'name': 'arm_return', 'start_s': 4., 'end_s': 5.5, 'shoulder_rad': 0., 'linear_m_s': 0.},
            {'name': 'short_straight', 'start_s': 5.5, 'end_s': 6.5, 'shoulder_rad': 0., 'linear_m_s': .05},
            {'name': 'brake', 'start_s': 6.5, 'end_s': 8., 'shoulder_rad': 0., 'linear_m_s': 0.}],
        'corridor_base_x_m': [-2.2, -1.8], 'corridor_base_y_m': [1.0, 1.6],
        'collision_clearance_scope': 'External crop only; conservative envelope, conditional on remaining in the declared corridor. Internal robot validity is evaluated separately.',
        'crop_min_collision_x_m': -.4349853629193746,
        'robot_all_rotation_radius_bound_m': 1.0531759730892796,
        'external_crop_gap_lower_bound_m': .3118386639913458,
        'proof': 'Triangle inequality along every joint translation plus maximum posed local collider radius, including full prismatic limits, bounds every robot point by a root-centred sphere. Field bounding box comes from all frozen native plant meshes/spheres. No collision pair is exempted.',
        'commands': 'Existing native finite-force controllers only; no pose/velocity state writes; no gripper, arm/cut/release interaction command.',
        'fruit_change': 'Only the three detachable fruit model static flags become true. All their geometry, inertia metadata, names and poses remain identical; no fruit detachment is simulated.'}
    observer = {'pose': [-4.8, -2.9, 2.7, 0., .320, .829], 'width': 1280, 'height': 720,
                'fps': 10, 'horizontal_fov_rad': 1.1, 'topic': '/harvest/video_observer/image'}
    root = ET.fromstring(mobility.world(robot, protocol))
    world = root.find('world')
    source_world = ET.parse(plants/manifest['world_file']).getroot().find('world')
    output.mkdir(parents=True)
    assets = {}

    def relocate(tree, source_root, prefix):
        for item in tree.iter():
            if item.tag not in ('uri', 'albedo_map', 'normal_map', 'roughness_map', 'metalness_map'):
                continue
            original = (item.text or '').strip()
            source = local_file(source_root, original)
            target_uri = prefix+'/'+original
            destination = output/target_uri
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(source, destination)
            if sha(destination) != sha(source):
                raise ValueError('Copied asset identity mismatch')
            assets[target_uri] = {'source_uri': original, 'sha256': sha(source)}
            item.text = target_uri

    robot_model = world.find("model[@name='"+data['model_name']+"']")
    relocate(robot_model, args.asset_root.resolve(), 'robot')
    selected = {p['model_name'] for p in manifest['plants']} | {f['model_name'] for f in manifest['fruits']}
    fruit_models = {f['model_name'] for f in manifest['fruits']}
    crop_guards = []
    for model in source_world.findall('model'):
        if model.get('name') not in selected:
            continue
        copied = copy.deepcopy(model)
        if copied.get('name') in fruit_models:
            copied.find('static').text = 'true'
        before = xml_value(copied)
        relocate(copied, plants, 'crop')
        reverse = copy.deepcopy(copied)
        for entry in reverse.iter():
            if entry.tag in ('uri', 'albedo_map', 'normal_map', 'roughness_map', 'metalness_map'):
                entry.text = entry.text.removeprefix('crop/')
        if xml_value(reverse) != before:
            raise ValueError('Unexpected change to V8 model structure')
        crop_guards.append({'model': model.get('name'), 'only_static_change': model.get('name') in fruit_models,
                            'source_model_structure_sha256': hashlib.sha256(json.dumps(xml_value(model)).encode()).hexdigest()})
        world.append(copied)
    if len(crop_guards) != 6:
        raise ValueError('Expected exactly three plants and three preserved fruit bodies')
    # Ground contact stays identical to the commissioning bench. Only its
    # visual and the original scene lighting are added from the V8 package.
    ground = world.find("model[@name='ground']/link")
    for visual in source_world.findall("model[@name='ground']/link/visual"):
        copied = copy.deepcopy(visual)
        relocate(copied, plants, 'crop')
        ground.append(copied)
    for entry in source_world:
        if entry.tag in ('light', 'scene'):
            world.append(copy.deepcopy(entry))
    sensors = element(world, 'plugin', filename='gz-sim-sensors-system', name='gz::sim::systems::Sensors')
    element(sensors, 'render_engine', 'ogre2')
    _video_observer(world, observer)
    if any('HarvestSystem' in p.get('filename', '') for p in world.findall('.//plugin')):
        raise ValueError('A demonstration cannot include HarvestSystem')
    ET.indent(root, space='  ')
    (output/'world.sdf').write_text(ET.tostring(root, encoding='unicode')+'\n', encoding='utf-8')
    write(output/'robot_profile.json', data)
    write(output/'robot_contract.json', resolved_robot_contract(robot))
    write(output/'protocol.json', protocol)
    plugins = output/'plugins'
    plugins.mkdir()
    for name, digest in build['libraries_sha256'].items():
        source = args.plugin_dir/name
        if sha(source) != digest:
            raise ValueError('Native library differs from build provenance')
        shutil.copyfile(source, plugins/name)
    shutil.copyfile(args.plugin_dir/'build_provenance.json', plugins/'build_provenance.json')
    sources = ['scripts/cad_v8_function_demo.py', 'scripts/probe_cad_mobility.py',
               'scripts/harvest_native_video.py', 'scripts/run_neo_flight.py',
               'src/uchuva_gazebo/robot_drive_control.py', 'src/uchuva_gazebo/robot_spec.py',
               'src/uchuva_gazebo/robot_sdf.py', 'src/uchuva_gazebo/robot_kinematics.py',
               'src/uchuva_gazebo/harvest_pilot.py']
    source_hashes = {}
    for name in sources:
        destination = output/'source_snapshot'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
        source_hashes[name] = sha(destination)
    files = {path.relative_to(output).as_posix(): sha(path) for path in output.rglob('*') if path.is_file()}
    write(output/'manifest.json', {'schema_version': 'cad-v8-function-demo-package/1.0',
        'status': 'PREPARED_NOT_EXECUTED', 'robot_spec_sha256': robot.sha256,
        'source_v8_manifest_sha256': sha(plants/'manifest.json'),
        'source_v8_world_sha256': sha(plants/manifest['world_file']),
        'source_v8_all_files_verified': True, 'source_v8_file_count': len(manifest['files_sha256']),
        'plant_seeds': [p['seed'] for p in manifest['plants']], 'target_ids': [f['id'] for f in manifest['fruits']],
        'crop_model_guards': crop_guards, 'asset_identity': assets, 'files_sha256': files,
        'source_sha256': source_hashes, 'video_observer': observer,
        'scope': 'Diagnostic visual evidence only; fixed gripper, static fruit and no harvesting.'})
    print(json.dumps({'prepared': str(output), 'robot_spec_sha256': robot.sha256,
                      'assets': len(assets), 'native_execution': 'NOT_RUN'}))


def run(args):
    from uchuva_gazebo.robot_drive_control import DriveReferenceController
    package = args.package.resolve()
    manifest = read(package/'manifest.json')
    for uri, digest in manifest['files_sha256'].items():
        if sha(local_file(package, uri)) != digest:
            raise ValueError('Prepared file changed: '+uri)
    for uri, digest in manifest['source_sha256'].items():
        if sha(ROOT/uri) != digest:
            raise ValueError('Prepared implementation changed: '+uri)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = read(package/'protocol.json')
    data = read(package/'robot_profile.json')
    contract = read(package/'robot_contract.json')
    os.environ['GZ_PARTITION'] = 'cad-v8-demo-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(package/'plugins')
    os.environ['GZ_SIM_RESOURCE_PATH'] = str(package)
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.double_pb2 import Double
    from gz.msgs10.pose_v_pb2 import Pose_V
    from google.protobuf.json_format import MessageToDict
    from harvest_native_video import NativeVideoRecorder
    transport = Node()
    lock = threading.RLock()
    stop_requested = threading.Event()
    records = {key: [] for key in ('joints', 'poses', 'link_poses', 'force_control', 'commands')}
    errors = []
    drive = data['control']['drive']
    controller = DriveReferenceController(drive)
    arm_publishers = {name: transport.advertise(topic, Double) for name, topic in contract['topics']['joint_commands'].items()}
    wheel_publishers = {name: transport.advertise(data['namespace']+'/drive/'+name+'/cmd_vel', Double) for name in drive['joints']}
    references = dict(data['arm_home_positions'])
    previous_time = 0.

    def poses_callback(message):
        try:
            for p in message.pose:
                if p.name.rsplit('::', 1)[-1] != data['model_name']:
                    continue
                stamp = p.header.stamp.sec+p.header.stamp.nsec*1e-9
                values = [p.position.x, p.position.y, p.position.z, p.orientation.x, p.orientation.y, p.orientation.z, p.orientation.w]
                with lock:
                    controller.observe_pose(stamp, values)
                    records['poses'].append({'sim_time': stamp, 'pose': values})
                    if not (protocol['corridor_base_x_m'][0] <= values[0] <= protocol['corridor_base_x_m'][1]
                            and protocol['corridor_base_y_m'][0] <= values[1] <= protocol['corridor_base_y_m'][1]):
                        raise ValueError('Native chassis left the declared corridor')
        except Exception as error:
            errors.append('pose: '+str(error))
            stop_requested.set()

    def joint_callback(message):
        nonlocal previous_time
        try:
            row = json.loads(message.data)
            if row['robot_spec_sha256'] != manifest['robot_spec_sha256']:
                raise ValueError('Unexpected robot identity')
            stamp = row['sim_time']
            if not math.isfinite(stamp) or stamp < previous_time:
                raise ValueError('Invalid native timestamp')
            phase = next((p for p in protocol['phases'] if p['start_s'] <= stamp < p['end_s']), protocol['phases'][-1])
            with lock:
                dt = stamp-previous_time
                previous_time = stamp
                reference = controller.step(phase['linear_m_s'], 0., stamp)
                for name, publisher in arm_publishers.items():
                    target = phase['shoulder_rad'] if name == 'arm_shoulder_joint' else data['arm_home_positions'][name]
                    rate = data['control']['arm'][name]['command_velocity']
                    references[name] += max(-rate*dt, min(rate*dt, target-references[name]))
                    publisher.publish(Double(data=references[name]))
                for name, value in reference['wheel_velocity_references_rad_s'].items():
                    wheel_publishers[name].publish(Double(data=value))
                records['joints'].append(row)
                records['commands'].append({'sim_time': stamp, 'phase': phase['name'],
                    'arm_references_rad': dict(references), 'drive_reference': reference,
                    'gripper_commands': [], 'interaction_commands': [], 'pose_commands': []})
        except Exception as error:
            errors.append('command: '+str(error))
            stop_requested.set()

    def receive(key, protobuf=False):
        def callback(message):
            try:
                row = MessageToDict(message, preserving_proto_field_name=True) if protobuf else json.loads(message.data)
                with lock:
                    records[key].append(row)
            except Exception as error:
                errors.append(key+': '+str(error))
        return callback

    subscriptions = [(Pose_V, '/probe/cad_model_pose', poses_callback),
        (StringMsg, contract['topics_robot_telemetry'], joint_callback),
        (Pose_V, contract['topics']['link_poses'], receive('link_poses', True))]
    subscriptions += [(StringMsg, topic, receive('force_control')) for topic in contract['topics']['position_force_states'].values()]
    for typ, topic, callback in subscriptions:
        if not transport.subscribe(typ, topic, callback):
            raise ValueError('Native subscription failed: '+topic)
    video = NativeVideoRecorder(output, manifest['video_observer'])
    command = ['gz', 'sim', '--force-version', '8', '-s', '-r', '-v', '3', '--headless-rendering',
               '--iterations', str(round(protocol['duration_s']/protocol['dt_s'])+protocol['guard_steps']), str(package/'world.sdf')]
    write(output/'execution.json', {'command': command, 'package_manifest_sha256': sha(package/'manifest.json'),
        'robot_spec_sha256': manifest['robot_spec_sha256'], 'wall_timeout_s': protocol['wall_timeout_s'],
        'scope': 'Separate diagnostic recording; never changes the principal experiment.'})
    started = time.monotonic()
    with (output/'native.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=package, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic()+protocol['wall_timeout_s']
        while process.poll() is None and not stop_requested.is_set() and time.monotonic() < deadline:
            time.sleep(.05)
        if process.poll() is None:
            errors.append('native_observation_guard_stop' if stop_requested.is_set() else 'native_timeout')
            os.killpg(process.pid, signal.SIGINT)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=5)
        else:
            code = process.returncode
    time.sleep(.15)
    for _, topic, _ in subscriptions:
        transport.unsubscribe(topic)
    for key, values in records.items():
        with (output/(key+'.jsonl')).open('x', encoding='utf-8') as stream:
            for row in values:
                stream.write(json.dumps(row, allow_nan=False)+'\n')
    try:
        video_report = video.close()
    except Exception as error:
        errors.append('video: '+str(error))
        video_report = read(output/'video_report.json') if (output/'video_report.json').exists() else None
    poses = records['poses']
    in_corridor = bool(poses) and all(protocol['corridor_base_x_m'][0] <= p['pose'][0] <= protocol['corridor_base_x_m'][1]
        and protocol['corridor_base_y_m'][0] <= p['pose'][1] <= protocol['corridor_base_y_m'][1] for p in poses)
    if not in_corridor:
        errors.append('Observed chassis left the predeclared external-clearance corridor')
    complete = bool(records['joints']) and records['joints'][-1]['sim_time'] >= protocol['duration_s']-.02
    if not complete:
        errors.append('Incomplete native diagnostic interval')
    write(output/'result.json', {'status': 'DIAGNOSTIC_RECORDED' if code == 0 and not errors else 'DIAGNOSTIC_INCOMPLETE_OR_ERROR',
        'native_exit_code': code, 'wall_seconds': time.monotonic()-started, 'errors': errors,
        'observed_chassis_inside_corridor': in_corridor, 'sample_counts': {key: len(value) for key, value in records.items()},
        'last_sim_time': records['joints'][-1]['sim_time'] if records['joints'] else None,
        'video': video_report, 'robot_spec_sha256': manifest['robot_spec_sha256'],
        'full_robot_or_harvest_acceptance': False,
        'limitations': ['Fixed gripper q0; three target fruits explicitly static', 'No crop interaction, force-grasp, cutting, or long-turn evidence',
                        'Native observations retained for a separate physical audit; successful recording is not physical acceptance'],
        'files_sha256': {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({'output': str(output), 'native_exit_code': code, 'errors': errors}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--package', type=Path)
    for name in ('profile', 'asset-root', 'plant-package', 'acceptance-lock', 'plugin-dir'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args()
    if args.run:
        if args.package is None:
            parser.error('--run requires --package')
        run(args)
    else:
        if any(getattr(args, key) is None for key in ('profile', 'asset_root', 'plant_package', 'acceptance_lock', 'plugin_dir')):
            parser.error('Preparation requires profile, assets, plants, acceptance lock and plugin directory')
        prepare(args)


if __name__ == '__main__':
    main()
