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
import subprocess
import sys
import threading
import time
import uuid


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


def run_case(output, case, plugins):
    adjacent, enabled = {'adjacent': (True, True), 'nonadjacent': (False, True), 'disabled_control': (False, False)}[case]
    directory = output/case
    directory.mkdir()
    fixture = {'case': case, 'adjacent': adjacent, 'self_collide': enabled,
               'ball_initial_center_z_m': 1, 'ball_radius_m': .1, 'slab_top_z_m': .5,
               'slider_lower_m': -.8, 'gravity_m_s2': [0,0,-9.81], 'dt_s': .001}
    identity = hashlib.sha256(json.dumps(fixture, sort_keys=True).encode()).hexdigest()
    dump(directory/'fixture.json', fixture)
    sdf = directory/'probe.sdf'
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
    expected = criteria['blocked_center_z_m'] if case == 'nonadjacent' else criteria['passed_center_z_m']
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
    parser.add_argument('--case', choices=['adjacent', 'nonadjacent', 'disabled_control'])
    args = parser.parse_args()
    output, plugins = args.output.resolve(), args.plugin_dir.resolve()
    if args.case:
        return run_case(output, args.case, plugins)
    output.mkdir(parents=True, exist_ok=False)
    dump(output/'protocol.json', {'steady_start_s': 1.2, 'minimum_steady_samples': 50,
        'blocked_center_z_m': .6, 'passed_center_z_m': .2, 'height_tolerance_m': .005,
        'scope': 'DART native adjacency semantics only; not CAD geometry or whole-robot validation'})
    dump(output/'provenance.json', {'script_sha256': digest(__file__),
        'observer_sha256': digest(plugins/'libUchuvaRobotTelemetrySystem.so'),
        'gazebo_versions': subprocess.check_output(['gz', 'sim', '--versions'], text=True).strip(),
        'primary_sources': [
            'https://raw.githubusercontent.com/gazebosim/gz-physics/gz-physics7_7.8.0/dartsim/src/SDFFeatures.cc',
            'https://raw.githubusercontent.com/dartsim/dart/v6.13.2/dart/dynamics/Skeleton.cpp']})
    codes = {}
    for case in ('adjacent', 'nonadjacent', 'disabled_control'):
        codes[case] = subprocess.run([sys.executable, __file__, '--output', str(output), '--plugin-dir', str(plugins), '--case', case]).returncode
    result = {'status': 'PASS' if all(code == 0 for code in codes.values()) else 'FAIL',
              'cases': {case: json.loads((output/case/'result.json').read_text()) if (output/case/'result.json').exists() else {'status': 'NO OBSERVADO'} for case in codes},
              'return_codes': codes, 'not_cad_validation': True}
    dump(output/'summary.json', result)
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
