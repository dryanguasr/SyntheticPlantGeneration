"""Preserve native evidence and verify frozen source assets without Gazebo."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import run_cad_v8_demo_capture as capture_module
from uchuva_gazebo.harvest_pilot import VERSION


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StopBeforeNative(RuntimeError):
    pass


@contextmanager
def prepared_fixture():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        source, take = root / 'source', root / 'take'
        source.mkdir()
        take.mkdir()
        (source / 'source.sdf').write_text('<sdf version="1.9"><world name="source"/></sdf>')
        (source / 'calyx.obj').write_text('# frozen source geometry\n')
        source_manifest = {
            'schema_version': VERSION, 'world_file': 'source.sdf', 'fruits': [], 'bin': {},
            'interaction': {},
            'files_sha256': {name: digest(source / name) for name in ('source.sdf', 'calyx.obj')},
        }
        (source / 'manifest.json').write_text(json.dumps(source_manifest))
        (take / 'trajectory.tsv').write_text('0 0 0 0 0\n1 0 0 0 0\n')
        (take / 'commands.tsv').write_text('')
        world = ET.fromstring('<sdf version="1.9"><world name="demo"><model name="robot"/></world></sdf>')
        plugin = ET.SubElement(world.find('world/model'), 'plugin', name=capture_module.PLAYBACK_SYSTEM)
        for tag, name in (('trajectory_file', 'trajectory.tsv'), ('commands_file', 'commands.tsv'),
                          ('observations_file', 'native_motion.tsv')):
            ET.SubElement(plugin, tag).text = str(take / name)
        ET.ElementTree(world).write(take / 'demo.sdf', encoding='utf-8')
        manifest = {
            'world_file': 'demo.sdf', 'duration_s': 1., 'target_ids': [],
            'source_manifest_sha256': digest(source / 'manifest.json'),
            'files_sha256': {name: digest(take / name)
                             for name in ('demo.sdf', 'trajectory.tsv', 'commands.tsv')},
        }
        (take / 'demo_manifest.json').write_text(json.dumps(manifest))
        yield root, source, take, manifest


class CaptureIntegrityTests(unittest.TestCase):
    def test_reused_take_preserves_native_motion_before_any_process(self):
        with prepared_fixture() as (root, source, take, _):
            evidence = take / 'native_motion.tsv'
            evidence.write_bytes(b'previous native joint observations\n')
            before = evidence.read_bytes()
            with patch.object(capture_module.subprocess, 'run') as check, \
                    patch.object(capture_module.subprocess, 'Popen') as server:
                with self.assertRaisesRegex(FileExistsError, 'evidence already exists'):
                    capture_module.capture(take, source, [], root / 'second_run', 1., record_video=False)
                check.assert_not_called()
                server.assert_not_called()
            self.assertEqual(evidence.read_bytes(), before)
            self.assertFalse((root / 'second_run').exists())

    def test_fresh_take_reaches_validation_without_importing_native_video(self):
        with prepared_fixture() as (root, source, take, _):
            with patch.object(capture_module.subprocess, 'run', side_effect=StopBeforeNative) as check, \
                    patch.object(capture_module.subprocess, 'Popen') as server:
                with self.assertRaises(StopBeforeNative):
                    capture_module.capture(take, source, [], root / 'run', 1., record_video=False)
                self.assertEqual(check.call_args.args[0][:3], ['gz', 'sdf', '-k'])
                server.assert_not_called()
            self.assertFalse((root / 'run').exists())

    def test_capture_rejects_changed_frozen_source_asset_before_native_check(self):
        with prepared_fixture() as (root, source, take, _):
            (source / 'calyx.obj').write_text('# changed after the source was frozen\n')
            with patch.object(capture_module.subprocess, 'run') as check, \
                    patch.object(capture_module.subprocess, 'Popen') as server:
                with self.assertRaisesRegex(ValueError, 'Prepared asset missing, escaped or changed'):
                    capture_module.capture(take, source, [], root / 'run', 1., record_video=False)
                check.assert_not_called()
                server.assert_not_called()
            self.assertFalse((root / 'run').exists())

    def test_evidence_rejects_changed_source_before_loading_fruit_vertices(self):
        with prepared_fixture() as (root, source, _, _):
            (source / 'calyx.obj').write_text('# changed after the native run\n')
            with patch.object(capture_module, 'load_fruit_vertices') as vertices:
                with self.assertRaisesRegex(ValueError, 'Prepared asset missing, escaped or changed'):
                    capture_module.deposit_evidence(source, root / 'run')
                vertices.assert_not_called()
            self.assertFalse((root / 'run').exists())

    def test_intact_source_can_still_be_used_for_offline_evidence(self):
        with prepared_fixture() as (root, source, _, _):
            output = root / 'run'
            output.mkdir()
            (output / 'run.json').write_text(json.dumps({
                'source_manifest_sha256': digest(source / 'manifest.json'), 'target_ids': [],
            }))
            for name in ('telemetry.jsonl', 'events.jsonl'):
                (output / name).write_text('')
            with patch.object(capture_module, 'load_fruit_vertices', return_value={}) as vertices:
                report = capture_module.deposit_evidence(source, output)
                vertices.assert_called_once()
            self.assertEqual(report['deposited_fruit_ids'], [])
            self.assertTrue((output / 'deposit_audit.json').is_file())

    def test_moved_input_or_foreign_output_path_is_rejected(self):
        for tag in ('trajectory_file', 'commands_file', 'observations_file'):
            with self.subTest(tag=tag), prepared_fixture() as (root, source, take, manifest):
                world = ET.parse(take / 'demo.sdf')
                world.find(f'.//plugin/{tag}').text = str(root / 'other_copy.tsv')
                world.write(take / 'demo.sdf', encoding='utf-8')
                manifest['files_sha256']['demo.sdf'] = digest(take / 'demo.sdf')
                (take / 'demo_manifest.json').write_text(json.dumps(manifest))
                with patch.object(capture_module.subprocess, 'run') as check:
                    with self.assertRaisesRegex(ValueError, 'Playback'):
                        capture_module.capture(take, source, [], root / 'run', 1., record_video=False)
                    check.assert_not_called()


@unittest.skipUnless(os.name == 'posix', 'The Gazebo native writer uses POSIX exclusive creation')
class NativeObservationCreationTests(unittest.TestCase):
    """Compile the real exclusive-open helper alone; no Gazebo libraries needed."""

    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('c++') or shutil.which('g++')
        if compiler is None:
            raise unittest.SkipTest('No existing C++ compiler available')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        source = (ROOT / 'gazebo/harvest_system/HarvestDemoPlaybackSystem.cc').read_text(encoding='utf-8')
        start = source.index('std::FILE *OpenExclusiveObservation(')
        brace = source.index('{', start)
        depth, end = 1, brace + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        helper = source[start:end]
        harness = ('#include <cerrno>\n#include <cstdio>\n#include <cstring>\n'
                   '#include <fcntl.h>\n#include <unistd.h>\n#include <memory>\n'
                   '#include <stdexcept>\n#include <string>\n' + helper + '\n' +
                   'int main(int argc, char **argv) { try {\n'
                   'std::unique_ptr<std::FILE, decltype(&std::fclose)> '
                   'file(OpenExclusiveObservation(argv[1]), &std::fclose);\n'
                   'return std::fputs(argv[2], file.get()) < 0 || std::fflush(file.get()) != 0;\n'
                   '} catch (const std::exception &) { return 2; } }\n')
        cls.executable = cls.root / 'native_observation_creation'
        compiled = subprocess.run([compiler, '-std=c++17', '-x', 'c++', '-', '-o', str(cls.executable)],
                                  input=harness, text=True, capture_output=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)

    def test_direct_native_relaunch_does_not_replace_the_previous_trace(self):
        path = self.root / 'previous.tsv'
        first = subprocess.run([str(self.executable), str(path), 'original'], timeout=5)
        second = subprocess.run([str(self.executable), str(path), 'replacement'], timeout=5)
        self.assertEqual((first.returncode, second.returncode), (0, 2))
        self.assertEqual(path.read_text(), 'original')

    def test_concurrent_native_writers_cannot_truncate_or_mix_the_trace(self):
        path = self.root / 'concurrent.tsv'
        children = [subprocess.Popen([str(self.executable), str(path), text]) for text in ('first', 'second')]
        results = [child.wait(timeout=5) for child in children]
        self.assertEqual(sorted(results), [0, 2])
        self.assertIn(path.read_text(), ('first', 'second'))

    def test_native_writer_does_not_follow_an_existing_symlink(self):
        target, link = self.root / 'target.tsv', self.root / 'trace_link.tsv'
        target.write_text('preserved')
        link.symlink_to(target)
        result = subprocess.run([str(self.executable), str(link), 'replacement'], timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(target.read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()
