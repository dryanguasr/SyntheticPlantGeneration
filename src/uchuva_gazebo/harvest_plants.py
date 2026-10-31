"""Small morphology-derived Gazebo fixtures with independent harvestable units.

No Blender or Gazebo runtime is imported. The existing morphology/proxy
interpreter owns all organ positions. This module only converts its eight
internal units per metre to SI and supplies explicitly heuristic rigid-body
properties. A runtime system must attach the returned dynamic fruit models
before the first physics step; this exporter does not implement cutting.
"""

from __future__ import annotations

from copy import deepcopy
import math
import re
import xml.etree.ElementTree as ET

from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.scene import CultivationScene, PlantInstance
from uchuva_lsystem.sparse_pilot import UNITS_PER_METRE, walk_axes

from .field import element, material, numbers


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
}

LIMITATIONS = [
    "Technical small-plant fixture; adult field geometry is not calibrated.",
    "Rigid stems and ideal removable attachment; no compliant branches or fracture law.",
    "Fruit and calyx form one rigid body with a conservative spherical collider.",
    "Mass, inertia approximation, friction and cut fraction are engineering heuristics.",
    "Low-poly calyx/leaf visuals approximate existing morphology proxies, not Blender meshes.",
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
    if c["phenology_model"] != "legacy_independent":
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


def _mesh_visual(link, name, uri, center, color):
    visual = element(link, "visual", name=name)
    element(visual, "pose", numbers((*center, 0, 0, 0)))
    element(element(element(visual, "geometry"), "mesh"), "uri", uri)
    material(visual, color)


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


def _candidate_clearance(calyx, pedicel, proxies, config):
    """Conservative sphere-vs-capsule clearance, including the own cut stump."""
    center, radius = _metres(calyx.center), max(calyx.half_extents) / UNITS_PER_METRE
    cut = _lerp(_metres(pedicel.start), _metres(pedicel.end), config["cut_fraction"])
    distances = [(center[2] - radius, "ground")]
    for other in proxies:
        if other.kind in {"stem", "pedicel"} and other.start is not None:
            start, end = _metres(other.start), _metres(other.end)
            if other.proxy_id == pedicel.proxy_id:
                end = cut
            clearance = _point_segment_distance(center, start, end) - radius - other.radius / UNITS_PER_METRE
            distances.append((clearance, other.proxy_id))
        elif other.kind == "calyx" and other.proxy_id != calyx.proxy_id:
            # Non-selected calyces are visual-only, but avoid an obvious visual overlap too.
            clearance = math.dist(center, _metres(other.center)) - radius - max(other.half_extents) / UNITS_PER_METRE
            distances.append((clearance, other.proxy_id))
    clearance, obstacle = min(distances)
    return clearance, obstacle, cut


def build_harvest_plants(config: dict | None = None) -> dict:
    """Return sibling SDF models, OBJ texts and a traceable harvest inventory.

    Keys: ``models`` (Element objects), ``meshes`` (relative URI -> OBJ text),
    ``fruits`` (runtime contract), ``plants`` (source morphology and audit), and
    ``provenance``. Write every ``meshes`` key under the generated SDF directory.
    No directory is created and no simulation is run here.
    """
    c = _config(config or {})
    params = get_morphology_parameters(c["preset"])
    params["reproduction"]["target_reproductive_units_range"].update(min=c["reproductive_units_min"], max=c["reproductive_units_max"], status="engineering_heuristic")
    instances, plants = [], {}
    for index, seed in enumerate(c["seeds"]):
        name = f"plant_{index:03d}"
        instances.append(PlantInstance(name, seed, position=tuple(v * UNITS_PER_METRE for v in c["positions_m"][index]), rotation_deg=c["rotations_deg"][index], scale=1.0, role="harvest_fixture", training_mode="rigid_fixture"))
        plants[name] = generate_morphology_tree(seed, params=params, phenology_model=c["phenology_model"])
    scene = CultivationScene("harvest_pilot", VERSION, c["seeds"][0], plant_instances=instances, metadata={"units_per_metre": UNITS_PER_METRE})
    proxies = build_scene_proxies(scene, plants)
    pedicels = {p.attachment_id: p for p in proxies if p.kind == "pedicel"}
    calyces = {p.attachment_id: p for p in proxies if p.kind == "calyx"}
    units = {f"{name}:{node.reproductive_unit.id}": node.reproductive_unit for name, plant in plants.items() for axis in walk_axes(plant.axes) for node in axis.nodes if node.reproductive_unit and node.reproductive_unit.calyx and node.reproductive_unit.fruit}
    selected, audit_by_plant = {}, {}
    for instance in instances:
        origin = _metres(instance.position)
        choices, rejected = [], []
        for identifier, calyx in sorted(calyces.items()):
            if calyx.plant_id != instance.plant_id:
                continue
            center = _metres(calyx.center)
            clearance, obstacle, cut = _candidate_clearance(calyx, pedicels[identifier], proxies, c)
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
        if len(choices) < requested:
            raise ValueError(f"{instance.plant_id}: only {len(choices)} clear left-facing targets for {requested} requested; rejected={rejected}")
        for _x, _z, identifier, cut, record in choices[:requested]:
            selected[identifier] = {"cut": cut, "clearance": record}
        audit_by_plant[instance.plant_id] = {"candidate_count": len(choices) + len(rejected), "eligible_count": len(choices), "selected_ids": [item[2] for item in choices[:requested]], "rejected_candidates": rejected, "unselected_eligible_ids": [item[2] for item in choices[requested:]]}

    models, meshes, inventory, reports = [], {}, [], []
    for instance in instances:
        name, origin = instance.plant_id, _metres(instance.position)
        plant = plants[name]
        model = ET.Element("model", name=name)
        element(model, "static", "true")
        element(model, "self_collide", "true")
        element(model, "pose", numbers((*origin, 0, 0, 0)))
        link = element(model, "link", name="plant_link")
        own = [p for p in proxies if p.plant_id == name]
        for index, proxy in enumerate(own):
            if proxy.kind not in {"stem", "petiole", "pedicel"}:
                continue
            start, end = _metres(proxy.start), _metres(proxy.end)
            if proxy.kind == "pedicel" and proxy.attachment_id in selected:
                end = selected[proxy.attachment_id]["cut"]
            start, end = _sub(start, origin), _sub(end, origin)
            radius = proxy.radius / UNITS_PER_METRE
            _cylinder(link, f"organ_{index}", start, end, radius, color=(0.25, 0.34, 0.08, 1.0))
            if proxy.kind in {"stem", "pedicel"}:
                _cylinder(link, f"rigid_{index}", start, end, radius, collision=True)
        leaves = [p for p in own if p.kind == "leaf"]
        if leaves:
            uri = f"meshes/{name}_leaves.obj"
            meshes[uri] = _leaf_mesh(leaves, origin)
            _mesh_visual(link, "leaves_visual_only", uri, (0, 0, 0), (0.12, 0.36, 0.045, 1.0))
        static_ids = []
        for identifier, calyx in sorted(calyces.items()):
            if calyx.plant_id != name:
                continue
            unit = units[identifier]
            center = _metres(calyx.center)
            uri = f"meshes/{_identifier(identifier)}_calyx.obj"
            meshes[uri] = _calyx_mesh(calyx)
            if identifier not in selected:
                static_ids.append(identifier)
                _mesh_visual(link, f"calyx_{_identifier(unit.id)}", uri, _sub(center, origin), _calyx_color(unit))
                continue
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
            _mesh_visual(fruit_link, "calyx", uri, (0, 0, 0), _calyx_color(unit))
            _sphere(fruit_link, "berry_inside_calyx", (0, 0, 0), unit.fruit.radius_cm * 0.01, color=(0.95, 0.42, 0.035, 1.0))
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
        models.append(model)
        reports.append({
            "id": name, "seed": instance.seed, "model_name": name,
            "position_m": list(origin), "rotation_deg": instance.rotation_deg,
            "source_morphology": plant.to_dict(), "source_instance": instance.to_dict(),
            "node_count": plant.node_count(), "fruit_calyx_count": sum(p.kind == "calyx" for p in own),
            "dynamic_fruit_count": len(audit_by_plant[name]["selected_ids"]),
            "static_visual_only_fruit_ids": static_ids,
            "flower_visuals_omitted_count": sum(n.reproductive_unit is not None and n.reproductive_unit.stage == "flower" for a in walk_axes(plant.axes) for n in a.nodes),
            "selection_audit": audit_by_plant[name],
            "rigid_collision_count": len(link.findall("collision")),
            "source_stem_height_m": max(_metres(p.end)[2] for p in own if p.kind == "stem") - origin[2],
        })
    return {
        "models": models, "meshes": meshes, "fruits": inventory, "plants": reports,
        "provenance": {
            "script_version": VERSION, "config": c, "morphology_parameters": params,
            "source_units_per_metre": UNITS_PER_METRE, "output_units": "metres",
            "parameter_status": "engineering_heuristic", "human_validation": "pending",
            "selection_policy": "negative_x_face_then_height_with_conservative_clearance",
            "source_scene": scene.to_dict(), "limitations": list(LIMITATIONS),
        },
    }
