#!/usr/bin/env python3
"""Native, isolated actuator/observer probe. This fixture is NOT the CAD robot.

Run with WSL system Python after build_harvest_plugin.sh. Preserves SDF, raw
observations, preregistered criteria, native logs and binary/source hashes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def world(mass, effort, robot_hash):
    inertia = mass * (.3**2 + .04**2) / 12
    return f'''<sdf version="1.10"><world name="actuation_probe">
<gravity>0 0 -9.81</gravity>
<physics name="step" type="ignored"><max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor></physics>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<model name="probe"><pose>0 0 1 0 0 0</pose>
<link name="base"><inertial><mass>1</mass><inertia><ixx>0.01</ixx><iyy>0.01</iyy><izz>0.01</izz></inertia></inertial></link>
<joint name="anchor" type="fixed"><parent>world</parent><child>base</child></joint>
<link name="bar"><inertial><pose>.15 0 0 0 0 0</pose><mass>{mass}</mass><inertia><ixx>{mass*.04**2/6}</ixx><iyy>{inertia}</iyy><izz>{inertia}</izz></inertia></inertial>
<visual name="bar"><pose>.15 0 0 0 0 0</pose><geometry><box><size>.3 .04 .04</size></box></geometry></visual></link>
<joint name="hinge" type="revolute"><parent>base</parent><child>bar</child><axis><xyz>0 1 0</xyz><limit><lower>-1.2</lower><upper>1.2</upper><effort>{effort}</effort><velocity>2</velocity></limit><dynamics><damping>.02</damping></dynamics></axis></joint>
<plugin filename="gz-sim-joint-position-controller-system" name="gz::sim::systems::JointPositionController"><joint_name>hinge</joint_name><topic>/probe/position</topic><initial_position>-.3</initial_position><use_velocity_commands>false</use_velocity_commands><p_gain>40</p_gain><i_gain>0</i_gain><d_gain>3</d_gain><cmd_min>{-effort}</cmd_min><cmd_max>{effort}</cmd_max></plugin>
<plugin filename="libUchuvaRobotTelemetrySystem.so" name="uchuva::RobotTelemetrySystem"><robot_spec_sha256>{robot_hash}</robot_spec_sha256><topic>/probe/robot_telemetry</topic><publish_rate>100</publish_rate><joint name="hinge"><effort_limit>{effort}</effort_limit></joint></plugin>
</model></world></sdf>'''


def run_case(root, name, mass, effort, plugin_dir, criteria):
    output = root / name
    output.mkdir()
    spec = {"fixture": "one_hinge_gravity_probe_not_CAD", "mass_kg": mass,
            "effort_limit_nm": effort, "target_rad": -.3, "duration_s": 4.0}
    robot_hash = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    dump(output / "effective_fixture.json", spec)
    sdf = output / "probe.sdf"
    sdf.write_text(world(mass, effort, robot_hash))
    partition = "uchuva-actuation-" + uuid.uuid4().hex
    os.environ["GZ_PARTITION"] = partition
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    node = Node()
    observations, callback_errors = [], []
    lock = threading.Lock()
    def callback(message):
        try:
            data = json.loads(message.data)
            if data["robot_spec_sha256"] != robot_hash:
                raise ValueError("robot hash mismatch")
            with lock:
                observations.append(data)
        except Exception as error:
            callback_errors.append(str(error))
    if not node.subscribe(StringMsg, "/probe/robot_telemetry", callback):
        raise RuntimeError("Telemetry subscription failed")
    environment = dict(os.environ)
    environment["GZ_SIM_SYSTEM_PLUGIN_PATH"] = str(plugin_dir) + os.pathsep + environment.get("GZ_SIM_SYSTEM_PLUGIN_PATH", "")
    command = ["gz", "sim", "--force-version", "8", "-s", "-r", "--iterations", "4000", str(sdf)]
    with (output / "native.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env=environment, start_new_session=True)
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                code = process.wait(timeout=5)
            callback_errors.append("native_timeout")
    time.sleep(.15)
    node.unsubscribe("/probe/robot_telemetry")
    with (output / "robot_telemetry.jsonl").open("w") as stream:
        for row in observations:
            stream.write(json.dumps(row, allow_nan=False) + "\n")
    late = [r["joints"][0] for r in observations if r["sim_time"] >= criteria["steady_start_s"]]
    complete = [j for j in late if j["position_available"] and j["velocity_available"] and j["force_command_available"] and j["wrench_available"]]
    final_error = abs(complete[-1]["position"] + .3) if complete else None
    peak_command = max((r["joints"][0]["max_abs_force_command_window"] for r in observations), default=None)
    peak_velocity = max((r["joints"][0]["max_abs_velocity_window"] for r in observations), default=None)
    saturated = sum(r["joints"][0]["saturated_steps"] for r in observations)
    checks = {
        "native_exit": code == 0 and not callback_errors,
        "complete_observations": len(complete) >= criteria["minimum_steady_samples"],
        "command_limit": peak_command is not None and peak_command <= effort * (1 + criteria["effort_relative_tolerance"]),
        "velocity_limit": peak_velocity is not None and peak_velocity <= criteria["velocity_limit_rad_s"] + criteria["velocity_tolerance_rad_s"],
        "timing": bool(observations) and all(r["commanded_before_step_time"] < r["measured_after_step_time"] for r in observations),
        "response": final_error is not None and (final_error >= criteria["insufficient_error_min_rad"] and saturated > 0 if name == "insufficient" else final_error <= criteria["tracking_error_max_rad"]),
    }
    result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
              "final_error_rad": final_error, "peak_force_command_nm": peak_command,
              "peak_velocity_rad_s": peak_velocity, "saturated_steps": saturated,
              "late_mean_abs_command_nm": sum(abs(j["force_command"]) for j in complete)/len(complete) if complete else None,
              "observation_count": len(observations), "callback_errors": callback_errors,
              "sdf_sha256": digest(sdf), "telemetry_sha256": digest(output / "robot_telemetry.jsonl")}
    dump(output / "result.json", result)
    print(name, result["status"], flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plugin-dir", type=Path, required=True)
    args = parser.parse_args()
    output, plugin_dir = args.output.resolve(), args.plugin_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    criteria = {"steady_start_s": 2, "minimum_steady_samples": 100,
                "tracking_error_max_rad": .04, "insufficient_error_min_rad": .15,
                "effort_relative_tolerance": 1e-6,
                "velocity_limit_rad_s": 2, "velocity_tolerance_rad_s": .01,
                "scope": "engineering_fixture_tolerances_not_CAD_or_hardware_accuracy"}
    dump(output / "protocol.json", criteria)
    dump(output / "provenance.json", {"script_sha256": digest(__file__), "libraries_sha256": {
        "libUchuvaRobotTelemetrySystem.so": digest(plugin_dir / "libUchuvaRobotTelemetrySystem.so")},
        "gazebo": subprocess.check_output(["gz", "sim", "--versions"], text=True).strip()})
    cases = {name: run_case(output, name, mass, effort, plugin_dir, criteria)
             for name, mass, effort in [("nominal", .4, 2), ("insufficient", .4, .1), ("double_mass", .8, 2)]}
    nominal = cases["nominal"]["late_mean_abs_command_nm"]
    loaded = cases["double_mass"]["late_mean_abs_command_nm"]
    mass_effect = nominal is not None and loaded is not None and loaded > 1.7 * nominal
    summary = {"status": "PASS" if mass_effect and all(c["status"] == "PASS" for c in cases.values()) else "FAIL",
               "mass_effect": mass_effect, "cases": cases, "not_hardware_validation": True}
    dump(output / "summary.json", summary)
    return int(summary["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
