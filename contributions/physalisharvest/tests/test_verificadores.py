import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_repository
import check_git_context


def states(report):
    return {entry['id']: entry['status'] for entry in report.checks}


class RepositoryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name in check_repository.FILES:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# Documento\n', encoding='utf-8')
        for name in check_repository.DIRS:
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def tearDown(self): self.temp.cleanup()

    def test_empty_ros_scaffold_is_skipped(self):
        result = states(check_repository.check(self.root))
        self.assertEqual(result['REP-STRUCTURE'], 'PASS')
        self.assertEqual(result['REP-ROS-MANIFEST'], 'SKIP')

    def test_invalid_inputs_and_broken_link(self):
        (self.root / 'bad.py').write_text('def invalid(\n')
        (self.root / 'bad.json').write_text('{')
        (self.root / 'README.md').write_text('[falta](ausente.md)')
        p = self.root / 'ros2_ws/src/robot_brazo/package.xml'
        p.write_text('<package><name>otro</name></package>')
        result = states(check_repository.check(self.root))
        for key in ('REP-PYTHON', 'REP-JSON', 'REP-LINKS', 'REP-ROS-MANIFEST'):
            self.assertEqual(result[key], 'FAIL')
        (self.root / 'bad.py').write_text('value = 1\n')
        (self.root / 'bad.json').write_text('{}')
        (self.root / 'README.md').write_text('[válido](CONTRIBUTING.md) [raíz](/docs/pruebas/README.md)', encoding='utf-8')
        p.write_text('<package><name>robot_brazo</name></package>')
        result = states(check_repository.check(self.root))
        for key in ('REP-PYTHON', 'REP-JSON', 'REP-LINKS', 'REP-ROS-MANIFEST'):
            self.assertEqual(result[key], 'PASS')

    def test_secrets_and_ai_missing_reference(self):
        (self.root / 'credentials.txt').write_text('password = "' + 'x' * 20 + '"')
        (self.root / 'docs/AI_USAGE.md').write_text('IA')
        (self.root / 'docs/ai_usage.json').write_text(json.dumps({'uses': [{'paths': ['no-existe']}]}))
        result = states(check_repository.check(self.root))
        self.assertEqual(result['REP-CONTENT'], 'FAIL')
        self.assertEqual(result['REP-AI'], 'FAIL')

    def test_sin_falsos_positivos(self):
        (self.root / '.env.example').write_text('EXAMPLE=1\n')
        (self.root / 'README.md').write_text('```\n[x](no-existe.md)\n```\n`[y](falta.md)`\n')
        (self.root / '.gitignore').write_text('node_modules/\n')
        (self.root / 'node_modules').mkdir()
        (self.root / 'node_modules/bad.json').write_text('{')
        result = states(check_repository.check(self.root))
        self.assertEqual(result['REP-CONTENT'], 'PASS')
        self.assertEqual(result['REP-LINKS'], 'PASS')
        self.assertEqual(result['REP-JSON'], 'SKIP')
        (self.root / '.env').write_text('X=1\n')
        self.assertEqual(states(check_repository.check(self.root))['REP-CONTENT'], 'FAIL')

    def test_valid_and_invalid_yaml_when_parser_available(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest('PyYAML no disponible')
        path = self.root / 'config.yaml'
        path.write_text('key: value\n')
        self.assertEqual(states(check_repository.check(self.root))['REP-YAML'], 'PASS')
        path.write_text('key: [\n')
        self.assertEqual(states(check_repository.check(self.root))['REP-YAML'], 'FAIL')


class GitChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.root / 'example').write_text('test')
        self.git('add', 'example')
        self.git('commit', '-qm', 'initial')
        self.git('remote', 'add', 'origin', 'https://github.com/amayadiegoalejandro05/PhysalisHarvest.git')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')

    def tearDown(self): self.temp.cleanup()
    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True)

    def test_old_base_dirty_and_wrong_subsystem(self):
        self.git('switch', '-qc', 'feature/brazo-demo')
        old = self.git('rev-parse', 'HEAD').stdout.strip()
        (self.root / 'example').write_text('new')
        self.git('commit', '-qam', 'new')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('switch', '--detach', old)
        (self.root / 'untracked').write_text('x')
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_HEAD_REF': 'feature/brazo-demo', 'GITHUB_BASE_REF': 'main'}
        result = states(check_git_context.check(self.root, subsystem='vision', environ=env))
        self.assertEqual(result['GIT-BRANCH'], 'SKIP')
        self.assertEqual(result['GIT-WORKTREE'], 'SKIP')
        self.assertEqual(result['GIT-SUBSYSTEM'], 'FAIL')

    def test_divergence_and_conflict_are_advisory(self):
        self.git('switch', '-qc', 'feature/vision-demo')
        (self.root / 'example').write_text('local')
        self.git('commit', '-qam', 'local')
        self.git('switch', '-q', 'main')
        (self.root / 'example').write_text('remote')
        self.git('commit', '-qam', 'remote')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('switch', '-q', 'feature/vision-demo')
        report = check_git_context.check(self.root, target='main', environ={})
        entries = {x['id']: x for x in report.checks}
        self.assertEqual(entries['GIT-TARGET-DIVERGENCE']['status'], 'SKIP')
        self.assertIn('divergente', entries['GIT-TARGET-DIVERGENCE']['explanation'])
        self.assertNotIn('GIT-MAIN-DIVERGENCE', entries)
        self.assertEqual(entries['GIT-CONFLICTS']['status'], 'SKIP')
        self.assertIn('example', entries['GIT-CONFLICTS']['explanation'])
        self.assertEqual(entries['GIT-INCOMING']['status'], 'SKIP')

    def test_borrado_frente_a_modificacion_es_conflicto(self):
        self.git('switch', '-qc', 'feature/vision-demo')
        self.git('rm', '-q', 'example')
        self.git('commit', '-qm', 'delete')
        self.git('switch', '-q', 'main')
        (self.root / 'example').write_text('remote')
        self.git('commit', '-qam', 'modify')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('switch', '-q', 'feature/vision-demo')
        before = sorted(p.name for p in (self.root / '.git/objects').iterdir())
        self.assertEqual(states(check_git_context.check(self.root, target='main', environ={}))['GIT-CONFLICTS'], 'SKIP')
        self.assertEqual(sorted(p.name for p in (self.root / '.git/objects').iterdir()), before)

    def test_cambios_entrantes_no_son_propios(self):
        self.git('switch', '-qc', 'feature/vision-demo')
        own = self.root / 'ros2_ws/src/robot_percepcion_decision/node.py'
        own.parent.mkdir(parents=True)
        own.write_text('value = 1\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'vision')
        self.git('switch', '-q', 'main')
        other = self.root / 'ros2_ws/src/robot_brazo/node.py'
        other.parent.mkdir(parents=True)
        other.write_text('value = 1\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'arm')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('switch', '-q', 'feature/vision-demo')
        entries = {item['id']: item for item in check_git_context.check(self.root, target='main', environ={}).checks}
        self.assertEqual(entries['GIT-CROSS']['status'], 'PASS')
        self.assertNotIn('brazo', entries['GIT-OWNERS']['explanation'])
        self.assertEqual(entries['GIT-INCOMING']['status'], 'PASS')

    def test_vision_interna_no_alerta_contrato(self):
        self.git('switch', '-qc', 'feature/vision-interna')
        path = self.root / 'ros2_ws/src/robot_percepcion_decision/vision.py'
        path.parent.mkdir(parents=True)
        path.write_text('value = 1\n')
        result = {item['id']: item for item in check_git_context.check(self.root, target='main', environ={}).checks}
        self.assertEqual(result['GIT-SHARED']['status'], 'PASS')
        self.assertEqual(result['GIT-CROSS']['status'], 'PASS')
        self.assertIn('vision:', result['GIT-OWNERS']['explanation'])

    def test_rutas_compartidas_alertan_revision_conjunta(self):
        self.git('switch', '-qc', 'feature/vision-demo')
        agents = self.root / 'AGENTS.md'
        agents.write_text('policy')
        self.git('add', 'AGENTS.md')
        result = states(check_git_context.check(self.root, target='main', environ={}))
        self.assertEqual(result['GIT-SHARED'], 'SKIP')
        self.assertEqual(result['GIT-WORKTREE'], 'SKIP')
        self.git('commit', '-qm', 'policy')
        interface = self.root / 'ros2_ws/src/robot_interfaces/msg/Target.msg'
        interface.parent.mkdir(parents=True)
        interface.write_text('float64 x\n')
        entries = {item['id']: item for item in check_git_context.check(self.root, target='main', environ={}).checks}
        self.assertEqual(entries['GIT-SHARED']['status'], 'SKIP')
        self.assertIn('AGENTS.md', entries['GIT-SHARED']['explanation'])
        self.assertIn('robot_interfaces', entries['GIT-SHARED']['explanation'])

    def test_mover_fuera_de_interfaces_es_compartido(self):
        path = self.root / 'ros2_ws/src/robot_interfaces/msg/Target.msg'
        path.parent.mkdir(parents=True)
        path.write_text('float64 x\n')
        self.git('add', '-A')
        self.git('commit', '-qm', 'interface')
        self.git('update-ref', 'refs/remotes/origin/main', 'HEAD')
        self.git('switch', '-qc', 'feature/vision-move')
        destination = self.root / 'ros2_ws/src/robot_percepcion_decision/Target.msg'
        destination.parent.mkdir(parents=True)
        self.git('mv', 'ros2_ws/src/robot_interfaces/msg/Target.msg', str(destination))
        self.git('commit', '-qm', 'move')
        result = states(check_git_context.check(self.root, target='main', environ={}))
        self.assertEqual(result['GIT-SHARED'], 'SKIP')
        self.assertEqual(result['GIT-CROSS'], 'SKIP')

    def test_hardware_pertenece_a_su_subsistema(self):
        self.assertEqual(check_git_context.classify_path('hardware/brazo/pinza.step'), 'brazo')
        self.assertEqual(check_git_context.classify_path('hardware/locomocion/chasis.step'), 'locomocion')
        self.assertEqual(check_git_context.classify_path('firmware/main.c'), 'other')

    def test_cambios_en_dos_subsistemas_son_transversales(self):
        self.git('switch', '-qc', 'feature/vision-brazo')
        for package in ('robot_brazo', 'robot_percepcion_decision'):
            path = self.root / 'ros2_ws/src' / package / 'node.py'
            path.parent.mkdir(parents=True)
            path.write_text('value = 1\n')
        result = states(check_git_context.check(self.root, target='main', environ={}))
        self.assertEqual(result['GIT-SHARED'], 'PASS')
        self.assertEqual(result['GIT-CROSS'], 'SKIP')

    def test_permanent_branches_target_main(self):
        for name, area in (
            ('feat/vision', 'vision'), ('feat/arm', 'brazo'),
            ('feat/locomotion', 'locomocion'), ('feat/2WD', 'locomocion'),
        ):
            with self.subTest(branch=name):
                self.git('switch', '-qc', name)
                report = check_git_context.check(self.root, subsystem=area, environ={})
                entries = {entry['id']: entry for entry in report.checks}
                self.assertEqual(entries['GIT-SUBSYSTEM']['status'], 'PASS')
                self.assertIn('origin/main', entries['GIT-TARGET-DIVERGENCE']['explanation'])
                self.assertEqual('GIT-2WD' in entries, name == 'feat/2WD')
                self.git('switch', '-q', 'main')

    def test_2wd_branch_is_case_sensitive(self):
        self.git('switch', '-qc', 'feat/2wd')
        result = states(check_git_context.check(self.root, environ={}))
        self.assertEqual(result['GIT-SUBSYSTEM'], 'FAIL')
        self.assertNotIn('GIT-2WD', result)

    def test_temporary_branch_infers_destination_and_pr_base_takes_precedence(self):
        for source, destination in (
            ('feature/vision-demo', 'feat/vision'), ('fix/arm-demo', 'feat/arm'),
            ('test/locomotion-demo', 'feat/locomotion'), ('experiment/2WD-demo', 'feat/2WD'),
        ):
            with self.subTest(source=source):
                self.git('switch', '-qc', source)
                self.git('update-ref', 'refs/remotes/origin/' + destination, 'HEAD')
                report = check_git_context.check(self.root, environ={})
                self.assertEqual(states(report)['GIT-TARGET-DIVERGENCE'], 'PASS')
                self.assertEqual(states(report)['GIT-UPSTREAM'], 'SKIP')
                self.assertTrue(any('origin/' + destination in entry['explanation'] for entry in report.checks))
                self.git('switch', '-q', 'main')
        self.git('switch', '-qc', 'chore/repository-reorganization')
        self.assertEqual(states(check_git_context.check(self.root, target='main', environ={}))['GIT-SUBSYSTEM'], 'SKIP')
        self.git('switch', '--detach')
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'pull_request',
               'GITHUB_HEAD_REF': 'experiment/2WD-demo', 'GITHUB_BASE_REF': 'feat/locomotion'}
        report = check_git_context.check(self.root, environ=env)
        target = next(entry for entry in report.checks if entry['id'] == 'GIT-TARGET-DIVERGENCE')
        self.assertIn('origin/feat/locomotion', target['explanation'])

    def test_verifier_uses_only_read_operations(self):
        self.git('switch', '-qc', 'experiment/2WD-read-only')
        self.git('update-ref', 'refs/remotes/origin/feat/2WD', 'HEAD')
        with patch.object(check_git_context, 'git', wraps=check_git_context.git) as git:
            self.assertEqual(states(check_git_context.check(self.root, environ={}))['GIT-ORIGIN'], 'PASS')
        allowed = {'rev-parse', 'remote', 'symbolic-ref', 'rev-list', 'check-ref-format',
                   'merge-base', 'merge-tree', 'diff', 'ls-files'}
        for call in git.call_args_list:
            args = call.args[1:]
            if args[0] == '--no-optional-locks':
                self.assertEqual(args[1], 'status')
            else:
                self.assertIn(args[0], allowed)
            if args[0] == 'remote':
                self.assertEqual(args[1], 'get-url')
            if args[0] == 'merge-tree':
                scratch = Path(call.kwargs['env']['GIT_OBJECT_DIRECTORY'])
                self.assertNotIn(self.root.resolve(), scratch.resolve().parents)

    def test_origin_urls(self):
        for url, expected in (
            ('https://github.com/amayadiegoalejandro05/physalisharvest', 'PASS'),
            ('git@github.com:amayadiegoalejandro05/PhysalisHarvest.git', 'PASS'),
            ('ssh://git@github.com/amayadiegoalejandro05/PhysalisHarvest', 'PASS'),
            ('https://github.com/amayadiegoalejandro05/Robot-Cosechador.git', 'FAIL'),
        ):
            with self.subTest(url=url):
                self.git('remote', 'set-url', 'origin', url)
                self.assertEqual(states(check_git_context.check(self.root, environ={}))['GIT-ORIGIN'], expected)
        self.git('remote', 'set-url', 'origin', 'https://github.com/amayadiegoalejandro05/PhysalisHarvest.git')
        self.git('remote', 'set-url', '--push', 'origin', 'https://example.invalid/other.git')
        self.assertEqual(states(check_git_context.check(self.root, environ={}))['GIT-ORIGIN'], 'FAIL')

    def test_sin_base_comun_no_da_pass(self):
        self.git('update-ref', '-d', 'refs/remotes/origin/main')
        self.git('switch', '-qc', 'feature/vision-demo')
        result = states(check_git_context.check(self.root, target='main', environ={}))
        for key in ('GIT-INCOMING', 'GIT-SHARED', 'GIT-CROSS'):
            self.assertEqual(result[key], 'SKIP')

    def test_detached_pull_request_does_not_claim_source_is_current(self):
        self.git('switch', '--detach')
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_HEAD_REF': 'feature/vision-test', 'GITHUB_BASE_REF': 'main'}
        result = states(check_git_context.check(self.root, environ=env))
        self.assertEqual(result['GIT-TARGET-DIVERGENCE'], 'SKIP')


class RosInventoryChecks(unittest.TestCase):
    def test_package_counts_and_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'ros2_ws/src/robot_brazo'
            package.mkdir(parents=True)
            (package / 'package.xml').write_text('<package><name>robot_brazo</name></package>')
            results = root / 'ros2_ws/build/robot_brazo/test_results'
            results.mkdir(parents=True)
            (results / 'result.xml').write_text('<testsuite><testcase name="one"/></testsuite>')
            script = Path(__file__).resolve().parents[1] / 'scripts/report_ros_packages.py'
            result = subprocess.run([sys.executable, str(script), str(root)], check=True, capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            self.assertIn('Paquetes ROS detectados: 1', result.stdout)
            self.assertIn('brazo: 1 paquetes', result.stdout)
            self.assertIn('1 casos con resultado', result.stdout)
            self.assertIn('visión: SKIP', result.stdout)
            (results / 'result.xml').unlink()
            ctest = root / 'ros2_ws/build/robot_brazo/Testing/20261116-1200'
            ctest.mkdir(parents=True)
            (ctest / 'Test.xml').write_text('<Site><Testing><Test Status="passed"/></Testing></Site>')
            result = subprocess.run([sys.executable, str(script), str(root)], check=True, capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            self.assertIn('1 casos con resultado', result.stdout)
            (package / 'msg').mkdir()
            (package / 'msg/Target.msg').write_text('float64 x\n')
            (package / 'msg/notes.txt').write_text('')
            result = subprocess.run([sys.executable, str(script), '--interfaces', str(root)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.splitlines(), ['robot_brazo/msg/Target'])


if __name__ == '__main__': unittest.main()
