#!/usr/bin/env python3
"""Native DART adjacent/nonadjacent contact controls, independent of any CAD.

One passive slider falls under gravity toward a collision slab in its own
skeleton. Reparenting through a collisionless intermediate link changes only
adjacency. A self_collide=false control must pass through the same slab.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
CASES = ('adjacent', 'nonadjacent', 'disabled_control',
         'masked_excluded', 'masked_required', 'masked_external')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def world(adjacent, enabled, identity):
    middle = '' if adjacent else '''<link name="middle"><inertial><mass>.1</mass><inertia><ixx>.001</ixx><iyy>.001</iyy><izz>.001</izz></inertia></inertial></link>
<joint name="middle_anchor" type="fixed"><parent>base</parent><child>middle</child></joint>'''
    parent = 'base' if adjacent else 'middle'
    return f'''<sdf version="1.10"><world name="contact_probe"><gravity>0 0 -9.81</gravity>
<physics name="step" type="ignored"><max_step_size>.001</max_step_size><real_time_factor>1</real_time_factor></physics>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<model name="probe"><self_collide>{str(enabled).lower()}</self_collide>
<link name="base"><inertial><mass>1</mass><inertia><ixx>.1</ixx><iyy>.1</iyy><izz>.1</izz></inertia></inertial>
<collision name="slab"><pose>0 0 .4 0 0 0</pose><geometry><box><size>1 1 .2</size></box></geometry><surface><contact><collide_bitmask>65535</collide_bitmask></contact></surface></collision></link>
<joint name="anchor" type="fixed"><parent>world</parent><child>base</child></joint>{middle}
<link name="ball"><pose>0 0 1 0 0 0</pose><inertial><mass>.2</mass><inertia><ixx>.0008</ixx><iyy>.0008</iyy><izz>.0008</izz></inertia></inertial>
<collision name="ball"><geometry><sphere><radius>.1</radius></sphere></geometry><surface><contact><collide_bitmask>65535</collide_bitmask></contact></surface></collision></link>
<joint name="slider" type="prismatic"><parent>{parent}</parent><child>ball</child><axis><xyz>0 0 1</xyz><limit><lower>-.8</lower><upper>.1</upper><effort>10</effort><velocity>5</velocity></limit><dynamics><damping>.01</damping></dynamics></axis></joint>
<plugin filename="libUchuvaRobotTelemetrySystem.so" name="uchuva::RobotTelemetrySystem"><robot_spec_sha256>{identity}</robot_spec_sha256><topic>/probe/contact_observer</topic><publish_rate>100</publish_rate><joint name="slider"><effort_limit>0</effort_limit></joint></plugin>
</model></world></sdf>'''


def masked_world(case, identity):
    """Use the production compiler; required pairs keep a shared mask bit."""
    from uchuva_gazebo.robot_collision_filters import collision_masks
    data = {'links': [{'name':name,'collisions':[] if name=='middle' else [{}]}
                      for name in ('base','middle','ball','witness')],
            'joints': [{'parent':a,'child':b} for a,b in
                       (('base','middle'),('middle','ball'),('base','witness'))],
            'collision_policy': {'excluded_pairs': [{'links':[a,b]} for a,b in
                       (('base','middle'),('middle','ball'),('base','witness'),('base','ball'))]}}
    masks = collision_masks(data)
    sdf = ET.fromstring(world(False, True, identity))
    model = sdf.find('world/model')
    # Same joint graph and compiled masks in all three controls. Only which
    # stationary slab lies under the falling ball differs.
    base = model.find("link[@name='base']")
    slab = base.find('collision')
    slab.find('pose').text = ('0' if case=='masked_excluded' else '2')+' 0 .4 0 0 0'
    witness = ET.SubElement(model,'link',name='witness')
    inertial = ET.SubElement(witness,'inertial')
    ET.SubElement(inertial,'mass').text='.1'
    tensor = ET.SubElement(inertial,'inertia')
    for name in ('ixx','iyy','izz'):ET.SubElement(tensor,name).text='.001'
    witness_slab = ET.fromstring(ET.tostring(slab))
    witness_slab.find('pose').text = ('0' if case=='masked_required' else '2')+' 0 .4 0 0 0'
    witness.append(witness_slab)
    joint = ET.SubElement(model,'joint',name='witness_anchor',type='fixed')
    ET.SubElement(joint,'parent').text='base';ET.SubElement(joint,'child').text='witness'
    for link in model.findall('link'):
        for collision in link.findall('collision'):
            collision.find('surface/contact/collide_bitmask').text=str(masks[link.get('name')])
    if case=='masked_external':
        external=ET.SubElement(sdf.find('world'),'model',name='external')
        ET.SubElement(external,'static').text='true'
        link=ET.SubElement(external,'link',name='slab')
        collider=ET.fromstring(ET.tostring(slab))
        collider.find('pose').text='0 0 .4 0 0 0'
        collider.find('surface/contact/collide_bitmask').text='65535'
        link.append(collider)
    ET.indent(sdf,space='  ')
    return ET.tostring(sdf,encoding='unicode'), {'compiler_input':data,'compiled_masks':masks}


def run_case(output, case, plugins):
    adjacent, enabled = {'adjacent': (True, True), 'nonadjacent': (False, True), 'disabled_control': (False, False)}.get(case,(False,True))
    directory = output/case
    directory.mkdir()
    fixture = {'case': case, 'adjacent': adjacent, 'self_collide': enabled,
               'ball_initial_center_z_m': 1, 'ball_radius_m': .1, 'slab_top_z_m': .5,
               'slider_lower_m': -.8, 'gravity_m_s2': [0,0,-9.81], 'dt_s': .001}
    identity = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()
    dump(directory/'fixture.json', fixture)
    sdf = directory/'probe.sdf'
    if case.startswith('masked_'):
        text, mask_report = masked_world(case,identity)
        dump(directory/'collision_masks.json',mask_report)
        sdf.write_text(text)
    else:
        sdf.write_text(world(adjacent, enabled, identity))
    check = subprocess.run(['gz', 'sdf', '-k', str(sdf)], capture_output=True, text=True)
    (directory/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:
        raise RuntimeError('Native SDF check failed')
    os.environ['GZ_PARTITION'] = 'uchuva-self-contact-'+uuid.uuid4().hex
    os.environ['GZ_SIM_SYSTEM_PLUGIN_PATH'] = str(plugins)+os.pathsep+os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', '')
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    node, records, errors, mutex = Node(), [], [], threading.Lock()
    def callback(message):
        try:
            row = json.loads(message.data)
            if row['robot_spec_sha256'] != identity:
                raise ValueError('Wrong isolated fixture identity')
            with mutex:
                records.append(row)
        except Exception as error:
            errors.append(str(error))
    if not node.subscribe(StringMsg, '/probe/contact_observer', callback):
        raise RuntimeError('Observer subscription failed')
    with (directory/'native.log').open('w') as log:
        process = subprocess.Popen(['gz', 'sim', '--force-version', '8', '-s', '-r', '--iterations', '2000', str(sdf)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=5)
            errors.append('native timeout')
    time.sleep(.15)
    node.unsubscribe('/probe/contact_observer')
    (directory/'robot_telemetry.jsonl').write_text(''.join(json.dumps(row, allow_nan=False)+'\n' for row in records))
    criteria = json.loads((output/'protocol.json').read_text())
    late = [row['joints'][0] for row in records if row['sim_time'] >= criteria['steady_start_s']]
    complete = [j for j in late if j['position_available'] and j['velocity_available'] and j['wrench_available']]
    heights = [1+j['position'] for j in complete]
    expected = criteria['blocked_center_z_m'] if case in ('nonadjacent','masked_required','masked_external') else criteria['passed_center_z_m']
    checks = {'native_exit': code == 0 and not errors,
              'observed_physics': len(complete) >= criteria['minimum_steady_samples'],
              'contact_outcome': bool(heights) and max(abs(z-expected) for z in heights) <= criteria['height_tolerance_m']}
    result = {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks,
              'expected_center_z_m': expected, 'final_center_z_m': heights[-1] if heights else None,
              'minimum_late_center_z_m': min(heights, default=None), 'maximum_late_center_z_m': max(heights, default=None),
              'observations': len(records), 'late_observations': len(complete), 'errors': errors,
              'sdf_sha256': digest(sdf), 'telemetry_sha256': digest(directory/'robot_telemetry.jsonl')}
    dump(directory/'result.json', result)
    print(case, result['status'], result['final_center_z_m'], flush=True)
    return int(result['status'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--plugin-dir', required=True, type=Path)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    output, plugins = args.output.resolve(), args.plugin_dir.resolve()
    if args.case:
        return run_case(output, args.case, plugins)
    output.mkdir(parents=True, exist_ok=False)
    frozen_plugins=output/'plugins';frozen_plugins.mkdir()
    for name in ('libUchuvaRobotTelemetrySystem.so','build_provenance.json'):
        shutil.copyfile(plugins/name,frozen_plugins/name)
    build=json.loads((frozen_plugins/'build_provenance.json').read_text())
    if build['libraries_sha256']['libUchuvaRobotTelemetrySystem.so']!=digest(frozen_plugins/'libUchuvaRobotTelemetrySystem.so'):
        raise ValueError('Observer binary differs from build provenance')
    plugins=frozen_plugins
    (output/'probe_source.py').write_bytes(Path(__file__).read_bytes())
    compiler=REPO/'src/uchuva_gazebo/robot_collision_filters.py'
    (output/'collision_compiler_source.py').write_bytes(compiler.read_bytes())
    dump(output/'protocol.json', {'steady_start_s': 1.2, 'minimum_steady_samples': 50,
        'blocked_center_z_m': .6, 'passed_center_z_m': .2, 'height_tolerance_m': .005,
        'scope': 'DART native adjacency and exact declared extra pair masks; not CAD geometry or whole-robot validation'})
    dump(output/'provenance.json', {'script_sha256': digest(__file__),
        'observer_sha256': digest(plugins/'libUchuvaRobotTelemetrySystem.so'),
        'collision_compiler_sha256': digest(compiler),
        'gazebo_versions': subprocess.check_output(['gz', 'sim', '--versions'], text=True).strip(),
        'primary_sources': [
            'https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7_7.8.0/dartsim/src/SDFFeatures.cc',
            'https://raw.githubusercontent.com/dartsim/dart/v6.13.2/dart/dynamics/Skeleton.cpp']})
    codes = {}
    for case in CASES:
        codes[case] = subprocess.run([sys.executable, __file__, '--output', str(output), '--plugin-dir', str(plugins), '--case', case]).returncode
    result = {'status': 'PASS' if all(code == 0 for code in codes.values()) else 'FAIL',
              'cases': {case: json.loads((output/case/'result.json').read_text()) if (output/case/'result.json').exists() else {'status': 'NO OBSERVADO'} for case in codes},
              'return_codes': codes, 'not_cad_validation': True}
    dump(output/'summary.json', result)
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
