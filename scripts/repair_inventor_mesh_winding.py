#!/usr/bin/env python3
"""Create a traceable OBJ derivative aligned with native CAD vertex normals."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil


VERSION = "1.0"
DEGENERATE_CROSS_NORM_M2 = 1e-15


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repair_mesh_bytes(data: bytes) -> tuple[bytes, dict]:
    """Keep vertex/normal lines byte-identical; only reorder or remove faces."""
    lines = data.splitlines(keepends=True)
    vertices, normals = [], []
    for line in lines:
        fields = line.split()
        if fields and fields[0] in (b"v", b"vn"):
            if len(fields) != 4:
                raise ValueError("Expected three-dimensional native vertex/normal")
            vector = tuple(float(value) for value in fields[1:])
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("Nonfinite vertex/normal")
            (vertices if fields[0] == b"v" else normals).append(vector)
    if not vertices or not normals:
        raise ValueError("Missing native vertices or normals")
    result, changes = [], []
    face_count = reversed_count = degenerate_count = 0
    for line_number, line in enumerate(lines, 1):
        fields = line.split()
        if not fields or fields[0] != b"f":
            result.append(line)
            continue
        face_count += 1
        if len(fields) != 4:
            raise ValueError("Expected triangulated native OBJ")
        indices = []
        for token in fields[1:]:
            index = token.split(b"/")
            if len(index) != 3 or not index[0] or not index[2]:
                raise ValueError("Expected explicit OBJ vertex and normal indices")
            vertex, normal = int(index[0]), int(index[2])
            if not 1 <= vertex <= len(vertices) or not 1 <= normal <= len(normals):
                raise ValueError("Out-of-range vertex or normal index")
            indices.append((vertex - 1, normal - 1))
        a, b, c = (vertices[index[0]] for index in indices)
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        cross_norm = math.sqrt(sum(value*value for value in cross))
        if cross_norm < DEGENERATE_CROSS_NORM_M2:
            changes.append({"original_line_number": line_number, "original_face_index": face_count,
                            "action": "removed_degenerate_triangle", "cross_norm_m2": cross_norm,
                            "original_face": line.decode("ascii").rstrip("\r\n")})
            degenerate_count += 1
            continue
        mean_normal = [sum(normals[index[1]][i] for index in indices)/3 for i in range(3)]
        dot = sum(cross[i]*mean_normal[i] for i in range(3))/cross_norm
        if dot < 0:
            ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b""
            replacement = b" ".join((b"f", fields[1], fields[3], fields[2])) + ending
            result.append(replacement)
            changes.append({"original_line_number": line_number, "original_face_index": face_count,
                            "action": "reversed_face_order", "cross_norm_m2": cross_norm,
                            "original_normal_dot": dot, "original_face": line.decode("ascii").rstrip("\r\n"),
                            "derived_face": replacement.decode("ascii").rstrip("\r\n")})
            reversed_count += 1
        else:
            result.append(line)
    if face_count - degenerate_count == 0:
        raise ValueError("No nondegenerate facets remain")
    output = b"".join(result)
    return output, {"vertices": len(vertices), "normals": len(normals), "original_triangles": face_count,
                    "derived_triangles": face_count-degenerate_count, "reversed_faces": reversed_count,
                    "removed_degenerate_triangles": degenerate_count, "changes": changes,
                    "original_sha256": sha256(data), "derived_sha256": sha256(output),
                    "vertex_and_normal_lines_unchanged": True}


def checked_artifact(root: Path, record: dict) -> Path:
    path = (root/record["uri"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Export artifact escapes inventory directory")
    if sha256(path.read_bytes()) != record["sha256"]:
        raise ValueError(f"Source artifact hash mismatch: {path}")
    return path


def derive_inventory(inventory_path: Path, output: Path) -> dict:
    source_bytes = inventory_path.read_bytes()
    source = json.loads(source_bytes.decode("utf-8-sig"))
    inventory = copy.deepcopy(source)
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": "uchuva.inventor_mesh_winding_derivative/1", "script_version": VERSION,
              "script_sha256": sha256(Path(__file__).read_bytes()),
              "source_inventory": str(inventory_path.resolve()), "source_inventory_sha256": sha256(source_bytes),
              "protocol": {"degenerate_cross_norm_m2": DEGENERATE_CROSS_NORM_M2,
                           "reverse_if_cross_dot_mean_native_normal_below": 0,
                           "coordinate_changes": False, "normal_changes": False,
                           "chord_tolerance_m": source["chord_tolerance_m"],
                           "source_export_and_its_failures_preserved": True}, "meshes": []}
    for document in inventory["documents"]:
        exports = document.get("exports", {})
        obj = exports.get("obj", {})
        if obj.get("status") == "exported":
            input_mesh = checked_artifact(inventory_path.parent, obj)
            mesh_bytes, details = repair_mesh_bytes(input_mesh.read_bytes())
            destination = output/obj["uri"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(mesh_bytes)
            obj["sha256"] = details["derived_sha256"]
            obj.setdefault("details", {})["triangles"] = details["derived_triangles"]
            obj["winding_derivative"] = {"original_sha256": details["original_sha256"],
                                         "reversed_faces": details["reversed_faces"],
                                         "removed_degenerate_triangles": details["removed_degenerate_triangles"]}
            report["meshes"].append({"source_path": document["source_path"], "uri": obj["uri"], **details})
        step = exports.get("step", {})
        if step.get("status") == "exported":
            input_step = checked_artifact(inventory_path.parent, step)
            destination = output/step["uri"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(input_step, destination)
    report["summary"] = {"meshes": len(report["meshes"]),
                         "reversed_faces": sum(m["reversed_faces"] for m in report["meshes"]),
                         "removed_degenerate_triangles": sum(m["removed_degenerate_triangles"] for m in report["meshes"])}
    report_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
    (output/"mesh_repair_report.json").write_bytes(report_bytes)
    inventory["mesh_derivative"] = {"source_inventory": str(inventory_path.resolve()),
                                     "source_inventory_sha256": sha256(source_bytes),
                                     "repair_report": "mesh_repair_report.json", "repair_report_sha256": sha256(report_bytes),
                                     "original_export_status": source["status"],
                                     "note": "Original issues/status retained; only facet winding/degeneracy repaired. Reaudit required."}
    (output/"cad_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    for name in ("exporter_source.ps1", "inventor_reference_resolver.cs"):
        if (inventory_path.parent/name).exists():
            shutil.copyfile(inventory_path.parent/name, output/name)
    shutil.copyfile(__file__, output/"repair_inventor_mesh_winding.py")
    return report["summary"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(derive_inventory(args.inventory, args.output)))


if __name__ == "__main__":
    main()
