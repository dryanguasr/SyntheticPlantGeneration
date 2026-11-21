"""Deterministic cultivation-level adaptation for several uchuva plants.

The individual grammar remains responsible for botanical attachment.  This
module applies a bounded, auditable relaxation after every individual has
been generated and before Blender interprets the morphology.  It represents
plastic response to neighbours, light, fruit load, and individual stakes;
it is not a time-resolved biomechanics simulation.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .morphology import Axis, Plant
from .grammar import (
    enforce_parent_radius_continuity,
    generate_morphology_tree,
    record_reproductive_counts,
)
from .growth import coordinate_synchronous_growth
from .parameters import get_morphology_parameters
from .scene import CultivationScene, CultivationSupport, PlantInstance
from .collisions import resolve_global_collisions
from .spatial import ContactPolicy


ADAPTATION_VERSION = "0.4.0-stratified-light-trellis"
RELAXATION_ITERATIONS = 3
CM_TO_SCENE_UNIT = 0.08


MODEL_VARIANTS = {
    "A_baseline_independent",
    "B_morphology_calibrated",
    "C_plus_structural_support",
    "D_plus_synchronous_multi_plant",
    "E_plus_contact_policy_clearance",
    "F_plus_space_colonization_optional",
}


def generate_cultivation_morphologies(
    scene: CultivationScene,
    params: dict[str, Any] | None = None,
    model_variant: str = "E_plus_contact_policy_clearance",
    *,
    potential_plants: dict[str, Plant] | None = None,
    support_enabled_override: bool | None = None,
) -> tuple[CultivationScene, dict[str, Plant], dict[str, Any]]:
    """Generate a cultivation morphology using an explicit A--F variant.

    ``legacy_posthoc`` remains available through
    :func:`adapt_cultivation_morphologies`; this API is the morphology-first
    coordinator for new experiments.
    """
    if model_variant not in MODEL_VARIANTS:
        raise ValueError(
            f"Unknown model_variant {model_variant!r}; expected one of "
            f"{sorted(MODEL_VARIANTS)}"
        )
    if model_variant == "A_baseline_independent":
        active_params = params or get_morphology_parameters(
            "initial_migration_manual_guess"
        )
    else:
        active_params = params or get_morphology_parameters("trained_trellis")
    active_scene = deepcopy(scene)
    if potential_plants is None:
        potential_plants = {
            instance.plant_id: generate_morphology_tree(
                instance.seed,
                params=active_params,
                condition=instance.condition,
            )
            for instance in active_scene.plant_instances
        }
    else:
        potential_plants = deepcopy(potential_plants)

    if model_variant == "A_baseline_independent":
        return adapt_cultivation_morphologies(
            active_scene,
            potential_plants,
        )

    if model_variant == "B_morphology_calibrated":
        report = {
            "version": ADAPTATION_VERSION,
            "growth_mode": "budgeted_individual_no_scene_coordination",
            "proposal_count": 0,
            "decision_counts": {},
            "adjustments": [],
            "support_enabled": False,
            "shared_occupancy": False,
            "parameter_status": "engineering_heuristic",
        }
        active_scene.metadata["cultivation_adaptation"] = report
        _record_audit_stage(potential_plants)
        return active_scene, potential_plants, report

    variant_options = {
        "C_plus_structural_support": {
            "shared_occupancy": False,
            "support_enabled": True,
            "leaf_posture_enabled": True,
            "tangential_sliding_enabled": False,
            "space_colonization_enabled": False,
        },
        "D_plus_synchronous_multi_plant": {
            "shared_occupancy": True,
            "support_enabled": True,
            "leaf_posture_enabled": True,
            "tangential_sliding_enabled": False,
            "space_colonization_enabled": False,
        },
        "E_plus_contact_policy_clearance": {
            "shared_occupancy": True,
            "support_enabled": True,
            "leaf_posture_enabled": True,
            "tangential_sliding_enabled": True,
            "space_colonization_enabled": False,
        },
        "F_plus_space_colonization_optional": {
            "shared_occupancy": True,
            "support_enabled": True,
            "leaf_posture_enabled": True,
            "tangential_sliding_enabled": True,
            # The feature remains disabled in every normal preset.  Variant F
            # is the explicit experiment that turns it on for its retention
            # gate.
            "space_colonization_enabled": True,
        },
    }[model_variant]
    if support_enabled_override is not None:
        variant_options["support_enabled"] = bool(support_enabled_override)
        if active_scene.support_system is not None:
            active_scene.support_system.enabled = bool(support_enabled_override)
        if not support_enabled_override:
            active_scene.supports = []
        active_scene.metadata["support_enabled_override"] = bool(
            support_enabled_override
        )
    active_plants, report = coordinate_synchronous_growth(
        active_scene,
        potential_plants,
        contact_policy=ContactPolicy.default(),
        light_competition=active_params.get("light_competition", {}),
        **variant_options,
    )
    collision_report = None
    if model_variant in {
        "E_plus_contact_policy_clearance",
        "F_plus_space_colonization_optional",
    }:
        collision_report = resolve_global_collisions(
            active_scene,
            active_plants,
            iterations=8,
            include_contact_audit=True,
        )
        report["collision_resolution"] = collision_report
        report["physical_collisions"] = collision_report[
            "physical_collisions"
        ]
        report["leaf_calyx_micro_lift"] = collision_report[
            "leaf_calyx_micro_lift"
        ]
    report["model_variant"] = model_variant
    report["posthoc_mode"] = "local_only_no_global_axis_relaxation"
    report["support_count"] = (
        len(active_scene.support_system.posts)
        + len(active_scene.support_system.lines)
        + len(active_scene.support_system.ties)
        if active_scene.support_system is not None
        else len(active_scene.supports)
    )
    active_scene.metadata["cultivation_adaptation"] = report
    _record_audit_stage(active_plants)
    return active_scene, active_plants, report


def adapt_cultivation_morphologies(
    scene: CultivationScene,
    plants_by_id: dict[str, Plant],
    params: dict[str, Any] | None = None,
) -> tuple[CultivationScene, dict[str, Plant], dict[str, Any]]:
    """Return adapted copies of a scene and its morphology trees.

    Structural stems, bases, stakes, and calyxes are treated as hard-space
    constraints.  Leaf and canopy overlap remains deliberately permissive so
    dense scenes can interlace visually without being reported as collision.
    """
    from .nodal_repulsion import require_legacy_pose_inputs
    require_legacy_pose_inputs(plants_by_id.values(),'adapt_cultivation_morphologies')
    active_scene = deepcopy(scene)
    active_plants = deepcopy(plants_by_id)
    options = {
        "iterations": RELAXATION_ITERATIONS,
        "candidate_offsets_deg": (-45.0, -22.5, 0.0, 22.5, 45.0),
        "max_main_deflection_deg": 12.0,
        "max_lateral_deflection_deg": 35.0,
    }
    if params:
        options.update(params)

    instances = {item.plant_id: item for item in active_scene.plant_instances}
    supports = {item.plant_id: item for item in active_scene.supports}
    missing = sorted(set(instances) - set(active_plants))
    if missing:
        raise ValueError(f"Missing morphology trees for plant instances: {missing}")

    pair_interactions = _pair_interactions(active_scene.plant_instances)
    adapted_axes: list[dict[str, Any]] = []

    for plant_id in sorted(active_plants):
        plant = active_plants[plant_id]
        instance = instances[plant_id]
        support = supports.get(plant_id)
        if support is not None:
            _fit_support_to_plant(support, plant, instance)

        neighbour_instances = [
            other
            for other in active_scene.plant_instances
            if other.plant_id != plant_id
        ]
        for _iteration in range(int(options["iterations"])):
            for root_axis in plant.axes:
                _relax_axis_directions(
                    root_axis,
                    instance=instance,
                    neighbours=neighbour_instances,
                    support=support,
                    candidate_offsets=tuple(options["candidate_offsets_deg"]),
                    adapted_axes=adapted_axes,
                    iteration=_iteration,
                )

        for root_axis in plant.axes:
            _assign_mechanical_load(
                root_axis,
                max_main_deflection=float(options["max_main_deflection_deg"]),
                max_lateral_deflection=float(options["max_lateral_deflection_deg"]),
            )
            _separate_axillary_organs(root_axis)

        plant.metadata["cultivation_adaptation"] = {
            "version": ADAPTATION_VERSION,
            "iterations": int(options["iterations"]),
            "support_id": support.support_id if support else None,
            "neighbour_ids": sorted(item.plant_id for item in neighbour_instances),
            "policy": "light_and_gap_relaxation_with_load_deflection",
        }

    collision_report = resolve_global_collisions(
        active_scene,
        active_plants,
        iterations=int(options.get("collision_iterations", 8)),
        include_contact_audit=bool(
            options.get("include_contact_audit", False)
        ),
    )

    report = {
        "version": ADAPTATION_VERSION,
        "iterations": int(options["iterations"]),
        "plant_count": len(active_plants),
        "adapted_axis_count": len({(item["plant_id"], item["axis_id"]) for item in adapted_axes}),
        "axis_adjustments": adapted_axes,
        "pair_interactions": pair_interactions,
        "visual_canopy_overlap_count": sum(
            1 for item in pair_interactions if item["canopy_overlap"]
        ),
        "physical_collisions": collision_report["physical_collisions"],
        "collision_resolution": collision_report,
        "support_count": len(active_scene.supports),
        "collision_policy": {
            "hard": ["plant_base", "structural_axis", "stake", "calyx"],
            "permissive": ["projected_occlusion"],
            "intentional_contact": ["stem_tie"],
        },
        "parameter_status": "manual_initial_guess_dataset_guided",
    }
    active_scene.metadata["cultivation_adaptation"] = report
    _record_audit_stage(active_plants)
    return active_scene, active_plants, report


def _record_audit_stage(plants: dict[str, Plant]) -> None:
    for plant in plants.values():
        if plant.metadata.get("reproductive_load_policy") == "architecture_driven":
            enforce_parent_radius_continuity(plant, stage="adapted")
            record_reproductive_counts(plant, "adapted")


def _relax_axis_directions(
    axis: Axis,
    *,
    instance: PlantInstance,
    neighbours: list[PlantInstance],
    support: CultivationSupport | None,
    candidate_offsets: tuple[float, ...],
    adapted_axes: list[dict[str, Any]],
    iteration: int,
) -> None:
    nearest_distance, nearest_azimuth = _nearest_neighbour(instance, neighbours)
    canopy_radius = float(instance.collision_proxy.get("canopy_radius", 0.5))
    neighbour_influence = (
        max(0.0, min(1.0, (canopy_radius * 2.2 - nearest_distance) / max(canopy_radius * 1.7, 1e-6)))
        if nearest_distance is not None
        else 0.0
    )
    axis.neighbor_influence = round(neighbour_influence, 4)

    if axis.order == 0:
        axis.support_influence = 1.0 if support is not None else 0.0
        if support is not None:
            stake_azimuth = math.degrees(
                math.atan2(
                    support.position[1] - instance.position[1],
                    support.position[0] - instance.position[0],
                )
            ) % 360.0
            stake_azimuth = (stake_azimuth - instance.rotation_deg) % 360.0
            for index, internode in enumerate(axis.internodes):
                fraction = (index + 1) / max(1, len(axis.internodes))
                attraction = (1.0 - fraction) * 0.85 + 0.15
                internode.bend_azimuth_deg = round(
                    _circular_lerp(internode.bend_azimuth_deg, stake_azimuth, 0.12 * attraction),
                    3,
                )
                internode.bend_angle_deg = round(
                    min(5.0, internode.bend_angle_deg + 0.22 * attraction),
                    3,
                )
    else:
        axis.support_influence = round(max(0.0, 0.32 - axis.order * 0.08), 4)
        original = axis.azimuth_deg
        original_world = (original + instance.rotation_deg) % 360.0
        best_azimuth = original_world
        best_score = -math.inf
        for offset in candidate_offsets:
            candidate = (original_world + offset) % 360.0
            score = _candidate_score(
                candidate,
                offset=offset,
                neighbour_azimuth=nearest_azimuth,
                neighbour_distance=nearest_distance,
                canopy_radius=canopy_radius,
                neighbour_influence=neighbour_influence,
                support=support,
                instance=instance,
            )
            if score > best_score:
                best_score = score
                best_azimuth = candidate

        if (
            nearest_azimuth is not None
            and neighbour_influence > 0.05
            and abs(_signed_angle_delta(original_world, best_azimuth)) < 1.0
        ):
            tangents = (
                (nearest_azimuth + 90.0) % 360.0,
                (nearest_azimuth - 90.0) % 360.0,
            )
            best_azimuth = min(
                tangents,
                key=lambda value: abs(_signed_angle_delta(original_world, value)),
            )

        blend = 0.34 + 0.12 * neighbour_influence
        adjusted_world = _circular_lerp(original_world, best_azimuth, blend)
        adjusted = (adjusted_world - instance.rotation_deg) % 360.0
        if abs(_signed_angle_delta(original, adjusted)) >= 0.05:
            axis.azimuth_deg = round(adjusted, 3)
            axis.branch_angle_deg = round(
                max(34.0, min(82.0, axis.branch_angle_deg + 2.2 * neighbour_influence)),
                3,
            )
            adapted_axes.append(
                {
                    "plant_id": instance.plant_id,
                    "axis_id": axis.id,
                    "iteration": iteration,
                    "azimuth_before_deg": round(original, 3),
                    "azimuth_after_deg": axis.azimuth_deg,
                    "neighbour_influence": axis.neighbor_influence,
                }
            )

    for child in axis.child_axes:
        _relax_axis_directions(
            child,
            instance=instance,
            neighbours=neighbours,
            support=support,
            candidate_offsets=candidate_offsets,
            adapted_axes=adapted_axes,
            iteration=iteration,
        )


def _candidate_score(
    azimuth_deg: float,
    *,
    offset: float,
    neighbour_azimuth: float | None,
    neighbour_distance: float | None,
    canopy_radius: float,
    neighbour_influence: float,
    support: CultivationSupport | None,
    instance: PlantInstance,
) -> float:
    preservation = 1.0 - abs(offset) / 70.0
    if neighbour_azimuth is None or neighbour_distance is None:
        return preservation

    angular_separation = abs(_signed_angle_delta(neighbour_azimuth, azimuth_deg))
    # A tangential direction grows into a shared canopy gap without aiming at
    # the neighbouring structural base.
    tangential = 1.0 - abs(90.0 - angular_separation) / 90.0
    away_from_base = min(1.0, angular_separation / 55.0)
    interlace_band = max(
        0.0,
        1.0 - abs(neighbour_distance - canopy_radius * 1.25) / max(canopy_radius, 1e-6),
    )
    score = (
        preservation * 0.22
        + tangential * 0.48 * neighbour_influence
        + interlace_band * 0.24 * neighbour_influence
        + away_from_base * 0.24 * neighbour_influence
    )
    if angular_separation < 18.0 and neighbour_distance < canopy_radius * 1.05:
        score -= 2.0

    if support is not None:
        stake_azimuth = math.degrees(
            math.atan2(
                support.position[1] - instance.position[1],
                support.position[0] - instance.position[0],
            )
        ) % 360.0
        if abs(_signed_angle_delta(stake_azimuth, azimuth_deg)) < 12.0:
            score -= 0.45
    return score


def _assign_mechanical_load(
    axis: Axis,
    *,
    max_main_deflection: float,
    max_lateral_deflection: float,
) -> float:
    own_load = sum(_node_reproductive_load(node) for node in axis.nodes)
    child_load = sum(
        _assign_mechanical_load(
            child,
            max_main_deflection=max_main_deflection,
            max_lateral_deflection=max_lateral_deflection,
        )
        for child in axis.child_axes
    )
    total_load = own_load + child_load
    length_cm = sum(internode.length_cm for internode in axis.internodes)
    mean_radius = (
        sum(internode.radius_cm for internode in axis.internodes) / len(axis.internodes)
        if axis.internodes
        else 0.1
    )
    torque_proxy = total_load * max(length_cm, 1.0) / max(mean_radius**2, 0.004)
    load_factor = torque_proxy / (torque_proxy + 3500.0)
    deflection_cap = max_main_deflection if axis.order == 0 else max_lateral_deflection
    order_gain = 0.72 if axis.order == 0 else min(1.0, 0.82 + axis.order * 0.09)
    axis.reproductive_load = round(load_factor, 4)
    axis.mechanical_deflection_deg = round(deflection_cap * load_factor * order_gain, 3)
    return total_load


def _node_reproductive_load(node: Any) -> float:
    unit = node.reproductive_unit
    if unit is None:
        return 0.0
    load = 0.08 if unit.stage == "flower" else 0.0
    if unit.fruit is not None:
        load += max(0.0, unit.fruit.radius_cm) ** 3
    if unit.calyx is not None:
        load += (
            max(0.0, unit.calyx.radius_cm) ** 2
            * max(0.0, unit.calyx.length_cm)
            * 0.12
        )
    return load


def _separate_axillary_organs(axis: Axis) -> None:
    """Keep leaves out of the initial branch/reproductive emergence sector."""
    children_by_node: dict[str, list[Axis]] = {}
    for child in axis.child_axes:
        if child.parent_node_id:
            children_by_node.setdefault(child.parent_node_id, []).append(child)
    for node in axis.nodes:
        leaf = node.leaf
        if leaf is None:
            continue
        forbidden: list[float] = [child.azimuth_deg for child in children_by_node.get(node.id, [])]
        if node.reproductive_unit is not None:
            forbidden.append(node.reproductive_unit.pedicel.azimuth_deg)
        for occupied_azimuth in forbidden:
            if abs(_signed_angle_delta(occupied_azimuth, leaf.azimuth_deg)) < 52.0:
                sign = -1.0 if sum(ord(value) for value in leaf.id) % 2 else 1.0
                leaf.azimuth_deg = round((occupied_azimuth + sign * 82.0) % 360.0, 3)
    for child in axis.child_axes:
        _separate_axillary_organs(child)


def _fit_support_to_plant(
    support: CultivationSupport,
    plant: Plant,
    instance: PlantInstance,
) -> None:
    main_height = max(
        (
            sum(internode.length_cm for internode in axis.internodes)
            * CM_TO_SCENE_UNIT
            * instance.scale
            for axis in plant.axes
        ),
        default=support.height,
    )
    support.height = round(max(2.4, main_height * 0.92), 3)
    maximum_main_radius_cm = max(
        (
            internode.radius_cm
            for axis in plant.axes
            if axis.order == 0
            for internode in axis.internodes
        ),
        default=0.35,
    )
    main_stem_diameter = maximum_main_radius_cm * 2.0 * CM_TO_SCENE_UNIT * instance.scale
    support.section_width = round(max(0.08, min(0.14, main_stem_diameter * 3.0)), 4)
    support.section_depth = round(support.section_width * 1.25, 4)
    support.radius = round(
        0.5 * math.hypot(support.section_width, support.section_depth),
        4,
    )
    dx = support.position[0] - instance.position[0]
    dy = support.position[1] - instance.position[1]
    distance = math.hypot(dx, dy)
    required_offset = max(
        0.32 * instance.scale,
        support.radius + maximum_main_radius_cm * CM_TO_SCENE_UNIT * instance.scale + 0.045,
    )
    if distance < required_offset:
        direction_x, direction_y = (
            (dx / distance, dy / distance) if distance > 1e-8 else (1.0, 0.0)
        )
        support.position = (
            round(instance.position[0] + direction_x * required_offset, 4),
            round(instance.position[1] + direction_y * required_offset, 4),
            support.position[2],
        )
    tie_count = 3 if main_height >= 3.0 else 2
    support.tie_heights = [
        round(support.height * fraction, 3)
        for fraction in (0.34, 0.61, 0.82)[:tie_count]
    ]


def _nearest_neighbour(
    instance: PlantInstance,
    neighbours: list[PlantInstance],
) -> tuple[float | None, float | None]:
    nearest: tuple[float, float] | None = None
    for other in neighbours:
        dx = other.position[0] - instance.position[0]
        dy = other.position[1] - instance.position[1]
        distance = math.hypot(dx, dy)
        azimuth = math.degrees(math.atan2(dy, dx)) % 360.0
        if nearest is None or distance < nearest[0]:
            nearest = (distance, azimuth)
    return nearest if nearest is not None else (None, None)


def _pair_interactions(instances: list[PlantInstance]) -> list[dict[str, Any]]:
    interactions: list[dict[str, Any]] = []
    ordered = sorted(instances, key=lambda item: item.plant_id)
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            distance = math.hypot(
                right.position[0] - left.position[0],
                right.position[1] - left.position[1],
            )
            combined = float(left.collision_proxy.get("canopy_radius", 0.0)) + float(
                right.collision_proxy.get("canopy_radius", 0.0)
            )
            interactions.append(
                {
                    "plant_a": left.plant_id,
                    "plant_b": right.plant_id,
                    "base_distance": round(distance, 4),
                    "canopy_overlap": distance < combined,
                    "structural_clearance": round(
                        distance
                        - float(left.collision_proxy.get("base_radius", 0.1))
                        - float(right.collision_proxy.get("base_radius", 0.1)),
                        4,
                    ),
                }
            )
    return interactions


def _signed_angle_delta(start_deg: float, end_deg: float) -> float:
    return (end_deg - start_deg + 180.0) % 360.0 - 180.0


def _circular_lerp(start_deg: float, end_deg: float, amount: float) -> float:
    return (start_deg + _signed_angle_delta(start_deg, end_deg) * amount) % 360.0
