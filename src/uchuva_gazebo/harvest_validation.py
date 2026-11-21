"""Dependency-free acceptance of *observed* harvest telemetry, never commands alone.

The runtime deliberately uses simulation truth for this mechanics fixture. These
checks do not establish visual perception, real cutting forces or sim-to-real
accuracy. Missing, stale or contradictory evidence must fail acceptance.
"""
from __future__ import annotations

import math


def _vector(values, count, label):
    if not isinstance(values, (list, tuple)) or len(values) != count:
        raise ValueError(f"{label} requires {count} components")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in values):
        raise ValueError(f"{label} requires finite numeric components")
    return values


def _pose(values, label):
    _vector(values, 7, label)
    if sum(v*v for v in values[3:7]) < 1e-18:
        raise ValueError(f"{label} has a zero orientation quaternion")
    return values


def distance(a, b):
    _vector(a, 3, "first point")
    _vector(b, 3, "second point")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def rotate_vector(quaternion, vector, inverse=False):
    """Rotate by a normalized xyzw quaternion; reject invalid telemetry."""
    _vector(quaternion, 4, "quaternion")
    _vector(vector, 3, "vector")
    length = math.sqrt(sum(float(v) ** 2 for v in quaternion))
    if not math.isfinite(length) or length < 1e-9:
        raise ValueError("Invalid orientation quaternion")
    x, y, z, w = (float(v) / length for v in quaternion)
    if inverse:
        x, y, z = -x, -y, -z
    vx, vy, vz = vector
    tx, ty, tz = 2 * (y * vz - z * vy), 2 * (z * vx - x * vz), 2 * (x * vy - y * vx)
    return [vx + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx]


def local_point(world_xyz, base_pose):
    _vector(world_xyz, 3, "world point")
    _pose(base_pose, "base pose")
    return rotate_vector(base_pose[3:7], [a - b for a, b in zip(world_xyz, base_pose[:3])], True)


def world_point(local_xyz, base_pose):
    _vector(local_xyz, 3, "local point")
    _pose(base_pose, "base pose")
    return [a + b for a, b in zip(rotate_vector(base_pose[3:7], local_xyz), base_pose[:3])]


def yaw_of(pose):
    _pose(pose, "pose")
    norm = math.sqrt(sum(v*v for v in pose[3:7]))
    x, y, z, w = (v/norm for v in pose[3:7])
    return math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))


def angle_error(target, actual):
    return math.atan2(math.sin(target - actual), math.cos(target - actual))


def fruit_map(state):
    fruits = state.get("fruits", [])
    mapped = {f["id"]: f for f in fruits}
    if len(mapped) != len(fruits):
        raise ValueError("Duplicate fruit IDs in telemetry")
    return mapped


def sphere_in_bin(position, radius, bin_spec):
    """Full collision sphere inside inner bin bounds, allowing 4 mm contact error."""
    lower, upper = bin_spec["inner_min_m"], bin_spec["inner_max_m"]
    _vector(position, 3, "fruit position")
    _vector(lower, 3, "bin lower bound")
    _vector(upper, 3, "bin upper bound")
    if not math.isfinite(radius) or radius <= 0 or any(lo >= hi for lo, hi in zip(lower, upper)):
        raise ValueError("Invalid fruit radius or bin bounds")
    return all(lo + radius - .004 <= p <= hi - radius + .004
               for p, lo, hi in zip(position, lower, upper))


def deposited_interval(samples, fruit_id, radius, bin_spec,
                       min_duration=.7, max_speed=.035):
    """Require consecutive released samples, geometric containment and low speed."""
    first = None
    previous = None
    best = 0.0
    for sample in samples:
        fruit = fruit_map(sample).get(fruit_id)
        t = sample.get("sim_time")
        if fruit is None or not isinstance(t, (int, float)):
            first = previous = None
            continue
        current = (t, fruit["position"])
        valid = (fruit["state"] == "RELEASED" and fruit.get("joint_present") is False
                 and fruit.get("joint_parent") == "none"
                 and fruit.get("removal_pending") is False)
        valid = valid and sphere_in_bin(fruit["position"], radius, bin_spec)
        if previous is not None:
            dt = t - previous[0]
            valid = valid and 0 < dt <= .25 and distance(fruit["position"], previous[1]) / dt <= max_speed
        else:
            valid = False
        if valid:
            first = t if first is None else first
            best = max(best, t - first)
        else:
            first = None
        previous = current
    # A previous stable deposit is insufficient if the fruit later escapes,
    # bounces or is displaced by the next fruit. Require stability at the END.
    tail = previous[0] - first if first is not None and previous is not None else 0.0
    return {"passed": tail >= min_duration, "settled_duration_s": tail,
            "longest_settled_duration_s": best,
            "required_duration_s": min_duration, "max_speed_m_s": max_speed}


def evaluate_harvest_run(manifest, samples, events, target_ids, *, mode="harvest",
                         execution_error=None):
    """Return a fail-closed report for a native smoke test or complete harvest.

    A cut acknowledgement is not evidence of physical detachment; a released
    label is not evidence of deposit. Held motion, constraint residual and
    released containment are checked independently from accepted commands.
    """
    if mode not in ("smoke", "harvest"):
        raise ValueError("mode must be smoke or harvest")
    specs = {f["id"]: f for f in manifest["fruits"]}
    checks = []

    def check(name, passed, *, observed=True, **evidence):
        checks.append({"name": name, "passed": bool(passed),
                       "status": "PASS" if passed else "FAIL" if observed else "NO OBSERVADO",
                       **evidence})

    check("runtime_completed", execution_error is None, error=execution_error)
    check("telemetry_available", len(samples) >= 30, observed=bool(samples), sample_count=len(samples))
    check("targets_known_and_unique", bool(target_ids) and len(set(target_ids)) == len(target_ids)
          and set(target_ids).issubset(specs), target_ids=target_ids)
    if not samples:
        return {"schema_version": "harvest-acceptance/1.0", "mode": mode,
                "passed": False, "checks": checks, "physical_validation": "failed_or_unobserved"}

    malformed = []
    previous_time = None
    max_gap = 0.0
    known_states = {"ATTACHED", "ARMED", "CUT_PENDING", "HELD", "RELEASE_PENDING", "RELEASED"}
    ranks = {name: i for i, name in enumerate(("ATTACHED", "ARMED", "CUT_PENDING", "HELD", "RELEASE_PENDING", "RELEASED"))}
    previous_states = {}
    for index, sample in enumerate(samples):
        try:
            t = sample["sim_time"]
            fruits = fruit_map(sample)
            _pose(sample["tool_pose"], "tool pose")
            _pose(sample["robot_pose"], "robot pose")
            _vector([t], 1, "simulation time")
            if type(sample.get("ready")) is not bool or sample.get("status") not in ("ready", "initializing"):
                raise ValueError("missing or invalid runtime readiness")
            if set(fruits) != set(specs):
                raise ValueError("missing or unexpected fruit IDs")
            if any(f["state"] not in known_states for f in fruits.values()):
                raise ValueError("unknown/error fruit state")
            for identifier, fruit in fruits.items():
                _vector(fruit["position"], 3, "fruit position")
                state = fruit["state"]
                if type(fruit.get("joint_present")) is not bool or type(fruit.get("removal_pending")) is not bool:
                    raise ValueError("missing or non-boolean constraint evidence")
                if state in ("ATTACHED", "ARMED", "HELD"):
                    expected_parent = "tool" if state == "HELD" else "plant"
                    if fruit["joint_present"] is not True or fruit.get("joint_parent") != expected_parent or fruit["removal_pending"]:
                        raise ValueError("fruit state contradicts constraint ownership")
                    residual = fruit.get("constraint_error_m")
                    # Attach publishes one HELD/ready=false observation before
                    # Physics can measure the new constraint. Preserve that
                    # transition, but never count it as retention evidence.
                    if not (sample.get("ready") is False and residual is None):
                        _vector([residual], 1, "constraint residual")
                        if residual < 0:
                            raise ValueError("negative constraint residual")
                elif fruit["joint_present"] or fruit.get("joint_parent") != "none":
                    raise ValueError("detaching/released fruit still has a constraint")
                elif state == "RELEASED" and fruit["removal_pending"]:
                    raise ValueError("released fruit still awaits constraint removal")
                prior = previous_states.get(identifier)
                if prior is not None and ranks[state] < ranks[prior] and (prior, state) != ("ARMED", "ATTACHED"):
                    raise ValueError("fruit state regressed after cutting")
                previous_states[identifier] = state
            if previous_time is not None:
                if t <= previous_time:
                    raise ValueError("non-increasing simulation time / reset")
                max_gap = max(max_gap, t - previous_time)
            previous_time = t
            if sample.get("status") == "error":
                raise ValueError(sample.get("error", "runtime system error"))
        except (KeyError, TypeError, ValueError) as error:
            malformed.append({"sample": index, "error": str(error)})
    check("telemetry_integrity", not malformed and max_gap <= .25,
          errors=malformed[:10], maximum_gap_s=max_gap)
    if malformed:
        return {"schema_version": "harvest-acceptance/1.0", "mode": mode,
                "passed": False, "checks": checks, "physical_validation": "failed_or_unobserved"}

    check("runtime_ready_at_end", samples[-1].get("ready") is True)

    baseline = [s for s in samples if s.get("phase") == "baseline"]
    baseline_span = baseline[-1]["sim_time"] - baseline[0]["sim_time"] if len(baseline) > 1 else 0
    drift = max((distance(f["position"], specs[f["id"]]["center_world_m"])
                 for s in baseline for f in s["fruits"]), default=math.inf)
    check("attached_without_commands", baseline_span >= 2 and drift <= .012
          and all(s.get("ready") is True for s in baseline)
          and all(f["state"] == "ATTACHED" and f.get("joint_present")
                  for s in baseline for f in s["fruits"]),
          duration_s=baseline_span, max_initial_drift_m=drift)
    acks = [ev for ev in events if ev.get("phase") == "ack"]
    check("no_failed_runtime_results", not any(ev.get("phase") == "result"
          and ev.get("accepted") is False for ev in events))
    check("unknown_target_rejected", any(ev.get("id") == "unknown_fruit"
          and ev.get("accepted") is False and ev.get("reason") == "unknown_fruit" for ev in acks))
    check("distant_arm_rejected", any(ev.get("client_phase") == "negative_far"
          and ev.get("action") == "arm" and ev.get("accepted") is False
          and ev.get("reason") == "cut_point_out_of_range" for ev in acks))
    check("distant_cut_rejected", any(ev.get("client_phase") == "negative_far"
          and ev.get("action") == "cut" and ev.get("accepted") is False for ev in acks))

    maximum_jump = 0.0
    maximum_robot_jump = maximum_tool_jump = 0.0
    max_attached_drift = 0.0
    tilted = False
    for sample in samples:
        z_up = rotate_vector(sample["robot_pose"][3:7], [0, 0, 1])
        tilted = tilted or z_up[2] < math.cos(.30)
        for f in sample["fruits"]:
            if f["state"] in ("ATTACHED", "ARMED"):
                max_attached_drift = max(max_attached_drift,
                                        distance(f["position"], specs[f["id"]]["center_world_m"]))
    for a, b in zip(samples, samples[1:]):
        before, after = fruit_map(a), fruit_map(b)
        maximum_jump = max(maximum_jump, *(distance(after[k]["position"], before[k]["position"])
                                          for k in specs))
        maximum_robot_jump = max(maximum_robot_jump, distance(a["robot_pose"][:3], b["robot_pose"][:3]))
        maximum_tool_jump = max(maximum_tool_jump, distance(a["tool_pose"][:3], b["tool_pose"][:3]))
    check("attached_fruits_stable", max_attached_drift <= .012, maximum_drift_m=max_attached_drift)
    check("base_not_tipped", not tilted, tilt_limit_rad=.30)
    check("no_large_pose_jumps", max(maximum_jump, maximum_robot_jump, maximum_tool_jump) <= .12,
          maximum_sample_jump_m=maximum_jump, maximum_robot_jump_m=maximum_robot_jump,
          maximum_tool_jump_m=maximum_tool_jump,
          note="20 Hz sampled continuity gate; native contact review is still required")

    expected = set() if mode == "smoke" else set(target_ids)
    unexpected = {f["id"] for s in samples for f in s["fruits"]
                  if f["state"] not in ("ATTACHED", "ARMED") and f["id"] not in expected}
    check("no_unrequested_detachments", not unexpected, unexpected_ids=sorted(unexpected))
    minimum_separation = math.inf
    limiting_pair = None
    for sample in samples:
        bodies = sample['fruits']
        for i, first in enumerate(bodies):
            for second in bodies[i+1:]:
                gap = (distance(first['position'], second['position'])
                       - specs[first['id']]['radius_m'] - specs[second['id']]['radius_m'])
                if gap < minimum_separation:
                    minimum_separation = gap
                    limiting_pair = [first['id'], second['id'], sample['sim_time']]
    # Same 4 mm contact allowance as full-sphere bin containment; this is a
    # sampled geometric penetration check, not a contact-force measurement.
    check("fruit_bodies_not_interpenetrating", minimum_separation >= -.004,
          minimum_sphere_gap_m=minimum_separation if limiting_pair else None,
          limiting_pair_and_time=limiting_pair, contact_allowance_m=.004)
    if mode == "harvest":
        base_travel = max(math.hypot(s["robot_pose"][0] - samples[0]["robot_pose"][0],
                                     s["robot_pose"][1] - samples[0]["robot_pose"][1]) for s in samples)
        check("base_really_moved", base_travel >= .15, max_displacement_m=base_travel)
        for identifier in target_ids:
            if identifier not in specs:
                continue
            own_events = [ev for ev in acks if ev.get("id") == identifier]
            for action in ("arm", "cut", "release"):
                accepted = [ev for ev in own_events if ev.get("action") == action and ev.get("accepted") is True]
                check(f"{identifier}:one_{action}", len(accepted) == 1,
                      observed=bool(accepted), accepted_count=len(accepted))
            accepted_actions = {action: [ev for ev in own_events if ev.get("action") == action
                                and ev.get("accepted") is True] for action in ("arm", "cut", "release")}
            times = [accepted_actions[action][0].get("sim_time") if len(accepted_actions[action]) == 1 else None
                     for action in ("arm", "cut", "release")]
            ordered = (all(type(t) in (int, float) and math.isfinite(t) for t in times)
                       and samples[0]["sim_time"] <= times[0] < times[1] < times[2] <= samples[-1]["sim_time"])
            check(f"{identifier}:ordered_actions", ordered, observed=all(t is not None for t in times))
            check(f"{identifier}:repeat_cut_rejected", any(ev.get("client_phase") == "negative_repeat"
                  and ev.get("action") == "cut" and ev.get("accepted") is False for ev in own_events))
            check(f"{identifier}:armed_distant_cut_rejected", any(ev.get("client_phase") == "negative_armed_far"
                  and ev.get("action") == "cut" and ev.get("accepted") is False
                  and ev.get("reason") == "cut_point_out_of_range" for ev in own_events))
            held = [(s, fruit_map(s)[identifier]) for s in samples
                    if fruit_map(s)[identifier]["state"] == "HELD" and s.get("ready") is True]
            span = held[-1][0]["sim_time"] - held[0][0]["sim_time"] if len(held) > 1 else 0
            motion = max((distance(f["position"], held[0][1]["position"]) for _, f in held), default=0)
            residual = max((f.get("constraint_error_m", math.inf) for _, f in held), default=math.inf)
            offsets = [local_point(f["position"], s["tool_pose"]) for s, f in held]
            slip = max((distance(offset, offsets[0]) for offset in offsets), default=math.inf)
            check(f"{identifier}:physical_retention", span >= .4 and motion >= .10
                  and residual <= .015 and slip <= .015
                  and all(f.get("joint_present") and f.get("joint_parent") == "tool" for _, f in held),
                  observed=bool(held), held_duration_s=span, held_displacement_m=motion,
                  maximum_constraint_error_m=residual, relative_slip_m=slip)
            result = deposited_interval(samples, identifier, specs[identifier]["radius_m"], manifest["bin"])
            released = [s for s in samples if fruit_map(s)[identifier]['state'] == 'RELEASED']
            check(f"{identifier}:settled_in_bin", result.pop("passed"), observed=bool(released), **result)
    passed = all(item["passed"] for item in checks)
    return {"schema_version": "harvest-acceptance/1.0", "mode": mode, "passed": passed,
            "checks": checks, "physical_validation": "observed_pilot_pass" if passed else "failed_or_unobserved",
            "scope": "ideal cut/latch mechanics with simulation truth; no perception or force validation"}
