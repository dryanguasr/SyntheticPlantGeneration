"""Early validation for uchuva morphology trees.

The validator reports morphology concerns separately from future geometric
collision and visual occlusion checks.
"""

from __future__ import annotations

import math
from typing import Any

from .morphology import Axis, Node, Plant
from .parameters import get_initial_parameters
from .scene import CultivationScene


def validate_morphology_tree(plant: Plant) -> dict[str, Any]:
    """Return a lightweight validation report for a morphology tree."""
    warnings: list[dict[str, str]] = []
    params = get_initial_parameters()
    axis_count = 0
    node_count = 0
    reproductive_count = 0
    fruiting_count = 0
    flower_count = 0
    calyx_state_counts: dict[str, int] = {}
    leaf_light_summary = {
        "assigned_leaf_count": 0,
        "strata": {"lower": 0, "middle": 0, "upper": 0},
        "mean_daily_light_interception_proxy": 0.0,
        "mean_projected_coverage_gain": 0.0,
        "mean_intraspecific_shading_fraction": 0.0,
        "mean_interspecific_shading_fraction": 0.0,
    }

    if plant.condition not in {"healthy", "drying"}:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"Plant condition {plant.condition!r} is not healthy or drying.",
        )

    for axis in plant.axes:
        axis_count += _count_axes(axis)
        node_count += _validate_axis(axis, warnings)
        reproductive_count += _count_reproductive_units(axis)
        fruiting_count += _count_fruiting_units(axis)
        flower_count += _count_flowers(axis)
        _collect_calyx_states(axis, calyx_state_counts)
        _validate_stem_color_coherence(axis, plant.condition, warnings)

    _validate_individual_scope(plant, params, warnings)
    light_enabled = bool(
        plant.metadata.get("synchronous_growth", {}).get(
            "light_competition_enabled",
            plant.metadata.get("light_competition", {}).get("enabled", False),
        )
    )
    leaf_light_summary = _validate_leaf_light_response(
        plant,
        warnings,
        required=light_enabled,
    )
    phenology_summary = _validate_phenology_coherence(plant, warnings)

    return {
        "plant_seed": plant.seed,
        "status": "valid_with_warnings" if warnings else "valid",
        "summary": {
            "axis_count": axis_count,
            "node_count": node_count,
            "reproductive_unit_count": reproductive_count,
            "fruiting_reproductive_unit_count": fruiting_count,
            "flower_count": flower_count,
            "calyx_state_counts": calyx_state_counts,
            "leaf_light_response": leaf_light_summary,
            "phenology": phenology_summary,
        },
        "warnings": warnings,
        "checks": {
            "geometric_collision": "not_evaluated_in_initial_migration",
            "visual_occlusion": "not_evaluated_in_initial_migration",
            "out_of_range_morphology": "basic_morphology_and_calyx_checks",
            "individual_width_scope": "basic_axis_span_estimate",
            "stratified_light_response": (
                "validated_additive_proxy_fields"
                if light_enabled
                else "not_enabled"
            ),
            "phenology_coherence": phenology_summary["status"],
        },
    }


def validate_cultivation_scene(scene: CultivationScene) -> dict[str, Any]:
    """Validate scene-level placement under a canopy-permissive policy."""
    warnings: list[dict[str, str]] = []
    physical_collisions: list[dict[str, Any]] = []
    visual_occlusions: list[dict[str, Any]] = []
    instances = scene.plant_instances
    instances_by_id = {item.plant_id: item for item in instances}

    for left_index in range(len(instances)):
        for right_index in range(left_index + 1, len(instances)):
            left = instances[left_index]
            right = instances[right_index]
            distance = math.hypot(
                left.position[0] - right.position[0],
                left.position[1] - right.position[1],
            )
            min_base_distance = (
                left.collision_proxy.get("base_radius", 0.1)
                + right.collision_proxy.get("base_radius", 0.1)
                + 0.16
            )
            if distance < min_base_distance:
                collision = {
                    "type": "base_or_main_stem_too_close",
                    "plant_a": left.plant_id,
                    "plant_b": right.plant_id,
                    "distance": round(distance, 3),
                    "minimum": round(min_base_distance, 3),
                }
                physical_collisions.append(collision)
                _warn(
                    warnings,
                    "geometric_collision",
                    f"{left.plant_id} and {right.plant_id} bases are too close.",
                )
            canopy_radius = (
                left.collision_proxy.get("canopy_radius", 0.0)
                + right.collision_proxy.get("canopy_radius", 0.0)
            )
            if distance < canopy_radius:
                visual_occlusions.append(
                    {
                        "type": "canopy_overlap_allowed",
                        "plant_a": left.plant_id,
                        "plant_b": right.plant_id,
                        "distance": round(distance, 3),
                    }
                )

    supports_by_plant: dict[str, list[Any]] = {}
    for support in scene.supports:
        supports_by_plant.setdefault(support.plant_id, []).append(support)
        if support.plant_id not in instances_by_id:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{support.support_id} references missing plant {support.plant_id}.",
            )
        if not 2 <= len(support.tie_heights) <= 3:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{support.support_id} must have two or three tie contacts.",
            )
        for other in instances:
            if other.plant_id == support.plant_id:
                continue
            clearance = math.hypot(
                support.position[0] - other.position[0],
                support.position[1] - other.position[1],
            ) - support.radius - other.collision_proxy.get("base_radius", 0.1)
            if clearance < 0.035:
                collision = {
                    "type": "stake_to_foreign_base_collision",
                    "support_id": support.support_id,
                    "plant_id": other.plant_id,
                    "clearance": round(clearance, 4),
                }
                physical_collisions.append(collision)
                _warn(
                    warnings,
                    "geometric_collision",
                    f"{support.support_id} intersects the base of {other.plant_id}.",
                )

    uses_continuous_support = (
        scene.support_system is not None
        and scene.support_system.enabled
        and scene.support_system.mode == "continuous_row_trellis"
    )
    for instance in instances:
        if (
            not uses_continuous_support
            and len(supports_by_plant.get(instance.plant_id, [])) != 1
        ):
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{instance.plant_id} must have exactly one cultivation support.",
            )
    if uses_continuous_support:
        system = scene.support_system
        assert system is not None
        if not system.posts or not system.lines:
            _warn(
                warnings,
                "out_of_range_morphology",
                "Continuous trellis must contain posts and lines.",
            )
        known_lines = {item.id for item in system.lines}
        for tie in system.ties:
            if tie.plant_id not in instances_by_id:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{tie.id} references missing plant {tie.plant_id}.",
                )
            if tie.support_line_id not in known_lines:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{tie.id} references missing line {tie.support_line_id}.",
                )

    scene_warnings = scene.metadata.get("unresolved_warnings", [])
    for message in scene_warnings:
        _warn(warnings, "out_of_range_morphology", message)

    for geometry_report in scene.metadata.get("geometry_reports", []):
        for collision in geometry_report.get("physical_collisions", []):
            enriched = {"plant_id": geometry_report.get("plant_id"), **collision}
            physical_collisions.append(enriched)
            _warn(
                warnings,
                "geometric_collision",
                f"{geometry_report.get('plant_id')} has unresolved organ collision: {collision.get('type')}.",
            )
        for occlusion in geometry_report.get("visual_occlusions", []):
            visual_occlusions.append(
                {"plant_id": geometry_report.get("plant_id"), **occlusion}
            )

    adaptation = scene.metadata.get("cultivation_adaptation", {})
    for collision in adaptation.get("physical_collisions", []):
        physical_collisions.append(collision)
        _warn(
            warnings,
            "geometric_collision",
            f"Cultivation adaptation reported collision: {collision.get('type')}.",
        )
    mesh_audit = scene.metadata.get("mesh_collision_audit", {})
    for collision in mesh_audit.get("physical_collisions", []):
        physical_collisions.append(collision)
        _warn(
            warnings,
            "geometric_collision",
            f"Evaluated Blender meshes intersect: {collision.get('object_a')} / {collision.get('object_b')}.",
        )
    return {
        "scene_id": scene.scene_id,
        "status": "valid_with_warnings" if warnings else "valid",
        "summary": {
            "plant_count": len(instances),
            "collision_policy": scene.metadata.get("collision_policy"),
            "physical_collision_count": len(physical_collisions),
            "visual_occlusion_count": len(visual_occlusions),
            "placement_retries": scene.metadata.get("placement_retries", 0),
            "support_count": len(scene.supports),
            "support_system_mode": (
                scene.support_system.mode
                if scene.support_system is not None
                else "individual_stakes"
            ),
            "intentional_contact_count": (
                len(scene.support_system.contacts)
                if scene.support_system is not None
                else 0
            ),
            "adapted_axis_count": adaptation.get("adapted_axis_count", 0),
        },
        "physical_collisions": physical_collisions,
        "visual_occlusions": visual_occlusions,
        "warnings": warnings,
    }


def _validate_axis(axis: Axis, warnings: list[dict[str, str]]) -> int:
    parent_radius = _max_axis_radius(axis)
    node_count = 0
    for node in axis.nodes:
        node_count += 1
        _validate_node(node, axis, warnings)

    for child_axis in axis.child_axes:
        if child_axis.order != axis.order + 1:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{child_axis.id} has order {child_axis.order}, expected {axis.order + 1}.",
            )
        child_radius = _max_axis_radius(child_axis)
        if child_radius is not None and parent_radius is not None:
            if child_radius >= parent_radius:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{child_axis.id} radius does not decrease relative to {axis.id}.",
                )
        node_count += _validate_axis(child_axis, warnings)
    return node_count


def _validate_leaf_light_response(
    plant: Plant,
    warnings: list[dict[str, str]],
    *,
    required: bool,
) -> dict[str, Any]:
    strata = {"lower": 0, "middle": 0, "upper": 0}
    interception: list[float] = []
    coverage: list[float] = []
    intraspecific: list[float] = []
    interspecific: list[float] = []

    def visit(axis: Axis) -> None:
        for node in axis.nodes:
            leaf = node.leaf
            if leaf is None:
                continue
            if leaf.canopy_stratum in strata:
                strata[leaf.canopy_stratum] += 1
            elif required:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{leaf.id} has no valid lower/middle/upper canopy stratum.",
                )
            values = (
                (
                    "daily_light_interception_proxy",
                    leaf.daily_light_interception_proxy,
                    interception,
                ),
                (
                    "projected_coverage_gain",
                    leaf.projected_coverage_gain,
                    coverage,
                ),
                (
                    "intraspecific_shading_fraction",
                    leaf.intraspecific_shading_fraction,
                    intraspecific,
                ),
                (
                    "interspecific_shading_fraction",
                    leaf.interspecific_shading_fraction,
                    interspecific,
                ),
            )
            for name, value, output in values:
                if value is None:
                    if required and name in {
                        "daily_light_interception_proxy",
                        "projected_coverage_gain",
                    }:
                        _warn(
                            warnings,
                            "out_of_range_morphology",
                            f"{leaf.id} is missing {name}.",
                        )
                    continue
                numeric = float(value)
                if not 0.0 <= numeric <= 1.0:
                    _warn(
                        warnings,
                        "out_of_range_morphology",
                        f"{leaf.id} has {name}={numeric}, expected 0..1.",
                    )
                output.append(numeric)
        for child in axis.child_axes:
            visit(child)

    for root in plant.axes:
        visit(root)
    return {
        "assigned_leaf_count": sum(strata.values()),
        "strata": strata,
        "mean_daily_light_interception_proxy": _mean(interception),
        "mean_projected_coverage_gain": _mean(coverage),
        "mean_intraspecific_shading_fraction": _mean(intraspecific),
        "mean_interspecific_shading_fraction": _mean(interspecific),
        "interpretation": "engineering proxy, not physical absorption",
    }


def _validate_node(node: Node, axis: Axis, warnings: list[dict[str, str]]) -> None:
    if node.order != axis.order:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.id} order {node.order} does not match axis order {axis.order}.",
        )

    if node.leaf is None:
        _warn(warnings, "out_of_range_morphology", f"{node.id} has no leaf.")
    elif node.leaf.node_id != node.id:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.leaf.id} is attached to {node.leaf.node_id}, expected {node.id}.",
        )
    elif abs(node.leaf.curl) > 0.08 or abs(node.leaf.twist_deg) > 4.0:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.leaf.id} exceeds the calibrated near-planar leaf range.",
        )

    if node.axillary_bud is None:
        _warn(warnings, "out_of_range_morphology", f"{node.id} has no axillary bud.")
    elif node.axillary_bud.node_id != node.id:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.axillary_bud.id} is attached to {node.axillary_bud.node_id}, expected {node.id}.",
        )

    if node.reproductive_unit is not None:
        _validate_reproductive_unit(node, warnings)


def _validate_reproductive_unit(
    node: Node, warnings: list[dict[str, str]]
) -> None:
    unit = node.reproductive_unit
    if unit is None:
        return
    if unit.node_id != node.id:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{unit.id} is attached to {unit.node_id}, expected node {node.id}.",
        )
    if unit.pedicel.node_id != node.id or unit.pedicel.connects_to != unit.id:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{unit.pedicel.id} does not connect node {node.id} to {unit.id}.",
        )
    fruit_stages = {
        "young_fruit_with_calyx",
        "mature_fruit_with_calyx",
        "exposed_fruit",
    }
    if unit.stage in fruit_stages and unit.fruit is None:
        _warn(warnings, "out_of_range_morphology", f"{unit.id} has no fruit.")
    if unit.stage in fruit_stages and unit.calyx is None:
        _warn(warnings, "out_of_range_morphology", f"{unit.id} has no calyx.")
    if unit.fruit is not None and unit.calyx is None and unit.stage != "exposed_fruit":
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{unit.id} has fruit without calyx outside an explicitly exposed stage.",
        )
    if unit.calyx is not None:
        _validate_calyx(node, warnings)


def _validate_calyx(node: Node, warnings: list[dict[str, str]]) -> None:
    unit = node.reproductive_unit
    if unit is None or unit.calyx is None:
        return

    calyx = unit.calyx
    if unit.pedicel.connects_to != unit.id:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} is not connected to its reproductive unit through the pedicel.",
        )
    if not 5 <= calyx.ribs <= 10:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} has {calyx.ribs} main ribs; expected 5 to 10.",
        )
    if not 0.0 <= calyx.openness <= 0.75:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} openness {calyx.openness} is outside the early valid range.",
        )
    if calyx.openness > 0.0:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} is open, but the current iteration requires closed capachos.",
        )
    if not 0.75 <= calyx.inflation <= 1.45:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} inflation {calyx.inflation} is outside the early valid range.",
        )
    aspect_ratio = calyx.length_cm / max(calyx.radius_cm * 2.0, 1e-6)
    if not 1.15 <= aspect_ratio <= 1.55:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} height/width ratio {aspect_ratio:.3f} is outside 1.15..1.55.",
        )
    if calyx.profile != "lantern_squash":
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} uses profile {calyx.profile!r}, expected lantern_squash.",
        )
    expected_prefix = {
        "inflated_green": "calyx_green_v",
        "transitioning_yellow": "calyx_transition_v",
        "straw_yellow": "calyx_straw_v",
        "dry_deteriorated": "calyx_dry_v",
    }.get(calyx.state)
    if expected_prefix and not calyx.texture_variant.startswith(expected_prefix):
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{calyx.id} texture variant {calyx.texture_variant!r} conflicts with {calyx.state}.",
        )
    if unit.fruit is not None:
        fruit_diameter = unit.fruit.radius_cm * 2.0
        inner_width = calyx.radius_cm * calyx.inflation * 2.0
        if fruit_diameter > inner_width * 0.92 or fruit_diameter > calyx.length_cm * 0.92:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{unit.fruit.id} is too large for {calyx.id}; fruit may sit outside the capacho.",
            )
    if unit.fruit_visibility == "hidden" and calyx.openness > 0.0:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{unit.id} marks fruit as hidden but calyx is open.",
        )
    if unit.fruit_visibility not in {None, "hidden"} and calyx.openness <= 0.0:
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{unit.id} has fruit visibility {unit.fruit_visibility} with a closed capacho.",
        )


def _count_axes(axis: Axis) -> int:
    return 1 + sum(_count_axes(child) for child in axis.child_axes)


def _validate_stem_color_coherence(
    axis: Axis,
    condition: str,
    warnings: list[dict[str, str]],
) -> None:
    for internode in axis.internodes:
        if condition == "healthy" and internode.pigmentation >= 0.52:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{internode.id} is brown-range inside a healthy plant.",
            )
        elif condition == "drying" and internode.pigmentation < 0.52:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{internode.id} is healthy-green inside a drying plant.",
            )
    for child in axis.child_axes:
        _validate_stem_color_coherence(child, condition, warnings)


def _count_reproductive_units(axis: Axis) -> int:
    own = sum(1 for node in axis.nodes if node.reproductive_unit is not None)
    return own + sum(_count_reproductive_units(child) for child in axis.child_axes)


def _count_fruiting_units(axis: Axis) -> int:
    own = sum(
        1
        for node in axis.nodes
        if node.reproductive_unit is not None
        and node.reproductive_unit.fruit is not None
        and node.reproductive_unit.calyx is not None
    )
    return own + sum(_count_fruiting_units(child) for child in axis.child_axes)


def _count_flowers(axis: Axis) -> int:
    own = sum(
        1
        for node in axis.nodes
        if node.reproductive_unit is not None
        and node.reproductive_unit.stage == "flower"
    )
    return own + sum(_count_flowers(child) for child in axis.child_axes)


def _collect_calyx_states(axis: Axis, counts: dict[str, int]) -> None:
    for node in axis.nodes:
        unit = node.reproductive_unit
        if unit is not None and unit.calyx is not None:
            counts[unit.calyx.state] = counts.get(unit.calyx.state, 0) + 1
    for child in axis.child_axes:
        _collect_calyx_states(child, counts)


def _validate_phenology_coherence(
    plant: Plant,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    model = str(plant.metadata.get("phenology_model", "legacy_independent"))
    if model != "literature_cohort_v1":
        return {
            "status": "legacy_not_evaluated",
            "model": model,
            "evaluated_unit_count": 0,
            "severe_inversion_count": 0,
        }
    units = []
    for axis in plant.axes:
        units.extend(_phenology_units(axis))
    stage_index = {
        "flower": 0,
        "young_fruit_with_calyx": 1,
        "mature_fruit_with_calyx": 2,
        "exposed_fruit": 3,
    }
    severe_inversions = 0
    ordered = sorted(
        units,
        key=lambda item: (
            -float(item.ontogenetic_rank or 0.0),
            item.id,
        ),
    )
    for older, younger in zip(ordered, ordered[1:]):
        if stage_index.get(older.stage, 0) + 1 < stage_index.get(younger.stage, 0):
            severe_inversions += 1
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{older.id} and {younger.id} contain a phenology inversion greater than one stage.",
            )
    for unit in units:
        if unit.stage == "flower":
            if unit.estimated_days_after_anthesis is not None or unit.bbch_principal_stage != 6:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{unit.id} flower has inconsistent BBCH/DAA metadata.",
                )
            continue
        if unit.estimated_days_after_anthesis is None or unit.calyx is None:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{unit.id} fruiting cohort lacks DAA or calyx metadata.",
            )
            continue
        daa = float(unit.estimated_days_after_anthesis)
        progress = max(0.0, min(1.0, (daa - 45.0) / 45.0))
        expected_area = 1.0 - 0.14 * progress
        expected_circularity = 0.59 - 0.20 * progress
        expected_turgor = 1.0 - 0.24 * progress
        if abs(unit.calyx.projected_area_scale - expected_area) > 0.015:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{unit.calyx.id} projected area is inconsistent with its maturity progress.",
            )
        if (
            unit.calyx.circularity_target is None
            or abs(unit.calyx.circularity_target - expected_circularity) > 0.015
        ):
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{unit.calyx.id} circularity target is inconsistent with its maturity progress.",
            )
        if abs(unit.calyx.turgor - expected_turgor) > 0.015:
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{unit.calyx.id} turgor is inconsistent with its maturity progress.",
            )

    snapshot = plant.metadata.get("phenology_snapshot") or {}
    threshold = snapshot.get("first_bifurcation_node")
    if threshold is not None:
        for main_axis in plant.axes:
            positions = {node.id: node.position_index + 1 for node in main_axis.nodes}
            for child in main_axis.child_axes:
                parent_position = positions.get(str(child.parent_node_id))
                if parent_position is not None and parent_position < int(threshold):
                    _warn(
                        warnings,
                        "out_of_range_morphology",
                        f"{child.id} bifurcates at node {parent_position}, before literature threshold {threshold}.",
                    )
    return {
        "status": "valid" if severe_inversions == 0 else "invalid",
        "model": model,
        "evaluated_unit_count": len(units),
        "severe_inversion_count": severe_inversions,
        "first_bifurcation_node": threshold,
    }


def _phenology_units(axis: Axis) -> list[Any]:
    units = [
        node.reproductive_unit
        for node in axis.nodes
        if node.reproductive_unit is not None
    ]
    for child in axis.child_axes:
        units.extend(_phenology_units(child))
    return units


def _max_axis_radius(axis: Axis) -> float | None:
    if not axis.internodes:
        return None
    return max(internode.radius_cm for internode in axis.internodes)


def _validate_individual_scope(
    plant: Plant, params: dict[str, Any], warnings: list[dict[str, str]]
) -> None:
    max_ratio = params["individual_scope"]["max_width_to_height_ratio"]["value"]
    height = sum(_axis_length(axis) for axis in plant.axes)
    lateral_span = sum(_estimated_lateral_span(axis) for axis in plant.axes)
    if height <= 0.0:
        return
    ratio = lateral_span / height
    if ratio > max_ratio:
        _warn(
            warnings,
            "out_of_range_morphology",
            "Individual plant lateral span is high; use CultivationScene neighbors instead of widening one plant.",
        )


def _axis_length(axis: Axis) -> float:
    own = sum(internode.length_cm for internode in axis.internodes)
    child_heights = [_axis_length(child) for child in axis.child_axes]
    return own + (max(child_heights) if child_heights else 0.0)


def _estimated_lateral_span(axis: Axis) -> float:
    span = 0.0
    for child in axis.child_axes:
        child_length = sum(internode.length_cm for internode in child.internodes)
        span += child_length * abs(math.sin(math.radians(child.branch_angle_deg)))
        span += _estimated_lateral_span(child)
    return span


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 6)


def _warn(warnings: list[dict[str, str]], category: str, message: str) -> None:
    warnings.append({"category": category, "message": message})
