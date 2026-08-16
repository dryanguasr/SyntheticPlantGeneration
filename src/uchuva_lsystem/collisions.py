"""Pure-Python global organ clearance for dense cultivation scenes.

The broad phase uses a spatial hash.  The narrow phase represents stems and
petioles as capsules, leaves and timber stakes as oriented boxes, and calyxes
as oriented ellipsoids.  Pose corrections are written back to morphology
joints before Blender creates any mesh.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

from .morphology import Axis, Plant
from .scene import CultivationScene, PlantInstance
from .spatial import ContactPolicy, classify_contact


Vec3 = tuple[float, float, float]
GLOBAL_COLLISION_VERSION = "0.3.0-leaf-calyx-micro-clearance"
DEFAULT_ITERATIONS = 8
CM_TO_SCENE_UNIT = 0.08
LEAF_CALYX_TARGET_CLEARANCE = 0.006
LEAF_CALYX_LIFT_STEP_CM = 0.15
LEAF_CALYX_MAX_LIFT_CM = 0.45


@dataclass
class CollisionProxy:
    proxy_id: str
    plant_id: str
    kind: str
    shape: str
    center: Vec3
    axes: tuple[Vec3, Vec3, Vec3]
    half_extents: Vec3
    start: Vec3 | None = None
    end: Vec3 | None = None
    radius: float = 0.0
    control_kind: str | None = None
    control_id: str | None = None
    attachment_id: str | None = None
    group_id: str | None = None
    axis_id: str | None = None
    axis_parent_node_id: str | None = None
    internode_index: int = -1

    def aabb(self, padding: float = 0.0) -> tuple[Vec3, Vec3]:
        if self.shape == "capsule" and self.start is not None and self.end is not None:
            minimum = tuple(
                min(self.start[index], self.end[index]) - self.radius - padding
                for index in range(3)
            )
            maximum = tuple(
                max(self.start[index], self.end[index]) + self.radius + padding
                for index in range(3)
            )
            return minimum, maximum
        extent = tuple(
            sum(abs(self.axes[axis][coordinate]) * self.half_extents[axis] for axis in range(3))
            + padding
            for coordinate in range(3)
        )
        return _sub(self.center, extent), _add(self.center, extent)


def resolve_global_collisions(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    *,
    iterations: int = DEFAULT_ITERATIONS,
    include_contact_audit: bool = True,
) -> dict[str, Any]:
    """Resolve non-exempt organ intersections by changing morphology joints."""
    adjustments: list[dict[str, Any]] = []
    total_candidates = 0
    total_detected = 0
    resolved_keys: set[tuple[str, str]] = set()

    for iteration in range(iterations):
        proxies = build_scene_proxies(scene, plants_by_id)
        pairs = _candidate_pairs(proxies)
        total_candidates += len(pairs)
        collisions = _collisions_from_pairs(pairs)
        total_detected += len(collisions)
        if not collisions:
            break
        lookup = _control_lookup(plants_by_id)
        adjusted_controls: set[tuple[str, str, str]] = set()
        for collision in sorted(
            collisions,
            key=lambda item: (-item["penetration"], item["proxy_a"].proxy_id, item["proxy_b"].proxy_id),
        ):
            change = _resolve_collision(
                collision,
                iteration=iteration,
                lookup=lookup,
                scene=scene,
                adjusted_controls=adjusted_controls,
            )
            if change is not None:
                adjustments.append(change)
                resolved_keys.add(tuple(sorted((collision["proxy_a"].proxy_id, collision["proxy_b"].proxy_id))))

    preliminary_proxies = build_scene_proxies(scene, plants_by_id)
    preliminary_collisions = _collisions_from_pairs(_candidate_pairs(preliminary_proxies))
    adjustments.extend(
        _optimise_remaining_organ_poses(
            scene,
            plants_by_id,
            preliminary_collisions,
        )
    )
    # After organ poses settle, choose a fixed vertical corridor for every
    # rectangular stake.  Sampling at the end prevents a later leaf response
    # from rotating a blade back through an already cleared support.
    adjustments.extend(_optimise_support_corridors(scene, plants_by_id))
    post_support_proxies = build_scene_proxies(scene, plants_by_id)
    post_support_collisions = _collisions_from_pairs(_candidate_pairs(post_support_proxies))
    adjustments.extend(
        _optimise_remaining_organ_poses(
            scene,
            plants_by_id,
            post_support_collisions,
        )
    )
    micro_lift_adjustments, micro_lift_report = (
        _apply_leaf_calyx_micro_clearance_lifts(scene, plants_by_id)
    )
    adjustments.extend(micro_lift_adjustments)
    final_proxies = build_scene_proxies(scene, plants_by_id)
    final_pairs = _candidate_pairs(final_proxies)
    final_collisions = _collisions_from_pairs(final_pairs)
    clearances = [
        _proxy_clearance(left, right)
        for left, right in final_pairs
        if not _is_exempt(left, right)
    ]
    unresolved = [_collision_to_dict(item) for item in final_collisions]
    contact_audit = (
        audit_proxy_contacts(
            scene,
            plants_by_id,
            proxies=final_proxies,
            contact_policy=ContactPolicy.default(),
        )
        if include_contact_audit
        else None
    )
    return {
        "version": GLOBAL_COLLISION_VERSION,
        "iterations": iterations,
        "proxy_count": len(final_proxies),
        "candidate_pair_count": total_candidates,
        "detected_pair_count": total_detected,
        "resolved_pair_count": len(resolved_keys),
        "adjustment_count": len(adjustments),
        "adjustments": adjustments,
        "leaf_calyx_micro_lift": micro_lift_report,
        "minimum_clearance": round(min(clearances), 5) if clearances else None,
        **(
            {
                "strict_minimum_clearance": contact_audit[
                    "strict_minimum_clearance"
                ],
                "proxy_conflicts": contact_audit["proxy_conflicts"],
                "clearance_violations": contact_audit[
                    "clearance_violations"
                ],
                "soft_occupancy_overlaps": contact_audit[
                    "soft_occupancy_overlaps"
                ],
                "intentional_contacts": contact_audit[
                    "intentional_contacts"
                ],
                "near_contacts": contact_audit["near_contacts"],
                "visual_occlusions": contact_audit["visual_occlusions"],
            }
            if contact_audit is not None
            else {}
        ),
        "unresolved_pair_count": len(unresolved),
        "unresolved_pairs": unresolved,
        # Conservative proxies may overlap while the tapered evaluated meshes
        # do not.  Exact physical collisions are populated only by the Blender
        # BVH audit; unresolved proxies remain fail-closed pipeline evidence.
        "physical_collisions": [],
        "status": "valid" if not unresolved else "proxy_unresolved_pending_mesh_audit",
        "policy": "strict_3d_intersection_projected_occlusion_allowed",
    }


def _optimise_remaining_organ_poses(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    collisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deterministically select the least-colliding pose for unresolved organs."""
    lookup = _control_lookup(plants_by_id)
    control_keys: set[tuple[str, str, str]] = set()
    for collision in collisions:
        for proxy in (collision["proxy_a"], collision["proxy_b"]):
            if proxy.control_kind in {"leaf", "pedicel"} and proxy.control_id is not None:
                control_keys.add((proxy.plant_id, proxy.control_kind, proxy.control_id))
            elif proxy.kind == "petiole" and proxy.attachment_id:
                _, leaf_id = proxy.attachment_id.split(":", 1)
                control_keys.add((proxy.plant_id, "leaf", leaf_id))

    adjustments: list[dict[str, Any]] = []
    for key in sorted(control_keys):
        target = lookup.get(key)
        if target is None:
            continue
        plant_id, control_kind, control_id = key
        if control_kind == "leaf":
            before = (target.azimuth_deg, target.insertion_angle_deg)
            candidates = [
                (float(azimuth), float(insertion))
                for azimuth in range(0, 360, 45)
                for insertion in (56.0, 72.0, 88.0)
            ]
            candidates.append(before)
            candidates = sorted(
                set(candidates),
                key=lambda pose: (
                    _circular_distance(pose[0], before[0]),
                    abs(pose[1] - before[1]),
                    pose,
                ),
            )
            best_pose = before
            best_score = _control_pose_score(scene, plants_by_id, key)
            if best_score[0] == 0:
                continue
            for azimuth, insertion in candidates:
                target.azimuth_deg = azimuth
                target.insertion_angle_deg = insertion
                score = _control_pose_score(scene, plants_by_id, key) + (
                    round(_circular_distance(azimuth, before[0]), 4),
                    round(abs(insertion - before[1]), 4),
                )
                comparable_best = best_score + (
                    round(_circular_distance(best_pose[0], before[0]), 4),
                    round(abs(best_pose[1] - before[1]), 4),
                )
                if score < comparable_best:
                    best_score = score[:3]
                    best_pose = (azimuth, insertion)
                    if best_score[0] == 0:
                        break
            target.azimuth_deg, target.insertion_angle_deg = best_pose
            target.curl = 0.0
            target.twist_deg = 0.0
        else:
            before = (target.azimuth_deg, target.angle_deg)
            candidates = [
                (float(azimuth), float(angle))
                for azimuth in range(0, 360, 45)
                for angle in (32.0, 52.0, 70.0)
            ]
            candidates.append(before)
            candidates = sorted(
                set(candidates),
                key=lambda pose: (
                    _circular_distance(pose[0], before[0]),
                    abs(pose[1] - before[1]),
                    pose,
                ),
            )
            best_pose = before
            best_score = _control_pose_score(scene, plants_by_id, key)
            if best_score[0] == 0:
                continue
            for azimuth, angle in candidates:
                target.azimuth_deg = azimuth
                target.angle_deg = angle
                score = _control_pose_score(scene, plants_by_id, key) + (
                    round(_circular_distance(azimuth, before[0]), 4),
                    round(abs(angle - before[1]), 4),
                )
                comparable_best = best_score + (
                    round(_circular_distance(best_pose[0], before[0]), 4),
                    round(abs(best_pose[1] - before[1]), 4),
                )
                if score < comparable_best:
                    best_score = score[:3]
                    best_pose = (azimuth, angle)
                    if best_score[0] == 0:
                        break
            target.azimuth_deg, target.angle_deg = best_pose
        if best_pose != before:
            adjustments.append(
                {
                    "iteration": "discrete_pose_search",
                    "plant_id": plant_id,
                    "control_kind": control_kind,
                    "control_id": control_id,
                    "before": before,
                    "after": best_pose,
                    "score": best_score,
                }
            )
    return adjustments


def _apply_leaf_calyx_micro_clearance_lifts(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Lift only near-contact leaves by a bounded, serializable few millimetres.

    Leaf--calyx occlusion remains visually allowed.  This pass addresses only
    conservative 3-D proxy clearances below the soft-contact target and keeps
    the petiole attached at its node by changing its outgoing direction.
    """
    lookup = _control_lookup(plants_by_id)
    adjustments: list[dict[str, Any]] = []
    for pass_index in range(3):
        proxies = build_scene_proxies(scene, plants_by_id)
        candidates: list[tuple[float, CollisionProxy, CollisionProxy]] = []
        for left, right in _candidate_pairs(proxies):
            if _is_exempt(left, right) or {left.kind, right.kind} != {"leaf", "calyx"}:
                continue
            clearance = _proxy_clearance(left, right)
            if clearance < LEAF_CALYX_TARGET_CLEARANCE:
                leaf_proxy = left if left.kind == "leaf" else right
                calyx_proxy = right if leaf_proxy is left else left
                candidates.append((clearance, leaf_proxy, calyx_proxy))

        adjusted_leaf_ids: set[tuple[str, str]] = set()
        for clearance, leaf_proxy, calyx_proxy in sorted(
            candidates,
            key=lambda item: (
                item[0],
                item[1].proxy_id,
                item[2].proxy_id,
            ),
        ):
            if leaf_proxy.control_id is None:
                continue
            leaf_key = (leaf_proxy.plant_id, leaf_proxy.control_id)
            if leaf_key in adjusted_leaf_ids:
                continue
            target = lookup.get((leaf_proxy.plant_id, "leaf", leaf_proxy.control_id))
            if target is None:
                continue
            before_cm = float(getattr(target, "clearance_lift_cm", 0.0))
            if before_cm >= LEAF_CALYX_MAX_LIFT_CM - 1e-9:
                continue
            after_cm = min(
                LEAF_CALYX_MAX_LIFT_CM,
                before_cm + LEAF_CALYX_LIFT_STEP_CM,
            )
            target.clearance_lift_cm = round(after_cm, 3)
            target.clearance_lift_reason = "leaf_calyx_soft_clearance"
            adjusted_leaf_ids.add(leaf_key)
            adjustments.append(
                {
                    "iteration": f"leaf_calyx_micro_lift_{pass_index}",
                    "plant_id": leaf_proxy.plant_id,
                    "control_kind": "leaf",
                    "control_id": leaf_proxy.control_id,
                    "lift_before_cm": round(before_cm, 3),
                    "lift_after_cm": target.clearance_lift_cm,
                    "trigger_pair": [leaf_proxy.proxy_id, calyx_proxy.proxy_id],
                    "clearance_before": round(clearance, 6),
                    "target_clearance": LEAF_CALYX_TARGET_CLEARANCE,
                    "parameter_status": "engineering_heuristic",
                }
            )
        if not adjusted_leaf_ids:
            break

    remaining = []
    final_proxies = build_scene_proxies(scene, plants_by_id)
    for left, right in _candidate_pairs(final_proxies):
        if _is_exempt(left, right) or {left.kind, right.kind} != {"leaf", "calyx"}:
            continue
        clearance = _proxy_clearance(left, right)
        if clearance < LEAF_CALYX_TARGET_CLEARANCE:
            remaining.append(clearance)
    lifted_leaf_count = len(
        {
            (item["plant_id"], item["control_id"])
            for item in adjustments
        }
    )
    return adjustments, {
        "status": "bounded_micro_lift_applied" if adjustments else "not_needed",
        "lifted_leaf_count": lifted_leaf_count,
        "adjustment_count": len(adjustments),
        "lift_step_cm": LEAF_CALYX_LIFT_STEP_CM,
        "maximum_lift_cm": LEAF_CALYX_MAX_LIFT_CM,
        "target_proxy_clearance": LEAF_CALYX_TARGET_CLEARANCE,
        "remaining_near_contact_pair_count": len(remaining),
        "minimum_remaining_clearance": (
            round(min(remaining), 6) if remaining else None
        ),
        "occlusion_policy": "visual_occlusion_preserved_geometric_near_contact_reduced",
        "parameter_status": "engineering_heuristic",
    }


def _control_pose_score(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    key: tuple[str, str, str],
) -> tuple[int, float, float]:
    plant_id, control_kind, control_id = key
    proxies = build_scene_proxies(scene, plants_by_id)
    if control_kind == "leaf":
        attachment_id = f"{plant_id}:{control_id}"
        targets = [
            proxy
            for proxy in proxies
            if proxy.plant_id == plant_id
            and (
                (proxy.control_kind == "leaf" and proxy.control_id == control_id)
                or proxy.attachment_id == attachment_id
            )
        ]
    else:
        targets = [
            proxy
            for proxy in proxies
            if proxy.plant_id == plant_id
            and proxy.control_kind == "pedicel"
            and proxy.control_id == control_id
        ]
    conflicts: set[tuple[str, str]] = set()
    penetration_sum = 0.0
    maximum_penetration = 0.0
    for target in targets:
        target_aabb = target.aabb(0.004)
        for other in proxies:
            if target is other or _is_exempt(target, other):
                continue
            pair_key = tuple(sorted((target.proxy_id, other.proxy_id)))
            if pair_key in conflicts or not _aabb_overlap(target_aabb, other.aabb(0.004)):
                continue
            clearance = _proxy_clearance(target, other)
            if clearance < 0.0:
                penetration = -clearance
                conflicts.add(pair_key)
                penetration_sum += penetration
                maximum_penetration = max(maximum_penetration, penetration)
    return (
        len(conflicts),
        round(penetration_sum, 6),
        round(maximum_penetration, 6),
    )


def _circular_distance(left_deg: float, right_deg: float) -> float:
    difference = abs((left_deg - right_deg) % 360.0)
    return min(difference, 360.0 - difference)


def build_scene_proxies(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
) -> list[CollisionProxy]:
    instances = {item.plant_id: item for item in scene.plant_instances}
    proxies: list[CollisionProxy] = []
    for plant_id in sorted(plants_by_id):
        instance = instances[plant_id]
        for axis in plants_by_id[plant_id].axes:
            _append_axis_proxies(
                proxies,
                axis,
                instance=instance,
                start=(0.0, 0.0, 0.0),
                parent_direction=_normalise((0.05, -0.03, 1.0)),
                node_frames={},
            )
    proxies.extend(_support_proxy(support) for support in scene.supports)
    proxies.extend(_support_system_proxies(scene))
    return proxies


def audit_proxy_contacts(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    *,
    proxies: list[CollisionProxy] | None = None,
    contact_policy: ContactPolicy | None = None,
) -> dict[str, Any]:
    """Classify conservative proxy pairs without conflating contact and view."""
    active_proxies = proxies or build_scene_proxies(scene, plants_by_id)
    policy = contact_policy or ContactPolicy.default()
    categories: dict[str, list[dict[str, Any]]] = {
        "proxy_conflicts": [],
        "clearance_violations": [],
        "soft_occupancy_overlaps": [],
        "intentional_contacts": [],
        "near_contacts": [],
        "visual_occlusions": [],
    }
    strict_clearances: list[float] = []
    for left, right in _candidate_pairs(active_proxies):
        if _is_exempt(left, right):
            continue
        left_kind = _contact_kind(left.kind)
        right_kind = _contact_kind(right.kind)
        if left_kind.startswith("support_") and right_kind.startswith(
            "support_"
        ):
            continue
        rule = policy.rule_for(left_kind, right_kind)
        clearance = _proxy_clearance(left, right)
        intentional = rule.intentional_contact_allowed and (
            "support_" in left_kind or "support_" in right_kind
        )
        classification = classify_contact(
            clearance,
            rule,
            intentional=intentional,
        )
        if rule.policy == "hard_occupancy":
            strict_clearances.append(clearance - rule.clearance)
        category = {
            "proxy_conflict": "proxy_conflicts",
            "clearance_violation": "clearance_violations",
            "intentional_contact": "intentional_contacts",
            "near_contact": "near_contacts",
            "visual_occlusion": "visual_occlusions",
        }.get(classification)
        if (
            classification in {"proxy_conflict", "clearance_violation"}
            and rule.policy == "soft_occupancy"
        ):
            category = "soft_occupancy_overlaps"
        if category is None:
            continue
        categories[category].append(
            {
                "proxy_a": left.proxy_id,
                "proxy_b": right.proxy_id,
                "plant_a": left.plant_id,
                "plant_b": right.plant_id,
                "organ_a": left_kind,
                "organ_b": right_kind,
                "clearance": round(clearance, 6),
                "required_clearance": rule.clearance,
                "policy": rule.policy,
            }
        )
    return {
        "version": GLOBAL_COLLISION_VERSION,
        **categories,
        "counts": {
            key: len(value)
            for key, value in categories.items()
        },
        "strict_minimum_clearance": (
            round(min(strict_clearances), 6)
            if strict_clearances
            else None
        ),
        "mesh_intersections": [],
        "parameter_status": "engineering_heuristic",
    }


def _support_proxy(support: Any) -> CollisionProxy:
    yaw = math.radians(support.rotation_deg)
    axes = (
        (math.cos(yaw), math.sin(yaw), 0.0),
        (-math.sin(yaw), math.cos(yaw), 0.0),
        (0.0, 0.0, 1.0),
    )
    return CollisionProxy(
        proxy_id=support.support_id,
        plant_id=support.plant_id,
        kind="stake",
        shape="obb",
        center=(
            support.position[0],
            support.position[1],
            support.position[2] + support.height * 0.5,
        ),
        axes=axes,
        half_extents=(
            support.section_width * 0.5,
            support.section_depth * 0.5,
            support.height * 0.5,
        ),
        group_id=support.support_id,
    )


def _support_system_proxies(scene: CultivationScene) -> list[CollisionProxy]:
    system = scene.support_system
    if system is None or not system.enabled:
        return []
    proxies: list[CollisionProxy] = []
    for post in system.posts:
        proxies.append(
            CollisionProxy(
                proxy_id=post.id,
                plant_id="support",
                kind="support_post",
                shape="obb",
                center=(
                    post.position[0],
                    post.position[1],
                    post.position[2] + post.height * 0.5,
                ),
                axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                half_extents=(
                    post.section_width * 0.5,
                    post.section_depth * 0.5,
                    post.height * 0.5,
                ),
                group_id=post.id,
            )
        )
    for line in system.lines:
        proxies.append(
            CollisionProxy(
                proxy_id=line.id,
                plant_id="support",
                kind="support_line",
                shape="capsule",
                center=_mid(line.start, line.end),
                axes=_frame_from_long(_normalise(_sub(line.end, line.start))),
                half_extents=(0.0, 0.0, 0.0),
                start=line.start,
                end=line.end,
                radius=line.radius,
                group_id=line.id,
            )
        )
    for tie in system.ties:
        proxies.append(
            CollisionProxy(
                proxy_id=tie.id,
                plant_id=tie.plant_id,
                kind="support_tie",
                shape="capsule",
                center=_mid(tie.start, tie.end),
                axes=_frame_from_long(_normalise(_sub(tie.end, tie.start))),
                half_extents=(0.0, 0.0, 0.0),
                start=tie.start,
                end=tie.end,
                radius=0.008,
                group_id=tie.id,
            )
        )
    return proxies


def _contact_kind(kind: str) -> str:
    return {
        "stake": "support_post",
        "support_post": "support_post",
        "support_line": "support_line",
        "support_tie": "support_tie",
        "pedicel": "stem",
    }.get(kind, kind)


def _aabb_overlap(
    left: tuple[Vec3, Vec3],
    right: tuple[Vec3, Vec3],
) -> bool:
    return all(
        left[0][axis] <= right[1][axis] and right[0][axis] <= left[1][axis]
        for axis in range(3)
    )


def _optimise_support_corridors(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
) -> list[dict[str, Any]]:
    """Place each fixed stake in the nearest sampled vertical clearance corridor."""
    instances = {item.plant_id: item for item in scene.plant_instances}
    organ_proxies = [
        proxy
        for proxy in build_scene_proxies(scene, plants_by_id)
        if proxy.kind != "stake"
    ]
    adjustments: list[dict[str, Any]] = []
    for support in sorted(scene.supports, key=lambda item: item.support_id):
        instance = instances[support.plant_id]
        before = support.position
        candidates: list[tuple[tuple[float, ...], Vec3, float]] = []
        for distance_factor in (
            0.34,
            0.46,
            0.58,
            0.70,
            0.82,
            0.94,
            1.06,
            1.18,
            1.30,
        ):
            distance = distance_factor * instance.scale
            for angle_deg in range(0, 360, 15):
                angle = math.radians(angle_deg)
                position = (
                    instance.position[0] + math.cos(angle) * distance,
                    instance.position[1] + math.sin(angle) * distance,
                    support.position[2],
                )
                support.position = position
                candidate_proxy = _support_proxy(support)
                candidate_aabb = candidate_proxy.aabb()
                conflicts = 0
                penetration = 0.0
                for organ in organ_proxies:
                    if not _aabb_overlap(candidate_aabb, organ.aabb()):
                        continue
                    clearance = _proxy_clearance(candidate_proxy, organ)
                    if clearance < 0.0:
                        conflicts += 1
                        penetration += -clearance
                # The legacy stake optimiser predates the explicit base
                # occupancy proxy.  Keep its compatibility behaviour, but do
                # not let a stake chosen for one plant invade another plant's
                # protected root/base clearance.
                for other in scene.plant_instances:
                    if other.plant_id == support.plant_id:
                        continue
                    base_clearance = (
                        math.hypot(
                            position[0] - other.position[0],
                            position[1] - other.position[1],
                        )
                        - support.radius
                        - float(other.collision_proxy.get("base_radius", 0.1))
                    )
                    required_base_clearance = 0.035
                    if base_clearance < required_base_clearance:
                        conflicts += 1
                        penetration += required_base_clearance - base_clearance
                score = (
                    float(conflicts),
                    round(penetration, 8),
                    abs(distance_factor - 0.46),
                    float(angle_deg),
                )
                candidates.append((score, position, float(angle_deg)))
        _, best_position, best_angle = min(candidates, key=lambda item: item[0])
        support.position = (
            round(best_position[0], 4),
            round(best_position[1], 4),
            best_position[2],
        )
        support.rotation_deg = round((best_angle + 90.0) % 360.0, 3)
        adjustments.append(
            {
                "iteration": -1,
                "plant_id": support.plant_id,
                "control_kind": "support_corridor",
                "control_id": support.support_id,
                "before": before,
                "after": support.position,
                "sampled_angle_deg": best_angle,
            }
        )
    return adjustments


def _append_axis_proxies(
    output: list[CollisionProxy],
    axis: Axis,
    *,
    instance: PlantInstance,
    start: Vec3,
    parent_direction: Vec3,
    node_frames: dict[str, tuple[Vec3, Vec3]],
) -> None:
    scale = CM_TO_SCENE_UNIT * instance.scale
    direction = (
        _normalise(tuple(axis.resolved_direction))
        if axis.resolved_direction is not None
        else _axis_direction(
            parent_direction,
            axis.azimuth_deg,
            axis.branch_angle_deg,
        )
    )
    current = start
    local_frames: dict[str, tuple[Vec3, Vec3]] = {}
    for index, internode in enumerate(axis.internodes):
        direction = _bend_direction(direction, internode.bend_azimuth_deg, internode.bend_angle_deg)
        direction = _load_deflection(direction, axis, index, len(axis.internodes))
        end = _add(current, _mul(direction, internode.length_cm * scale))
        world_start = _world_point(current, instance)
        world_end = _world_point(end, instance)
        segment_vector = _sub(world_end, world_start)
        segment_length = _length(segment_vector)
        flatness = math.sqrt(segment_vector[0] ** 2 + segment_vector[1] ** 2) / max(
            segment_length,
            1e-9,
        )
        sag_factor = (
            0.012 + axis.reproductive_load * 0.025
            if axis.order == 0
            else 0.045 + axis.reproductive_load * 0.115
        )
        sag = segment_length * sag_factor * (flatness**1.35)
        # Blender renders loaded axes as a six-point sagging polyline. Matching
        # that curve here is essential: a straight capsule can clear a leaf
        # while the evaluated stem mesh bends through it.
        curve_points: list[Vec3] = []
        for point_index in range(6):
            t = point_index / 5.0
            point = _add(world_start, _mul(segment_vector, t))
            curve_points.append((point[0], point[1], point[2] - sag * math.sin(math.pi * t)))
        for sub_index, (sub_start, sub_end) in enumerate(zip(curve_points, curve_points[1:])):
            output.append(
                CollisionProxy(
                    proxy_id=f"{instance.plant_id}:{internode.id}:segment_{sub_index}",
                    plant_id=instance.plant_id,
                    kind="stem",
                    shape="capsule",
                    center=_mid(sub_start, sub_end),
                    axes=_frame_from_long(_normalise(_sub(sub_end, sub_start))),
                    half_extents=(0.0, 0.0, 0.0),
                    start=sub_start,
                    end=sub_end,
                    radius=max(internode.radius_cm * scale, 0.008),
                    control_kind="axis" if axis.order > 0 else None,
                    control_id=axis.id if axis.order > 0 else None,
                    group_id=f"{instance.plant_id}:{internode.id}",
                    axis_id=axis.id,
                    axis_parent_node_id=axis.parent_node_id,
                    internode_index=index,
                )
            )
        if index < len(axis.nodes):
            node = axis.nodes[index]
            local_frames[node.id] = (end, direction)
            node_frames[node.id] = (end, direction)
            if node.leaf is not None:
                _append_leaf_proxies(output, node.leaf, end, direction, instance)
            if node.reproductive_unit is not None:
                _append_reproductive_proxies(output, node.reproductive_unit, end, instance)
        current = end

    for child in axis.child_axes:
        frame = node_frames.get(child.parent_node_id or "")
        if frame is not None:
            _append_axis_proxies(
                output,
                child,
                instance=instance,
                start=frame[0],
                parent_direction=frame[1],
                node_frames=node_frames,
            )


def _append_leaf_proxies(
    output: list[CollisionProxy],
    leaf: Any,
    node: Vec3,
    axis_direction: Vec3,
    instance: PlantInstance,
) -> None:
    scale = CM_TO_SCENE_UNIT * instance.scale
    angle = math.radians(leaf.insertion_angle_deg)
    radial = _radial(leaf.azimuth_deg)
    direction = _normalise(_add(_mul(axis_direction, math.cos(angle)), _mul(radial, math.sin(angle))))
    petiole_length = leaf.petiole_length_cm * scale
    direction = _leaf_direction_with_clearance_lift(
        direction,
        petiole_length,
        float(getattr(leaf, "clearance_lift_cm", 0.0)) * scale,
    )
    petiole_end = _add(node, _mul(direction, petiole_length))
    world_node = _world_point(node, instance)
    world_petiole = _world_point(petiole_end, instance)
    attachment = f"{instance.plant_id}:{leaf.id}"
    output.append(
        CollisionProxy(
            proxy_id=f"{attachment}:petiole",
            plant_id=instance.plant_id,
            kind="petiole",
            shape="capsule",
            center=_mid(world_node, world_petiole),
            axes=_frame_from_long(_world_direction(direction, instance)),
            half_extents=(0.0, 0.0, 0.0),
            start=world_node,
            end=world_petiole,
            # Clearance envelope, intentionally wider than the rendered
            # petiole, absorbs proxy/mesh discretisation differences.
            radius=max(0.035 * scale, 0.018),
            attachment_id=attachment,
            group_id=attachment,
        )
    )
    length = leaf.length_cm * scale
    width = leaf.width_cm * scale
    world_long = _world_direction(direction, instance)
    flatness = max(0.0, min(1.0, 1.0 - abs(world_long[2])))
    sag = length * 0.10 * (flatness**1.35)
    base_frame = _frame_from_long(world_long)
    local_up = base_frame[2]
    width_axis = base_frame[1]
    # Three tapered slabs follow the ovate blade much more closely than one
    # full-width box and avoid false collisions around the narrow tip/base.
    for segment_index, (t, width_factor) in enumerate(((0.24, 0.50), (0.53, 0.62), (0.81, 0.42))):
        tangent = _normalise(
            _sub(
                world_long,
                _mul(local_up, (2.0 * sag * t) / max(length, 1e-6)),
            )
        )
        axes = (tangent, width_axis, _normalise(_cross(tangent, width_axis)))
        segment_center = _add(
            world_petiole,
            _sub(_mul(world_long, length * t), _mul(local_up, sag * t * t)),
        )
        output.append(
            CollisionProxy(
                proxy_id=f"{attachment}:blade_{segment_index}",
                plant_id=instance.plant_id,
                kind="leaf",
                shape="obb",
                center=segment_center,
                axes=axes,
                half_extents=(length * 0.17, width * width_factor, 0.0055),
                control_kind="leaf",
                control_id=leaf.id,
                attachment_id=attachment,
                group_id=attachment,
            )
        )


def _leaf_direction_with_clearance_lift(
    direction: Vec3,
    petiole_length: float,
    lift: float,
) -> Vec3:
    """Tilt a connected petiole toward a slightly raised blade endpoint."""
    base = _normalise(direction)
    if lift <= 0.0 or petiole_length <= 1e-9:
        return base
    lifted_target = _add(
        _mul(base, petiole_length),
        (0.0, 0.0, lift),
    )
    return _normalise(lifted_target)


def _append_reproductive_proxies(
    output: list[CollisionProxy],
    unit: Any,
    node: Vec3,
    instance: PlantInstance,
) -> None:
    if unit.calyx is None:
        return
    scale = CM_TO_SCENE_UNIT * instance.scale
    direction = _reproductive_direction(unit.pedicel.azimuth_deg, unit.pedicel.angle_deg)
    pedicel_end = _add(node, _mul(direction, unit.pedicel.length_cm * scale))
    world_node = _world_point(node, instance)
    world_pedicel = _world_point(pedicel_end, instance)
    attachment = f"{instance.plant_id}:{unit.id}"
    output.append(
        CollisionProxy(
            proxy_id=f"{attachment}:pedicel",
            plant_id=instance.plant_id,
            kind="pedicel",
            shape="capsule",
            center=_mid(world_node, world_pedicel),
            axes=_frame_from_long(_world_direction(direction, instance)),
            half_extents=(0.0, 0.0, 0.0),
            start=world_node,
            end=world_pedicel,
            radius=max(0.028 * scale, 0.018),
            attachment_id=attachment,
            group_id=attachment,
        )
    )
    length = unit.calyx.length_cm * scale
    radius = unit.calyx.radius_cm * scale * unit.calyx.inflation
    center_local = _add(pedicel_end, _mul(direction, length * 0.5))
    long_axis = _world_direction(direction, instance)
    output.append(
        CollisionProxy(
            proxy_id=f"{instance.plant_id}:{unit.calyx.id}",
            plant_id=instance.plant_id,
            kind="calyx",
            shape="ellipsoid",
            center=_world_point(center_local, instance),
            axes=_frame_from_long(long_axis),
            half_extents=(length * 0.53, radius * 1.04, radius * 1.04),
            control_kind="pedicel",
            control_id=unit.pedicel.id,
            attachment_id=attachment,
            group_id=attachment,
        )
    )


def _candidate_pairs(proxies: list[CollisionProxy], cell_size: float = 0.45) -> list[tuple[CollisionProxy, CollisionProxy]]:
    grid: dict[tuple[int, int, int], list[int]] = {}
    pairs: set[tuple[int, int]] = set()
    for index, proxy in enumerate(proxies):
        minimum, maximum = proxy.aabb(0.004)
        lows = tuple(math.floor(value / cell_size) for value in minimum)
        highs = tuple(math.floor(value / cell_size) for value in maximum)
        for x in range(lows[0], highs[0] + 1):
            for y in range(lows[1], highs[1] + 1):
                for z in range(lows[2], highs[2] + 1):
                    cell = (x, y, z)
                    for other in grid.get(cell, []):
                        pairs.add((min(index, other), max(index, other)))
                    grid.setdefault(cell, []).append(index)
    return [(proxies[left], proxies[right]) for left, right in sorted(pairs)]


def _collisions_from_pairs(pairs: Iterable[tuple[CollisionProxy, CollisionProxy]]) -> list[dict[str, Any]]:
    collisions = []
    for left, right in pairs:
        if _is_exempt(left, right):
            continue
        clearance = _proxy_clearance(left, right)
        if clearance < -0.002:
            collisions.append(
                {
                    "proxy_a": left,
                    "proxy_b": right,
                    "clearance": clearance,
                    "penetration": -clearance,
                }
            )
    return collisions


def _is_exempt(left: CollisionProxy, right: CollisionProxy) -> bool:
    if left.proxy_id == right.proxy_id:
        return True
    if left.group_id and left.group_id == right.group_id:
        return True
    if left.attachment_id and left.attachment_id == right.attachment_id:
        return True
    if (
        left.kind == right.kind == "stem"
        and left.plant_id == right.plant_id
        and _is_axis_attachment_pair(left, right)
    ):
        return True
    if left.plant_id == right.plant_id and _is_nodal_attachment_pair(left, right):
        return True
    if (
        left.plant_id == right.plant_id
        and left.shape == right.shape == "capsule"
        and left.start is not None
        and left.end is not None
        and right.start is not None
        and right.end is not None
    ):
        endpoint_distance = min(
            _length(_sub(a, b))
            for a in (left.start, left.end)
            for b in (right.start, right.end)
        )
        if endpoint_distance <= left.radius + right.radius + 0.012:
            return True
    return False


def _is_axis_attachment_pair(left: CollisionProxy, right: CollisionProxy) -> bool:
    if left.axis_id and left.axis_id == right.axis_id:
        return abs(left.internode_index - right.internode_index) <= 1
    if (
        left.internode_index == 0
        and _parent_node_near_axis_segment(
            left.axis_parent_node_id,
            right.axis_id,
            right.internode_index,
        )
    ):
        return True
    if (
        right.internode_index == 0
        and _parent_node_near_axis_segment(
            right.axis_parent_node_id,
            left.axis_id,
            left.internode_index,
        )
    ):
        return True
    return False


def _parent_node_near_axis_segment(
    parent_node_id: str | None,
    axis_id: str | None,
    internode_index: int,
) -> bool:
    if (
        not parent_node_id
        or not axis_id
        or "_node_" not in parent_node_id
    ):
        return False
    parent_axis, node_index_text = parent_node_id.rsplit("_node_", 1)
    try:
        node_index = int(node_index_text)
    except ValueError:
        return False
    return (
        parent_axis == axis_id
        and internode_index in {node_index - 1, node_index, node_index + 1}
    )


def _is_nodal_attachment_pair(left: CollisionProxy, right: CollisionProxy) -> bool:
    kinds = {left.kind, right.kind}
    if "stem" not in kinds or not kinds.intersection({"petiole", "pedicel"}):
        return False
    stem = left if left.kind == "stem" else right
    attachment = right if stem is left else left
    stem_path = stem.proxy_id.split(":", 1)[-1].split(":segment_", 1)[0]
    attachment_path = attachment.proxy_id.split(":", 1)[-1].split(":", 1)[0]
    if "_internode_" not in stem_path or "_node_" not in attachment_path:
        return False
    stem_axis, stem_index = stem_path.rsplit("_internode_", 1)
    attachment_axis, node_suffix = attachment_path.rsplit("_node_", 1)
    node_index = node_suffix.split("_", 1)[0]
    return (
        stem_axis == attachment_axis
        and stem_index in {node_index, str(int(node_index) + 1)}
    )


def _proxy_clearance(left: CollisionProxy, right: CollisionProxy) -> float:
    if left.shape == right.shape == "capsule":
        distance = _segment_segment_distance(left.start, left.end, right.start, right.end)
        return distance - left.radius - right.radius
    if left.shape == right.shape == "obb":
        return _obb_clearance(left, right)
    if left.shape == right.shape == "ellipsoid":
        return _ellipsoid_pair_clearance(left, right)
    if left.shape == "capsule":
        return _capsule_shape_clearance(left, right)
    if right.shape == "capsule":
        return _capsule_shape_clearance(right, left)
    if left.shape == "ellipsoid" and right.shape == "obb":
        return _ellipsoid_obb_clearance(left, right)
    if right.shape == "ellipsoid" and left.shape == "obb":
        return _ellipsoid_obb_clearance(right, left)
    return _length(_sub(left.center, right.center)) - max(left.half_extents) - max(right.half_extents)


def _obb_clearance(left: CollisionProxy, right: CollisionProxy) -> float:
    delta = _sub(right.center, left.center)
    minimum_overlap = math.inf
    axes = list(left.axes) + list(right.axes)
    axes.extend(_cross(a, b) for a in left.axes for b in right.axes)
    for axis in axes:
        if _length(axis) < 1e-8:
            continue
        normal = _normalise(axis)
        distance = abs(_dot(delta, normal))
        left_radius = sum(left.half_extents[i] * abs(_dot(left.axes[i], normal)) for i in range(3))
        right_radius = sum(right.half_extents[i] * abs(_dot(right.axes[i], normal)) for i in range(3))
        overlap = left_radius + right_radius - distance
        if overlap < 0.0:
            return -overlap
        minimum_overlap = min(minimum_overlap, overlap)
    return -minimum_overlap if minimum_overlap < math.inf else 0.0


def _ellipsoid_pair_clearance(left: CollisionProxy, right: CollisionProxy) -> float:
    delta = _sub(right.center, left.center)
    distance = _length(delta)
    direction = _normalise(delta) if distance > 1e-9 else left.axes[0]
    return distance - _ellipsoid_support(left, direction) - _ellipsoid_support(right, _mul(direction, -1.0))


def _ellipsoid_obb_clearance(ellipsoid: CollisionProxy, box: CollisionProxy) -> float:
    closest = _closest_point_obb(ellipsoid.center, box)
    delta = _sub(closest, ellipsoid.center)
    distance = _length(delta)
    direction = _normalise(delta) if distance > 1e-9 else box.axes[2]
    return distance - _ellipsoid_support(ellipsoid, direction)


def _capsule_shape_clearance(capsule: CollisionProxy, other: CollisionProxy) -> float:
    samples = [_lerp(capsule.start, capsule.end, index / 16.0) for index in range(17)]
    if other.shape == "obb":
        distance = min(_length(_sub(point, _closest_point_obb(point, other))) for point in samples)
        return distance - capsule.radius
    distances = []
    for point in samples:
        delta = _sub(point, other.center)
        distance = _length(delta)
        direction = _normalise(delta) if distance > 1e-9 else other.axes[0]
        distances.append(distance - _ellipsoid_support(other, direction))
    return min(distances) - capsule.radius


def _ellipsoid_support(proxy: CollisionProxy, direction: Vec3) -> float:
    return math.sqrt(
        sum((proxy.half_extents[i] * _dot(direction, proxy.axes[i])) ** 2 for i in range(3))
    )


def _closest_point_obb(point: Vec3, box: CollisionProxy) -> Vec3:
    delta = _sub(point, box.center)
    result = box.center
    for index, axis in enumerate(box.axes):
        distance = max(-box.half_extents[index], min(box.half_extents[index], _dot(delta, axis)))
        result = _add(result, _mul(axis, distance))
    return result


def _resolve_collision(
    collision: dict[str, Any],
    *,
    iteration: int,
    lookup: dict[tuple[str, str, str], Any],
    scene: CultivationScene,
    adjusted_controls: set[tuple[str, str, str]],
) -> dict[str, Any] | None:
    proxies = sorted(
        (collision["proxy_a"], collision["proxy_b"]),
        key=lambda item: ({"leaf": 0, "calyx": 1, "stem": 2, "stake": 3}.get(item.kind, 4), item.proxy_id),
    )
    for proxy in proxies:
        if proxy.control_kind is None or proxy.control_id is None:
            continue
        key = (proxy.plant_id, proxy.control_kind, proxy.control_id)
        if key in adjusted_controls:
            continue
        target = lookup.get(key)
        if target is None and proxy.control_kind != "support":
            continue
        adjusted_controls.add(key)
        direction_sign = -1.0 if sum(ord(value) for value in proxy.proxy_id) % 2 else 1.0
        other = collision["proxy_b"] if proxy is collision["proxy_a"] else collision["proxy_a"]
        instance = next(item for item in scene.plant_instances if item.plant_id == proxy.plant_id)
        away_world = math.degrees(
            math.atan2(proxy.center[1] - other.center[1], proxy.center[0] - other.center[0])
        ) % 360.0
        away_local = (away_world - instance.rotation_deg) % 360.0
        if proxy.control_kind == "leaf":
            before = (target.azimuth_deg, target.insertion_angle_deg)
            if other.kind in {"leaf", "petiole", "pedicel"}:
                obstacle_azimuth = math.degrees(math.atan2(other.axes[0][1], other.axes[0][0])) % 360.0
                perpendicular_local = (obstacle_azimuth + direction_sign * 90.0 - instance.rotation_deg) % 360.0
                target.azimuth_deg = round(
                    (perpendicular_local + direction_sign * iteration * 4.0) % 360.0,
                    3,
                )
            else:
                # For a stem, calyx or stake, the obstacle centre is a more
                # stable escape direction than the almost-vertical long axis.
                fan_offset = direction_sign * (10.0 + iteration * 6.0)
                target.azimuth_deg = round((away_local + fan_offset) % 360.0, 3)
            if other.kind in {"stem", "stake", "petiole", "pedicel"}:
                # A nearly radial blade clears the vertical/axial obstacle and
                # does not curl the blade itself.
                target.insertion_angle_deg = 88.0
            elif other.kind == "leaf":
                target.insertion_angle_deg = 52.0 if direction_sign < 0.0 else 78.0
            else:
                target.insertion_angle_deg = 72.0
            target.curl = 0.0
            target.twist_deg = 0.0
            after = (target.azimuth_deg, target.insertion_angle_deg)
        elif proxy.control_kind == "pedicel":
            before = (target.azimuth_deg, target.angle_deg)
            target.azimuth_deg = round((away_local + direction_sign * (12.0 + iteration * 6.0)) % 360.0, 3)
            target.angle_deg = (28.0, 42.0, 56.0, 70.0)[(sum(ord(value) for value in target.id) + iteration) % 4]
            after = (target.azimuth_deg, target.angle_deg)
        elif proxy.control_kind == "axis":
            before = (target.azimuth_deg, target.branch_angle_deg)
            target.azimuth_deg = round((away_local + direction_sign * (6.0 + iteration * 3.0)) % 360.0, 3)
            target.branch_angle_deg = round(max(32.0, min(84.0, target.branch_angle_deg + direction_sign * 2.0)), 3)
            after = (target.azimuth_deg, target.branch_angle_deg)
        else:
            support = next((item for item in scene.supports if item.support_id == proxy.control_id), None)
            if support is None:
                continue
            away = _normalise((support.position[0] - other.center[0], support.position[1] - other.center[1], 0.0))
            before = support.position
            support.position = (
                round(support.position[0] + away[0] * 0.035, 4),
                round(support.position[1] + away[1] * 0.035, 4),
                support.position[2],
            )
            after = support.position
        return {
            "iteration": iteration,
            "plant_id": proxy.plant_id,
            "control_kind": proxy.control_kind,
            "control_id": proxy.control_id,
            "before": before,
            "after": after,
            "trigger_pair": [collision["proxy_a"].proxy_id, collision["proxy_b"].proxy_id],
            "penetration": round(collision["penetration"], 5),
        }
    return None


def _control_lookup(plants: dict[str, Plant]) -> dict[tuple[str, str, str], Any]:
    result: dict[tuple[str, str, str], Any] = {}
    for plant_id, plant in plants.items():
        for axis in plant.axes:
            _append_controls(result, plant_id, axis)
    return result


def _append_controls(result: dict[tuple[str, str, str], Any], plant_id: str, axis: Axis) -> None:
    result[(plant_id, "axis", axis.id)] = axis
    for node in axis.nodes:
        if node.leaf is not None:
            result[(plant_id, "leaf", node.leaf.id)] = node.leaf
        if node.reproductive_unit is not None:
            pedicel = node.reproductive_unit.pedicel
            result[(plant_id, "pedicel", pedicel.id)] = pedicel
    for child in axis.child_axes:
        _append_controls(result, plant_id, child)


def _collision_to_dict(item: dict[str, Any]) -> dict[str, Any]:
    left, right = item["proxy_a"], item["proxy_b"]
    return {
        "type": f"{left.kind}_{right.kind}_intersection",
        "plant_a": left.plant_id,
        "plant_b": right.plant_id,
        "object_a": left.proxy_id,
        "object_b": right.proxy_id,
        "clearance": round(item["clearance"], 5),
        "penetration": round(item["penetration"], 5),
    }


def _axis_direction(parent: Vec3, azimuth_deg: float, angle_deg: float) -> Vec3:
    parent = _normalise(parent)
    if angle_deg <= 0.001:
        return parent
    radial = _radial(azimuth_deg)
    radial = _normalise(_sub(radial, _mul(parent, _dot(radial, parent))))
    angle = math.radians(angle_deg)
    return _normalise(_add(_mul(parent, math.cos(angle)), _mul(radial, math.sin(angle))))


def _bend_direction(direction: Vec3, azimuth_deg: float, angle_deg: float) -> Vec3:
    current = _normalise(direction)
    radial = _radial(azimuth_deg)
    radial = _normalise(_sub(radial, _mul(current, _dot(radial, current))))
    angle = math.radians(max(-12.0, min(12.0, angle_deg)))
    bent = _normalise(_add(_mul(current, math.cos(angle)), _mul(radial, math.sin(angle))))
    return _normalise((bent[0], bent[1], max(-0.15, bent[2])))


def _load_deflection(direction: Vec3, axis: Axis, index: int, count: int) -> Vec3:
    if axis.mechanical_deflection_deg <= 0.0 or count <= 0:
        return direction
    horizontal = _normalise((direction[0], direction[1], 0.0))
    tilt = math.atan2(direction[2], math.hypot(direction[0], direction[1]))
    gain = 0.45 + 0.55 * ((index + 1) / count)
    target = max(math.radians(-35.0), tilt - math.radians(axis.mechanical_deflection_deg) / count * gain)
    return _normalise((horizontal[0] * math.cos(target), horizontal[1] * math.cos(target), math.sin(target)))


def _reproductive_direction(azimuth_deg: float, angle_deg: float) -> Vec3:
    radial = _radial(azimuth_deg)
    angle = math.radians(max(5.0, min(72.0, angle_deg)))
    return _normalise((radial[0] * math.cos(angle), radial[1] * math.cos(angle), -math.sin(angle)))


def _world_point(point: Vec3, instance: PlantInstance) -> Vec3:
    rotated = _rotate_z(point, instance.rotation_deg)
    return _add(rotated, instance.position)


def _world_direction(direction: Vec3, instance: PlantInstance) -> Vec3:
    return _normalise(_rotate_z(direction, instance.rotation_deg))


def _frame_from_long(long_axis: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    long_axis = _normalise(long_axis)
    width = _cross((0.0, 0.0, 1.0), long_axis)
    if _length(width) < 1e-8:
        width = (1.0, 0.0, 0.0)
    width = _normalise(width)
    normal = _normalise(_cross(long_axis, width))
    return long_axis, width, normal


def _segment_segment_distance(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> float:
    # Closest points on two finite segments (Real-Time Collision Detection).
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if a <= 1e-12 and e <= 1e-12:
        return _length(r)
    if a <= 1e-12:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = _dot(d1, r)
        if e <= 1e-12:
            t, s = 0.0, max(0.0, min(1.0, -c / a))
        else:
            b = _dot(d1, d2)
            denominator = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / denominator)) if denominator else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    return _length(_sub(_add(p1, _mul(d1, s)), _add(p2, _mul(d2, t))))


def _radial(angle_deg: float) -> Vec3:
    angle = math.radians(angle_deg)
    return math.cos(angle), math.sin(angle), 0.0


def _rotate_z(value: Vec3, angle_deg: float) -> Vec3:
    angle = math.radians(angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    return value[0] * cosine - value[1] * sine, value[0] * sine + value[1] * cosine, value[2]


def _add(left: Vec3, right: Vec3) -> Vec3:
    return left[0] + right[0], left[1] + right[1], left[2] + right[2]


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return left[0] - right[0], left[1] - right[1], left[2] - right[2]


def _mul(value: Vec3, scalar: float) -> Vec3:
    return value[0] * scalar, value[1] * scalar, value[2] * scalar


def _dot(left: Vec3, right: Vec3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Vec3, right: Vec3) -> Vec3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(value: Vec3) -> float:
    return math.sqrt(_dot(value, value))


def _normalise(value: Vec3) -> Vec3:
    length = _length(value)
    return _mul(value, 1.0 / length) if length > 1e-12 else (1.0, 0.0, 0.0)


def _mid(left: Vec3, right: Vec3) -> Vec3:
    return _mul(_add(left, right), 0.5)


def _lerp(left: Vec3, right: Vec3, amount: float) -> Vec3:
    return _add(left, _mul(_sub(right, left), amount))
