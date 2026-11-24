#!/usr/bin/env python3
"""Probe DART's native split-and-weld closures with frozen CAD fixtures.

Retains original rejected-SDF/open-control evidence in its existing directory.
No tolerance relaxation, passive position prescription or artificial stiffness.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO/'src'))
from uchuva_gazebo.closed_loops import adapt_loop_joint
import probe_cad_suspension_loop as suspension
import probe_cad_gripper_loop as gripper


def build_world(config, closed):
    original = gripper.world if 'axis_points_cad_m' in config else suspension.world
    root = ET.fromstring(original(config, closed))
    if closed:
        adapt_loop_joint(root.find('world/model'),
                         config.get('closure_joint_name', 'lower_eye_closure'))
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode')+'\n'


def run_case(output, plugins, case):
    suspension.run_case(output, plugins, case, build_world)
    result_path = output/case/'result.json'
    result = json.loads(result_path.read_text())
    result['closure_adapter'] = 'native_dart_split_and_weld' if case == 'closed_loop' else None
    if case == 'closed_loop':
        config = json.loads((output/'fixture.json').read_text())
        protocol = json.loads((output/'protocol.json').read_text())
        name = config.get('closure_joint_name', 'lower_eye_closure')
        model = ET.fromstring(build_world(config, False)).find('world/model')
        # Same original physical body as the rejected direct closure.
        closed_model = ET.fromstring(build_world(config, True)).find('world/model')
        closure = closed_model.find("plugin[@name='uchuva::ClosedLoopSystem']/closure")
        body, auxiliary = closure.findtext('body'), closure.findtext('auxiliary')
        distance, angle = [], []
        for line in (output/case/'poses.jsonl').read_text().splitlines():
            row = json.loads(line)
            if row['sim_time'] < protocol['observe_from_s']:
                continue
            a, b = row['poses'][body], row['poses'][auxiliary]
            distance.append(math.dist(a['xyz_m'], b['xyz_m']))
            dot = abs(sum(x*y for x,y in zip(a['quaternion_xyzw'], b['quaternion_xyzw'])))
            angle.append(2*math.acos(min(1., dot)))
        result['maximum_auxiliary_translation_residual_m'] = max(distance, default=None)
        result['maximum_auxiliary_rotation_residual_rad'] = max(angle, default=None)
        result['auxiliary_weld_observed'] = (bool(distance) and
            max(distance) <= protocol['maximum_closure_residual_m'] and
            max(angle) <= protocol['maximum_auxiliary_rotation_residual_rad'])
        result['native_topology_supported_and_observed'] &= result['auxiliary_weld_observed']
        if not result['native_topology_supported_and_observed']:
            result['status'] = 'FAIL'
        result['interpretation'] = ('Four moving joints are native tree joints; the closing child has a '
            'mass-partitioned auxiliary rigidly reunited by DART WeldJointConstraint. '
            'Both closing-pin and full auxiliary-pose residuals are checked.')
    suspension.dump(result_path, result)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plugin-dir', type=Path, required=True)
    parser.add_argument('--suspension-fixture', type=Path)
    parser.add_argument('--gripper-fixture', type=Path)
    parser.add_argument('--case', choices=['closed_loop','open_control'])
    args = parser.parse_args()
    output, plugins = args.output.resolve(), args.plugin_dir.resolve()
    if args.case:
        return run_case(output, plugins, args.case)
    output.mkdir(parents=True, exist_ok=False)
    frozen = output/'plugins'; frozen.mkdir()
    build = json.loads((plugins/'build_provenance.json').read_text())
    for name in ('libUchuvaRobotTelemetrySystem.so', 'libUchuvaClosedLoopSystem.so'):
        if suspension.sha(plugins/name) != build['libraries_sha256'][name]:
            raise ValueError('Plugin hash disagrees with build provenance')
        shutil.copyfile(plugins/name, frozen/name)
    shutil.copyfile(plugins/'build_provenance.json', frozen/'build_provenance.json')
    for name in ('ClosedLoopSystem.cc', 'RobotTelemetrySystem.cc'):
        if suspension.sha(REPO/'gazebo/harvest_system'/name) != build['source_sha256'][name]:
            raise ValueError('Plugin source differs from build provenance')
    summary = {}
    for name, fixture in (('suspension', args.suspension_fixture), ('gripper', args.gripper_fixture)):
        if fixture is None:
            continue
        directory = output/name; directory.mkdir()
        shutil.copyfile(fixture/'fixture.json', directory/'fixture.json')
        protocol = json.loads((fixture/'protocol.json').read_text())
        # Additional rigid-weld check; original pin tolerances remain untouched.
        protocol['maximum_auxiliary_rotation_residual_rad'] = .001
        protocol['adapter'] = 'native_dart_split_and_weld'
        suspension.dump(directory/'protocol.json', protocol)
        suspension.dump(directory/'source_fixture.json', {'path': str(fixture.resolve()),
            'fixture_sha256': suspension.sha(fixture/'fixture.json'),
            'protocol_sha256': suspension.sha(fixture/'protocol.json')})
        for case in ('closed_loop','open_control'):
            subprocess.run([sys.executable,__file__,'--output',str(directory),
                '--plugin-dir',str(frozen),'--case',case], check=True)
        summary[name] = {case: json.loads((directory/case/'result.json').read_text())
                         for case in ('closed_loop','open_control')}
    sources = [Path(__file__), Path(suspension.__file__), Path(gripper.__file__),
               REPO/'src/uchuva_gazebo/closed_loops.py']
    for source in sources:
        shutil.copyfile(source, output/source.name)
    suspension.dump(output/'provenance.json', {'sources_sha256': {
        str(path.relative_to(REPO)): suspension.sha(path) for path in sources},
        'build_provenance_sha256': suspension.sha(frozen/'build_provenance.json'),
        'native_route_primary_source': 'https://github.com/gazebosim/gz-physics/blob/gz-physics7_7.8.0/dartsim/src/JointFeatures.cc#L431-L477'})
    suspension.dump(output/'summary.json', {'cases': summary,
        'status': 'PASS' if summary and all(case['status']=='PASS'
            for mechanism in summary.values() for case in mechanism.values()) else 'FAIL',
        'scope': 'Frozen CAD mechanisms under the original estimated fixture loads, not hardware calibration'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
