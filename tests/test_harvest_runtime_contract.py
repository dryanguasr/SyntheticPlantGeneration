"""Adversarial evidence and lifecycle tests; these never run or imitate Gazebo.

All temporary scenes, library bytes and telemetry in this module are explicitly
artificial. They exercise refusal paths and recorded-evidence contracts only.
"""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
from audit_harvest_pilot import audit, strict_json_loads
from run_harvest_pilot import NativePilot, verified_plugin_build
from uchuva_gazebo.harvest_pilot import VERSION, sha256_file


def artificial_package(root):
    package = root / 'package'
    package.mkdir()
    (package / 'harvest.sdf').write_text('<sdf version="1.9"><world name="artificial_fixture"/></sdf>')
    source_files = {name: sha256_file(REPO / name) for name in (
        'gazebo/harvest_system/HarvestSystem.cc', 'gazebo/harvest_system/CMakeLists.txt')}
    manifest = {'schema_version': VERSION, 'fixture_provenance': 'artificial_unit_test_not_native_evidence',
        'world_file': 'harvest.sdf', 'files_sha256': {'harvest.sdf': sha256_file(package / 'harvest.sdf')},
        'source': {'files_sha256': source_files},
        'fruits': [{'id': 'target', 'center_world_m': [.6, 0, .6], 'radius_m': .02}],
        'bin': {'inner_min_m': [.25, .05, .4], 'inner_max_m': [.55, .35, .65]},
        'mission': {'targets': [{'id': 'target'}]}, 'robot_config': {'camera': False}}
    (package / 'manifest.json').write_text(json.dumps(manifest))
    return package, manifest


def artificial_sample(t, phase='baseline', ready=True):
    return {'sim_time': t, 'ready': ready, 'status': 'ready' if ready else 'initializing',
            'phase': phase, 'robot_pose': [0, 0, 0, 0, 0, 0, 1],
            'tool_pose': [0, 0, .6, 0, 0, 0, 1],
            'fruits': [{'id': 'target', 'position': [.6, 0, .6], 'state': 'ATTACHED',
                        'joint_present': True, 'joint_parent': 'plant',
                        'removal_pending': False, 'constraint_error_m': .001}]}


def artificial_run(root, package):
    run = root / 'run'
    run.mkdir()
    metadata = {'mode': 'smoke', 'target_ids': ['target'], 'native_executed': False,
                'forced_gazebo_major': 8, 'manifest_sha256': sha256_file(package / 'manifest.json')}
    (run / 'run.json').write_text(json.dumps(metadata))
    (run / 'outcome.json').write_text(json.dumps({'error': None}))
    samples = [artificial_sample(i*.05) for i in range(51)]
    events = [
        {'phase': 'ack', 'id': 'unknown_fruit', 'accepted': False, 'reason': 'unknown_fruit'},
        {'phase': 'ack', 'id': 'target', 'action': 'arm', 'accepted': False,
         'client_phase': 'negative_far', 'reason': 'cut_point_out_of_range'},
        {'phase': 'ack', 'id': 'target', 'action': 'cut', 'accepted': False,
         'client_phase': 'negative_far', 'reason': 'state_must_be_ARMED'},
    ]
    for name, records in (('telemetry', samples), ('events', events), ('commands', [{'kind': 'artificial'}])):
        (run / f'{name}.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in records))
    (run / 'server.log').write_text('Artificial fixture; no native server was started.\n')
    return run, samples


def callback_fixture():
    """Construct callback state without importing bindings or a simulator."""
    pilot = NativePilot.__new__(NativePilot)
    pilot.condition = threading.Condition()
    pilot._closing = False
    pilot._subscriptions = []
    pilot.phase = 'test'
    pilot.active_target = None
    pilot.joints = {}
    pilot.joint_time = None
    pilot.state = None
    pilot.events = []
    pilot.samples = []
    pilot.callback_error = None
    pilot.recording = False
    pilot.last_state_wall = time.monotonic()
    pilot.streams = {key: io.StringIO() for key in ('telemetry', 'events', 'commands')}
    pilot.manifest = {'robot': {'arm_joint_names': ['yaw', 'shoulder', 'elbow', 'pitch', 'roll']}}
    return pilot


class HarvestRuntimeContractTests(unittest.TestCase):
    def test_blocked_without_gazebo_writes_reauditable_strict_json_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package, _ = artificial_package(root)
            no_tools = root / 'empty_path'
            no_tools.mkdir()
            output = root / 'blocked'
            environment = dict(os.environ, PATH=str(no_tools))
            result = subprocess.run([sys.executable, str(REPO / 'scripts/run_harvest_pilot.py'),
                str(package), '--output', str(output)], env=environment,
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            summary = strict_json_loads((output / 'summary.json').read_text())
            self.assertFalse(summary['passed'])
            self.assertIn('not available', strict_json_loads((output / 'outcome.json').read_text())['error'])
            self.assertFalse(strict_json_loads((output / 'run.json').read_text())['native_executed'])
            self.assertFalse(audit(package, output)['passed'])
            json.dumps(summary, allow_nan=False)

    def test_existing_pass_label_cannot_replace_native_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package, _ = artificial_package(root)
            run, _ = artificial_run(root, package)
            (run / 'summary.json').write_text('{"passed": true}')
            report = audit(package, run)
            self.assertFalse(report['passed'])
            result = {c['name']: c['passed'] for c in report['checks']}
            self.assertTrue(result['attached_without_commands'])
            self.assertFalse(result['native_execution_recorded'])
            self.assertFalse(result['native_plugin_provenance'])

    def test_partial_run_missing_baseline_has_serializable_unknown_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package, _ = artificial_package(root)
            run, samples = artificial_run(root, package)
            for sample in samples:
                sample['phase'] = 'startup'
            (run / 'telemetry.jsonl').write_text(''.join(json.dumps(s)+'\n' for s in samples))
            report = audit(package, run)
            self.assertFalse(report['passed'])
            json.dumps(report, allow_nan=False)
            baseline = next(c for c in report['checks'] if c['name'] == 'attached_without_commands')
            self.assertIsNone(baseline['max_initial_drift_m'])

    def test_missing_truncated_nonobject_or_nonfinite_evidence_fails_without_exception(self):
        for fault in ('missing', 'truncated', 'nonobject', 'nan', 'wrong_manifest'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                package, _ = artificial_package(root)
                run, _ = artificial_run(root, package)
                path = run / 'telemetry.jsonl'
                if fault == 'missing': path.unlink()
                elif fault == 'truncated': path.write_text('{"sim_time":')
                elif fault == 'nonobject': path.write_text('[]\n')
                elif fault == 'nan': path.write_text('{"sim_time": NaN}\n')
                else:
                    metadata = strict_json_loads((run / 'run.json').read_text())
                    metadata['manifest_sha256'] = '0'*64
                    (run / 'run.json').write_text(json.dumps(metadata))
                report = audit(package, run)
                self.assertFalse(report['passed'])
                self.assertIn('error', report)
                json.dumps(report, allow_nan=False)

    def test_audit_cli_missing_run_prints_json_failure_without_creating_false_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package, _ = artificial_package(root)
            absent = root / 'no_such_run'
            result = subprocess.run([sys.executable, str(REPO / 'scripts/audit_harvest_pilot.py'),
                                     str(package), str(absent)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(strict_json_loads(result.stdout)['passed'])
            self.assertFalse(absent.exists())

    def test_plugin_provenance_rejects_omitted_sources_stale_build_or_changed_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, manifest = artificial_package(root)
            build = root / 'build'
            build.mkdir()
            library = build / 'libUchuvaHarvestSystem.so'
            library.write_bytes(b'Artificial library bytes; never load or execute.')
            original = {'library_sha256': sha256_file(library),
                        'source_sha256': {Path(k).name: v for k, v in manifest['source']['files_sha256'].items()}}
            path = build / 'build_provenance.json'
            path.write_text(json.dumps(original))
            self.assertEqual(verified_plugin_build(manifest, build)['library_sha256'], sha256_file(library))
            for sources in ({}, {'HarvestSystem.cc': original['source_sha256']['HarvestSystem.cc']},
                            {**original['source_sha256'], 'HarvestSystem.cc': '0'*64}):
                path.write_text(json.dumps({**original, 'source_sha256': sources}))
                with self.assertRaises(RuntimeError): verified_plugin_build(manifest, build)
            path.write_text(json.dumps(original))
            library.write_bytes(library.read_bytes()+b' changed')
            with self.assertRaises(RuntimeError): verified_plugin_build(manifest, build)

    def test_callbacks_retain_transfer_states_and_refuse_reset_or_event_replay(self):
        pilot = callback_fixture()
        send = lambda s: pilot._state_callback(SimpleNamespace(data=json.dumps(s)))
        send(artificial_sample(0, ready=False))
        self.assertFalse(pilot.samples)
        send(artificial_sample(.1))
        send(artificial_sample(.15, ready=False))
        self.assertEqual(len(pilot.samples), 2)
        self.assertFalse(pilot.samples[-1]['ready'])
        send(artificial_sample(.05))
        self.assertIn('regressed', pilot.callback_error)
        self.assertEqual(len(pilot.samples), 2)
        pilot.callback_error = None
        event = {'seq': 1, 'sim_time': .1, 'phase': 'ack', 'id': 'target',
                 'action': 'arm', 'accepted': True}
        pilot._event_callback(SimpleNamespace(data=json.dumps(event)))
        pilot._event_callback(SimpleNamespace(data=json.dumps(event)))
        self.assertEqual(len(pilot.events), 1)
        self.assertIn('Duplicate', pilot.callback_error)

    def test_native_initializing_null_poses_are_allowed_until_ready(self):
        pilot = callback_fixture()
        pilot.server = SimpleNamespace(poll=lambda: None, returncode=None)
        pilot.started_wall, pilot.wall_timeout = time.monotonic(), 60
        sample = artificial_sample(0, ready=False)
        sample['tool_pose'] = sample['robot_pose'] = None
        pilot._state_callback(SimpleNamespace(data=json.dumps(sample)))
        self.assertFalse(pilot._health()['ready'])
        self.assertFalse(pilot.samples)
        sample.update(ready=True, status='ready', sim_time=.1)
        pilot._state_callback(SimpleNamespace(data=json.dumps(sample)))
        with self.assertRaisesRegex(RuntimeError, 'missing the observed robot pose'):
            pilot._health()

    def test_close_quiesces_callbacks_before_unsubscribing_and_closing_files(self):
        pilot = callback_fixture()
        pilot._subscriptions = ['/state', '/events']
        seen = []
        def unsubscribe(topic):
            seen.append(topic)
            # Model a late callback while the binding drains its subscription.
            pilot._state_callback(SimpleNamespace(data=json.dumps(artificial_sample(1))))
        pilot.node = SimpleNamespace(unsubscribe=unsubscribe)
        pilot.close()
        self.assertEqual(seen, ['/state', '/events'])
        self.assertFalse(pilot.samples)
        for stream in pilot.streams.values(): stream.close()
        pilot._state_callback(SimpleNamespace(data='not valid JSON'))
        pilot._event_callback(SimpleNamespace(data='not valid JSON'))
        self.assertIsNone(pilot.callback_error)
        pilot.close()
        self.assertEqual(len(seen), 2)

    def test_invalid_joint_state_does_not_replace_last_coherent_observation(self):
        pilot = callback_fixture()
        names = pilot.manifest['robot']['arm_joint_names']
        def message(pairs, stamp=1):
            return SimpleNamespace(joint=[SimpleNamespace(name=n, axis1=SimpleNamespace(position=v)) for n, v in pairs],
                header=SimpleNamespace(stamp=SimpleNamespace(sec=stamp, nsec=0)))
        pilot._joint_callback(message([], 0))
        self.assertIsNone(pilot.callback_error)
        self.assertIsNone(pilot.joint_time)
        pilot._joint_callback(message([(name, .1) for name in names]))
        original = dict(pilot.joints)
        for pairs in ([(name, .1) for name in names[:-1]],
                      [(name, .1) for name in names]+[(names[0], .2)],
                      [(name, float('nan')) for name in names]):
            pilot.callback_error = None
            pilot._joint_callback(message(pairs, 2))
            self.assertIsNotNone(pilot.callback_error)
            self.assertEqual(pilot.joints, original)
            self.assertEqual(pilot.joint_time, 1)
        pilot.callback_error = None
        pilot._joint_callback(message([(name, .1) for name in names], 0))
        self.assertIn('regressed', pilot.callback_error)


if __name__ == '__main__':
    unittest.main()
