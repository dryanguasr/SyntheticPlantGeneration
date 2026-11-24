"""Central build/launch path regressions; no ROS, camera or serial required."""
import contextlib
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from uchuva_gazebo.physalisharvest_launch import (
    NODE_COMMANDS, create_launch_plan, execute_launch_plan,
)
import physalisharvest_ros as launcher


class LaunchPathTests(unittest.TestCase):
    def test_build_and_every_node_use_one_install_outside_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "outputs/central_ros"
            build = create_launch_plan("compilar", root, output_root=output)
            tokens = shlex.split(build.command[-1])
            self.assertEqual(tokens[tokens.index("--install-base") + 1], "outputs/central_ros/install")
            for action in NODE_COMMANDS:
                with self.subTest(action=action):
                    plan = create_launch_plan(action, root, output_root=output)
                    self.assertEqual(plan.setup, build.output_root / "install/setup.bash")
                    self.assertIn("source outputs/central_ros/install/setup.bash", plan.command[-1])
                    self.assertNotIn("source install/setup.bash", plan.command[-1])
                    self.assertEqual(plan.cwd, root.resolve())

    def test_wsl_paths_and_ros_arguments_survive_spaces_and_shell_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo with spaces"
            output = "outputs/ROS student's build"
            arguments = ["--ros-args", "-p", "label:=value;$(not_executed)"]
            plan = create_launch_plan("monitor", root, output_root=output,
                                      platform="win32", node_args=arguments)
            self.assertEqual(plan.command[0:3], ("wsl.exe", "-d", "Ubuntu-24.04"))
            self.assertEqual(plan.command[4], str(root.resolve()))
            tokens = shlex.split(plan.command[-1])
            self.assertIn("outputs/ROS student's build/install/setup.bash", tokens)
            self.assertEqual(tokens[-len(arguments):], arguments)
            self.assertNotIn("-l", plan.command)

    def test_missing_install_never_starts_a_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = create_launch_plan("estado", temporary)
            with patch("uchuva_gazebo.physalisharvest_launch.subprocess.run") as run:
                with self.assertRaisesRegex(FileNotFoundError, "mismo --output-root"):
                    execute_launch_plan(plan)
                run.assert_not_called()

    def test_existing_install_runs_the_upstream_node_without_changing_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = create_launch_plan("estado", temporary)
            plan.setup.parent.mkdir(parents=True)
            plan.setup.write_text("# installation fixture\n", encoding="utf-8")
            with patch("uchuva_gazebo.physalisharvest_launch.subprocess.run") as run:
                run.return_value.returncode = 7
                self.assertEqual(execute_launch_plan(plan), 7)
                run.assert_called_once_with(plan.command, cwd=plan.cwd, check=False)

    def test_read_only_actions_never_launch_controller_or_arm_service(self):
        for action in ("estado", "monitor", "recibir", "fuente"):
            plan = create_launch_plan(action, ROOT)
            command = shlex.split(plan.command[-1])
            self.assertNotIn("controller", command)
            self.assertNotIn("armar", command)
        for action in ("armar", "parar"):
            plan = create_launch_plan(action, ROOT)
            self.assertEqual(shlex.split(plan.command[-1])[-5:],
                             ["ros2", "run", "bench_2wd_drv8833", "session", action])

    def test_invalid_output_or_domain_does_not_create_snapshot_artifacts(self):
        for output in ("contributions/physalisharvest/ros2_ws", "../elsewhere", "outputs", "."):
            with self.subTest(output=output), self.assertRaises(ValueError):
                create_launch_plan("compilar", ROOT, output_root=output)
        for domain in (0, 102, True, "83"):
            with self.subTest(domain=domain), self.assertRaises(ValueError):
                create_launch_plan("estado", ROOT, domain_id=domain)
        with self.assertRaises(ValueError):
            create_launch_plan("compilar", ROOT, node_args=["--install-base", "elsewhere"])

    def test_cli_dry_run_reports_missing_setup_without_launching_or_arming(self):
        with tempfile.TemporaryDirectory() as temporary:
            stream = io.StringIO()
            with patch.object(launcher, "ROOT", Path(temporary)), \
                 patch.object(launcher, "verify_snapshot", return_value={"status": "PASS"}), \
                 patch.object(launcher, "execute_launch_plan") as run, contextlib.redirect_stdout(stream):
                status = launcher.main(["--dry-run", "--output-root", "outputs/review", "estado"])
            self.assertEqual(status, 0)
            run.assert_not_called()
            result = json.loads(stream.getvalue())
            self.assertFalse(result["installation_ready"])
            self.assertEqual(result["execution"], "not_started")
            self.assertEqual(result["action"], "estado")

    def test_cli_rejects_modified_upstream_before_build_or_launch(self):
        with patch.object(launcher, "verify_snapshot", return_value={"status": "FAIL"}), \
             patch.object(launcher, "execute_launch_plan") as run, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(launcher.main(["compilar"]), 2)
            run.assert_not_called()

    def test_cli_options_after_action_share_setup_and_forward_only_explicit_node_args(self):
        stream = io.StringIO()
        with patch.object(launcher, "verify_snapshot", return_value={"status": "PASS"}), \
             patch.object(launcher, "execute_launch_plan") as run, contextlib.redirect_stdout(stream):
            status = launcher.main(["estado", "--dry-run", "--output-root", "outputs/review",
                                    "--domain-id", "97", "--", "--once"])
        self.assertEqual(status, 0)
        run.assert_not_called()
        report = json.loads(stream.getvalue())
        self.assertEqual(shlex.split(report["command"][-1])[-1], "--once")
        self.assertIn("ROS_DOMAIN_ID=97", report["command"][-1])
        self.assertTrue(report["install_setup"].replace("\\", "/").endswith("outputs/review/install/setup.bash"))


if __name__ == "__main__":
    unittest.main()
