#!/usr/bin/env python3
"""Create a static Gazebo inspection of native Inventor occurrences in SI.

This is an inspection artifact, not an integrated or articulated harvester.
Separate assembly roots retain independent frames and are labelled explicitly.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def node(parent, tag, text=None, **attributes):
    result = ET.SubElement(parent, tag, attributes)
    if text is not None:
        result.text = str(text)
    return result


def matrix_pose(matrix):
    if len(matrix) != 16 or any(type(x) not in (float, int) or not math.isfinite(x) for x in matrix):
        raise ValueError("Invalid occurrence matrix")
    if any(abs(matrix[12+i]-v) > 1e-7 for i, v in enumerate((0, 0, 0, 1))):
        raise ValueError("Invalid homogeneous row")
    for i in range(3):
        for j in range(3):
            if abs(sum(matrix[k*4+i]*matrix[k*4+j] for k in range(3))-(i == j)) > 1e-6:
                raise ValueError("Occurrence transform is not rigid")
    determinant = (matrix[0]*(matrix[5]*matrix[10]-matrix[6]*matrix[9])
                   - matrix[1]*(matrix[4]*matrix[10]-matrix[6]*matrix[8])
                   + matrix[2]*(matrix[4]*matrix[9]-matrix[5]*matrix[8]))
    if abs(determinant - 1) > 1e-6:
        raise ValueError("Reflected CAD occurrence needs explicit geometry handling")
    pitch = math.asin(max(-1, min(1, -matrix[8])))
    if abs(math.cos(pitch)) > 1e-8:
        roll, yaw = math.atan2(matrix[9], matrix[10]), math.atan2(matrix[4], matrix[0])
    else:
        roll, yaw = 0, math.atan2(-matrix[1], matrix[5])
    return [matrix[3], matrix[7], matrix[11], roll, pitch, yaw]


def prepare(inventory_path, output, allow_partial=False):
    inventory_path, output = Path(inventory_path).resolve(), Path(output).resolve()
    data = json.loads(inventory_path.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != "uchuva.inventor_cad_inventory/1":
        raise ValueError("Unsupported CAD inventory")
    if data.get("status") != "exported_cad_not_hardware_validated" and not allow_partial:
        raise ValueError("Partial CAD extraction: explicitly request partial INSPECTION only")
    documents = {d["id"]: d for d in data["documents"]}
    roots = list(dict.fromkeys(o["root_document_id"] for o in data["occurrences"]))
    sdf = ET.Element("sdf", version="1.10")
    world = node(sdf, "world", name="cad_inspection")
    node(world, "gravity", "0 0 0")
    for filename, name in (("gz-sim-physics-system", "Physics"),
                           ("gz-sim-scene-broadcaster-system", "SceneBroadcaster"),
                           ("gz-sim-user-commands-system", "UserCommands")):
        node(world, "plugin", filename=filename, name="gz::sim::systems::"+name)
    scene = node(world, "scene")
    node(scene, "ambient", ".55 .55 .55 1")
    node(scene, "background", ".1 .12 .15 1")
    light = node(world, "light", type="directional", name="inspection_light")
    node(light, "diffuse", ".8 .8 .8 1")
    node(light, "direction", "-.4 -.5 -1")
    models = {}
    for index, root in enumerate(roots):
        model = node(world, "model", name="CAD_"+root)
        node(model, "static", "true")
        node(model, "pose", f"{index*2} 0 0 0 0 0")
        models[root] = node(model, "link", name="inspection_only")
    records, missing, copies = [], [], {}
    for occurrence in data["occurrences"]:
        if occurrence.get("suppressed") or occurrence.get("visible") is False:
            continue
        document = documents.get(occurrence.get("document_id"), {})
        export = document.get("exports", {}).get("obj", {})
        if export.get("status") == "compose_from_occurrences":
            continue
        if occurrence.get("status") != "resolved" or export.get("status") != "exported":
            missing.append(occurrence["id"])
            continue
        source = (inventory_path.parent / export["uri"]).resolve()
        if not source.is_relative_to(inventory_path.parent) or sha(source) != export["sha256"]:
            raise ValueError("CAD mesh path/hash mismatch")
        pose = matrix_pose(occurrence["transform_root_m"])
        uri = "meshes/"+document["id"]+".obj"
        copies[uri] = source
        visual = node(models[occurrence["root_document_id"]], "visual", name="occ_"+str(len(records)))
        node(visual, "pose", " ".join(format(v, ".15g") for v in pose))
        mesh = node(node(visual, "geometry"), "mesh")
        node(mesh, "uri", uri)
        node(mesh, "scale", "1 1 1")
        material = node(visual, "material")
        # Inspection palette, explicitly not CAD appearance or material evidence.
        color = ((.35,.55,.7,1),(.65,.68,.72,1),(.3,.35,.4,1))[len(records)%3]
        node(material, "ambient", " ".join(map(str, color)))
        node(material, "diffuse", " ".join(map(str, color)))
        records.append({"occurrence_id": occurrence["id"], "document_id": document["id"],
                        "source_path": document["source_path"], "mesh_sha256": export["sha256"],
                        "transform_root_m": occurrence["transform_root_m"], "pose_rpy": pose})
    if missing and not allow_partial:
        raise ValueError("Unresolved visible CAD occurrences")
    if not records:
        raise ValueError("No resolved mesh occurrences")
    output.mkdir(parents=True, exist_ok=False)
    (output / "meshes").mkdir()
    for uri, source in copies.items():
        shutil.copyfile(source, output / uri)
    ET.indent(sdf)
    ET.ElementTree(sdf).write(output / "inspection.sdf", encoding="utf-8", xml_declaration=True)
    report = {"schema_version": "cad-inspection/1.0", "status": "PARTIAL" if missing or data.get("issues") else "EXPORTED",
              "purpose": "static independent CAD assemblies; not integrated robot or dynamic validation",
              "root_layout": [{"document_id": root, "source_path": documents[root]["source_path"], "presentation_translation_m": [i*2,0,0]} for i, root in enumerate(roots)],
              "native_CAD_coordinates_preserved": True, "appearance": "inspection_palette_not_CAD_materials",
              "inventory_sha256": sha(inventory_path), "occurrences": records, "missing_occurrences": missing,
              "source_issues_count": len(data.get("issues", [])), "simulation_validation": "NO EJECUTADO"}
    (output / "inspection_manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-partial-inspection", action="store_true")
    args = parser.parse_args()
    report = prepare(args.inventory, args.output, args.allow_partial_inspection)
    print(json.dumps({"status": report["status"], "occurrences": len(report["occurrences"]), "missing": len(report["missing_occurrences"])}))


if __name__ == "__main__":
    main()
