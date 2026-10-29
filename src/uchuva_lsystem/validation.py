"""Early validation for uchuva morphology trees.

The validator reports morphology concerns separately from future geometric
collision and visual occlusion checks.
"""

from __future__ import annotations

import math
import hashlib
import json
from typing import Any

from .morphology import Axis, Node, Plant
from .parameters import get_initial_parameters, leaf_length_factor
from .scene import CultivationScene


def validate_morphology_tree(
    plant: Plant, *, params: dict[str, Any] | None = None, stage: str | None = None,
) -> dict[str, Any]:
    """Validate integrity and the recorded parameter contract at its actual stage.

    Old trees remain readable. Without an effective snapshot (or explicitly
    supplied parameters), their parameter contract is unknown, not silently
    inferred from the initial preset. Geometric validity requires a mesh audit.
    """
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    stage = stage or ("adapted" if plant.metadata.get("model_stage") == "adapted"
                     or plant.metadata.get("synchronous_growth")
                     or plant.metadata.get("cultivation_adaptation") else "generated")
    if stage not in {"generated", "adapted"}:
        raise ValueError("Morphology validation stage must be generated or adapted")
    params, parameter_contract = _resolve_validation_parameters(plant, params, errors)
    range_params = params if parameter_contract['contract_available'] else None
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
        node_count += _validate_axis(axis, warnings, range_params, stage, errors)
        reproductive_count += _count_reproductive_units(axis)
        fruiting_count += _count_fruiting_units(axis)
        flower_count += _count_flowers(axis)
        _collect_calyx_states(axis, calyx_state_counts)
        _validate_stem_color_coherence(axis, plant.condition, warnings)

    _validate_individual_scope(plant, params, warnings)
    light_enabled = bool(
        plant.metadata.get("synchronous_growth", {}).get(
            "light_competition_enabled",
            plant.metadata.get("light_competition", {}).get("enabled",
                bool(range_params and range_params.get("light_competition", {}).get(
                    "enabled", {}).get("value", False))),
        )
    )
    leaf_light_summary = _validate_leaf_light_response(
        plant,
        warnings,
        required=light_enabled and stage == "adapted",
    )
    phenology_summary = _validate_phenology_coherence(plant, warnings, range_params, errors)
    _validate_recorded_counts(plant, stage, errors)
    nodal_summary = _validate_nodal_growth_poses(plant,stage,errors,warnings)
    from .reproductive_space import validate_admission
    try:
        space_summary = validate_admission(plant)
    except (ValueError, KeyError, TypeError) as exc:
        space_summary = dict(applied=True, status='invalid')
        _warn(errors, 'reproductive_space_admission', str(exc))
    from .spatial_admission import validate_plan
    try:
        spatial_summary = validate_plan(plant)
    except (ValueError, KeyError, TypeError) as exc:
        spatial_summary = dict(applied=True,status='invalid')
        _warn(errors,'spatial_admission',str(exc))

    return {
        "plant_seed": plant.seed,
        "status": "invalid" if errors else "valid_with_warnings" if warnings else "valid",
        "validation_stage": stage,
        "parameter_contract": parameter_contract,
        "errors": errors,
        "summary": {
            "axis_count": axis_count,
            "node_count": node_count,
            "reproductive_unit_count": reproductive_count,
            "fruiting_reproductive_unit_count": fruiting_count,
            "flower_count": flower_count,
            "calyx_state_counts": calyx_state_counts,
            "leaf_light_response": leaf_light_summary,
            "phenology": phenology_summary,
            "nodal_growth_poses":nodal_summary,
            "reproductive_space_admission":space_summary,
            "spatial_admission":spatial_summary,
        },
        "warnings": warnings,
        "checks": {
            "geometric_collision": "not_evaluated_in_initial_migration",
            "visual_occlusion": "not_evaluated_in_initial_migration",
            "out_of_range_morphology": "basic_morphology_and_calyx_checks",
            "individual_width_scope": "projection_sum_proxy_requires_evaluated_envelope",
            "stratified_light_response": (
                "validated_additive_proxy_fields"
                if light_enabled and stage == "adapted"
                else "not_required_before_scene_adaptation" if light_enabled
                else "not_enabled"
            ),
            "phenology_coherence": phenology_summary["status"],
        },
    }


def _validate_nodal_growth_poses(plant,stage,errors,warnings):
    """Recorded directions are actual adapted poses; legacy angles stay initial.

    Numerical bounds are engineering integrity checks, not measured botanical
    ranges or proof that a collision has been eliminated.
    """
    from .nodal_repulsion import KEY, axes, dot, unit, protected_anatomy
    expected=bool(plant.metadata.get('nodal_repulsion_requested')) and stage=='adapted'
    checked=0;missing=0
    for axis in axes(plant.axes):
        controls=[('branch',p) for p in axis.internodes]
        for node in axis.nodes:
            if node.reproductive_unit and KEY in node.reproductive_unit.provenance:
                try:
                    from .reproductive_orientation import organ_direction
                    organ_direction(node.reproductive_unit)
                except (ValueError,KeyError,TypeError) as exc:
                    _warn(errors,'nodal_growth_pose',f'{node.reproductive_unit.id}: {exc}')
            if node.leaf:controls.append(('leaf',node.leaf))
            if node.reproductive_unit:controls.append(('pedicel',node.reproductive_unit.pedicel))
        for kind,part in controls:
            record=part.provenance.get(KEY)
            if record is None:
                missing+=1
                continue
            checked+=1
            try:
                direction=record['direction'];initial=record['input_direction']
                if len(direction)!=3 or len(initial)!=3:raise ValueError('Direction must have three components')
                if record['frame']!='plant' or record['status']!='engineering_heuristic':raise ValueError('Missing frame/provenance')
                if abs(sum(float(v)**2 for v in direction)-1)>1e-5:raise ValueError('Direction is not normalized')
                angle=math.degrees(math.acos(max(-1,min(1,dot(unit(direction),unit(initial))))))
                limit={'branch':35.,'leaf':120.,'pedicel':75.}[kind]
                if kind=='pedicel' and record.get('excursion_limit_deg',75)!=75:
                    revision=next((r for r in plant.metadata.get('nodal_mobility_revisions',[]) if r['sha256']==record.get('mobility_revision_sha256')),None)
                    if revision is None:raise ValueError('Missing explicit mobility revision')
                    policy=revision['policy'];digest=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                    if digest!=revision['sha256'] or policy['excursion_from_input_deg']!=record['excursion_limit_deg'] or not 75<=record['excursion_limit_deg']<=180:
                        raise ValueError('Mobility revision hash or limit differs')
                    limit=record['excursion_limit_deg']
                if angle>limit+1e-5:raise ValueError('Pose exceeds declared engineering excursion')
                if kind=='branch':unit(record['input_incoming_direction'])
            except (ValueError,KeyError,TypeError,OverflowError) as exc:
                _warn(errors,'nodal_growth_pose',f'{part.id}: {exc}')
    if expected and missing:_warn(errors,'nodal_growth_pose',f'{missing} expected nodal directions missing')
    recorded=plant.metadata.get('nodal_repulsion',{}).get('anatomy_after')
    if recorded and protected_anatomy(plant)!=recorded:
        _warn(errors,'nodal_growth_pose','Protected anatomy differs from the completed nodal search')
    if checked:
        _warn(warnings,'out_of_range_morphology','Nodal growth postures are unmeasured engineering hypotheses; independent evaluated-mesh and ground audits remain necessary.')
    return dict(checked=checked,missing=missing,required=expected,physical_validity='not established by morphology validation')


def _parameters_digest(params: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _resolve_validation_parameters(plant: Plant, explicit: dict | None, errors: list) -> tuple[dict, dict]:
    snapshot = plant.metadata.get("effective_parameters")
    recorded = plant.metadata.get("effective_parameters_sha256")
    if snapshot is not None:
        digest = _parameters_digest(snapshot)
        if recorded != digest:
            _warn(errors, "parameter_contract", "Effective parameter snapshot hash is missing or mismatched.")
        if explicit is not None and _parameters_digest(explicit) != digest:
            _warn(errors, "parameter_contract", "Explicit parameters do not match the effective snapshot.")
        return snapshot, dict(contract_available=True, source="effective_snapshot", sha256=digest,
                              recorded_sha256=recorded, snapshot_verified=recorded == digest)
    if explicit is not None:
        return explicit, dict(contract_available=True, source="explicit_parameters_without_historical_snapshot",
                              sha256=_parameters_digest(explicit), snapshot_verified=False)
    return get_initial_parameters(), dict(contract_available=False,
        source="legacy_snapshot_missing", snapshot_verified=False,
        limitation="Original effective parameters unknown; sampled parameter ranges are not certified.")


def _validate_recorded_counts(plant: Plant, stage: str, errors: list) -> None:
    recorded = plant.metadata.get("reproductive_counts_by_stage", {}).get(stage)
    if recorded is None:
        return
    counts = dict(reproductive_units=0, flowers=0, fruits=0, fruits_with_calyx=0)
    for root in plant.axes:
        for unit in _phenology_units(root):
            counts["reproductive_units"] += 1
            counts["flowers"] += unit.stage == "flower"
            counts["fruits"] += unit.fruit is not None
            counts["fruits_with_calyx"] += unit.fruit is not None and unit.calyx is not None
    if counts != recorded:
        _warn(errors, "parameter_contract", f"Recorded {stage} reproductive counts differ from the tree traversal.")


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


def _validate_axis(axis: Axis, warnings: list[dict[str, str]], params: dict | None,
                   stage: str, errors: list) -> int:
    _validate_registered_axis_pose(axis, params, stage, errors)
    parent_radius = _max_axis_radius(axis)
    node_count = 0
    for index, internode in enumerate(axis.internodes):
        if internode.order != axis.order:
            _warn(errors, "integrity", f"{internode.id} order differs from its axis.")
        for field in ("length_cm", "radius_cm"):
            value = getattr(internode, field)
            if not math.isfinite(value) or value <= 0:
                _warn(errors, "integrity", f"{internode.id} has nonpositive/nonfinite {field}.")
        if params is not None:
            table = params.get("internode", {}).get("radius_cm_by_order", {})
            bounds = table.get(str(axis.order))
            if bounds is None:
                _warn(errors, "parameter_contract", f"No radius parameters for enabled order {axis.order}.")
            elif stage == "generated":
                sampling = internode.provenance.get("radius_sampling")
                budgeted = params.get("growth", {}).get("mode", {}).get("value") == "incremental_budgeted"
                # Actual axes can stop before their requested node budget. A
                # taper reconstructed from final length would create false alarms.
                taper = float(sampling["taper_factor"]) if sampling else 1.0
                # Continuity may lower a sampled radius; never mistake its
                # declared reduction for a different botanical sampling range.
                continuity = internode.provenance.get("radius_continuity", {})
                minimum = 0.0 if continuity else float(bounds["min"]) * (
                    taper if sampling or not budgeted else .52)
                maximum = float(bounds["max"]) * taper
                if not minimum - .001 <= internode.radius_cm <= maximum + .001:
                    _warn(warnings, "parameter_contract", f"{internode.id} radius is outside its effective tapered range.")
    for node in axis.nodes:
        node_count += 1
        _validate_node(node, axis, warnings, params, stage, errors)

    for child_axis in axis.child_axes:
        if child_axis.order != axis.order + 1:
            _warn(errors, "integrity", f"{child_axis.id} has inconsistent branch order.")
            _warn(
                warnings,
                "out_of_range_morphology",
                f"{child_axis.id} has order {child_axis.order}, expected {axis.order + 1}.",
            )
        child_radius = _max_axis_radius(child_axis)
        if child_radius is not None and parent_radius is not None:
            if child_radius > parent_radius + 1e-9:
                _warn(
                    warnings,
                    "out_of_range_morphology",
                    f"{child_axis.id} radius does not decrease relative to {axis.id}.",
                )
        if params is not None:
            positions = {node.id: i for i, node in enumerate(axis.nodes)}
            position = positions.get(child_axis.parent_node_id)
            if position is None or position >= len(axis.internodes):
                _warn(errors, "integrity", f"{child_axis.id} has no valid parent insertion node/internode.")
            elif child_radius is not None and child_radius > axis.internodes[position].radius_cm + 1e-9:
                _warn(errors, "parameter_contract", f"{child_axis.id} radius exceeds the parent at insertion {child_axis.parent_node_id}.")
        node_count += _validate_axis(child_axis, warnings, params, stage, errors)
    return node_count


def _validate_registered_axis_pose(axis: Axis, params: dict | None, stage: str, errors: list) -> None:
    """Keep generated angle ranges and bound cumulative adapted nodal changes."""
    if not params or axis.order == 0:
        return
    branching = params.get("branching", {})
    if branching.get("frame", {}).get("value") != "local_cone_v1":
        return
    bounds = branching.get("branch_angle_deg_by_order", {}).get(str(axis.order))
    if not bounds:
        _warn(errors,"parameter_contract",f"{axis.id} lacks an effective branch angle range.")
        return
    low,high = float(bounds["min"]),float(bounds["max"])
    if not math.isfinite(axis.branch_angle_deg) or not low-1e-8 <= axis.branch_angle_deg <= high+1e-8:
        _warn(errors,"parameter_contract",f"{axis.id} branch angle is outside its effective range at {stage} stage.")
    if not math.isfinite(axis.azimuth_deg):
        _warn(errors,"integrity",f"{axis.id} azimuth is nonfinite.")
    record = axis.provenance.get("axis_pose_repair_v1")
    if record is None:
        return
    if stage != "adapted" or record.get("stage") != "adapted":
        _warn(errors,"parameter_contract",f"{axis.id} repaired axis pose requires the adapted stage.")
    if not axis.provenance.get("branch_frame_v140") or axis.resolved_direction is not None:
        _warn(errors,"parameter_contract",f"{axis.id} repaired pose does not have an unambiguous local branch frame.")
    try:
        from .axis_pose_repair import local_pose_distance_deg
        original = tuple(float(v) for v in record["generated_pose"])
        effective = tuple(float(v) for v in record["effective_pose"])
        maximum = float(params["growth"]["max_final_axis_correction_deg"]["value"])
        if (len(original) != 2 or len(effective) != 2
                or not all(math.isfinite(v) for v in (*original,*effective,maximum))):
            raise ValueError("nonfinite or malformed pose")
        actual = (axis.azimuth_deg,axis.branch_angle_deg)
        if any(abs(a-b)>1e-6 for a,b in zip(effective,actual)):
            raise ValueError("effective pose does not match the axis")
        if not low-1e-8 <= original[1] <= high+1e-8:
            raise ValueError("original angle is outside generated range")
        if record.get("angle_range_deg") != [low,high] or abs(float(record["max_correction_deg"])-maximum)>1e-8:
            raise ValueError("registered bounds differ from the effective parameters")
        if record.get("frame") != "local_cone_v1" or not record.get("changes"):
            raise ValueError("missing frame or change history")
        if local_pose_distance_deg(original,actual)>maximum+1e-6 or abs((actual[0]-original[0]+180)%360-180)>maximum+1e-6:
            raise ValueError("cumulative correction exceeds the effective maximum")
        if record["changes"][0]["from_pose"] != list(original) or record["changes"][-1]["to_pose"] != list(effective):
            raise ValueError("change history endpoints differ from registered poses")
    except (KeyError,TypeError,ValueError) as exc:
        _warn(errors,"parameter_contract",f"{axis.id} invalid axis pose repair record: {exc}.")


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


def _validate_leaf_pose_contract(leaf: Any, leaf_params: dict, stage: str,
                                 warnings: list, errors: list) -> None:
    """Validate opt-in pose sampling without treating adapted poses as samples.

    Historical presets did not expose this contract. Their interpretation and
    provenance remain unchanged rather than retroactively claiming a range.
    """
    frame = leaf_params.get("insertion_frame")
    if frame is not None:
        expected = frame.get("value") if isinstance(frame, dict) else None
        if expected not in {"orthogonal_local_v1", "local_cone_v2"}:
            _warn(errors, "parameter_contract", f"{leaf.id} has an unsupported effective insertion frame.")
        elif leaf.provenance.get("insertion_frame") != expected:
            _warn(errors, "parameter_contract", f"{leaf.id} insertion_frame differs from its effective parameters.")

    bounds = leaf_params.get("insertion_angle_deg_range")
    if bounds is None:
        return
    try:
        low, high = float(bounds["min"]), float(bounds["max"])
        valid = math.isfinite(low) and math.isfinite(high) and 0 <= low <= high <= 180
    except (TypeError, ValueError, KeyError):
        valid = False
    if not valid:
        _warn(errors, "parameter_contract", f"{leaf.id} has an invalid effective insertion angle range.")
        return

    sampled = leaf.provenance.get("pose_sampling", {})
    try:
        recorded_low = float(sampled["range_min_deg"])
        recorded_high = float(sampled["range_max_deg"])
        provenance_valid = (math.isfinite(recorded_low) and math.isfinite(recorded_high)
            and abs(recorded_low-low) <= 1e-9 and abs(recorded_high-high) <= 1e-9
            and sampled.get("status") == bounds.get("status")
            and bool(sampled.get("method")))
    except (TypeError, ValueError, KeyError):
        provenance_valid = False
    if not provenance_valid:
        _warn(errors, "parameter_contract", f"{leaf.id} pose_sampling differs from its effective range/provenance.")

    values = {}
    for field in ("preferred_insertion_angle_deg", "insertion_angle_deg"):
        try:
            value = float(getattr(leaf, field))
            finite_angle = math.isfinite(value) and 0 <= value <= 180
        except (TypeError, ValueError):
            finite_angle = False
        if not finite_angle:
            _warn(errors, "integrity", f"{leaf.id} has missing/nonfinite/out-of-angle {field}.")
            continue
        values[field] = value
        if field == "preferred_insertion_angle_deg" or stage == "generated":
            if not low-.01 <= value <= high+.01:
                _warn(errors, "parameter_contract", f"{leaf.id} {field}={value} is outside its effective sampled range.")
    if len(values) != 2:
        return
    difference = abs(values["insertion_angle_deg"]-values["preferred_insertion_angle_deg"])
    if stage == "generated" and difference > .011:
        _warn(errors, "parameter_contract", f"{leaf.id} generated insertion angle differs from its preferred sample.")
    elif stage == "adapted" and difference > .011:
        documented = (bool(leaf.orientation_cost_terms) or bool(leaf.orientation_adjustment_deg)
                      or bool(leaf.provenance.get("mesh_feedback_pose")))
        if not documented:
            _warn(warnings, "parameter_contract", f"{leaf.id} adapted insertion angle has no leaf-level pose-adjustment record.")


def _validate_mesh_feedback_pose(target: Any, *, kind: str, organ_id: str, node_id: str,
                                  stage: str, warnings: list, errors: list) -> None:
    """Validate the separate engineering contract of post-contact angular poses.

    These bounds do not replace generated sampling ranges or preferred poses.
    Older v2 artifacts retain only their last local record; their available
    record is checked without inventing missing history.
    """
    record=target.provenance.get("mesh_feedback_pose_v2")
    history=target.provenance.get("mesh_feedback_pose_history_v2")
    if record is None and history is None:
        return
    from .blender_pose_repair_v2 import ADAPTED_ANGLE_LIMITS
    low,high=ADAPTED_ANGLE_LIMITS[kind]
    if stage!="adapted":
        _warn(errors,"parameter_contract",f"{organ_id} mesh-feedback pose requires the adapted stage.")
    try:
        angle=target.insertion_angle_deg if kind=="leaf" else target.angle_deg
        actual=(float(target.azimuth_deg),float(angle))
        if not all(math.isfinite(v) for v in actual) or not 0 <= actual[0] <= 360 or not low <= actual[1] <= high:
            raise ValueError(f"effective pose outside adapted {kind} limits {low}..{high}")
        if not isinstance(record,dict):
            raise ValueError("missing last mesh-feedback record")
        available=history if history is not None else [record]
        if not isinstance(available,list) or not available or available[-1]!=record:
            raise ValueError("history and last record disagree")
        if history is not None and target.provenance.get("mesh_feedback_pose_history_prefix_v2") not in {
                "complete_since_first_mesh_repair","only_last_legacy_record_available"}:
            raise ValueError("unknown cumulative history prefix")
        previous=None
        for item in available:
            if item.get("organ_id")!=organ_id or item.get("node_id")!=node_id or item.get("kind")!=kind:
                raise ValueError("record identifies a different organ, node or kind")
            before=tuple(float(v) for v in item["before_deg"])
            after=tuple(float(v) for v in item["after_deg"])
            if (len(before)!=2 or len(after)!=2 or not all(math.isfinite(v) for v in (*before,*after))
                    or not 0 <= before[0] <= 360 or not 0 <= before[1] <= 180
                    or not 0 <= after[0] <= 360 or not low <= after[1] <= high):
                raise ValueError("nonfinite/malformed pose or adapted range violation in history")
            if previous is not None and any(abs(a-b)>1e-6 for a,b in zip(before,previous)):
                raise ValueError("noncontiguous cumulative pose history")
            limits=item.get("angular_limits_deg")
            if limits is not None and limits!={"azimuth":[0,360],"inclination":[low,high]}:
                raise ValueError("recorded adapted limits differ from the v2 engineering contract")
            if item.get("dimensions_unchanged") is not True or item.get("status")!="engineering_heuristic":
                raise ValueError("missing dimension-preservation or engineering provenance")
            previous=after
        if any(abs(a-b)>1e-6 for a,b in zip(actual,previous)):
            raise ValueError("recorded after_deg differs from the current pose")
        if history is None:
            message="Legacy mesh-feedback v2 artifacts preserve the last per-organ record only; missing cumulative history is not reconstructed."
            if not any(w.get("message")==message for w in warnings):
                _warn(warnings,"provenance_limitation",message)
    except (KeyError,TypeError,ValueError,AttributeError) as exc:
        _warn(errors,"parameter_contract",f"{organ_id} invalid mesh-feedback pose: {exc}.")


def _validate_node(node: Node, axis: Axis, warnings: list[dict[str, str]],
                   params: dict | None, stage: str, errors: list) -> None:
    if node.leaf is not None:
        ratio = node.leaf.transverse_arch_ratio
        if not 0.0 <= ratio <= 0.2:
            _warn(warnings, "out_of_range_morphology", f"{node.leaf.id} has invalid transverse_arch_ratio={ratio}.")
        if ratio != 0.0 and node.leaf.provenance.get("surface_relief_ratio", 0.0) != 0.0:
            _warn(warnings, "out_of_range_morphology", f"{node.leaf.id} combines smooth arch and legacy corrugation.")
    if node.order != axis.order:
        _warn(errors, "integrity", f"{node.id} order differs from its axis.")
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.id} order {node.order} does not match axis order {axis.order}.",
        )

    if node.leaf is None:
        _warn(warnings, "out_of_range_morphology", f"{node.id} has no leaf.")
    elif node.leaf.node_id != node.id:
        _warn(errors, "integrity", f"{node.leaf.id} is associated with the wrong node.")
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.leaf.id} is attached to {node.leaf.node_id}, expected {node.id}.",
        )
    if node.leaf is not None:
        leaf = node.leaf
        _validate_mesh_feedback_pose(leaf,kind="leaf",organ_id=leaf.id,node_id=node.id,
                                     stage=stage,warnings=warnings,errors=errors)
        for field in ("length_cm", "width_cm", "petiole_length_cm"):
            value = getattr(leaf, field)
            if not math.isfinite(value) or value <= 0:
                _warn(errors, "integrity", f"{leaf.id} has nonpositive/nonfinite {field}.")
        if params is not None:
            _validate_leaf_pose_contract(leaf, params["leaf"], stage, warnings, errors)
            for field, key in (("curl", "curl_range"), ("twist_deg", "twist_deg_range"),
                               ("petiole_length_cm", "petiole_length_cm_range")):
                bounds = params["leaf"].get(key)
                value = getattr(leaf, field)
                if bounds and not float(bounds["min"]) - .001 <= value <= float(bounds["max"]) + .001:
                    _warn(warnings, "parameter_contract", f"{leaf.id} {field}={value} is outside its effective {stage} range.")
            if stage == "generated":
                factor = 1.0
                if params.get("growth", {}).get("mode", {}).get("value") == "incremental_budgeted":
                    factor = leaf_length_factor(params, axis.order, axis.vigor)
                bounds = params["leaf"]["length_cm_range"]
                if not float(bounds["min"]) * factor - .002 <= leaf.length_cm <= float(bounds["max"]) * factor + .002:
                    _warn(warnings, "parameter_contract", f"{leaf.id} length is outside its effective order/vigor range.")

    if node.axillary_bud is None:
        _warn(warnings, "out_of_range_morphology", f"{node.id} has no axillary bud.")
    elif node.axillary_bud.node_id != node.id:
        _warn(errors, "integrity", f"{node.axillary_bud.id} is associated with the wrong node.")
        _warn(
            warnings,
            "out_of_range_morphology",
            f"{node.axillary_bud.id} is attached to {node.axillary_bud.node_id}, expected {node.id}.",
        )

    if node.reproductive_unit is not None:
        unit = node.reproductive_unit
        pedicel=unit.pedicel
        from .reproductive_orientation import KEY, organ_direction
        orientation = (params or {}).get("reproduction", {}).get("organ_orientation")
        if orientation and KEY not in unit.provenance:
            _warn(errors, "parameter_contract", f"{unit.id} lacks its required gravity-referenced organ posture.")
        if KEY in unit.provenance:
            try:
                organ_direction(unit)
                pose = unit.provenance[KEY]
                if orientation and (pose["policy"] != orientation["value"] or
                        pose["inclination_bounds_deg"] != orientation["inclination_from_down_deg_range"]):
                    raise ValueError("Orientation differs from effective parameter snapshot")
            except (ValueError, KeyError, TypeError, OverflowError) as exc:
                _warn(errors, "parameter_contract", f"{unit.id} invalid reproductive orientation: {exc}")
        for name in ("angle_deg","azimuth_deg"):
            value=getattr(pedicel,name)
            maximum=180 if name=="angle_deg" else 360
            if not math.isfinite(value) or not 0 <= value <= maximum:
                _warn(errors,"integrity",f"{pedicel.id} has nonfinite/out-of-angle {name}.")
        if params and stage=="generated":
            bounds=params.get("reproduction",{}).get("pedicel_angle_deg_range")
            if bounds and not float(bounds["min"])-.01 <= pedicel.angle_deg <= float(bounds["max"])+.01:
                _warn(errors,"parameter_contract",f"{pedicel.id} angle is outside its effective generated range.")
        _validate_mesh_feedback_pose(pedicel,kind="reproductive",organ_id=unit.id,node_id=node.id,
                                     stage=stage,warnings=warnings,errors=errors)
        if unit.node_id != node.id or unit.pedicel.node_id != node.id or unit.pedicel.connects_to != unit.id:
            _warn(errors, "integrity", f"{unit.id} is not connected to its node through its pedicel.")
        if unit.stage in {"young_fruit_with_calyx", "mature_fruit_with_calyx", "exposed_fruit"} and (
            unit.fruit is None or unit.calyx is None
        ):
            _warn(errors, "integrity", f"{unit.id} lacks fruit/calyx required by its recorded stage.")
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
                "morphology_proxy",
                f"{unit.fruit.id} nominal dimensions approach/exceed {calyx.id}; evaluate final mesh envelopes and surfaces before inferring containment or intersection.",
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
    params: dict[str, Any] | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    model = str(plant.metadata.get("phenology_model", "legacy_independent"))
    branching = (params or {}).get("branching", {})
    independent = branching.get("activation_policy", {}).get("value") == "vegetative_onset_independent_v1"
    if model != "literature_cohort_v1":
        if independent:
            _warn(errors if errors is not None else warnings, "parameter_contract",
                  "Independent vegetative activation requires the recorded literature-cohort reproductive landmark; an unknown transition cannot be silently substituted.")
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
    vegetative_threshold = branching.get("vegetative_first_main_node", {}).get("value") if independent else None
    contract = plant.metadata.get("vegetative_branching_contract", {})
    if independent:
        effective_threshold = (params or {}).get("reproduction", {}).get("first_bifurcation_node", {}).get("value")
        if (isinstance(effective_threshold, bool) or not isinstance(effective_threshold, int)
                or effective_threshold < 2):
            _warn(errors if errors is not None else warnings, "parameter_contract",
                  "Independent vegetative activation is missing a valid effective reproductive landmark.")
            effective_threshold = None
        if threshold != effective_threshold:
            _warn(errors if errors is not None else warnings, "parameter_contract",
                  "Phenology reproductive landmark disagrees with the effective parameter snapshot.")
        threshold = effective_threshold
        main_node_count = (params or {}).get("axis", {}).get("main_node_count", {}).get("value", 0)
        if (isinstance(vegetative_threshold, bool) or not isinstance(vegetative_threshold, int)
                or not 2 <= vegetative_threshold < main_node_count):
            _warn(errors if errors is not None else warnings, "parameter_contract",
                  "Independent vegetative activation has an invalid effective first main-axis node.")
            vegetative_threshold = None
        expected = {"policy": "vegetative_onset_independent_v1",
                    "first_eligible_main_node": vegetative_threshold,
                    "reproductive_landmark_node": threshold}
        for key, value in expected.items():
            if contract.get(key) != value:
                _warn(errors if errors is not None else warnings, "parameter_contract",
                      f"Vegetative branching contract {key} disagrees with effective parameters.")
    if threshold is not None:
        for main_axis in plant.axes:
            positions = {node.id: node.position_index + 1 for node in main_axis.nodes}
            nodes = {node.id: node for node in main_axis.nodes}
            if independent:
                for node in main_axis.nodes:
                    if node.reproductive_unit and node.position_index + 1 < int(threshold):
                        _warn(errors if errors is not None else warnings, "integrity",
                              f"{node.reproductive_unit.id} precedes reproductive landmark {threshold}; vegetative branching does not advance reproduction.")
            for child in main_axis.child_axes:
                parent_position = positions.get(str(child.parent_node_id))
                if independent:
                    origin = child.provenance.get("branch_origin", {})
                    node = nodes.get(child.parent_node_id)
                    axillary_origin = node.axillary_bud.provenance.get("branch_origin", {}) if node and node.axillary_bud else {}
                    expected_origin = {"policy": "vegetative_onset_independent_v1",
                                       "parent_node_number": parent_position,
                                       "first_eligible_main_node": vegetative_threshold,
                                       "reproductive_landmark_node": threshold,
                                       "interpretation": "vegetative_axillary_branch_not_reproductive_transition"}
                    if any(origin.get(key) != value for key, value in expected_origin.items()) or origin != axillary_origin:
                        _warn(errors if errors is not None else warnings, "parameter_contract",
                              f"{child.id} has inconsistent vegetative branch_origin provenance.")
                    if vegetative_threshold is not None and parent_position is not None and parent_position < int(vegetative_threshold):
                        _warn(errors if errors is not None else warnings, "integrity",
                              f"{child.id} starts before independent vegetative node {vegetative_threshold}.")
                elif parent_position is not None and parent_position < int(threshold):
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
        "vegetative_activation_policy": "vegetative_onset_independent_v1" if independent else "legacy_reproductive_gate",
        "first_eligible_vegetative_main_node": vegetative_threshold,
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
            "morphology_proxy",
            "Sum of projected branch spans is high; this is not a crown envelope. Measure evaluated world-space mesh bounds before interpreting plant width.",
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
