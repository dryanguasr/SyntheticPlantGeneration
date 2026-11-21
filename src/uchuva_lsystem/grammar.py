"""Preliminary morphology generation for uchuva.

This is a procedural first step, not a full formal string-rewriting L-System.
It preserves the conceptual grammar:

Apex -> Internode + Node + Apex
Node -> Leaf + AxillaryBud
AxillaryBud -> DormantBud | Branch | ReproductiveUnit
"""

from __future__ import annotations

import random
import math
from copy import deepcopy
from typing import Any

from .morphology import (
    AxillaryBud,
    Axis,
    Calyx,
    Fruit,
    Internode,
    Leaf,
    Node,
    Pedicel,
    Plant,
    ReproductiveUnit,
)
from .parameters import (
    get_initial_parameters,
    get_morphology_parameters,
    get_phenology_profile,
    leaf_length_factor,
)
from .phenology import (
    PHENOLOGY_MODELS,
    build_phenology_snapshot,
    coherent_stage_sequence,
    reproductive_phenology,
)
from .provenance import (
    audit_parameter_provenance,
    normalise_parameter_provenance,
    parameter_snapshot_sha256,
    provenance_for_status,
)

SCRIPT_VERSION = "0.11.0-literature-cohort-maturity"


def reproductive_load_policy(params: dict[str, Any]) -> str:
    """Missing policy denotes the historical contract, never a camera target."""
    policy = params.get("reproduction", {}).get("load_policy", {}).get(
        "value", "legacy_fruiting_range"
    )
    if policy not in {"architecture_driven", "legacy_fruiting_range"}:
        raise ValueError(f"Unknown reproductive load policy: {policy}")
    return policy


def reproductive_counts(plant_or_axis: Plant | Axis) -> dict[str, int]:
    """Count morphology organs; visibility and annotation are separate domains."""
    counts = dict(reproductive_units=0, flowers=0, fruits=0, fruits_with_calyx=0)
    roots = plant_or_axis.axes if isinstance(plant_or_axis, Plant) else [plant_or_axis]
    def visit(axis: Axis) -> None:
        for node in axis.nodes:
            unit = node.reproductive_unit
            if unit is None:
                continue
            counts["reproductive_units"] += 1
            counts["flowers"] += int(unit.stage == "flower")
            counts["fruits"] += int(unit.fruit is not None)
            counts["fruits_with_calyx"] += int(unit.fruit is not None and unit.calyx is not None)
        for child in axis.child_axes:
            visit(child)
    for root in roots:
        visit(root)
    return counts


def record_reproductive_counts(plant: Plant, stage: str) -> dict[str, int]:
    """Refresh stage-specific counts without imposing a reproductive quota."""
    counts = reproductive_counts(plant)
    plant.metadata.setdefault("reproductive_counts_by_stage", {})[stage] = counts
    plant.metadata["model_stage"] = stage
    return counts


def enforce_parent_radius_continuity(plant: Plant, *, stage: str) -> list[dict[str, Any]]:
    """Keep child axes no thicker than the parent at their actual insertion."""
    adjustments: list[dict[str, Any]] = []
    def visit(axis: Axis) -> None:
        at_node = {node.id: internode.radius_cm
                   for node, internode in zip(axis.nodes, axis.internodes)}
        for child in axis.child_axes:
            if child.parent_node_id not in at_node:
                raise ValueError(f"Missing parent insertion for {child.id}")
            limit = at_node[child.parent_node_id]
            largest = max((part.radius_cm for part in child.internodes), default=0.0)
            if largest > limit:
                scale = limit / largest
                for part in child.internodes:
                    proposed = part.radius_cm
                    part.radius_cm = min(limit, round(proposed * scale, 6))
                    record = dict(original_radius_cm=proposed, final_radius_cm=part.radius_cm,
                                  parent_node_id=child.parent_node_id, parent_radius_cm=limit,
                                  scale_factor=scale, stage=stage,
                                  policy="child_axis_max_at_most_parent_insertion")
                    part.provenance["radius_continuity"] = record
                    adjustments.append(dict(internode_id=part.id, **record))
            visit(child)
    for root in plant.axes:
        visit(root)
    plant.metadata.setdefault("radius_continuity_adjustments", []).extend(adjustments)
    return adjustments


def generate_morphology_tree(
    seed: int,
    params: dict[str, Any] | None = None,
    phenology_profile: str | None = None,
    *,
    condition: str = "healthy",
    preset_name: str | None = None,
    phenology_model: str = "legacy_independent",
    resolve_growth: bool = True,
    reproductive_space_plan: dict[str, Any] | None = None,
    spatial_admission_plan: dict[str, Any] | None = None,
) -> Plant:
    """Generate a small, reproducible morphology tree for early validation."""
    if condition not in {"healthy", "drying"}:
        raise ValueError("condition must be 'healthy' or 'drying'")
    if params is not None and preset_name is not None:
        raise ValueError("Pass either params or preset_name, not both")
    if phenology_model not in PHENOLOGY_MODELS:
        raise ValueError(
            f"phenology_model must be one of {', '.join(PHENOLOGY_MODELS)}"
        )
    active_params = (
        deepcopy(params)
        if params is not None
        else (
            get_morphology_parameters(preset_name)
            if preset_name is not None
            else get_initial_parameters()
        )
    )
    active_profile_name = phenology_profile or "mixed_balanced"
    load_policy = reproductive_load_policy(active_params)
    branch_activation = active_params["branching"].get("activation_policy", {}).get("value")
    if branch_activation not in {None, "legacy_reproductive_gate", "vegetative_onset_independent_v1"}:
        raise ValueError(f"Unknown branch activation policy: {branch_activation}")
    if branch_activation == "vegetative_onset_independent_v1":
        if load_policy != "architecture_driven" or active_params.get("growth", {}).get("mode", {}).get("value") != "incremental_budgeted":
            raise ValueError("Independent vegetative activation requires architecture_driven incremental_budgeted generation")
        first_node = active_params["branching"].get("vegetative_first_main_node", {}).get("value")
        main_nodes = int(active_params["axis"]["main_node_count"]["value"])
        if isinstance(first_node, bool) or not isinstance(first_node, int) or not 2 <= first_node < main_nodes:
            raise ValueError("Invalid vegetative first main node: require a one-based integer from 2 through main_node_count-1")
    leaf_pose_range = active_params["leaf"].get("insertion_angle_deg_range")
    leaf_pose_frame = active_params["leaf"].get("insertion_frame", {}).get("value")
    if leaf_pose_frame not in {None, "orthogonal_local_v1", "local_cone_v2"}:
        raise ValueError(f"Unknown leaf insertion frame: {leaf_pose_frame}")
    if leaf_pose_range is not None:
        low, high = float(leaf_pose_range["min"]), float(leaf_pose_range["max"])
        if not (math.isfinite(low) and math.isfinite(high) and 0 <= low <= high <= 180):
            raise ValueError("Invalid effective leaf insertion angle range")
    branch_frame = active_params["branching"].get("frame", {}).get("value")
    if branch_frame not in {None, "local_cone_v1"}:
        raise ValueError(f"Unknown branch frame: {branch_frame}")
    if branch_frame is not None:
        table = active_params["branching"].get("branch_angle_deg_by_order", {})
        for order in range(1, int(active_params["axis"]["max_branch_order"]["value"])+1):
            bounds = table.get(str(order))
            if bounds is None:
                raise ValueError(f"Missing branch angle range for enabled child order {order}")
            low, high = float(bounds["min"]), float(bounds["max"])
            if not (math.isfinite(low) and math.isfinite(high) and 0 <= low <= high <= 180):
                raise ValueError(f"Invalid branch angle range for child order {order}")
    leaf_length_factor(active_params, 0, 1.0)  # Reject unknown opt-in policy before RNG or generation.
    if load_policy == "architecture_driven":
        radii = active_params["internode"]["radius_cm_by_order"]
        missing = [order for order in range(int(active_params["axis"]["max_branch_order"]["value"]) + 1)
                   if str(order) not in radii]
        if missing:
            raise ValueError(f"Missing radius parameters for enabled branch orders: {missing}")
        for order in range(int(active_params["axis"]["max_branch_order"]["value"]) + 1):
            bounds = radii[str(order)]
            low, high = float(bounds["min"]), float(bounds["max"])
            if not (math.isfinite(low) and math.isfinite(high) and 0 < low <= high):
                raise ValueError(f"Invalid radius range for branch order {order}")
    if phenology_profile is not None:
        profile = get_phenology_profile(active_profile_name)
        active_params["reproduction"]["stage_weights"].update(
            profile["stage_weights"]
        )
    rng = random.Random(seed)
    phenology_rng = random.Random(seed + 910_117)
    phenology_snapshot = None
    if phenology_model == "literature_cohort_v1":
        phenology_snapshot = build_phenology_snapshot(
            active_profile_name,
            phenology_rng,
            rendered_main_axis_nodes=int(
                active_params["axis"]["main_node_count"]["value"]
            ),
        )
        active_params["reproduction"]["first_bifurcation_node"] = {
            "value": phenology_snapshot.first_bifurcation_node,
            "status": "literature_reported_range_site_bounded",
            "note": "Ramirez et al. 2013 reports the first bifurcation near nodes 8--12.",
            "provenance": provenance_for_status(
                "literature_reported_range_site_bounded",
                method="literature_bounded_sample_first_bifurcation_local_validation_pending",
                source_ids=["ramirez_2013_bbch_physalis"],
            ).to_dict(),
        }
        if branch_activation == "vegetative_onset_independent_v1":
            active_params["reproduction"]["first_bifurcation_node"]["model_application"] = {
                "status": "engineering_heuristic",
                "method": "main_axis_reproductive_eligibility_separate_from_vegetative_lateral_activation",
                "note": "The sampled literature landmark is retained; treating it separately from adult vegetative axillary branches is a model hypothesis, not a new claim about the source.",
            }
    stem_color_family = (
        rng.choice(("green", "dark_green"))
        if condition == "healthy"
        else rng.choice(("drying_olive", "drying_brown"))
    )
    stem_base_pigmentation = {
        "green": 0.22,
        "dark_green": 0.38,
        "drying_olive": 0.68,
        "drying_brown": 0.82,
    }[stem_color_family]

    main_axis = _generate_axis(
        rng=rng,
        params=active_params,
        order=0,
        axis_index=0,
        node_count=active_params["axis"]["main_node_count"]["value"],
        parent_node_id=None,
        branch_angle_deg=0.0,
        azimuth_deg=rng.uniform(0.0, 360.0),
        stem_base_pigmentation=stem_base_pigmentation,
        axis_vigor=1.0,
        development_step=0,
    )
    if load_policy == "architecture_driven":
        normalization_report = dict(policy=load_policy, applied=False,
                                    legacy_range_active=False,
                                    counts_before_cohorts=reproductive_counts(main_axis))
    else:
        normalization_report = _enforce_reproductive_unit_target(main_axis, rng, active_params)
        normalization_report["policy"] = "legacy_fruiting_range"
        normalization_report["count_stage"] = "before_cohorts"
    cohort_report: dict[str, Any] = {
        "model": "legacy_independent",
        "applied": False,
    }
    if phenology_model == "literature_cohort_v1":
        cohort_report = _apply_literature_cohorts(
            main_axis,
            rng,
            active_params,
        )

    plant = Plant(
        species="Physalis peruviana",
        common_name="uchuva",
        seed=seed,
        script_version=SCRIPT_VERSION,
        parameter_preset=active_params.get(
            "preset_name", "initial_migration_manual_guess"
        ),
        condition=condition,
        axes=[main_axis],
        metadata={
            "model_stage": "initial_migration",
            "architecture": "l_system_morphology_tree_with_blender_preview",
            "axiom": "Apex(order=0, age=0)",
            "conceptual_rules": [
                "Apex -> Internode + Node + Apex",
                "Node -> Leaf + AxillaryBud",
                "AxillaryBud -> DormantBud | Branch | ReproductiveUnit",
                "ReproductiveUnit -> Flower | YoungFruitWithCalyx | MatureFruitWithCalyx | ExposedFruit",
            ],
            "calyx_visibility_policy": (
                "Closed-calyx iteration: fruit remains represented in the "
                "morphology tree but is hidden by closed capachos in Blender."
            ),
            "implementation_note": (
                "The first implementation is procedural, but each generated "
                "organ is attached to an axis node according to the conceptual "
                "L-System grammar."
            ),
            "reproductive_normalization": normalization_report,
            "phenology_profile": active_profile_name,
            "phenology_model": phenology_model,
            "phenology_snapshot": (
                phenology_snapshot.to_dict()
                if phenology_snapshot is not None
                else None
            ),
            "reproductive_cohorts": cohort_report,
            "condition": condition,
            "stem_color_family": stem_color_family,
            "stem_color_policy": "one_family_per_plant_with_small_internode_delta",
            "growth_mode": active_params.get("growth", {})
            .get("mode", {})
            .get("value", "legacy_recursive"),
            "light_competition": {
                "enabled": active_params.get("light_competition", {})
                .get("enabled", {})
                .get("value", False),
                "model": active_params.get("light_competition", {}).get(
                    "model",
                    "disabled",
                ),
                "parameter_status": active_params.get(
                    "light_competition",
                    {},
                ).get("status", "implementation_constraint"),
            },
            "parameter_provenance_audit": audit_parameter_provenance(active_params),
        },
    )
    if load_policy == "architecture_driven":
        active_params = normalise_parameter_provenance(active_params)
        plant.script_version += "+audit-morphology/2"
        plant.metadata.update(
            morphology_contract_version="audit-morphology/2",
            reproductive_load_policy=load_policy,
            effective_parameters=deepcopy(active_params),
            effective_parameters_sha256=parameter_snapshot_sha256(active_params),
            parameter_provenance_audit=audit_parameter_provenance(active_params),
        )
        enforce_parent_radius_continuity(plant, stage="generated")
        record_reproductive_counts(plant, "generated")
    if branch_activation == "vegetative_onset_independent_v1":
        plant.metadata["vegetative_branching_contract"] = {
            "policy": branch_activation,
            "first_eligible_main_node": active_params["branching"]["vegetative_first_main_node"]["value"],
            "reproductive_landmark_node": active_params["reproduction"].get("first_bifurcation_node", {}).get("value"),
            "status": "engineering_heuristic",
            "interpretation": "vegetative_axillary_branch_not_reproductive_transition",
            "branch_count_target": None,
        }
    from .reproductive_orientation import assign_reproductive_orientation
    assign_reproductive_orientation(plant, active_params)
    if reproductive_space_plan is not None and spatial_admission_plan is not None:
        raise ValueError('Use only one explicit spatial admission contract')
    if spatial_admission_plan is not None:
        from .spatial_admission import apply_plan
        apply_plan(plant, spatial_admission_plan)
        plant.script_version += '+spatial-admission/2'
    if reproductive_space_plan is not None:
        from .reproductive_space import apply_admission_plan
        apply_admission_plan(plant, reproductive_space_plan)
    nodal_policy = active_params.get('growth',{}).get('nodal_repulsion')
    if nodal_policy:
        if nodal_policy['value'] != 'bottom_up_lower_first_v1':
            raise ValueError('Unknown nodal repulsion policy')
        for key,value in [('branch_rotation_limit_deg',35.),('leaf_rotation_limit_deg',120.),('pedicel_rotation_limit_deg',75.)]:
            if nodal_policy.get(key)!=value:raise ValueError(f'{key} is fixed by the versioned nodal implementation')
        plant.script_version += '+nodal-growth/1'
        plant.metadata['nodal_repulsion_requested'] = deepcopy(nodal_policy)
        if resolve_growth:
            from .nodal_repulsion import resolve_nodal_repulsion
            resolve_nodal_repulsion(plant,sweeps=nodal_policy['sweeps'],step_deg=nodal_policy['step_deg'],
                max_seconds=nodal_policy['max_active_seconds'],margin=nodal_policy['proxy_margin_bu'])
            record_reproductive_counts(plant,'adapted')
        else:
            plant.metadata['nodal_repulsion_pending'] = True
    return plant


def _generate_axis(
    rng: random.Random,
    params: dict[str, Any],
    order: int,
    axis_index: int,
    node_count: int,
    parent_node_id: str | None,
    branch_angle_deg: float,
    azimuth_deg: float,
    stem_base_pigmentation: float,
    axis_id: str | None = None,
    axis_vigor: float | None = None,
    development_step: int = 0,
) -> Axis:
    growth = params.get("growth", {})
    growth_mode = growth.get("mode", {}).get("value", "legacy_recursive")
    is_budgeted = growth_mode == "incremental_budgeted"
    vigor = (
        axis_vigor
        if axis_vigor is not None
        else max(0.35, 1.0 - 0.25 * order)
    )
    budget = 0.0
    maximum_internodes = node_count
    noise_phase = 0.0
    if is_budgeted:
        budget_ranges = growth.get("length_budget_cm_by_order", {})
        budget_range = budget_ranges.get(
            str(order),
            budget_ranges.get("3", {"min": 7.0, "max": 16.0}),
        )
        budget = _uniform_from_range(rng, budget_range) * max(0.55, vigor)
        maximum_internodes = int(
            growth.get("max_internodes_by_order", {})
            .get(str(order), {"value": node_count})
            .get("value", node_count)
        )
        node_count = min(node_count, maximum_internodes)
        noise_phase = rng.uniform(0.0, math.tau)
    axis = Axis(
        id=axis_id or f"axis_{order}_{axis_index}",
        order=order,
        parent_node_id=parent_node_id,
        branch_angle_deg=round(branch_angle_deg, 2),
        azimuth_deg=round(azimuth_deg % 360.0, 2),
        apex_age=node_count,
        vigor=round(vigor, 4),
        growth_budget_length_cm=round(budget, 4),
        remaining_budget_length_cm=round(budget, 4),
        max_internodes=maximum_internodes,
        development_step=development_step,
        correlated_noise_phase=round(noise_phase, 6),
        provenance=provenance_for_status(
            "engineering_heuristic" if is_budgeted else "manual_initial_guess",
            method="budgeted_axis_generation" if is_budgeted else "legacy_recursive_axis",
        ).to_dict(),
    )
    if order > 0 and params["branching"].get("frame", {}).get("value") == "local_cone_v1":
        axis.provenance["branch_frame_v140"] = True
        axis.provenance["branch_direction_frame"] = "local_cone_v1"
        axis.provenance["branch_angle_sampling"] = {
            "child_order": order,
            "range_min_deg": params["branching"]["branch_angle_deg_by_order"][str(order)]["min"],
            "range_max_deg": params["branching"]["branch_angle_deg_by_order"][str(order)]["max"],
            "status": "engineering_heuristic",
        }

    child_axis_index = 0
    used_length = 0.0
    for position_index in range(node_count):
        remaining_budget = budget - used_length if is_budgeted else math.inf
        minimum_length = float(params["internode"]["length_cm_range"]["min"])
        if is_budgeted and position_index >= 2 and remaining_budget < minimum_length * 0.72:
            break
        node_id = f"{axis.id}_node_{position_index}"
        internode = _make_internode(
            rng,
            params,
            axis.id,
            order,
            position_index,
            stem_base_pigmentation,
            axis_vigor=vigor,
            axis_node_count=node_count,
            noise_phase=noise_phase,
            budgeted=is_budgeted,
        )
        if is_budgeted and internode.length_cm > remaining_budget:
            internode.length_cm = round(max(0.6, remaining_budget), 3)
        used_length += internode.length_cm
        node = _make_node(
            rng,
            params,
            node_id,
            order,
            position_index,
            axis.azimuth_deg,
            axis_vigor=vigor,
            budgeted=is_budgeted,
        )

        if _can_branch(
            params,
            order,
            position_index,
            node_count,
            rng,
            axis_vigor=vigor,
        ):
            child_axis_id = f"{axis.id}_branch_{child_axis_index}"
            child_azimuth = (
                node.leaf.azimuth_deg + rng.uniform(-18.0, 18.0)
            ) % 360.0
            branch_angle_range = params["branching"].get("branch_angle_deg_by_order", {}).get(
                str(order+1), params["branching"]["branch_angle_deg_range"])
            child_branch_angle = _uniform_from_range(rng, branch_angle_range)
            node.axillary_bud.state = "branch"
            node.axillary_bud.branch_id = child_axis_id
            node.axillary_bud.decision = (
                "proposed_branch" if is_budgeted else "legacy_branch"
            )
            branch_node_count = rng.randint(
                params["axis"]["branch_node_count_range"]["min"],
                params["axis"]["branch_node_count_range"]["max"],
            )
            child_axis = _generate_axis(
                rng=rng,
                params=params,
                order=order + 1,
                axis_index=child_axis_index,
                node_count=branch_node_count,
                parent_node_id=node_id,
                branch_angle_deg=child_branch_angle,
                azimuth_deg=child_azimuth,
                stem_base_pigmentation=stem_base_pigmentation,
                axis_id=child_axis_id,
                axis_vigor=(
                    vigor
                    * float(
                        growth.get("vigor_decay_by_order", {})
                        .get("value", 0.78)
                    )
                    * rng.uniform(0.9, 1.08)
                    if is_budgeted
                    else None
                ),
                development_step=development_step + 1,
            )
            if params["branching"].get("activation_policy", {}).get("value") == "vegetative_onset_independent_v1":
                origin = {
                    "policy": "vegetative_onset_independent_v1",
                    "parent_axis_order": order,
                    "parent_node_number": position_index + 1,
                    "first_eligible_main_node": params["branching"]["vegetative_first_main_node"]["value"],
                    "reproductive_landmark_node": params["reproduction"].get("first_bifurcation_node", {}).get("value"),
                    "interpretation": "vegetative_axillary_branch_not_reproductive_transition",
                    "status": "engineering_heuristic",
                }
                child_axis.provenance["branch_origin"] = dict(origin)
                node.axillary_bud.provenance["branch_origin"] = dict(origin)
            axis.child_axes.append(child_axis)
            child_axis_index += 1
        elif _can_reproduce(params, order, position_index, rng):
            reproductive_unit = _make_reproductive_unit(
                rng, params, node_id, node.leaf.azimuth_deg
            )
            node.reproductive_unit = reproductive_unit
            node.axillary_bud.state = "reproductive"
            node.axillary_bud.reproductive_unit_id = reproductive_unit.id
            node.axillary_bud.decision = (
                "reproductive" if is_budgeted else "legacy_reproductive"
            )
        elif is_budgeted:
            node.axillary_bud.decision = "dormant"

        axis.internodes.append(internode)
        axis.nodes.append(node)

    if is_budgeted:
        axis.remaining_budget_length_cm = round(max(0.0, budget - used_length), 4)
        axis.growth_events.append(
            {
                "type": "axis_budget_consumed",
                "development_step": development_step,
                "used_length_cm": round(used_length, 4),
                "remaining_length_cm": axis.remaining_budget_length_cm,
                "internode_count": len(axis.internodes),
            }
        )
    return axis


def _make_internode(
    rng: random.Random,
    params: dict[str, Any],
    axis_id: str,
    order: int,
    position_index: int,
    stem_base_pigmentation: float,
    *,
    axis_vigor: float,
    axis_node_count: int,
    noise_phase: float,
    budgeted: bool,
) -> Internode:
    length = _uniform_from_range(rng, params["internode"]["length_cm_range"])
    if budgeted:
        order_scale = float(
            params.get("growth", {})
            .get("internode_length_scale_by_order", {})
            .get(str(order), {"value": 0.68})
            .get("value", 1.0)
        )
        age_fraction = position_index / max(axis_node_count - 1, 1)
        age_scale = 1.0 - 0.18 * age_fraction
        length *= order_scale * age_scale * max(0.65, min(1.08, axis_vigor))
    if reproductive_load_policy(params) == "architecture_driven":
        radius_range = params["internode"]["radius_cm_by_order"][str(order)]
    else:
        # Explicit compatibility branch for historical numerical baselines.
        radius_range = params["internode"]["radius_cm_by_order"].get(
            str(order), params["internode"]["radius_cm_by_order"]["1"]
        )
    radius = _uniform_from_range(rng, radius_range)
    taper_factor = 1.0
    if budgeted:
        taper_fraction = position_index / max(axis_node_count - 1, 1)
        taper_factor = max(0.52, 1.0 - 0.34 * taper_fraction)
        radius *= taper_factor
    bend_ranges = params["internode"]["bend_angle_deg_by_order"]
    bend_range = bend_ranges.get(str(order), bend_ranges["1"])
    bend_angle = _uniform_from_range(rng, bend_range)
    bend_azimuth = rng.uniform(0.0, 360.0)
    if budgeted:
        noise_strength = float(
            params.get("growth", {})
            .get("correlated_noise_strength_deg", {})
            .get("value", 5.5)
        )
        correlated = math.sin(noise_phase + position_index * 0.72)
        bend_angle = max(0.2, bend_angle + correlated * noise_strength * 0.22)
        bend_azimuth = (
            math.degrees(noise_phase)
            + position_index * 18.0
            + correlated * noise_strength
        ) % 360.0
    radius_provenance = provenance_for_status(
        str(radius_range["status"]), method="internode_range_by_branch_order",
    ).to_dict()
    if reproductive_load_policy(params) == "architecture_driven":
        radius_provenance["radius_sampling"] = {
            "taper_factor": taper_factor,
            "range_min_cm": float(radius_range["min"]),
            "range_max_cm": float(radius_range["max"]),
            "axis_node_count_at_sampling": axis_node_count,
        }
    return Internode(
        id=f"{axis_id}_internode_{position_index}",
        order=order,
        length_cm=round(length, 3),
        radius_cm=round(radius, 3),
        bend_angle_deg=round(bend_angle, 3),
        bend_azimuth_deg=round(bend_azimuth, 3),
        pigmentation=round(
            max(
                0.0,
                min(
                    1.0,
                    stem_base_pigmentation
                    + _uniform_from_range(
                        rng, params["internode"]["pigmentation_range"]
                    )
                    + min(position_index, 8) * 0.003,
                ),
            ),
            3,
        ),
        parameter_status=radius_range["status"],
        provenance=radius_provenance,
    )


def _make_node(
    rng: random.Random,
    params: dict[str, Any],
    node_id: str,
    order: int,
    position_index: int,
    axis_azimuth_deg: float,
    *,
    axis_vigor: float,
    budgeted: bool,
) -> Node:
    leaf_length = _uniform_from_range(rng, params["leaf"]["length_cm_range"])
    if budgeted:
        leaf_length *= leaf_length_factor(params, order, axis_vigor)
    leaf_width_ratio = _uniform_from_range(
        rng, params["leaf"]["width_to_length_ratio_range"]
    )
    petiole_length = _uniform_from_range(rng, params["leaf"]["petiole_length_cm_range"])
    divergence = params["phyllotaxis"]["divergence_angle_deg"]["value"]
    leaf_azimuth = (axis_azimuth_deg + position_index * divergence) % 360.0
    leaf_shape = rng.choice(params["leaf"]["shapes"]["values"])
    leaf_margin = rng.choice(params["leaf"]["margins"]["values"])
    # In the shared-canopy presets, blades should explore a broad oblique-to-
    # near-horizontal range.  The later daily-light optimiser can still tilt
    # them away from occupied projected cells, but starting every blade close
    # to the stem created an unrealistically edge-on, skeletal canopy.
    pose_range = params["leaf"].get("insertion_angle_deg_range")
    preferred_insertion = (
        _uniform_from_range(rng, pose_range) if pose_range is not None else
        rng.uniform(55.0, 86.0) if budgeted else rng.uniform(30.0, 78.0)
    )
    leaf_provenance = provenance_for_status(
        str(params["leaf"]["length_cm_range"]["status"]),
        method="leaf_scale_conditioned_by_order_and_vigor",
    ).to_dict()
    if params.get("growth", {}).get("leaf_vigor_scaling", {}).get("value") == "adult_independent":
        leaf_provenance["adult_blade_scaling"] = {
            "policy": "adult_independent", "status": "engineering_heuristic",
            "order": order, "factor": leaf_length_factor(params, order, axis_vigor),
            "base_min_cm": params["leaf"]["length_cm_range"]["min"],
            "base_max_cm": params["leaf"]["length_cm_range"]["max"],
            "axis_vigor_used_for_blade_length": False,
        }
    pose_frame = params["leaf"].get("insertion_frame", {}).get("value")
    if pose_frame is not None:
        leaf_provenance["insertion_frame"] = pose_frame
    if pose_range is not None:
        leaf_provenance["pose_sampling"] = {
            "range_min_deg": float(pose_range["min"]),
            "range_max_deg": float(pose_range["max"]),
            "status": str(pose_range["status"]),
            "method": "one_uniform_draw_in_existing_leaf_rng_position",
            "camera_dependency": "none",
        }
    leaf = Leaf(
        id=f"{node_id}_leaf",
        node_id=node_id,
        length_cm=round(leaf_length, 3),
        width_cm=round(leaf_length * leaf_width_ratio, 3),
        petiole_length_cm=round(petiole_length, 3),
        shape=leaf_shape,
        margin=leaf_margin,
        insertion_angle_deg=round(preferred_insertion, 2),
        azimuth_deg=round(leaf_azimuth, 2),
        curl=round(_uniform_from_range(rng, params["leaf"]["curl_range"]), 3),
        twist_deg=round(
            _uniform_from_range(rng, params["leaf"]["twist_deg_range"]), 3
        ),
        edge_damage=round(
            _uniform_from_range(rng, params["leaf"]["edge_damage_range"]), 3
        ),
        senescence=round(
            _uniform_from_range(rng, params["leaf"]["senescence_range"]), 3
        ),
        pubescence=round(
            _uniform_from_range(rng, params["leaf"]["pubescence_range"]), 3
        ),
        preferred_insertion_angle_deg=round(preferred_insertion, 2),
        preferred_azimuth_deg=round(leaf_azimuth, 2),
        provenance=leaf_provenance,
    )
    bud = AxillaryBud(
        id=f"{node_id}_axillary_bud",
        node_id=node_id,
        order=order,
        state="dormant",
        vigor=round(axis_vigor, 4),
        development_step=order,
        remaining_length_budget_cm=0.0,
        provenance=provenance_for_status(
            "engineering_heuristic" if budgeted else "manual_initial_guess",
            method="axillary_bud_initialisation",
        ).to_dict(),
    )
    return Node(
        id=node_id,
        order=order,
        age=position_index,
        position_index=position_index,
        leaf=leaf,
        axillary_bud=bud,
    )


def _make_reproductive_unit(
    rng: random.Random,
    params: dict[str, Any],
    node_id: str,
    axil_azimuth_deg: float,
    stage_override: str | None = None,
) -> ReproductiveUnit:
    stage = stage_override or _choose_reproductive_stage(rng, params)
    unit_id = f"{node_id}_reproductive_unit"
    pedicel_angle = _uniform_from_range(
        rng, params["reproduction"]["pedicel_angle_deg_range"]
    )
    pedicel_azimuth = (axil_azimuth_deg + rng.uniform(-12.0, 12.0)) % 360.0
    pedicel = Pedicel(
        id=f"{unit_id}_pedicel",
        node_id=node_id,
        length_cm=round(
            _uniform_from_range(rng, params["reproduction"]["pedicel_length_cm_range"]),
            3,
        ),
        angle_deg=round(pedicel_angle, 2),
        azimuth_deg=round(pedicel_azimuth, 2),
        connects_to=unit_id,
        provenance=provenance_for_status(
            str(params["reproduction"]["pedicel_length_cm_range"]["status"]),
            method="axillary_pedicel_range",
        ).to_dict(),
    )

    if stage == "flower":
        return ReproductiveUnit(id=unit_id, node_id=node_id, stage=stage, pedicel=pedicel)

    fruit_radius = _uniform_from_range(
        rng, params["reproduction"]["fruit_radius_cm_range"]
    )
    calyx_ratio = _uniform_from_range(
        rng, params["reproduction"]["calyx_to_fruit_radius_ratio_range"]
    )
    visibility = params["reproduction"]["fruit_visibility_by_stage"][stage]
    maturity = params["reproduction"]["maturity_by_stage"][stage]
    calyx_state = params["reproduction"]["calyx_state_by_stage"][stage]
    openness = params["reproduction"]["calyx_openness_by_state"][calyx_state]
    material_key = params["reproduction"]["calyx_material_by_state"][calyx_state]
    ribs = rng.randint(
        params["reproduction"]["calyx_ribs_range"]["min"],
        params["reproduction"]["calyx_ribs_range"]["max"],
    )
    inflation = _uniform_from_range(
        rng, params["reproduction"]["calyx_inflation_range"]
    )
    texture_variant, vein_contrast, apical_darkening = _choose_calyx_texture_variant(
        rng, calyx_state
    )

    fruit = Fruit(
        id=f"{unit_id}_fruit",
        radius_cm=round(fruit_radius, 3),
        maturity_stage=maturity,
        visibility=visibility,
        provenance=provenance_for_status(
            str(params["reproduction"]["fruit_radius_cm_range"]["status"]),
            method="fruit_radius_range_by_stage",
        ).to_dict(),
    )
    wrinkle_range = params["reproduction"]["calyx_wrinkle_by_state"][calyx_state]
    calyx_radius = fruit_radius * calyx_ratio * 0.82
    height_to_width = _uniform_from_range(
        rng, params["reproduction"]["calyx_height_to_width_ratio_range"]
    )
    calyx = Calyx(
        id=f"{unit_id}_calyx",
        length_cm=round(calyx_radius * 2.0 * height_to_width, 3),
        radius_cm=round(calyx_radius, 3),
        covers_fruit_fraction=_calyx_cover_fraction(stage),
        ribs=ribs,
        openness=round(openness, 3),
        inflation=round(inflation, 3),
        state=calyx_state,
        material_key=texture_variant or material_key,
        profile=params["reproduction"]["calyx_profile"]["value"],
        tip_length_ratio=round(
            _uniform_from_range(
                rng, params["reproduction"]["calyx_tip_length_ratio_range"]
            ),
            3,
        ),
        wrinkle=round(rng.uniform(float(wrinkle_range["min"]), float(wrinkle_range["max"])), 3),
        asymmetry=round(
            _uniform_from_range(rng, params["reproduction"]["calyx_asymmetry_range"]),
            3,
        ),
        pubescence=float(
            params["reproduction"]["calyx_pubescence_by_state"][calyx_state]
        ),
        texture_variant=texture_variant,
        vein_contrast=vein_contrast,
        apical_darkening=apical_darkening,
        provenance=provenance_for_status(
            str(
                params["reproduction"]["calyx_to_fruit_radius_ratio_range"][
                    "status"
                ]
            ),
            method="calyx_profile_from_fruit_scale_and_stage",
        ).to_dict(),
    )
    return ReproductiveUnit(
        id=unit_id,
        node_id=node_id,
        stage=stage,
        pedicel=pedicel,
        fruit_visibility=visibility,
        maturity=maturity,
        calyx_state=calyx_state,
        calyx=calyx,
        fruit=fruit,
    )


def _choose_calyx_texture_variant(
    rng: random.Random,
    calyx_state: str,
) -> tuple[str, float, float]:
    """Choose an auditable vascular variant correlated with calyx state."""
    variants = {
        "inflated_green": (
            ("calyx_green_v0", 0.30, 0.00),
            ("calyx_green_v1", 0.50, 0.10),
            ("calyx_green_v2", 0.72, 0.45),
            ("calyx_green_v3", 0.90, 0.75),
        ),
        "straw_yellow": (
            ("calyx_straw_v0", 0.22, 0.00),
            ("calyx_straw_v1", 0.38, 0.05),
            ("calyx_straw_v2", 0.55, 0.15),
        ),
        "dry_deteriorated": (
            ("calyx_dry_v0", 0.38, 0.00),
            ("calyx_dry_v1", 0.55, 0.08),
            ("calyx_dry_v2", 0.70, 0.18),
        ),
    }
    choices = variants.get(calyx_state, variants["inflated_green"])
    name, contrast, apical = rng.choice(choices)
    return name, contrast, apical


def _can_branch(
    params: dict[str, Any],
    order: int,
    position_index: int,
    node_count: int,
    rng: random.Random,
    *,
    axis_vigor: float = 1.0,
) -> bool:
    max_order = params["axis"]["max_branch_order"]["value"]
    if order >= max_order:
        return False
    if position_index == 0 or position_index >= node_count - 1:
        return False
    first_bifurcation = (
        params.get("reproduction", {})
        .get("first_bifurcation_node", {})
        .get("value")
    )
    independent_vegetative = params["branching"].get("activation_policy", {}).get("value") == "vegetative_onset_independent_v1"
    if order == 0 and independent_vegetative:
        if position_index + 1 < params["branching"]["vegetative_first_main_node"]["value"]:
            return False
    elif order == 0 and first_bifurcation is not None:
        if position_index + 1 < int(first_bifurcation):
            return False
    growth = params.get("growth", {})
    if growth.get("mode", {}).get("value") != "incremental_budgeted":
        return rng.random() < params["branching"]["branch_probability"]["value"]

    probability_spec = growth.get("branch_probability_by_order", {}).get(
        str(order),
        params["branching"]["branch_probability"],
    )
    probability = float(probability_spec["value"])
    apical_dominance = float(
        growth.get("apical_dominance", {}).get("value", 0.62)
    )
    position_fraction = position_index / max(node_count - 1, 1)
    basal_release = 0.72 + (1.0 - apical_dominance) * position_fraction
    vigor_factor = max(0.35, min(1.1, axis_vigor))
    return rng.random() < probability * basal_release * vigor_factor


def _can_reproduce(
    params: dict[str, Any], order: int, position_index: int, rng: random.Random
) -> bool:
    if position_index == 0:
        return False
    first_bifurcation = (
        params.get("reproduction", {})
        .get("first_bifurcation_node", {})
        .get("value")
    )
    if order == 0 and first_bifurcation is not None:
        if position_index + 1 < int(first_bifurcation):
            return False
    return rng.random() < params["reproduction"]["reproductive_probability"]["value"]


def _uniform_from_range(rng: random.Random, range_spec: dict[str, Any]) -> float:
    return rng.uniform(float(range_spec["min"]), float(range_spec["max"]))


def _choose_reproductive_stage(rng: random.Random, params: dict[str, Any]) -> str:
    stage_weights = params["reproduction"].get("stage_weights")
    if not stage_weights:
        return rng.choice(params["reproduction"]["stages"]["values"])

    stages = [
        stage
        for stage in params["reproduction"]["stages"]["values"]
        if stage in stage_weights
    ]
    total_weight = sum(float(stage_weights[stage]) for stage in stages)
    threshold = rng.random() * total_weight
    running = 0.0
    for stage in stages:
        running += float(stage_weights[stage])
        if threshold <= running:
            return stage
    return stages[-1]


def _calyx_cover_fraction(stage: str) -> float:
    if stage in {
        "young_fruit_with_calyx",
        "mature_fruit_with_calyx",
        "exposed_fruit",
    }:
        return 1.0
    return 0.0


def _enforce_reproductive_unit_target(
    main_axis: Axis,
    rng: random.Random,
    params: dict[str, Any],
) -> dict[str, Any]:
    target = params["reproduction"]["target_reproductive_units_range"]
    min_units = int(target["min"])
    max_units = int(target["max"])
    promoted = 0
    removed = 0

    fruit_nodes = _nodes_with_fruit_calyx(main_axis)
    if len(fruit_nodes) > max_units:
        retention_noise = {node.id: rng.random() for node in fruit_nodes}
        retained_first = sorted(
            fruit_nodes,
            key=lambda node: (
                node.order,
                -float(node.axillary_bud.vigor if node.axillary_bud else 0.0),
                retention_noise[node.id],
                node.id,
            ),
        )
        for node in retained_first[max_units:]:
            _clear_reproductive_unit(node)
            removed += 1

    fruit_nodes = _nodes_with_fruit_calyx(main_axis)
    if len(fruit_nodes) < min_units:
        candidates = _eligible_nodes_for_fruit(main_axis, params)
        # Units promoted only to satisfy the explicit target are placed first
        # on developmentally established axes. Those axes are more likely to
        # survive the later competition/tutoring stage than a newly proposed
        # high-order branch, while every unit remains attached to a real node.
        promotion_noise = {node.id: rng.random() for node in candidates}
        candidates.sort(
            key=lambda node: (
                node.order,
                -float(node.axillary_bud.vigor if node.axillary_bud else 0.0),
                promotion_noise[node.id],
                node.id,
            )
        )
        for node in candidates:
            if len(fruit_nodes) >= min_units:
                break
            stage = _choose_fruit_stage_for_promotion(rng, params)
            reproductive_unit = _make_reproductive_unit(
                rng,
                params,
                node.id,
                node.leaf.azimuth_deg if node.leaf else 0.0,
                stage_override=stage,
            )
            node.reproductive_unit = reproductive_unit
            if node.axillary_bud is not None:
                node.axillary_bud.state = "reproductive"
                node.axillary_bud.reproductive_unit_id = reproductive_unit.id
                node.axillary_bud.branch_id = None
            fruit_nodes.append(node)
            promoted += 1

    return {
        "target_min": min_units,
        "target_max": max_units,
        "final_fruiting_reproductive_units": len(_nodes_with_fruit_calyx(main_axis)),
        "promoted_axillary_buds": promoted,
        "removed_excess_units": removed,
        "promotion_priority": "established_low_order_axes_then_seeded_tie_break",
        "retention_priority": "established_low_order_axes_then_seeded_tie_break",
    }


def _nodes_with_fruit_calyx(axis: Axis) -> list[Node]:
    nodes: list[Node] = []
    for node in axis.nodes:
        unit = node.reproductive_unit
        if unit is not None and unit.fruit is not None and unit.calyx is not None:
            nodes.append(node)
    for child_axis in axis.child_axes:
        nodes.extend(_nodes_with_fruit_calyx(child_axis))
    return nodes


def _eligible_nodes_for_fruit(axis: Axis, params: dict[str, Any]) -> list[Node]:
    nodes: list[Node] = []
    first_bifurcation = (
        params.get("reproduction", {})
        .get("first_bifurcation_node", {})
        .get("value")
    )
    for node in axis.nodes:
        if node.position_index == 0:
            continue
        if axis.order == 0 and first_bifurcation is not None:
            if node.position_index + 1 < int(first_bifurcation):
                continue
        if node.axillary_bud is not None and node.axillary_bud.state == "branch":
            continue
        unit = node.reproductive_unit
        if unit is None or unit.fruit is None or unit.calyx is None:
            nodes.append(node)
    for child_axis in axis.child_axes:
        nodes.extend(_eligible_nodes_for_fruit(child_axis, params))
    return nodes


def _clear_reproductive_unit(node: Node) -> None:
    node.reproductive_unit = None
    if node.axillary_bud is not None:
        node.axillary_bud.state = "dormant"
        node.axillary_bud.reproductive_unit_id = None


def _choose_fruit_stage_for_promotion(
    rng: random.Random, params: dict[str, Any]
) -> str:
    weights = params["reproduction"].get("stage_weights", {})
    stages = [
        "young_fruit_with_calyx",
        "mature_fruit_with_calyx",
        "exposed_fruit",
    ]
    total = sum(float(weights.get(stage, 0.0)) for stage in stages)
    if total <= 0.0:
        return rng.choice(stages)
    threshold = rng.random() * total
    running = 0.0
    for stage in stages:
        running += float(weights.get(stage, 0.0))
        if threshold <= running:
            return stage
    return stages[-1]


def _apply_literature_cohorts(
    main_axis: Axis,
    rng: random.Random,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Replace independent stages with age-ranked, literature-bounded cohorts."""
    ranked = _ranked_reproductive_nodes(main_axis)
    if reproductive_load_policy(params) == "legacy_fruiting_range" and len(ranked) < 5:
        occupied = {node.id for _score, node in ranked}
        candidates = [
            node
            for node in _eligible_nodes_for_fruit(main_axis, params)
            if node.id not in occupied and node.reproductive_unit is None
        ]
        candidates.sort(key=lambda node: (node.order, node.position_index, node.id))
        if candidates:
            node = candidates[-1]
            unit = _make_reproductive_unit(
                rng,
                params,
                node.id,
                node.leaf.azimuth_deg if node.leaf else 0.0,
                stage_override="flower",
            )
            node.reproductive_unit = unit
            if node.axillary_bud is not None:
                node.axillary_bud.state = "reproductive"
                node.axillary_bud.reproductive_unit_id = unit.id
                node.axillary_bud.branch_id = None
                node.axillary_bud.decision = "phenology_flower_slot"
            ranked = _ranked_reproductive_nodes(main_axis)

    stages = coherent_stage_sequence(
        len(ranked),
        params["reproduction"].get("stage_weights", {}),
        rng,
    )
    counts: dict[str, int] = {}
    for cohort_index, ((_score, node), stage) in enumerate(zip(ranked, stages)):
        unit = _make_reproductive_unit(
            rng,
            params,
            node.id,
            node.leaf.azimuth_deg if node.leaf else 0.0,
            stage_override=stage,
        )
        assignment = reproductive_phenology(
            stage,
            cohort_index=cohort_index,
            unit_count=len(ranked),
            rng=rng,
        )
        unit.phenology_model = "literature_cohort_v1"
        unit.flowering_cohort = assignment.flowering_cohort
        unit.estimated_days_after_anthesis = (
            assignment.estimated_days_after_anthesis
        )
        unit.days_after_anthesis_range = assignment.days_after_anthesis_range
        unit.bbch_principal_stage = assignment.bbch_principal_stage
        unit.ontogenetic_rank = assignment.ontogenetic_rank
        unit.parameter_status = assignment.parameter_status
        unit.provenance = dict(assignment.provenance)
        if unit.calyx is not None:
            state = str(assignment.calyx_state)
            progress = assignment.maturity_progress
            area_scale = float(assignment.projected_area_scale or 1.0)
            size_scale = math.sqrt(area_scale)
            unit.calyx.radius_cm = round(unit.calyx.radius_cm * size_scale, 3)
            unit.calyx.length_cm = round(unit.calyx.length_cm * size_scale, 3)
            unit.calyx.state = state
            unit.calyx.material_key = str(assignment.texture_variant)
            unit.calyx.texture_variant = str(assignment.texture_variant)
            unit.calyx.vein_contrast = float(assignment.vein_contrast or 0.0)
            unit.calyx.apical_darkening = float(
                assignment.apical_darkening or 0.0
            )
            unit.calyx.maturity_progress = progress
            unit.calyx.projected_area_scale = area_scale
            unit.calyx.circularity_target = assignment.circularity_target
            unit.calyx.turgor = float(assignment.turgor or 1.0)
            unit.calyx.inflation = round(
                max(0.75, min(1.45, unit.calyx.inflation * (1.04 - 0.12 * progress))),
                3,
            )
            unit.calyx.asymmetry = round(
                min(0.14, unit.calyx.asymmetry * (0.82 + 0.45 * progress)),
                3,
            )
            wrinkle_range = params["reproduction"]["calyx_wrinkle_by_state"][state]
            unit.calyx.wrinkle = round(
                rng.uniform(
                    float(wrinkle_range["min"]),
                    float(wrinkle_range["max"]),
                ),
                3,
            )
            unit.calyx.pubescence = float(
                params["reproduction"]["calyx_pubescence_by_state"][state]
            )
            unit.calyx.openness = float(
                params["reproduction"]["calyx_openness_by_state"][state]
            )
            unit.calyx.parameter_status = assignment.parameter_status
            unit.calyx.provenance = dict(assignment.provenance)
            unit.calyx_state = state
            if assignment.estimated_days_after_anthesis is not None:
                daa = assignment.estimated_days_after_anthesis
                unit.maturity = (
                    "young" if daa < 60.0 else "mature" if daa < 85.0 else "overripe"
                )
                if unit.fruit is not None:
                    unit.fruit.maturity_stage = unit.maturity
                    unit.fruit.visibility = "hidden"
                    unit.fruit.parameter_status = assignment.parameter_status
                    unit.fruit.provenance = dict(assignment.provenance)
            unit.fruit_visibility = "hidden"
        node.reproductive_unit = unit
        if node.axillary_bud is not None:
            node.axillary_bud.state = "reproductive"
            node.axillary_bud.reproductive_unit_id = unit.id
            node.axillary_bud.branch_id = None
            node.axillary_bud.decision = "literature_cohort_assignment"
        counts[stage] = counts.get(stage, 0) + 1

    return {
        "model": "literature_cohort_v1",
        "applied": True,
        "unit_count": len(ranked),
        "stage_counts": counts,
        "ordering": "oldest_to_youngest_topological_rank",
        "overlap_policy": "seeded_adjacent_stage_swaps_only",
        "parameter_status": "literature_bounded_topological_inference",
    }


def _ranked_reproductive_nodes(axis: Axis) -> list[tuple[tuple[int, int, int, str], Node]]:
    ranked: list[tuple[tuple[int, int, int, str], Node]] = []
    for node in axis.nodes:
        if node.reproductive_unit is not None:
            ranked.append(
                (
                    (
                        int(axis.development_step),
                        int(axis.order),
                        int(node.position_index),
                        node.id,
                    ),
                    node,
                )
            )
    for child in axis.child_axes:
        ranked.extend(_ranked_reproductive_nodes(child))
    ranked.sort(key=lambda item: item[0])
    return ranked
