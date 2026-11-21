"""Bounded, deterministic motion screening for the small harvest fixture.

This is a sampled geometric check, not a general motion planner or continuous
collision certificate. It uses the *exported* rigid cylinders, the proxy
robot's collision boxes, and fruit collision spheres. Leaves remain visual.
Gazebo must still verify tracking error, contact response and constraint
transfer. No runtime imports or additional Python dependencies are required.
"""

from __future__ import annotations

import math
from pathlib import Path

from .harvest_collision_mesh import identity_digest, read_collision_prisms

from .harvester_robot import (
    HarvesterConfig, JOINT_LIMITS, inverse_kinematics, link_origins,
)


VERSION = "harvest-clearance/0.1"
# Finite technical choices, in metres relative to the actual pedicel cut.
# Try a short level withdrawal before any upward motion. Lateral escapes help
# when the fruit hangs on the inward face of a nodal branch.
EXTRACTION_OFFSETS = (
    (-0.12, 0.0, 0.0), (-0.08, 0.0, 0.03),
    (-0.12, 0.0, -0.05), (-0.12, 0.0, -0.08),
    (0.0, -0.12, 0.06), (0.0, 0.12, 0.06),
    (0.0, -0.12, 0.0), (0.0, 0.12, 0.0),
    (-0.06, -0.15, 0.0), (-0.06, 0.15, 0.0),
    (-0.08, -0.10, -0.05), (-0.08, 0.10, -0.05),
)


def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _rotate(v, yaw, elevation):
    # Rz(yaw) Ry(-elevation), consistent with the proxy arm axes.
    x = math.cos(elevation) * v[0] - math.sin(elevation) * v[2]
    z = math.sin(elevation) * v[0] + math.cos(elevation) * v[2]
    return [math.cos(yaw) * x - math.sin(yaw) * v[1],
            math.sin(yaw) * x + math.cos(yaw) * v[1], z]


def _inverse_rotate(v, yaw, elevation):
    x = math.cos(yaw) * v[0] + math.sin(yaw) * v[1]
    y = -math.sin(yaw) * v[0] + math.cos(yaw) * v[1]
    return [math.cos(elevation) * x + math.sin(elevation) * v[2], y,
            -math.sin(elevation) * x + math.cos(elevation) * v[2]]


def _point_segment_distance(point, start, end):
    d = _sub(end, start)
    denom = sum(v * v for v in d)
    t = sum(a * b for a, b in zip(_sub(point, start), d)) / denom if denom else 0
    t = max(0, min(1, t))
    return math.dist(point, [start[i] + t * d[i] for i in range(3)])


def _point_box_distance(point, half_extents):
    return math.sqrt(sum(max(abs(p) - h, 0) ** 2 for p, h in zip(point, half_extents)))


def _segment_box_distance(start, end, half_extents):
    """Exact segment-to-AABB distance by piecewise quadratic minimisation."""
    delta = _sub(end, start)
    cuts = [0.0, 1.0]
    for i in range(3):
        if abs(delta[i]) > 1e-14:
            for face in (-half_extents[i], half_extents[i]):
                t = (face - start[i]) / delta[i]
                if 0 < t < 1:
                    cuts.append(t)
    cuts = sorted(set(cuts))
    best = math.inf
    for lo, hi in zip(cuts, cuts[1:]):
        middle = (lo + hi) / 2
        terms = []
        for i in range(3):
            p = start[i] + middle * delta[i]
            if p < -half_extents[i]:
                terms.append((start[i] + half_extents[i], delta[i]))
            elif p > half_extents[i]:
                terms.append((start[i] - half_extents[i], delta[i]))
        denominator = sum(d * d for _, d in terms)
        t = max(lo, min(hi, -sum(a * d for a, d in terms) / denominator)) if denominator else middle
        point = [start[i] + t * delta[i] for i in range(3)]
        best = min(best, _point_box_distance(point, half_extents))
    return best


def rigid_cylinders(bundle, mesh_root=None):
    """Read SDF cylinders or verified prism outer bounds, with flat-end extension.

    Mesh text comes from ``bundle['meshes']`` during generation, or from an
    explicitly supplied package ``mesh_root`` for independent offline audits.
    An arbitrary OBJ is never interpreted as trusted collision primitives.
    """
    result = []
    reports = {row["model_name"]: row for row in bundle.get("plants", [])}

    def pose_of(item):
        pose = item.find("pose")
        if pose is not None and pose.attrib:
            raise ValueError("Relative or non-default pose conventions are unsupported")
        values = list(map(float, item.findtext("pose", "0 0 0 0 0 0").split()))
        if len(values) != 6 or not all(math.isfinite(value) for value in values):
            raise ValueError("Collision poses must contain six finite coordinates")
        return values

    def mesh_text(uri):
        if not uri or "\\" in uri or ":" in uri or uri.startswith("/") or ".." in Path(uri).parts:
            raise ValueError("Collision mesh URI must stay relative to its package")
        if uri in bundle.get("meshes", {}):
            return bundle["meshes"][uri]
        if mesh_root is None:
            raise ValueError("Collision mesh audit requires its OBJ text or explicit mesh_root")
        root = Path(mesh_root).resolve()
        path = (root / uri).resolve()
        if root not in path.parents:
            raise ValueError("Collision mesh escapes the package root")
        return path.read_text(encoding="utf-8")

    for model in bundle["models"]:
        if model.findtext("static") != "true":
            continue
        model_pose = pose_of(model)
        if any(abs(v) > 1e-12 for v in model_pose[3:]):
            raise ValueError("Harvest plant models must bake instance rotations into local geometry")
        for link in model.findall("link"):
            if any(abs(value) > 1e-12 for value in pose_of(link)):
                raise ValueError("Harvest plant links must bake poses into collision geometry")
        batch_rows = []
        for collision in model.findall("link/collision"):
            shape = collision.find("geometry/cylinder")
            pose = pose_of(collision)
            if shape is None:
                mesh = collision.find("geometry/mesh")
                if mesh is None or set(child.tag for child in mesh) - {"uri", "scale"}:
                    raise ValueError("Unexpected plant collider; update the geometric audit before accepting it")
                if any(value != 0 for value in pose) or mesh.findtext("scale", "1 1 1").split() != ["1", "1", "1"]:
                    raise ValueError("Prism meshes require identity collision pose and scale")
                rows = read_collision_prisms(mesh_text(mesh.findtext("uri")))
                batch_rows.extend(rows)
                for row in rows:
                    result.append({
                        "id": f"{model.attrib['name']}/{row['id']}",
                        "source_proxy_id": row["source_proxy_id"],
                        "start": [row["start"][i] + model_pose[i] for i in range(3)],
                        "end": [row["end"][i] + model_pose[i] for i in range(3)],
                        "radius": row["radius"], "source_radius": row["source_radius"],
                        "representation": row["representation"],
                    })
                continue
            if abs(pose[3]) > 1e-12:
                raise ValueError("Unexpected cylinder roll in fixture")
            radius, half_length = float(shape.findtext("radius")), float(shape.findtext("length")) / 2
            if not math.isfinite(radius) or not math.isfinite(half_length) or min(radius, half_length) <= 0:
                raise ValueError("Cylinder dimensions must be finite and positive")
            axis = (math.cos(pose[5]) * math.sin(pose[4]), math.sin(pose[5]) * math.sin(pose[4]), math.cos(pose[4]))
            center = [model_pose[i] + pose[i] for i in range(3)]
            result.append({
                "id": f"{model.attrib['name']}/{collision.attrib['name']}",
                "start": [center[i] - half_length * axis[i] for i in range(3)],
                "end": [center[i] + half_length * axis[i] for i in range(3)],
                "radius": radius,
            })
        if batch_rows:
            if len({row["id"] for row in batch_rows}) != len(batch_rows) or len({row["source_proxy_id"] for row in batch_rows}) != len(batch_rows):
                raise ValueError("Duplicate collision primitive identity across mesh batches")
            report = reports.get(model.attrib["name"])
            if report is not None and (report.get("rigid_primitive_count") != len(batch_rows)
                                      or report.get("rigid_primitive_identity_sha256") != identity_digest(batch_rows)):
                raise ValueError("Prism batch does not cover the declared plant primitive identities")
    return result


def _arm_boxes(joints, base, config):
    c = config
    landmarks = link_origins(joints, c)
    world = {name: [a + b for a, b in zip(_rotate(p, base[3], 0), base[:3])] for name, p in landmarks.items()}
    yaw = joints[0] + base[3]
    upper_angle, fore_angle, tool_angle = joints[1], sum(joints[1:3]), sum(joints[1:4])
    midpoint = lambda a, b: [(x + y) / 2 for x, y in zip(a, b)]
    offset = _rotate([-c.tool_length_m * 0.72, 0, 0.03], yaw, tool_angle)
    bottom = c.body_center_z_m + c.body_height_m / 2
    boxes = [
        ("upper_arm", midpoint(world["shoulder"], world["elbow"]), yaw, upper_angle, [c.upper_arm_m / 2, .0275, .0275]),
        ("forearm", midpoint(world["elbow"], world["wrist"]), yaw, fore_angle, [c.forearm_m / 2, .0225, .0225]),
        ("wrist", world["wrist"], yaw, tool_angle, [.0225, .025, .025]),
        ("tool_housing", [world["tool"][i] + offset[i] for i in range(3)], yaw, tool_angle, [c.tool_length_m * .225, .0375, .015]),
        ("chassis", [base[0], base[1], base[2] + c.body_center_z_m], base[3], 0, [c.body_length_m / 2, c.body_width_m / 2, c.body_height_m / 2]),
        ("pedestal", [base[0], base[1], base[2] + (bottom + c.shoulder_height_m) / 2], base[3], 0, [.045, .045, (c.shoulder_height_m - bottom) / 2]),
        ("yaw_housing", world["shoulder"], yaw, 0, [.0375, .0375, .0325]),
        # Conservative union box for the four wheel cylinders, including gaps.
        ("wheel_envelope", [base[0], base[1], base[2] + c.wheel_radius_m], base[3], 0, [c.wheelbase_m / 2 + c.wheel_radius_m, c.wheel_separation_m / 2 + c.wheel_width_m / 2, c.wheel_radius_m]),
    ]
    return boxes, world


class _CylinderIndex(list):
    """Exact broad phase over the unchanged exported cylinder envelopes."""

    def __init__(self, cylinders):
        super().__init__(cylinders)
        self.cell_size = .10
        self.grid = {}
        for index, row in enumerate(self):
            low = [math.floor((min(a, b) - row["radius"]) / self.cell_size) for a, b in zip(row["start"], row["end"])]
            high = [math.floor((max(a, b) + row["radius"]) / self.cell_size) for a, b in zip(row["start"], row["end"])]
            for x in range(low[0], high[0] + 1):
                for y in range(low[1], high[1] + 1):
                    for z in range(low[2], high[2] + 1):
                        self.grid.setdefault((x, y, z), []).append(index)

    def near(self, center, extent):
        low = [math.floor((p - extent) / self.cell_size) for p in center]
        high = [math.floor((p + extent) / self.cell_size) for p in center]
        indices = set()
        for x in range(low[0], high[0] + 1):
            for y in range(low[1], high[1] + 1):
                for z in range(low[2], high[2] + 1):
                    indices.update(self.grid.get((x, y, z), ()))
        # Keep original order to preserve equal-distance limiting IDs.
        return (self[index] for index in sorted(indices))


def _world_clearance(joints, base, cylinders, fruit_specs, held, config, report_cap=0.5):
    """Distances beyond report_cap are censored, retaining a valid lower bound."""
    boxes, world = _arm_boxes(joints, base, config)
    robot_min, held_min, held_robot_min = report_cap, report_cap, report_cap
    limiting_robot = limiting_held = limiting_held_robot = None
    for name, center, yaw, elevation, half in boxes:
        bound = math.sqrt(sum(v * v for v in half))
        nearby = cylinders.near(center, bound + max(0, robot_min)) if isinstance(cylinders, _CylinderIndex) else cylinders
        for obstacle in nearby:
            a, b, r = obstacle["start"], obstacle["end"], obstacle["radius"]
            if any(center[i] + bound + robot_min < min(a[i], b[i]) - r or center[i] - bound - robot_min > max(a[i], b[i]) + r for i in range(3)):
                continue
            local_a = _inverse_rotate(_sub(a, center), yaw, elevation)
            local_b = _inverse_rotate(_sub(b, center), yaw, elevation)
            distance = _segment_box_distance(local_a, local_b, half) - r
            if distance < robot_min:
                robot_min, limiting_robot = distance, [name, obstacle["id"]]
        for fruit in fruit_specs:
            if held is not None and fruit["id"] == held["id"]:
                continue
            local = _inverse_rotate(_sub(fruit["center_world_m"], center), yaw, elevation)
            distance = _point_box_distance(local, half) - fruit["radius_m"]
            if distance < robot_min:
                robot_min, limiting_robot = distance, [name, fruit["id"]]
        if name != "wheel_envelope":
            z_extent = abs(math.sin(elevation)) * half[0] + abs(math.cos(elevation)) * half[2]
            distance = center[2] - z_extent
            if distance < robot_min:
                robot_min, limiting_robot = distance, [name, "ground"]

    if held is not None:
        offset = _sub(held["center_world_m"], held["cut_point_world_m"])
        moved_offset = _rotate(offset, joints[0] + base[3], sum(joints[1:4]))
        center = [world["tool"][i] + moved_offset[i] for i in range(3)]
        radius = held["radius_m"]
        held_min, limiting_held = min(report_cap, center[2] - radius), "ground"
        nearby = cylinders.near(center, radius + max(0, held_min)) if isinstance(cylinders, _CylinderIndex) else cylinders
        for obstacle in nearby:
            distance = _point_segment_distance(center, obstacle["start"], obstacle["end"]) - radius - obstacle["radius"]
            if distance < held_min:
                held_min, limiting_held = distance, obstacle["id"]
        for fruit in fruit_specs:
            if fruit["id"] == held["id"]:
                continue
            distance = math.dist(center, fruit["center_world_m"]) - radius - fruit["radius_m"]
            if distance < held_min:
                held_min, limiting_held = distance, fruit["id"]
        for name, box_center, yaw, elevation, half in boxes:
            local = _inverse_rotate(_sub(center, box_center), yaw, elevation)
            distance = _point_box_distance(local, half) - radius
            if distance < held_robot_min:
                held_robot_min, limiting_held_robot = distance, name
    return {
        "robot_clearance_m": robot_min, "held_clearance_m": held_min if held else None,
        "held_robot_clearance_m": held_robot_min if held else None,
        "limiting_robot_pair": limiting_robot, "limiting_held_obstacle": limiting_held,
        "limiting_held_robot_link": limiting_held_robot,
        "tcp_world_m": world["tool"],
    }


def audit_joint_segment(start, end, base, cylinders, fruit_specs, *, held=None,
                        config=None, samples=81, clearance_m=.004, stop_on_failure=False):
    """Sample the commanded straight interpolation in joint space, fail closed."""
    if type(samples) is not int or samples < 2:
        raise ValueError("At least two samples are required")
    c = config or HarvesterConfig()
    # Every checked robot point lies within this conservative reachable box.
    # Expand it by the distance reporting cap, then discard whole distant
    # plants once per segment instead of repeating that broad phase per sample.
    held_extra = (math.dist(held["center_world_m"], held["cut_point_world_m"]) + held["radius_m"]) if held else 0.0
    reach = c.upper_arm_m + c.forearm_m + c.tool_length_m + max(.06, held_extra)
    chassis_bound = math.hypot(c.body_length_m / 2, c.body_width_m / 2)
    wheel_bound = math.hypot(c.wheelbase_m / 2 + c.wheel_radius_m,
                             c.wheel_separation_m / 2 + c.wheel_width_m / 2)
    extent = max(reach, chassis_bound, wheel_bound) + .5
    near_cylinders = [obstacle for obstacle in cylinders
                      if all(min(obstacle["start"][i], obstacle["end"][i]) - obstacle["radius"] <= base[i] + extent
                             and max(obstacle["start"][i], obstacle["end"][i]) + obstacle["radius"] >= base[i] - extent
                             for i in (0, 1))]
    near_cylinders = _CylinderIndex(near_cylinders)
    # Bound articulation increments as well as the minimum sample count.
    count = max(samples, math.ceil(max(abs(a - b) for a, b in zip(start, end)) / .004) + 1)
    result = {"passed": True, "samples": 0, "requested_samples": count,
              "minimum_robot_clearance_m": .5, "minimum_held_clearance_m": .5 if held else None,
              "minimum_held_robot_clearance_m": .5 if held else None,
              "minimum_joint_margin_rad": math.inf, "maximum_tcp_sample_step_m": 0.0,
              "clearance_threshold_m": clearance_m, "distance_report_cap_m": .5,
              "broad_phase_cylinders": len(near_cylinders), "source_cylinders": len(cylinders)}
    previous_tcp = None
    for index in range(count):
        t = index / (count - 1)
        joints = [(1 - t) * a + t * b for a, b in zip(start, end)]
        margin = min(min(value - limits[0], limits[1] - value) for value, limits in zip(joints, JOINT_LIMITS))
        result["minimum_joint_margin_rad"] = min(result["minimum_joint_margin_rad"], margin)
        state = _world_clearance(joints, base, near_cylinders, fruit_specs, held, c)
        result["samples"] += 1
        for source, target, detail in (
            ("robot_clearance_m", "minimum_robot_clearance_m", "limiting_robot_pair"),
            ("held_clearance_m", "minimum_held_clearance_m", "limiting_held_obstacle"),
            ("held_robot_clearance_m", "minimum_held_robot_clearance_m", "limiting_held_robot_link"),
        ):
            if state[source] is not None and state[source] < result[target]:
                result[target] = state[source]
                result[detail] = state[detail]
                result[detail + "_sample"] = index
        if previous_tcp is not None:
            result["maximum_tcp_sample_step_m"] = max(result["maximum_tcp_sample_step_m"], math.dist(previous_tcp, state["tcp_world_m"]))
        previous_tcp = state["tcp_world_m"]
        if margin < .025 or any(state[key] is not None and state[key] < clearance_m for key in ("robot_clearance_m", "held_clearance_m", "held_robot_clearance_m")):
            result["passed"] = False
            if stop_on_failure:
                break
    return result


def plan_harvest_motion(bundle, robot_config=None, *, samples_per_segment=81,
                        clearance_m=.004, carry_tcp_base_m=(.4, 0.0, .72),
                        pickup_standoff_m=.5):
    """Screen pickup/withdrawal waypoints for every exported fruit separately.

    Every other fruit remains present during each screen, so plans do not
    depend on a lucky harvest order. ``targets`` is keyed by reproductive ID.
    Base travel and deposit are separate runtime stages, outside this local
    joint-path screen. No plant, fruit or robot geometry is changed.
    """
    c = robot_config or HarvesterConfig()
    if not math.isfinite(clearance_m) or clearance_m <= 0:
        raise ValueError("clearance_m must be positive and finite")
    if not math.isfinite(pickup_standoff_m) or pickup_standoff_m <= .12:
        raise ValueError("pickup_standoff_m must be finite and greater than .12 m")
    carry = list(map(float, carry_tcp_base_m))
    if len(carry) != 3 or not all(math.isfinite(v) for v in carry):
        raise ValueError("carry_tcp_base_m must have three finite coordinates")
    cylinders = rigid_cylinders(bundle)
    fruit_specs = bundle["fruits"]
    if not fruit_specs or len({fruit["id"] for fruit in fruit_specs}) != len(fruit_specs):
        raise ValueError("Motion screening requires nonempty unique fruit identities")
    targets = {}
    for fruit in fruit_specs:
        cut = fruit["cut_point_world_m"]
        base = [cut[0] - pickup_standoff_m, cut[1], 0.0, 0.0]
        local_points = {"carry": list(carry), "preapproach": [pickup_standoff_m - .10, 0.0, cut[2] + .10], "cut": [pickup_standoff_m, 0.0, cut[2]]}
        joints = {name: list(inverse_kinematics(point, config=c)) for name, point in local_points.items()}
        approach = []
        for a, b in (("carry", "preapproach"), ("preapproach", "cut")):
            result = audit_joint_segment(joints[a], joints[b], base, cylinders, fruit_specs, config=c, samples=samples_per_segment, clearance_m=clearance_m)
            result.update({"from": a, "to": b, "held": False})
            approach.append(result)
        if not all(item["passed"] for item in approach):
            raise ValueError(f"No safe scripted approach for {fruit['id']}: {approach}")
        rejected, accepted = [], None
        for offset in EXTRACTION_OFFSETS:
            local = [pickup_standoff_m + offset[0], offset[1], cut[2] + offset[2]]
            try:
                candidate = list(inverse_kinematics(local, config=c))
            except ValueError as error:
                rejected.append({"offset_m": list(offset), "reason": str(error)})
                continue
            segments = []
            for a, b, start, end in (("cut", "extraction_0", joints["cut"], candidate), ("extraction_0", "carry", candidate, joints["carry"])):
                result = audit_joint_segment(start, end, base, cylinders, fruit_specs, held=fruit, config=c, samples=samples_per_segment, clearance_m=clearance_m, stop_on_failure=True)
                result.update({"from": a, "to": b, "held": True})
                segments.append(result)
                if not result["passed"]:
                    break
            if all(item["passed"] for item in segments) and len(segments) == 2:
                accepted = (local, candidate, offset, segments)
                break
            rejected.append({"offset_m": list(offset), "reason": "sampled_geometry_or_joint_margin", "segments": segments})
        if accepted is None:
            raise ValueError(f"Bounded extraction search failed for {fruit['id']}: {rejected}")
        local, candidate, offset, extraction = accepted
        local_points["extraction_0"] = local
        joints["extraction_0"] = candidate
        segments = approach + extraction
        targets[fruit["id"]] = {
            "pickup_base_pose": base, "joint_waypoints": joints,
            "tcp_waypoints_world_m": {name: [point[i] + base[i] for i in range(3)] for name, point in local_points.items()},
            "sequence": ["carry", "preapproach", "cut", "extraction_0", "carry"],
            "extraction_offset_m": list(offset),
            "audit": {"passed": True, "segments": segments, "rejected_candidates": rejected,
                      "minimum_robot_clearance_m": min(item["minimum_robot_clearance_m"] for item in segments),
                      "minimum_held_clearance_m": min(item["minimum_held_clearance_m"] for item in extraction),
                      "minimum_held_robot_clearance_m": min(item["minimum_held_robot_clearance_m"] for item in extraction)},
        }
    return {"targets": targets, "audit": {
        "schema_version": VERSION, "passed": True, "target_count": len(targets),
        "rigid_cylinder_count": len(cylinders), "clearance_threshold_m": clearance_m,
        "carry_tcp_base_m": carry, "pickup_standoff_m": pickup_standoff_m,
        "parameter_status": "engineering_heuristic", "gazebo_validation": "pending",
        "method": "sampled_joint_interpolation_exact_box_to_segment_distance_with_conservative_capsules",
        "scope": "stationary-base approach and extraction with other fruit bodies present",
        "limitations": ["No continuous collision guarantee or dynamic tracking-error allowance",
                        "Leaves and unselected fruit visual meshes are not colliders",
                        "Base travel, bin contact and robot self-contact require native validation",
                        "Proxy robot collision dimensions only; replace this adapter with the final robot"]}}
