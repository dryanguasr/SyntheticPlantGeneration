#!/usr/bin/env python3
"""Assemble private native CAD exports into an explicitly reduced RobotSpec.

The complete nominal profile remains incomplete while critical evidence is
missing. A separate diagnostic profile admits declared approximations only.
No private meshes or Inventor files need to enter version control.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_gazebo.robot_kinematics import (compose_poses, inverse_pose,
    pose_identity, pose_from_rpy, rotate_vector, transform_point)
from uchuva_gazebo.robot_spec import resolve_robot, verify_robot_assets
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract
from prepare_cad_inspection import matrix_pose


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False)+"\n", encoding="utf-8")


def pose(xyz=(0, 0, 0)):
    return {"xyz_m": list(xyz), "quaternion_xyzw": [0, 0, 0, 1]}


def from_matrix(matrix):
    values = matrix_pose(matrix)
    return pose_from_rpy(values[:3], values[3:])


# Proper rotation: Gazebo forward=-CAD Z, left=-CAD X, up=CAD Y.
CAD_ROTATION = from_matrix([0, 0, -1, 0, -1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1])


def aggregate_inertia(parts):
    """Transform COM tensors, then apply the parallel-axis theorem once.

parts contains (native mass_properties, link_T_document). The native exporter
checks the direct off-diagonal convention against all three principal-moment
invariants. Assemblies must never be added together with their own leaves.
"""
    transformed = []
    for mass, placement in parts:
        m = mass["mass_kg"]
        if not math.isfinite(m) or m <= 0:
            raise ValueError("Missing/nonpositive CAD part mass cannot be treated as zero")
        xx, yy, zz, xy, yz, xz = mass["xyz_moments_kg_m2"]
        native = [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]
        axes = [rotate_vector(placement["quaternion_xyzw"], v)
                for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
        rotated = [[sum(axes[k][i]*native[k][l]*axes[l][j]
                        for k in range(3) for l in range(3))
                    for j in range(3)] for i in range(3)]
        transformed.append((m, transform_point(placement, mass["center_of_mass_m"]), rotated))
    total = sum(m for m, _, _ in transformed)
    if total <= 0:
        raise ValueError("Rigid group has no physical CAD mass")
    center = [sum(m*c[i] for m, c, _ in transformed)/total for i in range(3)]
    tensor = [[0.0]*3 for _ in range(3)]
    for m, c, inertia in transformed:
        d = [c[i]-center[i] for i in range(3)]
        squared = sum(v*v for v in d)
        for i in range(3):
            for j in range(3):
                tensor[i][j] += inertia[i][j]+m*((squared if i == j else 0)-d[i]*d[j])
    return {"mass_kg": total, "com_m": center,
            "tensor_kg_m2": [tensor[0][0], tensor[1][1], tensor[2][2],
                             tensor[0][1], tensor[0][2], tensor[1][2]]}


def name_path(occurrence, occurrences):
    names = [occurrence["name"]]
    parent = occurrence.get("parent_id")
    while parent in occurrences:
        names.insert(0, occurrences[parent]["name"])
        parent = occurrences[parent].get("parent_id")
    return names


def gains(values, effort, velocity):
    return dict(zip(("p_gain", "i_gain", "d_gain"), values),
                i_min=0, i_max=0, cmd_min=-effort, cmd_max=effort,
                command_velocity=velocity)


def prepare(inventory_path, output, arm_mapping, base_mapping, assumptions_path,
            appearance_inventory=None):
    inventory_path, output = Path(inventory_path).resolve(), Path(output).resolve()
    inv, arm, base, assumptions = map(read, (inventory_path, arm_mapping, base_mapping, assumptions_path))
    if inv.get("status") not in ("exported_cad_not_hardware_validated", "partial_export"):
        raise ValueError("Finished native geometry export required")
    if not inv.get("source_integrity") or inv["source_integrity"]["changed_files"]:
        raise ValueError("Native export source integrity is not established")
    if output.exists():
        raise ValueError("Use a new output directory; previous evidence is immutable")
    documents = {d["id"]: d for d in inv["documents"]}
    occurrences = {o["id"]: o for o in inv["occurrences"]}
    roots = {d["source_path"]: d for d in inv["documents"]}
    arm_root = roots[arm["source_document_path"]]
    base_root = roots[base["source"]["root_source_path"]]
    for doc, expected in ((arm_root, arm["source_document_sha256"]),
                          (base_root, base["source"]["root_sha256"])):
        if doc["sha256"] != expected:
            raise ValueError("Mapping targets a different CAD root revision")
    appearance_docs, appearance_occurrences = {}, {}
    if appearance_inventory:
        appearances = read(appearance_inventory)
        if appearances.get("status") not in ("exported_cad_not_hardware_validated", "partial_export") or not appearances.get("source_integrity") or appearances["source_integrity"]["changed_files"]:
            raise ValueError("Finished, source-intact appearance inspection required")
        appearance_docs = {d["source_path"]: d for d in appearances["documents"]}
        app_docs = {d["id"]: d for d in appearances["documents"]}
        app_occ = {o["id"]: o for o in appearances["occurrences"]}
        for o in app_occ.values():
            root_path = app_docs[o["root_document_id"]]["source_path"]
            appearance_occurrences[(root_path, tuple(name_path(o, app_occ)))] = o
    nonphysical_docs = set()
    for doc in documents.values():
        extra = appearance_docs.get(doc["source_path"], doc)
        geometry = extra.get("geometry_inventory", {})
        if (extra.get("sha256") == doc["sha256"] and geometry.get("surface_bodies") == 0
                and geometry.get("mesh_feature_sets") == 0):
            nonphysical_docs.add(doc["id"])
    admitted_issues = []
    for issue in inv.get("issues", []):
        auxiliary = (issue["scope"] == "unresolved_or_ambiguous_reference"
                     and Path(issue["message"]).suffix.lower() in (".fins", ".fsat", ".ftes", ".fwiz", ".fmsh", ".fres")
                     and "\\FEA\\" in issue["message"])
        if issue["scope"] not in nonphysical_docs and not auxiliary:
            raise ValueError("Unclassified native export issue: "+str(issue))
        admitted_issues.append({**issue, "admission": "nonphysical construction geometry" if issue["scope"] in nonphysical_docs else "FEA result cache, not physical geometry"})
    mount = pose(assumptions["arm_mount_xyz_m"])
    arm_cad = compose_poses(mount, CAD_ROTATION)
    group_poses = {"base_link": pose(), "arm_base_mount": mount}
    for j in arm["joints"]:
        group_poses["arm_"+j["child_group"]] = pose(transform_point(arm_cad, j["point_root_m"]))
    for wheel in base["wheels"]:
        group_poses[wheel["group"]] = pose(wheel["center_base_m"])
    links = {name: {"name": name, "visuals": [], "collisions": []} for name in group_poses}
    inertias = {name: [] for name in links}
    records, skipped, copies = [], [], {}
    parents = {o.get("parent_id") for o in occurrences.values()}
    wheel_prefixes = {w["assembly_occurrence_id"].split("/", 1)[1]: w["group"] for w in base["wheels"]}
    for occurrence in occurrences.values():
        root = occurrence["root_document_id"]
        if root not in (arm_root["id"], base_root["id"]) or occurrence["id"] in parents:
            continue
        if occurrence.get("suppressed"):
            skipped.append({"id": occurrence["id"], "reason": "suppressed"})
            continue
        if occurrence.get("status") != "resolved":
            raise ValueError("Unresolved leaf: "+occurrence["id"])
        doc = documents[occurrence["document_id"]]
        if doc["id"] in nonphysical_docs:
            skipped.append({"id": occurrence["id"], "reason": "Native inspection confirms zero surface/mesh bodies", "source_path": doc["source_path"]})
            continue
        path = name_path(occurrence, occurrences)
        if root == arm_root["id"]:
            canonical_top = arm.get("occurrence_name_aliases", {}).get(path[0], path[0])
            group = arm["top_level_occurrence_groups"][canonical_top]
            for override in arm["nested_assignment_overrides"]:
                if path[:len(override["occurrence_path"])] == override["occurrence_path"]:
                    group = override["group"]
            group = "arm_"+group
            root_pose = arm_cad
        else:
            suffix = occurrence["id"].split("/", 1)[1]
            matches = [g for prefix, g in wheel_prefixes.items() if suffix == prefix or suffix.startswith(prefix+"/")]
            if len(matches) > 1:
                raise ValueError("Duplicate wheel assignment")
            group = matches[0] if matches else "base_link"
            root_pose = CAD_ROTATION
        placement = compose_poses(inverse_pose(group_poses[group]),
                                  compose_poses(root_pose, from_matrix(occurrence["transform_root_m"])))
        export = doc.get("exports", {}).get("obj", {})
        mass = doc.get("mass_properties", {})
        if not mass.get("tensor_principal_consistency", {}).get("consistent"):
            raise ValueError("Native inertia convention is not verified: "+doc["source_path"])
        if export.get("status") != "exported":
            # Skeletons have neither physical material nor facets. Do not use a
            # placeholder mass, box or visual to make the import pass.
            if mass.get("mass_kg", 0) == 0 and export.get("status") in ("no_surface_bodies", "empty_geometry", "no_solid_geometry"):
                skipped.append({"id": occurrence["id"], "reason": "nonphysical CAD skeleton", "source_path": doc["source_path"]})
                continue
            raise ValueError(f"No native visual geometry: {doc['source_path']} {export}")
        source = (inventory_path.parent / export["uri"]).resolve()
        if not source.is_relative_to(inventory_path.parent) or sha(source) != export["sha256"]:
            raise ValueError("Native mesh path/hash mismatch")
        uri = "meshes/"+export["sha256"]+".obj"
        copies[uri] = source
        key = "part_"+str(len(records))
        root_path = documents[root]["source_path"]
        appdoc = appearance_docs.get(doc["source_path"], doc)
        if appdoc.get("sha256") != doc["sha256"]:
            raise ValueError("Appearance and geometry revisions differ")
        appocc = appearance_occurrences.get((root_path, tuple(path)), occurrence)
        appearance = appocc.get("appearance") or appdoc.get("appearance") or {}
        color = appearance.get("diffuse_rgb")
        if color is None:
            wallpaint = appearance.get("colors", {}).get("wallpaint_color", {})
            if not wallpaint.get("has_connected_texture", True) and not wallpaint.get("has_multiple_values", True):
                color = wallpaint.get("rgb")
        color_status = "derivado_de_CAD" if color else "inspection_palette_not_CAD_appearance"
        visual = {"name": key, "pose": placement,
                  "geometry": {"type": "mesh", "uri": uri, "sha256": export["sha256"],
                               "scale": [1, 1, 1], "bound_parameters": {"/parameters/cad_geometry_revision": 1}},
                  "color_rgba": [*color, 1] if color else [.4, .45, .5, 1]}
        if occurrence.get("visible") is not False:
            links[group]["visuals"].append(visual)
        inertias[group].append((mass, placement))
        # Separate oriented bounds per part. Never one enclosing robot box.
        if not group.startswith("wheel_"):
            bounds = doc["bounds_m"]
            size = [b-a for a, b in zip(bounds["min"], bounds["max"])]
            center = [(a+b)/2 for a, b in zip(bounds["min"], bounds["max"])]
            if min(size) <= 0:
                raise ValueError("Degenerate physical part bounds")
            links[group]["collisions"].append({"name": key+"_bounds",
                "pose": compose_poses(placement, pose(center)),
                "geometry": {"type": "box", "size_m": size}})
        records.append({"occurrence_id": occurrence["id"], "occurrence_name_path": path,
                        "source_path": doc["source_path"], "source_sha256": doc["sha256"],
                        "link": group, "link_T_document": placement, "mass_properties": mass,
                        "mesh_sha256": export["sha256"], "appearance_status": color_status})
    for wheel in base["wheels"]:
        links[wheel["group"]]["collisions"].append({"name": wheel["name"]+"_tire",
            "pose": pose_from_rpy([0, 0, 0], [math.pi/2, 0, 0]),
            "geometry": {"type": "cylinder", "radius_m": wheel["radius_m"], "length_m": wheel["width_m"]},
            "surface": {"mu": assumptions["contact_mu"], "mu2": assumptions["contact_mu"]}})
    for name, link in links.items():
        link["inertial"] = aggregate_inertia(inertias[name])
    joints, actuators = [], []
    control = {"arm": {}, "drive": {"left_joints": [], "right_joints": [], "joint_signs": {}, "joints": {},
        "backend": "native_force", "wheel_radius_m": base["wheels"][0]["radius_m"],
        "wheel_separation_m": base["dimensions"]["wheel_separation_m"],
        "max_linear_velocity": .15, "max_angular_velocity": .3,
        "max_linear_acceleration": .2, "max_angular_acceleration": .4, "odom_publish_frequency": 30}, "gripper": {}}
    def joint(name, parent, child, axis, group, lower, upper, effort, velocity):
        joints.append({"name": name, "parent": parent, "child": child,
            "type": "fixed" if group == "fixed" else "revolute", "group": group,
            "origin": compose_poses(inverse_pose(group_poses[parent]), group_poses[child]),
            "child_pose": pose(), "axis": axis, "zero_offset": 0,
            "limits": {"lower": lower, "upper": upper, "effort": effort, "velocity": velocity}})
        if group != "fixed":
            actuators.append({"name": name+"_actuator", "joint": name,
                "continuous_effort": effort, "peak_effort": effort, "transmission_ratio": 1,
                "efficiency": 1, "effort_reference": "joint_output", "status": "estimado"})
    joint("arm_mount_joint", "base_link", "arm_base_mount", [0, 0, 1], "fixed", 0, 0, 0, 0)
    for item in arm["joints"]:
        effort, velocity = assumptions["arm_effort_limit_nm"], assumptions["arm_velocity_limit_rad_s"]
        name = item["name"]+"_joint"
        joint(name, "arm_"+item["parent_group"], "arm_"+item["child_group"],
              rotate_vector(CAD_ROTATION["quaternion_xyzw"], item["axis_root"]), "arm",
              item["provisional_limits"]["lower_rad"], item["provisional_limits"]["upper_rad"], effort, velocity)
        control["arm"][name] = gains(assumptions["arm_pid"], effort, velocity)
    for wheel in base["wheels"]:
        effort, velocity = assumptions["wheel_effort_limit_nm"], assumptions["wheel_velocity_limit_rad_s"]
        name = wheel["name"]+"_wheel_joint"
        joint(name, "base_link", wheel["group"], [0, 1, 0], "drive", -1e16, 1e16, effort, velocity)
        control["drive"]["joints"][name] = gains(assumptions["wheel_pid"], effort, velocity)
        control["drive"]["left_joints" if wheel["name"].endswith("left") else "right_joints"].append(name)
        control["drive"]["joint_signs"][name] = 1
    frames = [{"name": "arm_mount", "parent": "arm_base_mount", "pose": pose()}]
    for name in ("tcp", "cut_point", "grasp_center"):
        frames.append({"name": name, "parent": "arm_wrist_roll", "pose": compose_poses(
            inverse_pose(group_poses["arm_wrist_roll"]), compose_poses(arm_cad, arm["frames"][name]["pose_root"]))})
    revision = sha(inventory_path)
    provenance = {"status": "derivado_de_CAD", "source": "Native Inventor inventory + versioned CAD mappings",
                  "revision": revision, "method": "Leaf occurrence transforms, COM tensor aggregation; explicit reduced commissioning assumptions.",
                  "uncertainty": "CAD densities and rigid assignments are not measured hardware properties."}
    spec = {"schema_version": "robot-spec/1.0", "profile_id": "cad_diagnostic_frozen", "status": "complete",
        "model_name": "harvester", "namespace": "/harvester", "units": {"length": "m", "mass": "kg", "angle": "rad"},
        "root_link": "base_link", "capabilities": ["fk", "ik_position_direction", "collision_primitives", "native_force_drive"],
        "provenance": provenance, "missing_evidence": [], "parameters": {"cad_geometry_revision": 1},
        "parameter_metadata": {"/parameters/cad_geometry_revision": {**provenance, "update_class": "cad_reexport"}},
        "derived_values": [], "links": list(links.values()), "joints": joints, "frames": frames,
        "arm_home_positions": {j["name"]: 0 for j in joints if j["group"] == "arm"},
        "collision_policy": {"mode": "explicit_pairs", "excluded_pairs": [
            {"links": [j["parent"], j["child"]], "reason": "Connected adjacent rigid bodies; verified DART adjacency exclusion semantics."} for j in joints]},
        "actuators": actuators, "sensors": [], "control": control, "override_history": []}
    for axis, value in enumerate(assumptions["arm_mount_xyz_m"]):
        name = "arm_mount_"+"xyz"[axis]+"_m"
        spec["parameters"][name] = value
        spec["parameter_metadata"]["/parameters/"+name] = {"status": "estimado", "source": assumptions["mount_evidence"]["source"],
            "revision": sha(assumptions_path), "method": assumptions["mount_evidence"]["method"],
            "uncertainty": assumptions["mount_evidence"]["uncertainty_m"][axis], "update_class": "model_regeneration"}
        spec["derived_values"].append({"path": f"/joints/0/origin/xyz_m/{axis}", "expression": {"parameter": name}})
    # All dynamic/physical scalars have localizable source classification.
    for index, link in enumerate(spec["links"]):
        spec["parameter_metadata"][f"/links/{index}/inertial"] = {**provenance, "update_class": "model_regeneration"}
    for index, actuator in enumerate(actuators):
        for field in ("continuous_effort", "peak_effort"):
            spec["parameter_metadata"][f"/actuators/{index}/{field}"] = {
                "status": "estimado", "source": str(Path(assumptions_path).name), "revision": sha(assumptions_path),
                "method": assumptions["actuation_evidence"]["method"], "update_class": "model_regeneration"}
    # One command ceiling drives the actuator, joint and controller; changing
    # only one of those would create contradictory limits.
    for group, parameter in (("arm", "arm_effort_limit_nm"), ("drive", "wheel_effort_limit_nm")):
        spec["parameters"][parameter] = assumptions[parameter]
        spec["parameter_metadata"]["/parameters/"+parameter] = {
            "status": "estimado", "source": str(Path(assumptions_path).name), "revision": sha(assumptions_path),
            "method": assumptions["actuation_evidence"]["method"], "update_class": "model_regeneration"}
        for index, item in enumerate(joints):
            if item["group"] != group:
                continue
            expression = {"parameter": parameter}
            spec["derived_values"].append({"path": f"/joints/{index}/limits/effort", "expression": expression})
            ctrl = "/control/arm/" if group == "arm" else "/control/drive/joints/"
            spec["derived_values"].extend([
                {"path": ctrl+item["name"]+"/cmd_max", "expression": expression},
                {"path": ctrl+item["name"]+"/cmd_min", "expression": {"op": "mul", "args": [-1, expression]}}])
            actuator_index = next(i for i, a in enumerate(actuators) if a["joint"] == item["name"])
            for field in ("continuous_effort", "peak_effort"):
                spec["derived_values"].append({"path": f"/actuators/{actuator_index}/{field}", "expression": expression})
    joint_points = [j["point_root_m"] for j in arm["joints"]]
    # The verified shoulder/elbow axes are parallel. Their separation is a
    # geometry revision, never a runtime stretch of frozen visual meshes.
    delta = [b-a for a, b in zip(joint_points[1], joint_points[2])]
    axis = arm["joints"][1]["axis_root"]
    along = sum(a*b for a, b in zip(delta, axis))
    length = math.sqrt(sum((v-along*a)**2 for v, a in zip(delta, axis)))
    spec["parameters"]["upper_arm_axis_distance_m"] = length
    spec["parameter_metadata"]["/parameters/upper_arm_axis_distance_m"] = {**provenance, "update_class": "cad_reexport"}
    for link in links.values():
        for visual in link["visuals"]:
            visual["geometry"]["bound_parameters"]["/parameters/upper_arm_axis_distance_m"] = length
    resolved = resolve_robot(spec)
    output.mkdir(parents=True)
    (output / "meshes").mkdir()
    for uri, source in copies.items():
        shutil.copyfile(source, output / uri)
    verify_robot_assets(resolved, output)
    write(output / "cad_diagnostic_frozen.json", resolved.to_dict())
    nominal = copy.deepcopy(spec)
    nominal.update(profile_id="cad_nominal", status="incomplete", capabilities=[], missing_evidence=[
        "Metric chassis-arm mount and hardware joint zeros/limits remain unmeasured.",
        "Suspension and gripper closed loops require a validated dynamic representation.",
        "Joint-output continuous actuator capabilities and transmission losses remain unknown.",
        "Per-part bounds are diagnostic; gripper/cavity-aware collision bodies require validation.",
        "Battery, harvest basket and sensor mounting/properties remain pending."])
    write(output / "cad_nominal.json", nominal)
    contract = resolved_robot_contract(resolved)
    write(output / "robot_contract.json", contract)
    start_z = base["dimensions"]["cad_pose_chassis_origin_height_for_tire_tangent_ground_m"]+.002
    sdf = ET.Element("sdf", version="1.10")
    sdf.append(resolved_robot_model(resolved, (0, 0, start_z, 0)))
    ET.indent(sdf)
    ET.ElementTree(sdf).write(output / "model.sdf", encoding="utf-8", xml_declaration=True)
    report = {"schema_version": "cad-robot-import/1.0", "status": "DIAGNOSTIC_ONLY", "robot_spec_sha256": resolved.sha256,
        "inventory_sha256": revision, "arm_mapping_sha256": sha(arm_mapping), "base_mapping_sha256": sha(base_mapping),
        "assumptions_sha256": sha(assumptions_path), "script_sha256": sha(__file__),
        "appearance_inventory_sha256": sha(appearance_inventory) if appearance_inventory else None,
        "assumptions": assumptions, "start_pose": [0, 0, start_z, 0], "parts": records, "skipped": skipped,
        "admitted_source_issues": admitted_issues,
        "total_cad_mass_kg": sum(l["inertial"]["mass_kg"] for l in links.values()),
        "native_harvest_eligible": False, "native_validation": "NO EJECUTADO",
        "nominal_missing_evidence": nominal["missing_evidence"]}
    write(output / "cad_import_report.json", report)
    return {"status": report["status"], "links": len(links), "leaf_parts": len(records),
            "meshes": len(copies), "total_cad_mass_kg": report["total_cad_mass_kg"], "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--appearance-inventory", type=Path)
    parser.add_argument("--arm-mapping", type=Path, default=ROOT/"configs/robots/cad_arm_mapping.json")
    parser.add_argument("--base-mapping", type=Path, default=ROOT/"configs/robots/cad_base_mapping.json")
    parser.add_argument("--assumptions", type=Path, default=ROOT/"configs/robots/cad_diagnostic_assumptions.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.inventory, args.output, args.arm_mapping, args.base_mapping,
                             args.assumptions, args.appearance_inventory)))


if __name__ == "__main__":
    main()
