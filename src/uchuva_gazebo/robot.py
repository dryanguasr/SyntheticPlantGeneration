"""Public parametric robot interfaces, independent of Gazebo Python bindings."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import math
from pathlib import PurePosixPath
import re

from .robot_spec import RobotSpec, ResolvedRobot, resolve_robot, _number, _vector
from .robot_kinematics import (forward_kinematics, collision_shapes, solve_ik,
                               validate_auxiliary_joint_positions, _pose)
from .robot_sdf import resolved_robot_model, resolved_robot_contract


def build_robot_sdf(resolved, start_pose=(0, 0, 0, 0)):
    """Return the SDF model element, with x/y/z/yaw start pose."""
    return resolved_robot_model(resolved, start_pose)


def robot_contract(resolved):
    return resolved_robot_contract(resolved)


def _validated_obstacles(obstacles):
    """Validate external collision inputs before numerical or geometry work."""
    if not isinstance(obstacles, (list, tuple)):
        raise ValueError("Obstacles must be a list or tuple of collision shapes")
    result, names = [], set()
    geometry_fields = {"box": {"type", "size_m"}, "sphere": {"type", "radius_m"},
                       "cylinder": {"type", "radius_m", "length_m"},
                       "mesh": {"type", "uri", "sha256", "bound_parameters", "scale"}}
    for obstacle in obstacles:
        if (not isinstance(obstacle, Mapping)
                or not {"name", "pose", "geometry"} <= set(obstacle)
                or set(obstacle)-{"name", "link", "pose", "geometry", "surface"}):
            raise ValueError("Obstacle requires the collision-shape name, pose and geometry format")
        name = obstacle["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Obstacle names must be nonempty and unique")
        names.add(name)
        pose = obstacle["pose"]
        if not isinstance(pose, Mapping) or set(pose) != {"xyz_m", "quaternion_xyzw"}:
            raise ValueError("Obstacle pose requires explicit position and unit quaternion")
        pose = _pose(pose)
        geometry = obstacle["geometry"]
        if (not isinstance(geometry, Mapping) or not isinstance(geometry.get("type"), str)
                or geometry["type"] not in geometry_fields):
            raise ValueError("Unknown obstacle geometry")
        kind = geometry["type"]
        if set(geometry)-geometry_fields[kind]:
            raise ValueError("Obstacle geometry fields differ from its declared type")
        if kind == "box":
            if any(v <= 0 for v in _vector(geometry.get("size_m"), 3, "obstacle box")):
                raise ValueError("Obstacle box dimensions must be positive")
        elif kind in ("sphere", "cylinder"):
            _number(geometry.get("radius_m"), "obstacle radius", positive=True)
            if kind == "cylinder":
                _number(geometry.get("length_m"), "obstacle length", positive=True)
        else:
            uri = geometry.get("uri")
            if (not isinstance(uri, str) or not uri or "\\" in uri or ":" in uri
                    or PurePosixPath(uri).is_absolute() or ".." in PurePosixPath(uri).parts):
                raise ValueError("Obstacle mesh URI must stay relative to its explicit asset root")
            digest = geometry.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("Obstacle mesh requires its source SHA-256")
            if "scale" in geometry and _vector(geometry["scale"], 3, "obstacle mesh scale") != [1., 1., 1.]:
                raise ValueError("Obstacle mesh must already be in SI with unit scale")
            if "bound_parameters" in geometry and not isinstance(geometry["bound_parameters"], Mapping):
                raise ValueError("Obstacle mesh bound_parameters must be a mapping")
        result.append({**obstacle, "pose": pose, "geometry": dict(geometry)})
    return tuple(result)


def solve_task(resolved, constraints, seed=None, *, asset_root=None):
    """Bounded numerical task solution followed by declared collision checks.

The result reports full position/direction residuals even on failure. Optional
obstacles use the collision_shapes geometry/pose format. Primitive bounding
boxes are conservative; admitted meshes use their shared, hashed tessellation.
A rejected candidate is not proof that no solution exists. This checks a
posture, never an unobserved continuous trajectory.
"""
    from .robot_motion import box_separation, shape_box
    if not isinstance(constraints, dict):
        raise ValueError("Task constraints must be an explicit mapping")
    allowed = {"target_position_m", "target_direction", "tool_frame", "tool_axis",
               "orientation_mode", "position_tolerance_m", "direction_tolerance_rad",
               "max_iterations", "damping", "max_step_rad", "obstacles", "clearance_m",
               "auxiliary_joint_positions"}
    if set(constraints)-allowed or "target_position_m" not in constraints:
        raise ValueError("Unknown or incomplete task constraints")
    clearance = constraints.get("clearance_m", 0)
    if type(clearance) not in (int, float) or not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Task clearance must be finite and nonnegative")
    obstacles = _validated_obstacles(constraints.get("obstacles", []))
    auxiliary = validate_auxiliary_joint_positions(resolved, constraints.get('auxiliary_joint_positions', {}))
    needed = {j['name'] for j in resolved.joints if j['group'] in ('passive', 'gripper') and j['type'] != 'fixed'}
    if set(auxiliary) != needed:
        raise ValueError("Articulated passive/gripper task checks require an explicit observed mechanism state")
    options = {k: v for k, v in constraints.items() if k not in ("obstacles", "clearance_m", "auxiliary_joint_positions")}
    result = solve_ik(resolved, seed=seed, auxiliary_joint_positions=auxiliary, **options)
    observations = asdict(result)
    observations.update(robot_spec_sha256=resolved.sha256, collision_status="NO EJECUTADO",
                        collision_pairs=[], evaluated_posture_only=True)
    if not result.success:
        return observations
    positions = {**auxiliary, **dict(zip(resolved.joint_names, result.joint_positions))}
    shapes = collision_shapes(resolved, forward_kinematics(resolved, positions))
    geometries = [s['geometry'] for s in [*shapes, *obstacles] if s['geometry']['type'] == 'mesh']
    repository = None
    if geometries:
        if asset_root is None:
            raise ValueError('Mesh task checking requires an explicit verified asset root')
        from .robot_mesh_geometry import MeshRepository
        repository = MeshRepository(asset_root, geometries)
    def half_size(shape):
        return None if shape['geometry']['type'] == 'mesh' else shape_box(shape)
    def separation(a, ah, b, bh):
        gap = repository.shape_distance(a, b) if ah is None or bh is None else box_separation(a, ah, b, bh)
        return _number(gap, "collision separation")
    boxes = [(s, half_size(s)) for s in shapes]
    excluded = {tuple(sorted(pair["links"])) for pair in resolved.data["collision_policy"]["excluded_pairs"]}
    conflicts = []
    for i, (first, half) in enumerate(boxes):
        for second, other_half in boxes[i+1:]:
            if first["link"] == second["link"] or tuple(sorted((first["link"], second["link"]))) in excluded:
                continue
            gap = separation(first, half, second, other_half)
            if gap <= clearance:
                conflicts.append({"first": first["link"]+"/"+first["name"],
                                  "second": second["link"]+"/"+second["name"], "conservative_gap_m": gap})
        for obstacle in obstacles:
            gap = separation(first, half, obstacle, half_size(obstacle))
            if gap <= clearance:
                conflicts.append({"first": first["link"]+"/"+first["name"],
                                  "second": obstacle["name"], "conservative_gap_m": gap})
    observations.update(success=not conflicts, collision_status="FAIL" if conflicts else "PASS", collision_pairs=conflicts)
    if conflicts:
        observations["reason"] = "candidate_rejected_by_conservative_collision_check"
    return observations
