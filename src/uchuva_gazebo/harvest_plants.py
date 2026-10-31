"""Morphology-derived Gazebo plants with independent harvestable units.

No Blender or Gazebo runtime is imported. The existing morphology/proxy
interpreter owns all organ positions. Admitted trees may instead supply a
hash-linked catalog evaluated by their own source interpreter. This module
converts explicit source units to SI and supplies heuristic rigid-body
properties. A runtime system must attach the returned dynamic fruit models
before the first physics step; this exporter does not implement cutting.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from uchuva_lsystem.collisions import CollisionProxy, build_scene_proxies
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.scene import CultivationScene, PlantInstance
from uchuva_lsystem.sparse_pilot import UNITS_PER_METRE, walk_axes

from .field import element, material, numbers
from .harvest_visuals import (
    VERSION as VISUAL_VERSION,
    apply_plant_material,
    cylinder_batch_mesh,
    detailed_calyx_mesh,
    detailed_leaf_mesh,
    merge_obj_meshes,
    plant_texture_preset,
    texture_asset_paths,
)


VERSION = "harvest-plants/0.1"
DEFAULT_PLANT_CONFIG = {
    "seeds": [1031, 1032, 1033],
    "positions_m": [[0.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 4.0, 0.0]],
    # Turn the whole third instance towards the same aisle; organs stay nodal.
    "rotations_deg": [0.0, 0.0, 180.0],
    "preset": "trained_trellis",
    "phenology_model": "legacy_independent",
    "reproductive_units_min": 4,
    "reproductive_units_max": 6,
    "max_dynamic_fruits_per_plant": 2,
    "minimum_target_height_m": 0.10,
    "maximum_target_height_m": 0.90,
    "require_left_side": True,
    "fruit_mass_kg": 0.006,
    "clearance_m": 0.001,
    "cut_fraction": 0.5,
    "morphology_files": [],
    "proxy_catalog_files": [],
    "source_units_per_metre": UNITS_PER_METRE,
    "target_ids": [],
}

LIMITATIONS = [
    "Technical small-plant fixture; adult field geometry is not calibrated.",
    "Rigid stems and ideal removable attachment; no compliant branches or fracture law.",
    "Fruit and calyx form one rigid body with a conservative spherical collider.",
    "Mass, inertia approximation, friction and cut fraction are engineering heuristics.",
    "Textured curved leaves and five-rib calyces interpret source proxy poses; surfaces approximate rather than reproduce the source Blender meshes.",
    "Visual relief and material appearance are engineering interpretations, not measured anatomy or fruit maturity labels.",
    "Leaves and non-selected reproductive units are visual-only.",
    "Clearance audit concerns selected bodies and exported rigid geometry, not foliage meshes.",
    "Target selection uses privileged morphology for an interaction pilot, not perception.",
    "Legacy independent phenology avoids the separate post-cohort count issue; that issue is not fixed.",
]


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _config(config):
    unknown = set(config) - set(DEFAULT_PLANT_CONFIG)
    if unknown:
        raise ValueError(f"Unknown harvest plant config keys: {sorted(unknown)}")
    c = deepcopy(DEFAULT_PLANT_CONFIG)
    c.update(deepcopy(config))
    if not c["seeds"] or len(c["seeds"]) > 6:
        raise ValueError("The small pilot requires one to six plant seeds")
    if any(type(seed) is not int for seed in c["seeds"]):
        raise ValueError("Plant seeds must be integers")
    if len(c["positions_m"]) != len(c["seeds"]) or len(c["rotations_deg"]) != len(c["seeds"]):
        raise ValueError("seeds, positions_m and rotations_deg must have equal lengths")
    for i, xyz in enumerate(c["positions_m"]):
        if len(xyz) != 3:
            raise ValueError("Every plant position needs exactly three coordinates")
        c["positions_m"][i] = [_finite(v, "plant position") for v in xyz]
    c["rotations_deg"] = [_finite(v, "plant rotation") for v in c["rotations_deg"]]
    for key in ("reproductive_units_min", "reproductive_units_max", "max_dynamic_fruits_per_plant"):
        if type(c[key]) is not int or c[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if not c["reproductive_units_min"] <= c["reproductive_units_max"] <= 30:
        raise ValueError("Reproductive count bounds must be ordered and at most 30")
    if c["max_dynamic_fruits_per_plant"] > c["reproductive_units_max"]:
        raise ValueError("Dynamic fruit count exceeds the morphology budget")
    if c["target_ids"] and (len(c["target_ids"]) != len(c["seeds"]) * c["max_dynamic_fruits_per_plant"] or len(set(c["target_ids"])) != len(c["target_ids"]) or not all(isinstance(value, str) for value in c["target_ids"])):
        raise ValueError("Explicit target IDs must be unique and match the requested fruit count")
    imported = bool(c["morphology_files"])
    if bool(c["proxy_catalog_files"]) != imported:
        raise ValueError("Imported morphology requires matching proxy catalogs")
    if imported and (len(c["morphology_files"]) != len(c["seeds"]) or len(c["proxy_catalog_files"]) != len(c["seeds"])):
        raise ValueError("Imported files and seeds must have equal lengths")
    c["source_units_per_metre"] = _finite(c["source_units_per_metre"], "source units per metre")
    if c["source_units_per_metre"] <= 0:
        raise ValueError("Source units per metre must be positive")
    if not imported and c["source_units_per_metre"] != UNITS_PER_METRE:
        raise ValueError("Generated fixtures use the historical eight units per metre")
    if not imported and c["phenology_model"] != "legacy_independent":
        raise ValueError("This count-bounded fixture explicitly requires legacy_independent phenology")
    if type(c["require_left_side"]) is not bool:
        raise ValueError("require_left_side must be boolean")
    for key in ("fruit_mass_kg", "clearance_m", "cut_fraction", "minimum_target_height_m", "maximum_target_height_m"):
        c[key] = _finite(c[key], key)
    if c["fruit_mass_kg"] <= 0 or c["clearance_m"] < 0:
        raise ValueError("Fruit mass must be positive and clearance nonnegative")
    if not 0 < c["cut_fraction"] < 1:
        raise ValueError("cut_fraction must lie strictly inside the pedicel")
    if not 0 <= c["minimum_target_height_m"] < c["maximum_target_height_m"]:
        raise ValueError("Target height range is invalid")
    return c


def _load_catalog_plant(morphology_file, catalog_file, instance, source_units):
    """Consume evaluated v8 poses without invoking the historical interpreter.

    Input morphology bytes are hashed and the complete decoded payload is kept,
    including additive fields unknown to the local compatibility dataclasses.
    Only the catalog's instance transform and explicit unit conversion change.
    """
    morphology_path, catalog_path = Path(morphology_file), Path(catalog_file)
    raw_bytes = morphology_path.read_bytes()
    payload = json.loads(raw_bytes)
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if catalog.get("schema_version") != "uchuva.harvest_proxy_catalog/1":
        raise ValueError("Unsupported harvest proxy catalog")
    if catalog.get("morphology_sha256") != digest:
        raise ValueError("Morphology bytes do not match the frozen proxy catalog")
    if catalog.get("source_units_per_metre") != source_units:
        raise ValueError("Catalog and configured source units differ")
    if catalog.get("seed") != instance.seed or payload.get("seed") != instance.seed:
        raise ValueError("Catalog, morphology and configured seed differ")
    admission = catalog.get("admission", {})
    if admission.get("status") != "admitted" or admission.get("physical_crossings") != 0:
        raise ValueError("Catalog requires a source static admission")
    source_id = catalog["source_plant_id"]
    factor = UNITS_PER_METRE / source_units
    angle = math.radians(instance.rotation_deg)
    cosine, sine = math.cos(angle), math.sin(angle)

    def rotate(vector):
        return (cosine * vector[0] - sine * vector[1], sine * vector[0] + cosine * vector[1], vector[2])

    def point(vector):
        return tuple(value * factor + origin for value, origin in zip(rotate(vector), instance.position))

    def identifier(value):
        if value is None:
            return None
        prefix = source_id + ":"
        return instance.plant_id + ":" + value[len(prefix):] if value.startswith(prefix) else value

    proxies = []
    for source in catalog["proxies"]:
        row = deepcopy(source)
        if row["plant_id"] != source_id:
            raise ValueError("Unexpected plant identity in source catalog")
        row["plant_id"] = instance.plant_id
        for key in ("proxy_id", "attachment_id", "group_id"):
            row[key] = identifier(row.get(key))
        for key in ("center", "start", "end"):
            if row.get(key) is not None:
                row[key] = point(row[key])
        row["axes"] = tuple(rotate(axis) for axis in row["axes"])
        row["half_extents"] = tuple(value * factor for value in row["half_extents"])
        row["radius"] *= factor
        proxies.append(CollisionProxy(**row))
    plant = Plant.from_dict(payload)
    expected = {f"{instance.plant_id}:{node.reproductive_unit.id}" for axis in walk_axes(plant.axes) for node in axis.nodes if node.reproductive_unit and node.reproductive_unit.calyx}
    actual = {proxy.attachment_id for proxy in proxies if proxy.kind == "calyx"}
    if expected != actual or len({p.proxy_id for p in proxies}) != len(proxies):
        raise ValueError("Catalog loses or duplicates morphology organ identities")
    provenance = {key: deepcopy(value) for key, value in catalog.items() if key != "proxies"}
    provenance.update(morphology_file=str(morphology_path.resolve()), proxy_catalog_file=str(catalog_path.resolve()),
                      proxy_catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
                      internal_unit_factor=factor, instance_rotation_deg=instance.rotation_deg,
                      instance_translation_m=list(_metres(instance.position)),
                      interpreter="frozen_source_catalog_no_historical_pose_reconstruction")
    return plant, payload, proxies, provenance


def _metres(vector):
    return tuple(value / UNITS_PER_METRE for value in vector)


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _lerp(a, b, fraction):
    return tuple(x + fraction * (y - x) for x, y in zip(a, b))


def _point_segment_distance(point, start, end):
    direction = _sub(end, start)
    denominator = sum(v * v for v in direction)
    if denominator == 0:
        return math.dist(point, start)
    t = sum((p - a) * v for p, a, v in zip(point, start, direction)) / denominator
    return math.dist(point, _lerp(start, end, max(0.0, min(1.0, t))))


def _identifier(value):
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)


def _cylinder(link, name, start, end, radius, *, color=None, collision=False):
    delta = _sub(end, start)
    length = math.sqrt(sum(v * v for v in delta))
    if length <= 0 or radius <= 0:
        raise ValueError("Cylinder dimensions must be positive")
    item = element(link, "collision" if collision else "visual", name=name)
    pitch = math.acos(max(-1.0, min(1.0, delta[2] / length)))
    yaw = math.atan2(delta[1], delta[0])
    element(item, "pose", numbers((*_lerp(start, end, 0.5), 0, pitch, yaw)))
    cylinder = element(element(item, "geometry"), "cylinder")
    element(cylinder, "radius", f"{radius:.12g}")
    element(cylinder, "length", f"{length:.12g}")
    if color is not None and not collision:
        material(item, color)
    return item


def _sphere(link, name, center, radius, *, color=None, collision=False):
    item = element(link, "collision" if collision else "visual", name=name)
    element(item, "pose", numbers((*center, 0, 0, 0)))
    element(element(element(item, "geometry"), "sphere"), "radius", f"{radius:.12g}")
    if color is not None and not collision:
        material(item, color)
    return item


def _mesh_visual(link, name, uri, center, color=None, *, texture_preset=None):
    visual = element(link, "visual", name=name)
    element(visual, "pose", numbers((*center, 0, 0, 0)))
    element(element(element(visual, "geometry"), "mesh"), "uri", uri)
    if texture_preset is not None:
        apply_plant_material(visual, preset=texture_preset)
    elif color is not None:
        material(visual, color)
    return visual


def _obj(vertices, faces):
    """Triangular OBJ with explicit outward normals; no material dependencies."""
    lines = ["# Morphology-derived technical visual; metres", "o morphology_proxy"]
    lines.extend("v " + numbers(vertex) for vertex in vertices)
    for index, face in enumerate(faces, start=1):
        a, b, c = (vertices[i] for i in face)
        u, v = _sub(b, a), _sub(c, a)
        normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        norm = math.sqrt(sum(x * x for x in normal))
        if norm == 0:
            raise ValueError("Degenerate morphology visual triangle")
        lines.append("vn " + numbers(tuple(x / norm for x in normal)))
        lines.append("f " + " ".join(f"{i + 1}//{index}" for i in face))
    return "\n".join(lines) + "\n"


def _calyx_mesh(proxy):
    """Closed ellipsoid with shallow six-rib facets contained in its sphere."""
    semiaxes = _metres(proxy.half_extents)
    vertices, faces = [], []
    rings, sectors = 7, 12

    def point(local):
        return tuple(sum(local[j] * proxy.axes[j][i] for j in range(3)) for i in range(3))

    vertices.append(point((-semiaxes[0], 0, 0)))
    for ring in range(1, rings):
        theta = math.pi * ring / rings
        for sector in range(sectors):
            phi = 2 * math.pi * sector / sectors
            rib = 0.97 + 0.03 * math.cos(6 * phi)
            vertices.append(point((-semiaxes[0] * math.cos(theta), semiaxes[1] * math.sin(theta) * math.cos(phi) * rib, semiaxes[2] * math.sin(theta) * math.sin(phi) * rib)))
    tip = len(vertices)
    vertices.append(point((semiaxes[0], 0, 0)))
    for sector in range(sectors):
        following = (sector + 1) % sectors
        faces.append((0, 1 + following, 1 + sector))
        for ring in range(rings - 2):
            a = 1 + ring * sectors + sector
            b = 1 + ring * sectors + following
            c = a + sectors
            d = b + sectors
            faces.extend(((a, b, d), (a, d, c)))
        a = 1 + (rings - 2) * sectors + sector
        b = 1 + (rings - 2) * sectors + following
        faces.append((a, b, tip))
    return _obj(vertices, faces)


def _leaf_mesh(proxies, origin):
    """Batch the existing tapered leaf slabs into one low-poly visual."""
    vertices, faces = [], []
    for proxy in proxies:
        center = _sub(_metres(proxy.center), origin)
        length, width, _ = _metres(proxy.half_extents)
        start = len(vertices)
        for x, y in ((-length, 0), (-length * 0.2, -width), (length, 0), (-length * 0.2, width)):
            vertices.append(tuple(center[i] + x * proxy.axes[0][i] + y * proxy.axes[1][i] for i in range(3)))
        faces.extend(((start, start + 1, start + 2), (start, start + 2, start + 3)))
    return _obj(vertices, faces)


def _calyx_color(unit):
    state = unit.calyx.state
    if "dry" in state or "papery" in state or "straw" in state:
        return (0.72, 0.53, 0.18, 1.0)
    if "transition" in state or unit.stage == "mature_fruit_with_calyx":
        return (0.60, 0.58, 0.15, 1.0)
    return (0.29, 0.48, 0.08, 1.0)


def _clearance_obstacles(proxies):
    """Cache SI coordinates and a spatial index without changing colliders."""
    result = []
    for proxy in proxies:
        if proxy.kind in {"stem", "pedicel"} and proxy.start is not None:
            start, end = _metres(proxy.start), _metres(proxy.end)
            result.append((proxy.proxy_id, start, end, proxy.radius / UNITS_PER_METRE))
        elif proxy.kind == "calyx":
            center = _metres(proxy.center)
            result.append((proxy.proxy_id, center, center, max(proxy.half_extents) / UNITS_PER_METRE))
    cell_size = .10
    grid = {}
    for index, (_identifier, start, end, radius) in enumerate(result):
        low = [math.floor((min(a, b) - radius) / cell_size) for a, b in zip(start, end)]
        high = [math.floor((max(a, b) + radius) / cell_size) for a, b in zip(start, end)]
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                for z in range(low[2], high[2] + 1):
                    grid.setdefault((x, y, z), []).append(index)
    return {"rows": result, "grid": grid, "cell_size": cell_size}


def _candidate_clearance(calyx, pedicel, proxies, config, obstacles=None):
    """Conservative sphere-vs-capsule clearance, including the own cut stump."""
    center, radius = _metres(calyx.center), max(calyx.half_extents) / UNITS_PER_METRE
    cut = _lerp(_metres(pedicel.start), _metres(pedicel.end), config["cut_fraction"])
    best = (center[2] - radius, "ground")
    cache = obstacles if obstacles is not None else _clearance_obstacles(proxies)
    search = .05
    examined = set()
    while True:
        extent = search + radius
        low = [math.floor((p - extent) / cache["cell_size"]) for p in center]
        high = [math.floor((p + extent) / cache["cell_size"]) for p in center]
        candidates = set()
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                for z in range(low[2], high[2] + 1):
                    candidates.update(cache["grid"].get((x, y, z), ()))
        for index in sorted(candidates - examined):
            identifier, start, end, other_radius = cache["rows"][index]
            if identifier == calyx.proxy_id:
                continue
            if identifier == pedicel.proxy_id:
                end = cut
            clearance = _point_segment_distance(center, start, end) - radius - other_radius
            best = min(best, (clearance, identifier))
        examined.update(candidates)
        # Every excluded inflated obstacle AABB is outside the query cube,
        # hence has sphere clearance greater than search. The nearest result
        # is exact once it falls within that radius, including penetrations.
        if best[0] <= search:
            break
        search *= 2
    return best[0], best[1], cut


def build_harvest_plants(config: dict | None = None) -> dict:
    """Return sibling SDF models, OBJ texts and a traceable harvest inventory.

    Keys: ``models`` (Element objects), ``meshes`` (relative URI -> OBJ text),
    ``fruits`` (runtime contract), ``plants`` (source morphology and audit), and
    ``provenance``. Write every ``meshes`` key under the generated SDF directory.
    No directory is created and no simulation is run here.
    """
    c = _config(config or {})
    imported = bool(c["morphology_files"])
    params = None if imported else get_morphology_parameters(c["preset"])
    if params is not None:
        params["reproduction"]["target_reproductive_units_range"].update(min=c["reproductive_units_min"], max=c["reproductive_units_max"], status="engineering_heuristic")
    instances, plants, raw_morphologies, source_catalogs, proxies = [], {}, {}, {}, []
    for index, seed in enumerate(c["seeds"]):
        name = f"plant_{index:03d}"
        instances.append(PlantInstance(name, seed, position=tuple(v * UNITS_PER_METRE for v in c["positions_m"][index]), rotation_deg=c["rotations_deg"][index], scale=1.0, role="harvest_fixture", training_mode="rigid_fixture"))
        if imported:
            plant, raw, source_proxies, provenance = _load_catalog_plant(c["morphology_files"][index], c["proxy_catalog_files"][index], instances[-1], c["source_units_per_metre"])
            plants[name], raw_morphologies[name], source_catalogs[name] = plant, raw, provenance
            proxies.extend(source_proxies)
        else:
            plants[name] = generate_morphology_tree(seed, params=params, phenology_model=c["phenology_model"])
            raw_morphologies[name] = plants[name].to_dict()
    scene = CultivationScene("harvest_pilot", VERSION, c["seeds"][0], plant_instances=instances, metadata={"units_per_metre": UNITS_PER_METRE})
    if not imported:
        proxies = build_scene_proxies(scene, plants)
    pedicels = {p.attachment_id: p for p in proxies if p.kind == "pedicel"}
    calyces = {p.attachment_id: p for p in proxies if p.kind == "calyx"}
    units = {f"{name}:{node.reproductive_unit.id}": node.reproductive_unit for name, plant in plants.items() for axis in walk_axes(plant.axes) for node in axis.nodes if node.reproductive_unit and node.reproductive_unit.calyx and node.reproductive_unit.fruit}
    selected, audit_by_plant = {}, {}
    obstacles = _clearance_obstacles(proxies)
    for instance in instances:
        origin = _metres(instance.position)
        choices, rejected = [], []
        for identifier, calyx in sorted(calyces.items()):
            if calyx.plant_id != instance.plant_id:
                continue
            center = _metres(calyx.center)
            clearance, obstacle, cut = _candidate_clearance(calyx, pedicels[identifier], proxies, c, obstacles)
            reasons = []
            if not c["minimum_target_height_m"] <= center[2] <= c["maximum_target_height_m"]:
                reasons.append("height_out_of_fixture_range")
            if c["require_left_side"] and center[0] >= origin[0]:
                reasons.append("not_on_negative_x_face")
            if clearance < c["clearance_m"]:
                reasons.append("conservative_collider_clearance")
            record = {"id": identifier, "center_world_m": list(center), "minimum_clearance_m": clearance, "limiting_obstacle": obstacle, "reasons": reasons}
            if reasons:
                rejected.append(record)
            else:
                choices.append((center[0] - origin[0], -center[2], identifier, cut, record))
        choices.sort()
        requested = c["max_dynamic_fruits_per_plant"]
        picked = [item for item in choices if item[2] in c["target_ids"]] if c["target_ids"] else choices[:requested]
        if len(picked) != requested:
            raise ValueError(f"{instance.plant_id}: only {len(choices)} clear left-facing targets for {requested} requested; rejected={rejected}")
        for _x, _z, identifier, cut, record in picked:
            selected[identifier] = {"cut": cut, "clearance": record}
        audit_by_plant[instance.plant_id] = {"candidate_count": len(choices) + len(rejected), "eligible_count": len(choices), "selected_ids": [item[2] for item in picked], "rejected_candidates": rejected, "unselected_eligible_ids": [item[2] for item in choices if item not in picked]}

    models, meshes, inventory, reports = [], {}, [], []
    used_texture_presets = set()
    for instance in instances:
        name, origin = instance.plant_id, _metres(instance.position)
        plant = plants[name]
        model = ET.Element("model", name=name)
        element(model, "static", "true")
        element(model, "self_collide", "true")
        element(model, "pose", numbers((*origin, 0, 0, 0)))
        link = element(model, "link", name="plant_link")
        own = [p for p in proxies if p.plant_id == name]
        stem_segments = []
        for index, proxy in enumerate(own):
            if proxy.kind not in {"stem", "petiole", "pedicel"}:
                continue
            start, end = _metres(proxy.start), _metres(proxy.end)
            if proxy.kind == "pedicel" and proxy.attachment_id in selected:
                end = selected[proxy.attachment_id]["cut"]
            start, end = _sub(start, origin), _sub(end, origin)
            radius = proxy.radius / UNITS_PER_METRE
            stem_segments.append((start, end, radius))
            if proxy.kind in {"stem", "pedicel"}:
                _cylinder(link, f"rigid_{index}", start, end, radius, collision=True)
        if stem_segments:
            uri = f"meshes/{name}_stems.obj"
            meshes[uri] = cylinder_batch_mesh(stem_segments)
            _mesh_visual(link, "stems_visual", uri, (0, 0, 0), (0.25, 0.34, 0.08, 1.0))
        leaves = [p for p in own if p.kind == "leaf"]
        if leaves:
            uri = f"meshes/{name}_leaves.obj"
            leaf_shapes = {f"{name}:{node.leaf.id}": node.leaf.shape
                           for axis in walk_axes(plant.axes) for node in axis.nodes if node.leaf is not None}
            meshes[uri] = detailed_leaf_mesh(leaves, origin, leaf_shapes=leaf_shapes)
            preset = plant_texture_preset("leaf")
            used_texture_presets.add(preset)
            _mesh_visual(link, "leaves_visual_only", uri, (0, 0, 0), texture_preset=preset)
        static_ids = []
        static_calyx_batches = {}
        for identifier, calyx in sorted(calyces.items()):
            if calyx.plant_id != name:
                continue
            unit = units[identifier]
            center = _metres(calyx.center)
            calyx_mesh = detailed_calyx_mesh(calyx)
            preset = plant_texture_preset("calyx", unit.calyx.state, variant=1)
            used_texture_presets.add(preset)
            if identifier not in selected:
                static_ids.append(identifier)
                static_calyx_batches.setdefault(preset, []).append((calyx_mesh, _sub(center, origin)))
                continue
            uri = f"meshes/{_identifier(identifier)}_calyx.obj"
            meshes[uri] = calyx_mesh
            fruit_name = f"fruit_{_identifier(identifier)}"
            fruit = ET.Element("model", name=fruit_name)
            element(fruit, "static", "false")
            element(fruit, "pose", numbers((*center, 0, 0, 0)))
            fruit_link = element(fruit, "link", name="fruit_link")
            element(fruit_link, "gravity", "true")
            radius = max(calyx.half_extents) / UNITS_PER_METRE
            mass = c["fruit_mass_kg"]
            moment = 0.4 * mass * radius * radius
            inertial = element(fruit_link, "inertial")
            element(inertial, "mass", f"{mass:.12g}")
            inertia = element(inertial, "inertia")
            for axis in ("ixx", "iyy", "izz"):
                element(inertia, axis, f"{moment:.12g}")
            for axis in ("ixy", "ixz", "iyz"):
                element(inertia, axis, 0)
            collision = _sphere(fruit_link, "harvest_collision", (0, 0, 0), radius, collision=True)
            ode = element(element(element(collision, "surface"), "friction"), "ode")
            element(ode, "mu", 0.5)
            element(ode, "mu2", 0.5)
            _mesh_visual(fruit_link, "calyx", uri, (0, 0, 0), texture_preset=preset)
            _sphere(fruit_link, "berry_inside_calyx", (0, 0, 0), unit.fruit.radius_cm * 0.08 / c["source_units_per_metre"], color=(0.95, 0.42, 0.035, 1.0))
            cut, pedicel = selected[identifier]["cut"], pedicels[identifier]
            local_cut = _sub(cut, center)
            _cylinder(fruit_link, "distal_pedicel", local_cut, _sub(_metres(pedicel.end), center), pedicel.radius / UNITS_PER_METRE, color=(0.25, 0.34, 0.08, 1.0))
            models.append(fruit)
            inventory.append({
                "id": identifier, "plant_id": name, "node_id": unit.node_id,
                "unit_id": unit.id, "pedicel_id": unit.pedicel.id,
                "calyx_id": unit.calyx.id, "fruit_id": unit.fruit.id,
                "model_name": fruit_name, "link_name": "fruit_link",
                "model": fruit_name, "link": "fruit_link",
                "parent_model": name, "parent_link": "plant_link",
                "center_world_m": list(center), "cut_point_world_m": list(cut),
                "cut_point_local_m": list(local_cut),
                "pedicel_start_world_m": list(_metres(pedicel.start)),
                "pedicel_end_world_m": list(_metres(pedicel.end)),
                "cut_fraction": c["cut_fraction"], "radius_m": radius, "mass_kg": mass,
                "inertia_diagonal_kg_m2": [moment, moment, moment],
                "collision_representation": "conservative_calyx_bounding_sphere",
                "physics_parameter_status": "engineering_heuristic",
                "initial_state": "attached_to_plant_pending_runtime_initialization",
                "minimum_initial_clearance_m": selected[identifier]["clearance"]["minimum_clearance_m"],
                "agronomic_maturity": None,
            })
        for preset, pieces in sorted(static_calyx_batches.items()):
            uri = f"meshes/{name}_{preset}_static.obj"
            meshes[uri] = merge_obj_meshes(pieces)
            _mesh_visual(link, f"static_{preset}", uri, (0, 0, 0), texture_preset=preset)
        models.append(model)
        reports.append({
            "id": name, "seed": instance.seed, "model_name": name,
            "position_m": list(origin), "rotation_deg": instance.rotation_deg,
            "source_morphology": raw_morphologies[name], "source_instance": instance.to_dict(),
            **({"source_catalog": source_catalogs[name]} if imported else {}),
            "node_count": plant.node_count(), "fruit_calyx_count": sum(p.kind == "calyx" for p in own),
            "dynamic_fruit_count": len(audit_by_plant[name]["selected_ids"]),
            "static_visual_only_fruit_ids": static_ids,
            "flower_visuals_omitted_count": sum(n.reproductive_unit is not None and n.reproductive_unit.stage == "flower" for a in walk_axes(plant.axes) for n in a.nodes),
            "selection_audit": audit_by_plant[name],
            "rigid_collision_count": len(link.findall("collision")),
            "visual_count": len(link.findall("visual")),
            "visual_leaf_count": len({leaf.attachment_id for leaf in leaves}),
            "static_calyx_material_batches": {preset: len(pieces) for preset, pieces in sorted(static_calyx_batches.items())},
            "source_stem_height_m": max(_metres(p.end)[2] for p in own if p.kind == "stem") - origin[2],
        })
    return {
        "models": models, "meshes": meshes, "fruits": inventory, "plants": reports,
        "texture_assets": {uri: str(Path(__file__).resolve().parents[2] / path)
                           for uri, path in texture_asset_paths(used_texture_presets).items()},
        "provenance": {
            "script_version": VERSION, "config": c, "morphology_parameters": params,
            "source_units_per_metre": c["source_units_per_metre"], "output_units": "metres",
            **({"source_catalogs": source_catalogs, "morphology_mode": "admitted_source_catalog"} if imported else {}),
            "parameter_status": "engineering_heuristic", "human_validation": "pending",
            "visual_interpreter": {"version": VISUAL_VERSION,
                                   "surface_geometry": "continuous_curved_leaf_and_five_rib_calyx_from_source_proxy_poses",
                                   "texture_library": "assets/textures/current",
                                   "texture_presets": sorted(used_texture_presets),
                                   "batching": "one_stem_batch_one_leaf_batch_and_static_calyces_by_material_per_plant",
                                   "source_blender_mesh_equivalence": False,
                                   "collision_geometry_modified": False},
            "selection_policy": "negative_x_face_then_height_with_conservative_clearance",
            "source_scene": scene.to_dict(), "limitations": ([item for item in LIMITATIONS if not item.startswith(("Technical small-plant", "Legacy independent"))] + ["Source admission is static evidence; imported proxy colliders and harvesting dynamics require their own validation."] if imported else list(LIMITATIONS)),
        },
    }
