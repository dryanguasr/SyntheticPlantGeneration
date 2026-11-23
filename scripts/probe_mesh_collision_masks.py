#!/usr/bin/env python3
"""Observe production pair masks on native mesh collisions in one skeleton.

The primitive mask fixture is reused without changing its topology or masks.
Slabs become closed OBJ boxes; the witness is either the original sphere or
a closed OBJ cube with the same vertical extent. It falls only under gravity.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from probe_robot_self_collision import REPO, digest, dump, masked_world
from probe_dynamic_concave_mesh import cube_mesh

CASES = tuple(geometry+'_'+relation for geometry in ('sphere', 'mesh')
              for relation in ('excluded', 'required', 'external'))


def build_world(case, mesh_path, identity, detector='ode'):
    geometry_kind, relation = case.split('_')
    text, masks = masked_world('masked_'+relation, identity)
    sdf = ET.fromstring(text)
    world = sdf.find('world')
    dart = ET.SubElement(world.find('physics'), 'dart')
    ET.SubElement(ET.SubElement(dart, 'solver'), 'solver_type').text = 'pgs'
    ET.SubElement(dart, 'collision_detector').text = detector
    ET.SubElement(world, 'plugin', filename='gz-sim-contact-system', name='gz::sim::systems::Contact')
    for geometry in sdf.findall('.//collision/geometry'):
        box, sphere = geometry.find('box'), geometry.find('sphere')
        if box is not None:
            size = [float(value) for value in box.findtext('size').split()]
        elif sphere is not None and geometry_kind == 'mesh':
            size = [2*float(sphere.findtext('radius'))]*3
        else:
            continue
        for shape in list(geometry):
            geometry.remove(shape)
        mesh = ET.SubElement(geometry, 'mesh')
        ET.SubElement(mesh, 'uri').text = str(mesh_path)
        ET.SubElement(mesh, 'scale').text = ' '.join(str(value/.03) for value in size)
    witness = sdf.find("world/model[@name='probe']/link[@name='ball']")
    sensor = ET.SubElement(witness, 'sensor', name='witness_contact', type='contact')
    ET.SubElement(sensor, 'always_on').text = 'true'
    ET.SubElement(sensor, 'update_rate').text = '100'
    contact = ET.SubElement(sensor, 'contact')
    ET.SubElement(contact, 'collision').text = 'ball'
    ET.SubElement(contact, 'topic').text = '/probe/mesh_mask_contacts'
    ET.indent(sdf, space='  ')
    return ET.tostring(sdf, encoding='unicode')+'\n', masks


def run_case(output, plugins, case):
    directory = output/case
    directory.mkdir()
    protocol = json.loads((output/'protocol.json').read_text())
    identity = digest(output/'protocol.json')
    text, masks = build_world(case, output/'box.obj', identity,protocol['collision_detector'])
    (directory/'probe.sdf').write_text(text)
    dump(directory/'collision_masks.json', masks)
    check = subprocess.run(['gz', 'sdf', '-k', str(directory/'probe.sdf')], capture_output=True, text=True)
    (directory/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:
        raise RuntimeError('Native SDF validation failed')
    os.environ['GZ_PARTITION'] = 'mesh-mask-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(plugins)
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.contacts_pb2 import Contacts
    from google.protobuf.json_format import MessageToDict
    transport, records, contacts, errors = Node(), [], [], []
    lock = threading.Lock()

    def on_joint(message):
        try:
            row = json.loads(message.data)
            if row['robot_spec_sha256'] != identity:
                raise ValueError('Wrong fixture identity')
            with lock:
                records.append(row)
        except (ValueError, KeyError, TypeError) as error:
            errors.append(str(error))

    def on_contact(message):
        with lock:
            contacts.append(MessageToDict(message, preserving_proto_field_name=True))

    for message_type, topic, callback in ((StringMsg, '/probe/contact_observer', on_joint),
                                        (Contacts, '/probe/mesh_mask_contacts', on_contact)):
        if not transport.subscribe(message_type, topic, callback):
            raise RuntimeError('Native subscription failed: '+topic)
    with (directory/'native.log').open('w') as log:
        process = subprocess.Popen(['gz', 'sim', '--force-version', '8','-v','4', '-s', '-r', '--iterations', '2000',
                                    str(directory/'probe.sdf')], stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=5)
            errors.append('native_timeout')
    time.sleep(.15)
    transport.unsubscribe('/probe/contact_observer')
    transport.unsubscribe('/probe/mesh_mask_contacts')
    for name, rows in (('joints', records), ('contacts', contacts)):
        (directory/(name+'.jsonl')).write_text(''.join(json.dumps(row, allow_nan=False)+'\n' for row in rows))
    complete = [row['joints'][0] for row in records if row['sim_time'] >= protocol['steady_start_s']
                and all(row['joints'][0][key+'_available'] for key in ('position', 'velocity', 'wrench'))]
    heights = [1+joint['position'] for joint in complete]
    excluded = case.endswith('_excluded')
    expected = protocol['passed_center_z_m'] if excluded else protocol['blocked_center_z_m']
    contact_count = sum(len(row.get('contact', [])) for row in contacts)
    clean_log=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',(directory/'native.log').read_text(errors='replace'))
    active_detectors=re.findall(r'Using \[([^]]+)\] collision detector',clean_log)
    checks = {'native_exit': code == 0 and not errors,
              'collision_detector_confirmed':bool(active_detectors) and active_detectors[-1]==protocol['collision_detector'],
              'observed_physics': len(complete) >= protocol['minimum_steady_samples'],
              'geometric_outcome': bool(heights) and max(abs(value-expected) for value in heights) <= protocol['height_tolerance_m'],
              'raw_contact_outcome': contact_count == 0 if excluded else contact_count >= protocol['minimum_contact_samples']}
    result = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'case': case, 'checks': checks,
              'expected_center_z_m': expected, 'final_center_z_m': heights[-1] if heights else None,
              'maximum_height_error_m': max((abs(value-expected) for value in heights), default=None),
              'physical_contact_count': contact_count, 'native_exit_code': code,
              'observations': len(records), 'steady_observations': len(complete), 'errors': errors,
              'files_sha256': {path.name: digest(path) for path in directory.iterdir() if path.is_file()}}
    dump(directory/'result.json', result)
    print(case, result['status'], result['final_center_z_m'], contact_count, flush=True)
    return int(result['status'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plugin-dir', type=Path, required=True)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--collision-detector',choices=('ode','fcl','bullet','dart'),default='ode')
    args = parser.parse_args()
    output, plugins = args.output.resolve(), args.plugin_dir.resolve()
    if args.case:
        return run_case(output, plugins, args.case)
    output.mkdir(parents=True, exist_ok=False)
    (output/'box.obj').write_text(cube_mesh())
    dump(output/'protocol.json', {'step_s': .001, 'duration_s': 2, 'solver': 'pgs', 'collision_detector': args.collision_detector,
        'steady_start_s': 1.2, 'minimum_steady_samples': 50, 'minimum_contact_samples': 5,
        'blocked_center_z_m': .6, 'passed_center_z_m': .2, 'height_tolerance_m': .005,
        'cases': list(CASES), 'self_collide': True,
        'scope': 'Production pair masks in one skeleton; mesh slabs versus sphere or mesh cube, including external contact.',
        'inertia_scope': 'Fixture masses/inertias retained from primitive mask controls to isolate collision geometry; not CAD inertia or hardware validation.'})
    frozen = output/'plugins'
    frozen.mkdir()
    for name in ('libUchuvaRobotTelemetrySystem.so', 'build_provenance.json'):
        shutil.copyfile(plugins/name, frozen/name)
    build = json.loads((frozen/'build_provenance.json').read_text())
    if digest(frozen/'libUchuvaRobotTelemetrySystem.so') != build['libraries_sha256']['libUchuvaRobotTelemetrySystem.so']:
        raise ValueError('Observer binary differs from build provenance')
    sources = [Path(__file__), REPO/'scripts/probe_robot_self_collision.py',
               REPO/'scripts/probe_dynamic_concave_mesh.py', REPO/'src/uchuva_gazebo/robot_collision_filters.py']
    for source in sources:
        shutil.copyfile(source, output/source.name)
    dump(output/'provenance.json', {'sources_sha256': {str(path.relative_to(REPO)): digest(path) for path in sources},
        'fixture_mesh_sha256': digest(output/'box.obj'), 'build_provenance_sha256': digest(frozen/'build_provenance.json')})
    for case in CASES:
        subprocess.run([sys.executable, __file__, '--output', str(output), '--plugin-dir', str(frozen), '--case', case], check=False)
    results = {case: json.loads((output/case/'result.json').read_text())
               if (output/case/'result.json').exists() else {'status': 'NOT_OBSERVED'} for case in CASES}
    report = {'status': 'PASS' if all(result['status']=='PASS' for result in results.values()) else 'FAIL',
              'cases': results, 'source_sha256': digest(__file__), 'not_cad_acceptance': True}
    dump(output/'summary.json', report)
    return int(report['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
