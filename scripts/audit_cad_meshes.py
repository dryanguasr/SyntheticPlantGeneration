#!/usr/bin/env python3
"""Audit native OBJ units, indices and normals against independent CAD bounds."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path


def audit_mesh(path, bounds, tolerance):
    vertices, normals, faces = [], [], []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if fields[0] in ("v", "vn"):
            vector = [float(v) for v in fields[1:4]]
            if len(vector) != 3 or not all(math.isfinite(v) for v in vector):
                raise ValueError("Nonfinite vertex/normal")
            (vertices if fields[0] == "v" else normals).append(vector)
        elif fields[0] == "f":
            if len(fields) != 4:
                raise ValueError("Native facet export must be triangulated")
            faces.append([tuple(int(i) if i else None for i in f.split("/")) for f in fields[1:]])
    if not vertices or not normals or not faces:
        raise ValueError("Incomplete native OBJ")
    out_of_bounds = sum(any(v[i] < bounds["min"][i]-tolerance or v[i] > bounds["max"][i]+tolerance
                            for i in range(3)) for v in vertices)
    normal_errors = sum(abs(math.sqrt(sum(x*x for x in n))-1) > 1e-5 for n in normals)
    reversed_faces = degenerate = 0
    for face in faces:
        if any(len(index) != 3 or not 1 <= index[0] <= len(vertices) or index[2] is None
               or not 1 <= index[2] <= len(normals) for index in face):
            raise ValueError("Invalid OBJ vertex/normal index")
        a, b, c = [vertices[index[0]-1] for index in face]
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        length = math.sqrt(sum(x*x for x in cross))
        if length < 1e-15:
            degenerate += 1
            continue
        n = [sum(normals[index[2]-1][i] for index in face)/3 for i in range(3)]
        if sum(x*y for x, y in zip(cross, n))/length < -1e-5:
            reversed_faces += 1
    mesh_bounds = {"min": [min(v[i] for v in vertices) for i in range(3)],
                   "max": [max(v[i] for v in vertices) for i in range(3)]}
    return {"status": "PASS" if not any((out_of_bounds, normal_errors, reversed_faces, degenerate)) else "FAIL",
            "vertices": len(vertices), "triangles": len(faces), "out_of_CAD_bounds": out_of_bounds,
            "nonunit_normals": normal_errors, "reversed_faces": reversed_faces,
            "degenerate_triangles": degenerate, "mesh_bounds_m": mesh_bounds}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    protocol = {"schema_version": "native-mesh-audit/1.0", "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
                "bounds_tolerance_m": data["chord_tolerance_m"], "normal_length_tolerance": 1e-5,
                "negative_normal_dot_tolerance": 1e-5, "degenerate_cross_norm_m2": 1e-15,
                "criterion": "Zero nonfinite/out-of-bound vertices, invalid indices, reversed/degenerate triangles or nonunit normals. Native document RangeBox is independent of tessellation; it may be conservative.",
                "scope": "CAD export integrity only; not prototype dimensions or PBR material fidelity."}
    (args.output/"protocol.json").write_text(json.dumps(protocol, indent=2), encoding="utf-8")
    records = []
    for doc in data["documents"]:
        export = doc.get("exports", {}).get("obj", {})
        if export.get("status") != "exported":
            continue
        path = (args.inventory.parent/export["uri"]).resolve()
        if not path.is_relative_to(args.inventory.parent.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != export["sha256"]:
            raise ValueError("Mesh path/hash mismatch")
        records.append({"source_path": doc["source_path"], "mesh_sha256": export["sha256"],
                        **audit_mesh(path, doc["bounds_m"], protocol["bounds_tolerance_m"])})
    result = {"status": "PASS" if records and all(r["status"] == "PASS" for r in records) else "FAIL",
              "protocol": protocol, "meshes": records}
    (args.output/"summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "mesh_count": len(records),
                      "failed_meshes": [r for r in records if r["status"] != "PASS"]}))


if __name__ == "__main__":
    main()
