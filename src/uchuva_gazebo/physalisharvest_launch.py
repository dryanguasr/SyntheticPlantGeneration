"""Canonical ROS launch paths for the preserved PhysalisHarvest packages.

Only command planning uses the standard library. ROS is sourced when the
explicit command is executed; the snapshot itself is never rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import sys


VERSION = "physalisharvest-ros-launch/1.0"
DEFAULT_OUTPUT = "outputs/physalisharvest_ros"
PACKAGE_SOURCE = "contributions/physalisharvest/ros2_ws/src"
STATE_TOPIC = "/bench_2wd/drv8833/state"
NODE_COMMANDS = {
    "estado": ("ros2", "topic", "echo", STATE_TOPIC, "std_msgs/msg/String"),
    "monitor": ("ros2", "run", "bench_2wd_drv8833", "monitor"),
    "recibir": ("ros2", "run", "bench_2wd", "receiver"),
    "fuente": ("ros2", "run", "bench_2wd_drv8833", "aruco_source"),
    "controlador": ("ros2", "run", "bench_2wd_drv8833", "controller"),
    "armar": ("ros2", "run", "bench_2wd_drv8833", "session", "armar"),
    "parar": ("ros2", "run", "bench_2wd_drv8833", "session", "parar"),
}
ACTIONS = ("compilar", *NODE_COMMANDS)


@dataclass(frozen=True)
class LaunchPlan:
    action: str
    command: tuple[str, ...]
    cwd: Path
    output_root: Path
    setup: Path

    def as_dict(self):
        return {
            "schema_version": VERSION, "action": self.action,
            "command": list(self.command), "cwd": str(self.cwd),
            "output_root": str(self.output_root), "install_setup": str(self.setup),
            "installation_ready": self.setup.is_file(),
            "execution": "not_started", "snapshot_modified": False,
        }


def create_launch_plan(action, repository, *, output_root=DEFAULT_OUTPUT,
                       distro="Ubuntu-24.04", domain_id=83, node_args=(),
                       platform=None):
    """Use the same install path for build and all explicit ROS commands.

    Paths passed to Bash are relative to the repository working directory.
    On Windows WSL selects that directory with --cd, so no drive/mount-root
    assumptions or unquoted interpolation of Windows paths are needed.
    """
    if action not in ACTIONS:
        raise ValueError("Unknown PhysalisHarvest ROS action")
    if type(domain_id) is not int or not 1 <= domain_id <= 101:
        raise ValueError("ROS domain must be an integer from 1 to 101")
    if not isinstance(distro, str) or not distro.strip() or "\x00" in distro:
        raise ValueError("An explicit WSL distribution name is required")
    if not isinstance(node_args, (list, tuple)) or any(not isinstance(v, str) or "\x00" in v for v in node_args):
        raise ValueError("ROS arguments must be a sequence of strings")
    if action == "compilar" and node_args:
        raise ValueError("Build paths are configured with --output-root, not ROS arguments")
    root = Path(repository).resolve()
    output = (root / output_root).resolve()
    if output == root / "outputs" or not output.is_relative_to(root / "outputs"):
        raise ValueError("ROS artifacts must stay in a dedicated directory under outputs/")
    relative = output.relative_to(root).as_posix()
    setup = output / "install/setup.bash"
    environment = (
        "source /opt/ros/jazzy/setup.bash && "
        + shlex.join(("export", f"ROS_DOMAIN_ID={domain_id}",
                      "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
                      "PYTHONDONTWRITEBYTECODE=1", f"ROS_LOG_DIR={relative}/ros_logs"))
    )
    if action == "compilar":
        tokens = ("colcon", "--log-base", relative + "/log", "build",
                  "--base-paths", PACKAGE_SOURCE,
                  "--packages-select", "bench_2wd", "bench_2wd_drv8833",
                  "--build-base", relative + "/build", "--install-base", relative + "/install")
        shell = environment + " && " + shlex.join(tokens)
    else:
        shell = (environment + " && source " + shlex.quote(relative + "/install/setup.bash")
                 + " && exec " + shlex.join((*NODE_COMMANDS[action], *node_args)))
    if (platform or sys.platform) == "win32":
        command = ("wsl.exe", "-d", distro, "--cd", str(root), "--", "bash", "-c", shell)
    else:
        command = ("bash", "-c", shell)
    return LaunchPlan(action, command, root, output, setup)


def execute_launch_plan(plan):
    """Execute only after a completed installation; inherit normal stdin/out."""
    if plan.action != "compilar" and not plan.setup.is_file():
        raise FileNotFoundError(
            f"Falta {plan.setup}. Ejecuta compilar con el mismo --output-root antes de iniciar ROS."
        )
    return subprocess.run(plan.command, cwd=plan.cwd, check=False).returncode
