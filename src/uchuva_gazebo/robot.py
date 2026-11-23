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


def solve_task(resolved, constraints, seed=None):
    """Bounded numerical task solution followed by declared collision checks.

The result reports full position/direction residuals even on failure. Optional
obstacles use the same primitive/pose format as collision_shapes. Bounding-box
overlap is conservative: a rejected candidate is not proof that no solution
exists. This checks a posture, never an unobserved continuous trajectory.
"""
    from .robot_motion import box_separation, shape_box
    if not isinstance(constraints, dict):
        raise ValueError("Task constraints must be an explicit mapping")
    allowed = {"target_position_m", "target_direction", "tool_frame", "tool_axis",
               "orientation_mode", "position_tolerance_m", "direction_tolerance_rad",
               "max_iterations", "damping", "max_step_rad", "obstacles", "clearance_m"}
    if set(constraints)-allowed or "target_position_m" not in constraints:
        raise ValueError("Unknown or incomplete task constraints")
    clearance = constraints.get("clearance_m", 0)
    if type(clearance) not in (int, float) or not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Task clearance must be finite and nonnegative")
    options = {k: v for k, v in constraints.items() if k not in ("obstacles", "clearance_m")}
    result = solve_ik(resolved, seed=seed, **options)
    observations = asdict(result)
    observations.update(robot_spec_sha256=resolved.sha256, collision_status="NO EJECUTADO",
                        collision_pairs=[], evaluated_posture_only=True)
    if not result.success:
        return observations
    if any(j["group"] in ("passive", "gripper") and j["type"] != "fixed" for j in resolved.joints):
        raise ValueError("Articulated passive/gripper task checks require an explicit observed mechanism state")
    shapes = collision_shapes(resolved, forward_kinematics(resolved, result.joint_positions))
    boxes = [(s, shape_box(s)) for s in shapes]
    excluded = {tuple(sorted(pair["links"])) for pair in resolved.data["collision_policy"]["excluded_pairs"]}
    conflicts = []
    for i, (first, half) in enumerate(boxes):
        for second, other_half in boxes[i+1:]:
            if first["link"] == second["link"] or tuple(sorted((first["link"], second["link"]))) in excluded:
                continue
            gap = box_separation(first, half, second, other_half)
            if gap <= clearance:
                conflicts.append({"first": first["link"]+"/"+first["name"],
                                  "second": second["link"]+"/"+second["name"], "conservative_gap_m": gap})
        for obstacle in constraints.get("obstacles", []):
            gap = box_separation(first, half, obstacle, shape_box(obstacle))
            if gap <= clearance:
                conflicts.append({"first": first["link"]+"/"+first["name"],
                                  "second": obstacle["name"], "conservative_gap_m": gap})
    observations.update(success=not conflicts, collision_status="FAIL" if conflicts else "PASS", collision_pairs=conflicts)
    if conflicts:
        observations["reason"] = "candidate_rejected_by_conservative_collision_check"
    return observations
