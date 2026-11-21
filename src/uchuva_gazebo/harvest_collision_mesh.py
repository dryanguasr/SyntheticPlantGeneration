"""Closed conservative prism batches for static plant collision geometry.

Each original finite cylinder is enclosed by a regular circumscribed prism.
All endpoints and identities survive. With twelve sides the vertex radius is
r/cos(pi/12), about 3.53% larger: this is an explicit engineering approximation,
not identical analytical cylinder physics. The motion auditor uses that outer
cylinder, conservatively extending flat ends as it does for historical shapes.
"""
from __future__ import annotations

import hashlib
import json
import math

VERSION = "uchuva.collision_prisms/1"
SECTORS = 12
HEADER = "# uchuva_collision_prisms "
PRIMITIVE = "# primitive "


def radius_factor(sectors=SECTORS):
    if type(sectors) is not int or not 6 <= sectors <= 64:
        raise ValueError("Collision prism sectors must be an integer from 6 to 64")
    return 1.0 / math.cos(math.pi / sectors)


def _finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Collision coordinates and radii must be finite numbers")
    return float(value)


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("A collision endpoint must have three coordinates")
    return [_finite(component) for component in value]


def _validated(primitives, sectors):
    radius_factor(sectors)
    rows, ids, sources = [], set(), set()
    for primitive in primitives:
        if set(primitive) != {"id", "source_proxy_id", "start", "end", "radius"}:
            raise ValueError("Unexpected collision primitive fields")
        row = dict(primitive)
        for key, seen in (("id", ids), ("source_proxy_id", sources)):
            value = row[key]
            if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value) or value in seen:
                raise ValueError("Collision primitive identities must be unique nonempty strings")
            seen.add(value)
        row["start"], row["end"] = _point(row["start"]), _point(row["end"])
        row["radius"] = _finite(row["radius"])
        delta = [b - a for a, b in zip(row["start"], row["end"])]
        if row["radius"] <= 0 or not all(math.isfinite(v) for v in delta) or math.hypot(*delta) < 1e-10:
            raise ValueError("Collision cylinders require positive radius and nonzero finite length")
        rows.append(row)
    if not rows:
        raise ValueError("A collision batch cannot be empty")
    return rows


def identity_digest(primitives):
    identities = [[row["id"], row["source_proxy_id"]] for row in primitives]
    return hashlib.sha256(json.dumps(identities, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def prism_geometry(start, end, radius, sectors=SECTORS):
    """Return vertices and outward triangle faces for one closed SI prism."""
    row = _validated([dict(id="geometry", source_proxy_id="geometry", start=start, end=end, radius=radius)], sectors)[0]
    delta = [b - a for a, b in zip(row["start"], row["end"])]
    length = math.hypot(*delta)
    axis = [value / length for value in delta]
    index = min(range(3), key=lambda i: abs(axis[i]))
    reference = [float(i == index) for i in range(3)]
    u = _cross(axis, reference)
    norm = math.hypot(*u)
    u = [value / norm for value in u]
    v = _cross(axis, u)
    outer = row["radius"] * radius_factor(sectors)
    vertices = []
    for center in (row["start"], row["end"]):
        for sector in range(sectors):
            angle = 2 * math.pi * sector / sectors
            vertices.append(tuple(center[i] + outer * (u[i] * math.cos(angle) + v[i] * math.sin(angle)) for i in range(3)))
    vertices.extend((tuple(row["start"]), tuple(row["end"])))
    if not all(math.isfinite(value) for vertex in vertices for value in vertex):
        raise ValueError("Collision prism vertices overflow finite coordinates")
    faces = []
    for i in range(sectors):
        j = (i + 1) % sectors
        faces.extend(((i, j, j + sectors), (i, j + sectors, i + sectors),
                      (2 * sectors, j, i), (2 * sectors + 1, i + sectors, j + sectors)))
    return vertices, faces


def build_collision_prisms(primitives, sectors=SECTORS):
    """Serialize geometry and complete primitive metadata in one canonical OBJ."""
    rows = _validated(primitives, sectors)
    metadata = dict(schema_version=VERSION, sectors=sectors, primitive_count=len(rows),
                    identity_sha256=identity_digest(rows), units="metres",
                    radius_factor=radius_factor(sectors), approximation="circumscribed_finite_prisms")
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True)
    output = [HEADER + encode(metadata)]
    output.extend(PRIMITIVE + encode(dict(row, sectors=sectors)) for row in rows)
    offset = 1
    for row in rows:
        vertices, faces = prism_geometry(row["start"], row["end"], row["radius"], sectors)
        # Gazebo's DART importer requires a normal for every imported vertex.
        # Area-weighted outward vertex normals preserve the shared topology;
        # they do not alter any vertex, triangle or collision envelope.
        normals = [[0.0, 0.0, 0.0] for _ in vertices]
        for face in faces:
            a, b, c = [vertices[index] for index in face]
            normal = _cross([b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)])
            for index in face:
                for coordinate in range(3):
                    normals[index][coordinate] += normal[coordinate]
        for index, normal in enumerate(normals):
            length = math.hypot(*normal)
            if not math.isfinite(length) or length <= 0:
                raise ValueError("Collision prism requires finite nonzero outward normals")
            normals[index] = [value / length for value in normal]
        output.extend("v " + " ".join(format(component, ".17g") for component in vertex) for vertex in vertices)
        output.extend("vn " + " ".join(format(component, ".17g") for component in normal) for normal in normals)
        output.extend("f " + " ".join(f"{index + offset}//{index + offset}" for index in face) for face in faces)
        offset += len(vertices)
    return "\n".join(output) + "\n"


def read_collision_prisms(text):
    """Fail closed unless every triangle exactly matches the declared primitives.

    Returns local bounding cylinders. Canonical reconstruction detects dropped
    caps, changed coordinates, extra geometry, stale metadata and duplicate IDs.
    Package hashes and the plant report separately bind the batch to its source.
    """
    if not isinstance(text, str):
        raise ValueError("Collision OBJ must be text")
    lines = text.splitlines()
    if not lines or not lines[0].startswith(HEADER):
        raise ValueError("Collision mesh has no supported primitive header")
    try:
        metadata = json.loads(lines[0][len(HEADER):])
        if not isinstance(metadata, dict) or metadata.get("schema_version") != VERSION or type(metadata.get("primitive_count")) is not int:
            raise ValueError("Unsupported collision mesh schema")
        count, sectors = metadata["primitive_count"], metadata["sectors"]
        if count < 1 or count > len(lines) - 1:
            raise ValueError("Invalid collision primitive count")
        rows = []
        for line in lines[1:count + 1]:
            if not line.startswith(PRIMITIVE):
                raise ValueError("Missing collision primitive identity")
            row = json.loads(line[len(PRIMITIVE):])
            if row.pop("sectors") != sectors:
                raise ValueError("Inconsistent collision prism sectors")
            rows.append(row)
        expected = build_collision_prisms(rows, sectors)
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed collision primitive metadata") from error
    if text != expected:
        raise ValueError("Collision OBJ does not match its canonical primitive geometry")
    factor = radius_factor(sectors)
    return [dict(row, source_radius=row["radius"], radius=row["radius"] * factor,
                 sectors=sectors, representation="conservative_prism_outer_cylinder") for row in rows]
