#!/usr/bin/env python3
"""Derive one frozen, explicitly nonadmissible dynamics diagnostic from SDF.

Supports a changed time step, zero wheel feedback, or disabled contact masks.
Preparation and native execution are separate invocations. No production
profile, CAD asset or acceptance threshold is modified. Linux/WSL is required
only for --run; the installed Gazebo Python transport is used without downloads.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def xml_value(element):
    return [element.tag, sorted(element.attrib.items()), (element.text or '').strip(),
            [xml_value(child) for child in element]]


def derive(source, kind, step=None):
    """Return a derivative plus an exact reversible XML-text change register."""
    result = copy.deepcopy(source)
    changes = []
    undo = []

    def change(element, value, label):
        if element is None:
            raise ValueError('Required source element missing: '+label)
        old = element.text
        element.text = str(value)
        changes.append({'field': label, 'before': old, 'after': element.text})
        undo.append(lambda: setattr(element, 'text', old))

    def upsert(parent, tag, value, label):
        matches = parent.findall(tag)
        if len(matches) > 1:
            raise ValueError('Duplicate observation field: '+label)
        if matches:
            change(matches[0], value, label)
        else:
            element = ET.SubElement(parent, tag)
            element.text = str(value)
            changes.append({'field': label, 'before': None, 'after': element.text})
            undo.append(lambda: parent.remove(element))

    if kind == 'timestep':
        if step is None or not math.isfinite(step) or step <= 0:
            raise ValueError('A positive finite --step is required')
        change(result.find('world/physics/max_step_size'), format(step, '.17g'), 'physics.max_step_size')
        telemetry = 0
        for plugin in result.findall('.//plugin'):
            if plugin.get('filename') == 'libUchuvaRobotTelemetrySystem.so':
                upsert(plugin, 'publish_rate', format(1/step, '.17g'), 'RobotTelemetry.publish_rate')
                telemetry += 1
            if plugin.get('filename') == 'gz-sim-pose-publisher-system':
                upsert(plugin, 'update_frequency', '-1', 'PosePublisher.update_frequency')
        if not telemetry:
            raise ValueError('No per-step robot observer in source world')
    elif kind == 'zero-wheel-feedback':
        selected = [p for p in result.findall('.//plugin')
                    if p.get('filename') == 'gz-sim-joint-controller-system'
                    and p.findtext('joint_name', '').endswith('_wheel_joint')]
        if not selected:
            raise ValueError('No explicit wheel force controllers found')
        for plugin in selected:
            if plugin.findtext('use_force_commands') != 'true':
                raise ValueError('Wheel controller is not a force controller')
            for gain in ('p_gain', 'i_gain', 'd_gain'):
                change(plugin.find(gain), '0', plugin.findtext('joint_name')+'.'+gain)
    elif kind == 'zero-contact-masks':
        selected = result.findall('world/model/link/collision/surface/contact/collide_bitmask')
        if not selected:
            raise ValueError('No existing explicit collision masks found')
        for index, mask in enumerate(selected):
            change(mask, '0', 'collision_mask_'+str(index))
    else:
        raise ValueError('Unknown diagnostic kind')
    frozen = copy.deepcopy(result)
    for reverse in reversed(undo):
        reverse()
    if xml_value(result) != xml_value(source):
        raise AssertionError('Unexpected XML change outside the recorded fields')
    return frozen, changes


def contained_file(root, relative):
    if not relative or '://' in relative or Path(relative).is_absolute():
        raise ValueError('Only portable relative asset paths are supported: '+str(relative))
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Asset path leaves the explicit asset root')
    if not path.is_file():
        raise ValueError('Missing asset: '+str(path))
    return path


def prepare(args):
    source, output = args.source_case.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError('Use a fresh output directory')
    for value in (args.duration, args.wall_timeout):
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Duration and wall timeout must be positive finite values')
    world_file = source/'world.sdf'
    original_hash = sha(world_file)
    root = ET.parse(world_file).getroot()
    derived, changes = derive(root, args.kind, args.step)
    dt = float(derived.findtext('world/physics/max_step_size'))
    iterations = round(args.duration/dt)
    if iterations < 1 or abs(iterations*dt-args.duration) > 1e-10:
        raise ValueError('Duration must equal an integer number of integration steps')
    assets = {u.text: contained_file(args.asset_root, u.text) for u in root.findall('.//mesh/uri')}
    plugin_dir = args.plugin_dir.resolve()
    build = read(plugin_dir/'build_provenance.json')
    libraries = {name: contained_file(plugin_dir, name) for name in build['libraries_sha256']}
    for name, path in libraries.items():
        if sha(path) != build['libraries_sha256'][name]:
            raise ValueError('Native library does not match supplied build provenance: '+name)
    before = {str(p): sha(p) for p in [world_file, plugin_dir/'build_provenance.json', *assets.values(), *libraries.values()]}
    output.mkdir(parents=True)
    for relative, path in assets.items():
        target = output/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (output/'plugins').mkdir()
    for path in [plugin_dir/'build_provenance.json', *libraries.values()]:
        shutil.copyfile(path, output/'plugins'/path.name)
    # Keep original profile bytes as source evidence, never label the altered
    # causal world as an unchanged execution of that physical profile.
    if (source/'robot_resolved.json').exists():
        shutil.copyfile(source/'robot_resolved.json', output/'source_robot_resolved.json')
    ET.indent(derived, space='  ')
    (output/'world.sdf').write_text(ET.tostring(derived, encoding='unicode')+'\n', encoding='utf-8')
    if before != {path:sha(path) for path in before} or sha(world_file) != original_hash:
        raise ValueError('Source changed during preparation')
    files = {str(p.relative_to(output)).replace('\\','/'):sha(p) for p in output.rglob('*') if p.is_file()}
    write(output/'protocol.json', {
        'schema_version':'cad-dynamics-causal/1.0', 'status':'PREREGISTERED_NOT_EXECUTED',
        'scope':'NONADMISSIBLE causal diagnostic; no mobility, contact, cutting or harvesting acceptance',
        'kind':args.kind, 'source_world_sha256':original_hash, 'source_files_sha256':before,
        'recorded_xml_changes':changes, 'exact_reversible_xml_change_guard':True,
        'dt_s':dt, 'duration_s':args.duration, 'iterations':iterations, 'wall_timeout_s':args.wall_timeout,
        'engine':args.engine, 'helper_sha256':sha(__file__), 'files_sha256':files,
        'acceptance_thresholds_changed':False,
        'interpretation':'A stable contact ablation, zero feedback case, or smaller time step is not a production fix or a PASS. Compare complete observations against the declared unchanged source case.'})
    print(json.dumps({'prepared':str(output), 'changes':len(changes), 'iterations':iterations}))


def run(output):
    output = output.resolve()
    protocol = read(output/'protocol.json')
    if (output/'result.json').exists() or (output/'native.log').exists():
        raise ValueError('Preserve completed or interrupted native evidence')
    if protocol['helper_sha256'] != sha(__file__):
        raise ValueError('Helper changed after preregistration')
    for relative,digest in protocol['files_sha256'].items():
        if sha(contained_file(output, relative)) != digest:
            raise ValueError('Frozen fixture changed: '+relative)
    check = subprocess.run(['gz','sdf','-k',str(output/'world.sdf')], capture_output=True, text=True)
    (output/'sdf_check.log').write_text(check.stdout+check.stderr, encoding='utf-8')
    if check.returncode:
        raise ValueError('Invalid derived SDF')
    os.environ['GZ_PARTITION'] = 'cad-causal-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(output/'plugins')
    os.environ['GZ_SIM_RESOURCE_PATH'] = str(output)
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.pose_v_pb2 import Pose_V
    node = Node()
    records, errors, callbacks, subscriptions = [], [], [], []
    started = time.monotonic()
    def receive(topic, pose):
        def callback(message):
            try:
                data = ({'poses':[{'name':p.name, 'sim_time':p.header.stamp.sec+p.header.stamp.nsec*1e-9,
                          'pose':[p.position.x,p.position.y,p.position.z,p.orientation.x,p.orientation.y,p.orientation.z,p.orientation.w]}
                          for p in message.pose]} if pose else json.loads(message.data))
                records.append({'topic':topic,'wall_since_start':time.monotonic()-started,'message':data})
            except Exception as error:
                errors.append(str(error))
        return callback
    root = ET.parse(output/'world.sdf').getroot()
    topics = {}
    for plugin in root.findall('.//plugin'):
        filename = plugin.get('filename','')
        if filename == 'gz-sim-pose-publisher-system':
            if plugin.findtext('use_pose_vector_msg') != 'true':
                raise ValueError('Pose observer must publish Pose_V')
            topics[plugin.findtext('topic')] = True
        elif filename in ('libUchuvaRobotTelemetrySystem.so','libUchuvaGearCouplingSystem.so','libUchuvaClosedLoopSystem.so'):
            topics[plugin.findtext('topic')] = False
        elif filename == 'libUchuvaJointPositionForceSystem.so':
            topics[plugin.findtext('state_topic')] = False
    for topic, pose in topics.items():
        if not topic: continue
        callback = receive(topic, pose)
        callbacks.append(callback)
        if not node.subscribe(Pose_V if pose else StringMsg,topic,callback):
            raise ValueError('Subscription failed: '+topic)
        subscriptions.append(topic)
    if not subscriptions:
        raise ValueError('No explicit observations in fixture')
    command = ['gz','sim','--force-version','8','-s','-r','--iterations',str(protocol['iterations'])]
    if protocol['engine']: command += ['--physics-engine',protocol['engine']]
    command.append(str(output/'world.sdf'))
    with (output/'native.log').open('w',encoding='utf-8') as log:
        process = subprocess.Popen(command,cwd=output,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = process.wait(timeout=protocol['wall_timeout_s'])
        except subprocess.TimeoutExpired:
            errors.append('native_timeout')
            os.killpg(process.pid,signal.SIGINT)
            try: code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                code = process.wait()
    for topic in subscriptions: node.unsubscribe(topic)
    with (output/'observations.jsonl').open('w',encoding='utf-8') as stream:
        for row in records: stream.write(json.dumps(row,allow_nan=False)+'\n')
    write(output/'result.json', {'status':'DIAGNOSTIC_ONLY', 'native_exit_code':code,'errors':errors,
        'wall_seconds':time.monotonic()-started, 'observations':len(records), 'topics':subscriptions,
        'protocol_sha256':sha(output/'protocol.json'),'observations_sha256':sha(output/'observations.jsonl'),
        'native_log_sha256':sha(output/'native.log'), 'helper_sha256':sha(__file__),
        'command':command,'engine_sha256':sha(protocol['engine']) if protocol['engine'] else None,
        'acceptance':'NOT_EVALUATED; preserved thresholds belong to the separate source protocol'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-case',type=Path)
    parser.add_argument('--asset-root',type=Path)
    parser.add_argument('--plugin-dir',type=Path)
    parser.add_argument('--kind',choices=('timestep','zero-wheel-feedback','zero-contact-masks'))
    parser.add_argument('--step',type=float)
    parser.add_argument('--duration',type=float,default=.1)
    parser.add_argument('--wall-timeout',type=float,default=180)
    parser.add_argument('--engine',help='Explicit installed engine-library path; omitted preserves source default')
    parser.add_argument('--run',action='store_true')
    args = parser.parse_args()
    if args.run: run(args.output)
    else:
        if any(x is None for x in (args.source_case,args.asset_root,args.plugin_dir,args.kind)):
            parser.error('Preparation requires --source-case, --asset-root, --plugin-dir and --kind')
        prepare(args)


if __name__ == '__main__': main()
