"""Public parametric robot interfaces, independent of Gazebo Python bindings."""
from __future__ import annotations

from dataclasses import asdict
import math

from .robot_spec import RobotSpec, ResolvedRobot, resolve_robot
from .robot_kinematics import forward_kinematics, collision_shapes, solve_ik
from .robot_sdf import resolved_robot_model, resolved_robot_contract


def build_robot_sdf(resolved, start_pose=(0, 0, 0, 0)):
    """Return the SDF model element, with x/y/z/yaw start pose."""
    return resolved_robot_model(resolved, start_pose)


def robot_contract(resolved):
    return resolved_robot_contract(resolved)


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
    options = {k: v for k, v in constraints.items() if k not in ("obstacles", "clearance_m", "auxiliary_joint_positions")}
    result = solve_ik(resolved, seed=seed, **options)
    observations = asdict(result)
    observations.update(robot_spec_sha256=resolved.sha256, collision_status="NO EJECUTADO",
                        collision_pairs=[], evaluated_posture_only=True)
    if not result.success:
        return observations
    auxiliary = constraints.get('auxiliary_joint_positions', {})
    needed = {j['name'] for j in resolved.joints if j['group'] in ('passive', 'gripper') and j['type'] != 'fixed'}
    if not isinstance(auxiliary, dict) or set(auxiliary) != needed:
        raise ValueError("Articulated passive/gripper task checks require an explicit observed mechanism state")
    positions = {**auxiliary, **dict(zip(resolved.joint_names, result.joint_positions))}
    shapes = collision_shapes(resolved, forward_kinematics(resolved, positions))
    obstacles = constraints.get('obstacles', [])
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
        return repository.shape_distance(a, b) if ah is None or bh is None else box_separation(a, ah, b, bh)
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
