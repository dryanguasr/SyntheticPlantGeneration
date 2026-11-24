"""General rigid transforms and bounded five-axis task IK from ResolvedRobot.

The numerical solver certifies only its reported task residual and joint limits.
It neither certifies collision freedom nor creates a six-DOF arm from five axes.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

from .robot_spec import ResolvedRobot, _number, _vector, _thaw


def pose_identity():
    return {"xyz_m": [0.0, 0.0, 0.0], "quaternion_xyzw": [0.0, 0.0, 0.0, 1.0]}


def _quaternion(value):
    q = _vector(value, 4, "quaternion")
    length = math.sqrt(sum(v*v for v in q))
    if abs(length-1) > 1e-7:
        raise ValueError("Quaternion must be unit length")
    return [v/length for v in q]


def _pose(value):
    if value is None:
        return pose_identity()
    if not isinstance(value, Mapping):
        value = _vector(value, 7, "pose xyz+xyzw")
        value = {"xyz_m": value[:3], "quaternion_xyzw": value[3:]}
    return {"xyz_m": _vector(value["xyz_m"], 3, "position"),
            "quaternion_xyzw": _quaternion(value["quaternion_xyzw"])}


def _multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def rotate_vector(quaternion, vector):
    q = _quaternion(quaternion)
    v = _vector(vector, 3, "vector")
    return _multiply(_multiply(q, [*v, 0]), [-q[0], -q[1], -q[2], q[3]])[:3]


def transform_point(pose, point):
    p = _pose(pose)
    return [a+b for a, b in zip(p["xyz_m"], rotate_vector(p["quaternion_xyzw"], point))]


def compose_poses(a, b):
    a, b = _pose(a), _pose(b)
    return {"xyz_m": transform_point(a, b["xyz_m"]),
            "quaternion_xyzw": _quaternion(_multiply(a["quaternion_xyzw"], b["quaternion_xyzw"]))}


def inverse_pose(pose):
    p = _pose(pose)
    x, y, z, w = p["quaternion_xyzw"]
    q = [-x, -y, -z, w]
    return {"xyz_m": rotate_vector(q, [-v for v in p["xyz_m"]]), "quaternion_xyzw": q}


def axis_quaternion(axis, angle):
    axis = _vector(axis, 3, "axis")
    angle = _number(angle, "angle")
    if abs(sum(v*v for v in axis)-1) > 1e-7:
        raise ValueError("Rotation axis must be unit length")
    return [*(v*math.sin(angle/2) for v in axis), math.cos(angle/2)]


def pose_from_rpy(xyz, rpy):
    roll, pitch, yaw = _vector(rpy, 3, "rpy")
    q = _multiply(_multiply(axis_quaternion([0, 0, 1], yaw), axis_quaternion([0, 1, 0], pitch)), axis_quaternion([1, 0, 0], roll))
    return {"xyz_m": _vector(xyz, 3, "xyz"), "quaternion_xyzw": q}


def forward_kinematics(robot: ResolvedRobot, joint_positions=None, base_pose=None, *, check_limits=True):
    """Return every link and named frame in world coordinates.

    q is the commanded coordinate. Motion uses q+zero_offset. The full chain
    transform is parent * origin * joint_motion * child_pose; offsets after a
    wrist axis therefore rotate with it, unlike a planar length-only model.
    Missing passive/drive coordinates default to zero, never a measured state.
    """
    robot.require_capability("fk")
    if joint_positions is None:
        positions = dict(robot.data["arm_home_positions"])
    elif isinstance(joint_positions, Mapping):
        positions = dict(joint_positions)
    else:
        values = _vector(joint_positions, len(robot.joint_names), "arm coordinates")
        positions = dict(zip(robot.joint_names, values))
    names = {row["name"] for row in robot.joints}
    if set(positions)-names or set(robot.joint_names)-set(positions):
        raise ValueError("Joint coordinates have unknown names or omit arm joints")
    poses = {robot.data["root_link"]: _pose(base_pose)}
    pending = list(robot.joints)
    while pending:
        ready = [row for row in pending if row["parent"] in poses]
        if not ready:
            raise ValueError("Disconnected/cyclic joint tree")
        for row in ready:
            q = _number(positions.get(row["name"], 0), row["name"])
            motion = pose_identity()
            if row["type"] != "fixed":
                limits = row["limits"]
                if check_limits and not limits["lower"]-1e-12 <= q <= limits["upper"]+1e-12:
                    raise ValueError(f"Joint {row['name']} exceeds limits")
                q += row["zero_offset"]
                if row["type"] == "revolute":
                    motion["quaternion_xyzw"] = axis_quaternion(row["axis"], q)
                else:
                    motion["xyz_m"] = [q*v for v in row["axis"]]
            poses[row["child"]] = compose_poses(compose_poses(compose_poses(poses[row["parent"]], row["origin"]), motion), row["child_pose"])
            pending.remove(row)
    pending = list(robot.frames)
    while pending:
        ready = [row for row in pending if row["parent"] in poses]
        if not ready:
            raise ValueError("Disconnected/cyclic frames")
        for row in ready:
            poses[row["name"]] = compose_poses(poses[row["parent"]], row["pose"])
            pending.remove(row)
    return poses


def collision_shapes(robot, frame_poses):
    """Declared collision primitives/mesh identities with full observed/FK poses."""
    robot.require_capability("collision_primitives")
    result = []
    for link in robot.links:
        if link["name"] not in frame_poses:
            raise ValueError("Missing collision link pose")
        for shape in link["collisions"]:
            if shape["geometry"]["type"] not in ("box", "sphere", "cylinder", "mesh"):
                raise ValueError("Unsupported collision geometry")
            if shape['geometry']['type'] == 'mesh':
                robot.require_capability('collision_meshes')
            result.append({"name": shape["name"], "link": link["name"],
                           "geometry": _thaw(shape["geometry"]),
                           "pose": compose_poses(frame_poses[link["name"]], shape["pose"]),
                           **({"surface": _thaw(shape["surface"])} if "surface" in shape else {})})
    return tuple(result)


def validate_auxiliary_joint_positions(robot, positions):
    """Copy finite, bounded non-arm coordinates held fixed during a task solve.

    Omitting this optional map preserves the historical nominal-zero state.
    Callers claiming an observed passive/gripper state must supply it explicitly.
    """
    if positions is None:
        return {}
    if not isinstance(positions, Mapping):
        raise ValueError("Auxiliary joint positions must be an explicit mapping")
    rows = {row["name"]: row for row in robot.joints}
    if set(positions)-set(rows) or set(positions) & set(robot.joint_names):
        raise ValueError("Auxiliary coordinates must name known non-arm joints")
    result = {}
    for name, value in positions.items():
        value = _number(value, name)
        joint = rows[name]
        if joint["type"] == "fixed":
            if value != 0:
                raise ValueError(f"Fixed joint {name} cannot have a moving coordinate")
        elif not joint["limits"]["lower"] <= value <= joint["limits"]["upper"]:
            raise ValueError(f"Auxiliary joint {name} exceeds limits")
        result[name] = value
    return result


@dataclass(frozen=True)
class IKResult:
    success: bool
    joint_positions: tuple
    position_error_m: float
    direction_error_rad: float | None
    iterations: int
    reason: str
    orientation_mode: str
    unconstrained_rotation: str

    @property
    def joints(self):
        return self.joint_positions


def _solve_linear(matrix, right):
    a = [list(row)+[value] for row, value in zip(matrix, right)]
    n = len(right)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(a[i][col]))
        if abs(a[pivot][col]) < 1e-15:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        scale = a[col][col]
        a[col] = [v/scale for v in a[col]]
        for row in range(n):
            if row != col:
                scale = a[row][col]
                a[row] = [v-scale*w for v, w in zip(a[row], a[col])]
    return [row[-1] for row in a]


def solve_ik(robot, target_position_m, target_direction=None, *, tool_frame="tcp",
             seed=None, orientation_mode="position_direction", tool_axis=(0, 0, 1),
             position_tolerance_m=1e-5, direction_tolerance_rad=1e-4,
             max_iterations=160, damping=.003, max_step_rad=.20,
             auxiliary_joint_positions=None):
    """Bounded damped least squares: position + an explicit tool-axis direction.

    A direction has two independent constraints. Its axial rotation is free.
    Position-only is available only by explicit mode, never implicit fallback.
    Failure preserves the best candidate/residuals and does not imply global
    infeasibility. Numerical tolerances are solver controls, not CAD accuracy.
    Supplied non-arm coordinates remain fixed in every FK/Jacobian evaluation.
    """
    robot.require_capability("ik_position_direction")
    names = robot.joint_names
    if len(names) != 5:
        raise ValueError("This task solver supports exactly five arm joints")
    if orientation_mode not in ("position_direction", "position_only"):
        raise ValueError("Five-axis IK does not accept an arbitrary full six-DOF pose")
    target = _vector(target_position_m, 3, "target position")
    if type(max_iterations) is not int or not 1 <= max_iterations <= 2000:
        raise ValueError("Bounded max_iterations must be in [1, 2000]")
    for label, value in [("position tolerance", position_tolerance_m), ("direction tolerance", direction_tolerance_rad), ("damping", damping), ("max step", max_step_rad)]:
        _number(value, label, positive=True)
    axis = _vector(tool_axis, 3, "tool axis")
    if abs(sum(v*v for v in axis)-1) > 1e-7:
        raise ValueError("Tool axis must be unit length")
    direction = None
    if orientation_mode == "position_direction":
        direction = _vector(target_direction, 3, "required target direction")
        if abs(sum(v*v for v in direction)-1) > 1e-7:
            raise ValueError("Target direction must be unit length")
    elif target_direction is not None:
        raise ValueError("Position-only mode cannot silently ignore a supplied direction")
    rows = {row["name"]: row for row in robot.joints}
    auxiliary = validate_auxiliary_joint_positions(robot, auxiliary_joint_positions)
    if any(rows[name]["type"] != "revolute" for name in names):
        raise ValueError("Five-axis task solver currently requires revolute arm joints")
    if seed is None:
        q = [robot.data["arm_home_positions"][name] for name in names]
    elif isinstance(seed, Mapping):
        if set(seed) != set(names):
            raise ValueError("IK seed mapping must cover exactly the arm joints")
        q = [_number(seed[name], "seed") for name in names]
    else:
        q = _vector(seed, 5, "IK seed")
    limits = [(rows[name]["limits"]["lower"], rows[name]["limits"]["upper"]) for name in names]
    if any(not lo <= value <= hi for value, (lo, hi) in zip(q, limits)):
        raise ValueError("IK seed exceeds joint limits")
    orientation_weight = .3  # metre-scale numerical balancing, not a tolerance.

    def observe(values):
        positions = {**auxiliary, **dict(zip(names, values))}
        frames = forward_kinematics(robot, positions)
        if tool_frame not in frames:
            raise ValueError("Unknown IK task frame")
        pose = frames[tool_frame]
        d = rotate_vector(pose["quaternion_xyzw"], axis)
        features = list(pose["xyz_m"]) + ([orientation_weight*v for v in d] if direction else [])
        pe = math.dist(target, pose["xyz_m"])
        de = math.acos(max(-1, min(1, sum(a*b for a, b in zip(d, direction))))) if direction else None
        return features, pe, de

    goal = target + ([orientation_weight*v for v in direction] if direction else [])
    best = None
    for iteration in range(max_iterations+1):
        features, pe, de = observe(q)
        error = [a-b for a, b in zip(goal, features)]
        cost = sum(v*v for v in error)
        if best is None or cost < best[0]:
            best = (cost, tuple(q), pe, de, iteration)
        if pe <= position_tolerance_m and (de is None or de <= direction_tolerance_rad):
            return IKResult(True, tuple(q), pe, de, iteration, "task_converged", orientation_mode,
                            "rotation_about_target_direction" if direction else "all_orientation")
        if iteration == max_iterations:
            break
        columns = []
        for j, (lo, hi) in enumerate(limits):
            plus, minus = list(q), list(q)
            plus[j], minus[j] = min(hi, q[j]+1e-5), max(lo, q[j]-1e-5)
            span = plus[j]-minus[j]
            fp, fm = observe(plus)[0], observe(minus)[0]
            columns.append([(a-b)/span for a, b in zip(fp, fm)])
        normal = [[sum(a*b for a, b in zip(columns[i], columns[j])) + (damping*damping if i == j else 0) for j in range(5)] for i in range(5)]
        right = [sum(a*b for a, b in zip(column, error)) for column in columns]
        step = _solve_linear(normal, right)
        if step is None:
            break
        magnitude = max(abs(v) for v in step)
        if magnitude > max_step_rad:
            step = [v*max_step_rad/magnitude for v in step]
        improved = False
        for scale in (1, .5, .25, .125, .0625, .015625):
            candidate = [max(lo, min(hi, value+scale*delta)) for value, delta, (lo, hi) in zip(q, step, limits)]
            candidate_features = observe(candidate)[0]
            if sum((a-b)**2 for a, b in zip(goal, candidate_features)) < cost-1e-18:
                q, improved = candidate, True
                break
        if not improved:
            break
    _, q, pe, de, _ = best
    return IKResult(False, q, pe, de, iteration, "bounded_search_did_not_converge", orientation_mode,
                    "rotation_about_target_direction" if direction else "all_orientation")
