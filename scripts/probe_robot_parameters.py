#!/usr/bin/env python3
"""Exercise CAD parameter propagation without pretending to measure hardware."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from uchuva_gazebo.robot import resolve_robot, forward_kinematics, build_robot_sdf
from uchuva_gazebo.robot_spec import verify_robot_assets


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def run(profile, asset_root, output):
    output.mkdir(parents=True, exist_ok=False)
    robot = resolve_robot(profile)
    verify_robot_assets(robot, asset_root)
    protocol = {"schema_version": "robot-parameter-probe/1.0", "robot_spec_sha256": robot.sha256,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "numeric_tolerance": 1e-10, "mount_delta_x_m": -.02, "actuator_factor": .5,
        "hypothetical_battery_payload_mass_kg": 1.0, "hypothetical_payload_center_in_base_m": [-.1, 0, .1],
        "scope": "Software propagation and generated SDF only. Hypothetical payload is not a known installed battery. No dynamic or prototype PASS.",
        "cases": ["rigid_mount", "payload_mass_and_position", "actuator_ceiling", "reject_frozen_length"]}
    save(output/"protocol.json", protocol)
    evidence = {"status": "estimado", "source": "Predeclared diagnostic parameter probe",
                "revision": "1.0", "method": "Synthetic perturbation; not prototype measurement"}
    def change(path, value):
        return {path: {"value": value, "provenance": evidence}}
    reports = []
    def record(name, overrides, assertion):
        altered = resolve_robot(profile, overrides)
        verify_robot_assets(altered, asset_root)
        folder = output/name
        folder.mkdir()
        save(folder/"overrides.json", overrides)
        save(folder/"robot_resolved.json", altered.to_dict())
        xml = build_robot_sdf(altered)
        ET.ElementTree(xml).write(folder/"model.sdf", encoding="utf-8", xml_declaration=True)
        result = assertion(altered, xml)
        reports.append({"name": name, "status": "PASS" if result else "FAIL", "robot_spec_sha256": altered.sha256})
    base_pose = forward_kinematics(robot)["tcp"]
    mount_path = "/parameters/arm_mount_x_m"
    new_x = robot.data["parameters"]["arm_mount_x_m"]+protocol["mount_delta_x_m"]
    record("rigid_mount", change(mount_path, new_x), lambda changed, xml:
        abs(forward_kinematics(changed)["tcp"]["xyz_m"][0]-base_pose["xyz_m"][0]-protocol["mount_delta_x_m"]) < 1e-10
        and abs(float(xml.find("joint[@name='arm_mount_joint']/pose").text.split()[0])-new_x) < 1e-10)
    # Add a small isotropic inertia to the hypothetical payload and aggregate it
    # independently with the CAD chassis. Both translation and mass propagate.
    inertial = robot.to_dict()["links"][0]["inertial"]
    m, c = inertial["mass_kg"], inertial["com_m"]
    p = protocol["hypothetical_payload_center_in_base_m"]
    added = protocol["hypothetical_battery_payload_mass_kg"]
    total = m+added
    center = [(m*c[i]+added*p[i])/total for i in range(3)]
    xx, yy, zz, xy, xz, yz = inertial["tensor_kg_m2"]
    tensor = [[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]]
    for mass, point in ((m,c),(added,p)):
        d = [point[i]-center[i] for i in range(3)]
        for i in range(3):
            for j in range(3):
                tensor[i][j] += mass*((sum(v*v for v in d) if i==j else 0)-d[i]*d[j])
    for i in range(3):
        tensor[i][i] += added*.05**2/6
    payload = {"mass_kg": total, "com_m": center,
               "tensor_kg_m2": [tensor[0][0],tensor[1][1],tensor[2][2],tensor[0][1],tensor[0][2],tensor[1][2]]}
    record("payload_mass_and_position", change("/links/0/inertial", payload), lambda changed, xml:
        abs(float(xml.find("link[@name='base_link']/inertial/mass").text)-total) < 1e-10
        and math.dist([float(v) for v in xml.find("link[@name='base_link']/inertial/pose").text.split()[:3]], center) < 1e-10
        and math.dist(forward_kinematics(changed)["tcp"]["xyz_m"], base_pose["xyz_m"]) < 1e-10)
    cap = robot.data["parameters"]["arm_effort_limit_nm"]*protocol["actuator_factor"]
    record("actuator_ceiling", change("/parameters/arm_effort_limit_nm", cap), lambda changed, xml:
        all(j["limits"]["effort"] == cap for j in changed.joints if j["group"] == "arm")
        and all(v["cmd_max"] == cap and v["cmd_min"] == -cap for v in changed.data["control"]["arm"].values())
        and all(abs(float(xml.find(f"joint[@name='{name}']/axis/limit/effort").text)-cap) < 1e-10 for name in changed.joint_names))
    try:
        resolve_robot(profile, change("/parameters/upper_arm_axis_distance_m", .4))
    except ValueError as error:
        reports.append({"name": "reject_frozen_length", "status": "PASS" if "reexport" in str(error) else "FAIL", "diagnosis": str(error)})
    else:
        reports.append({"name": "reject_frozen_length", "status": "FAIL"})
    summary = {"status": "PASS" if all(x["status"]=="PASS" for x in reports) else "FAIL",
               "protocol": protocol, "cases": reports, "native_dynamic_validation": "NO EJECUTADO"}
    save(output/"summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.profile, args.asset_root, args.output)))
