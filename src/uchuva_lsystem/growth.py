"""Deterministic, synchronous multi-plant growth coordination.

The coordinator consumes potential morphology trees produced by the grammar.
It activates lateral axes in developmental steps, canonically orders all
proposals, and records every acceptance, deviation, shortening, deferral, or
cancellation.  The implementation is a morphology heuristic, not a claim
about the exact developmental physiology of *Physalis peruviana*.
"""

from __future__ import annotations

import hashlib
import math
import random
from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

from .light_competition import StratifiedLightField
from .morphology import Axis, Plant, SerializableMixin
from .scene import CultivationScene, PlantInstance
from .spatial import ContactPolicy, SpatialItem, SpatialOccupancy
from .support import SupportContact


Vec3 = tuple[float, float, float]
CM_TO_SCENE_UNIT = 0.08
GROWTH_COORDINATOR_VERSION = "0.3.1-stratified-light-guidance-bounded-bend"
TRAINED_AXIS_BEND_SCALE = 0.30


@dataclass
class GrowthProposal(SerializableMixin):
    plant_id: str
    bud_id: str
    axis_id: str
    parent_axis_id: str
    parent_node_id: str
    order: int
    origin: Vec3
    parent_direction: Vec3
    desired_direction: Vec3
    desired_length: float
    radius: float
    vigor: float
    age: int
    target_region: str
    provenance: dict[str, Any] = field(default_factory=dict)
    priority_key: tuple[Any, ...] = field(default_factory=tuple)
    development_step: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GrowthProposal":
        accepted = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in accepted})


@dataclass
class ProposalDecision(SerializableMixin):
    proposal_id: str
    plant_id: str
    axis_id: str
    status: str
    applied_direction: Vec3 | None
    applied_length: float
    angular_deviation_deg: float
    shortening_fraction: float
    cost_terms: dict[str, float]
    cause: str
    contacts: list[dict[str, Any]] = field(default_factory=list)
    development_step: int = 0
    target_region: str = "unassigned"
    training_phase: str = "unmodeled"
    training_target_direction: Vec3 | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProposalDecision":
        accepted = {item.name for item in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in accepted})


def coordinate_synchronous_growth(
    scene: CultivationScene,
    potential_plants: dict[str, Plant],
    *,
    contact_policy: ContactPolicy | None = None,
    shared_occupancy: bool = True,
    support_enabled: bool = True,
    leaf_posture_enabled: bool = True,
    tangential_sliding_enabled: bool = True,
    space_colonization_enabled: bool = False,
    light_competition: dict[str, Any] | None = None,
) -> tuple[dict[str, Plant], dict[str, Any]]:
    """Activate potential axes synchronously against a shared spatial index."""
    from .nodal_repulsion import require_legacy_pose_inputs
    require_legacy_pose_inputs(potential_plants.values(),'coordinate_synchronous_growth')
    policy = contact_policy or ContactPolicy.default()
    light_options = light_competition or {}
    light_competition_enabled = bool(
        light_options.get("enabled", {}).get("value", False)
    )
    light_field = (
        StratifiedLightField.from_parameters(light_options)
        if light_competition_enabled
        else None
    )
    instances = {item.plant_id: item for item in scene.plant_instances}
    missing = sorted(set(instances) - set(potential_plants))
    if missing:
        raise ValueError(f"Missing potential morphology trees: {missing}")

    active_plants = {
        plant_id: _root_only_copy(potential_plants[plant_id])
        for plant_id in sorted(potential_plants)
    }
    occupancy = SpatialOccupancy(policy)
    if support_enabled:
        _add_support_items(scene, occupancy)
    for plant_id in sorted(active_plants):
        _add_axis_items(
            occupancy,
            plant_id,
            instances[plant_id],
            active_plants[plant_id].axes,
        )

    potential_axes, potential_parent_axis = _index_potential_axes(potential_plants)
    active_axis_ids = {
        plant_id: {axis.id for axis in _walk_axes(plant.axes)}
        for plant_id, plant in active_plants.items()
    }
    decisions: list[ProposalDecision] = []
    proposal_count_by_step: dict[str, int] = {}
    maximum_step = max(
        (
            axis.development_step
            for plant in potential_plants.values()
            for axis in _walk_axes(plant.axes)
        ),
        default=0,
    )

    for development_step in range(1, maximum_step + 1):
        proposals: list[GrowthProposal] = []
        for plant_id in sorted(potential_plants):
            instance = instances[plant_id]
            node_frames = _node_frames(active_plants[plant_id], instance)
            for axis_id, potential_axis in sorted(
                potential_axes[plant_id].items()
            ):
                if axis_id in active_axis_ids[plant_id]:
                    continue
                parent_axis_id = potential_parent_axis[plant_id][axis_id]
                if parent_axis_id not in active_axis_ids[plant_id]:
                    continue
                if potential_axis.development_step != development_step:
                    continue
                frame = node_frames.get(potential_axis.parent_node_id or "")
                if frame is None:
                    continue
                origin, parent_direction = frame
                proposals.append(
                    _make_proposal(
                        plant_id,
                        potential_axis,
                        parent_axis_id,
                        origin,
                        parent_direction,
                        instance,
                    )
                )
        proposals.sort(key=lambda item: item.priority_key)
        proposal_count_by_step[str(development_step)] = len(proposals)
        for proposal in proposals:
            axis = potential_axes[proposal.plant_id][proposal.axis_id]
            decision = _resolve_proposal(
                proposal,
                axis,
                occupancy,
                scene,
                instances[proposal.plant_id],
                shared_occupancy=shared_occupancy,
                support_enabled=support_enabled,
                tangential_sliding_enabled=tangential_sliding_enabled,
                space_colonization_enabled=space_colonization_enabled,
                light_competition=light_options,
            )
            decisions.append(decision)
            _record_bud_decision(
                active_plants[proposal.plant_id],
                proposal,
                decision,
            )
            if decision.status in {"cancelled", "deferred"}:
                continue
            active_axis = deepcopy(axis)
            active_axis.child_axes = []
            if _trellis_training_enabled(light_options):
                for internode in active_axis.internodes:
                    internode.bend_angle_deg = round(
                        internode.bend_angle_deg * TRAINED_AXIS_BEND_SCALE,
                        4,
                    )
            if decision.applied_direction is not None:
                active_axis.resolved_direction = tuple(
                    round(value, 8)
                    for value in _rotate_about_vertical(
                        decision.applied_direction,
                        -instances[proposal.plant_id].rotation_deg,
                    )
                )
                active_axis.azimuth_deg, active_axis.branch_angle_deg = (
                    _fit_local_axis_angles(
                        decision.applied_direction,
                        proposal.parent_direction,
                        instances[proposal.plant_id],
                        initial_azimuth=axis.azimuth_deg,
                        initial_angle=axis.branch_angle_deg,
                    )
                )
            active_axis.canopy_stratum = decision.target_region
            active_axis.training_phase = decision.training_phase
            active_axis.training_target_direction = (
                tuple(decision.training_target_direction)
                if decision.training_target_direction is not None
                else None
            )
            if decision.shortening_fraction < 0.999:
                for internode in active_axis.internodes:
                    internode.length_cm = round(
                        internode.length_cm * decision.shortening_fraction,
                        3,
                    )
            active_axis.growth_events.append(decision.to_dict())
            _attach_axis(
                active_plants[proposal.plant_id],
                proposal.parent_axis_id,
                active_axis,
            )
            active_axis_ids[proposal.plant_id].add(active_axis.id)
            _add_axis_items(
                occupancy,
                proposal.plant_id,
                instances[proposal.plant_id],
                [active_axis],
                start_override=proposal.origin,
                parent_direction_override=decision.applied_direction,
            )
            _register_support_contact(
                scene,
                proposal,
                decision,
                active_axis,
            )

    reproductive_decisions: list[dict[str, Any]] = []
    for plant_id in sorted(active_plants):
        reproductive_decisions.extend(
            _select_reproductive_postures(
                active_plants[plant_id],
                instances[plant_id],
                occupancy,
                shared_occupancy=shared_occupancy,
            )
        )

    leaf_decisions: list[dict[str, Any]] = []
    if leaf_posture_enabled:
        leaf_decisions.extend(
            _select_leaf_postures(
                active_plants,
                instances,
                occupancy,
                shared_occupancy=shared_occupancy,
                light_field=light_field,
                light_options=light_options,
            )
        )

    status_counts: dict[str, int] = {}
    for decision in decisions:
        status_counts[decision.status] = status_counts.get(decision.status, 0) + 1
    contact_counts: dict[str, int] = {}
    for decision in decisions:
        for contact in decision.contacts:
            classification = str(contact["classification"])
            contact_counts[classification] = contact_counts.get(classification, 0) + 1

    report = {
        "version": GROWTH_COORDINATOR_VERSION,
        "growth_mode": "synchronous_shared_occupancy",
        "proposal_count": len(decisions),
        "proposal_count_by_step": proposal_count_by_step,
        "decision_counts": dict(sorted(status_counts.items())),
        "decisions": [item.to_dict() for item in decisions],
        "leaf_posture_decision_count": len(leaf_decisions),
        "leaf_posture_decisions": leaf_decisions,
        "reproductive_posture_decision_count": len(
            reproductive_decisions
        ),
        "reproductive_posture_decisions": reproductive_decisions,
        "hard_clearance_rejections": sum(
            item["status"] == "cancelled_hard_clearance"
            for item in reproductive_decisions
        ),
        "scene_growth_status": (
            "accepted_with_cancelled_buds_pending_mesh_audit"
            if any(
                item["status"] == "cancelled_hard_clearance"
                for item in reproductive_decisions
            )
            else "accepted_pending_mesh_audit"
        ),
        "contact_counts": dict(sorted(contact_counts.items())),
        "shared_occupancy": shared_occupancy,
        "support_enabled": support_enabled,
        "tangential_sliding_enabled": tangential_sliding_enabled,
        "space_colonization_enabled": space_colonization_enabled,
        "light_competition_enabled": light_competition_enabled,
        "stratified_light_field": (
            light_field.summary() if light_field is not None else None
        ),
        "canonical_order": "order,-vigor,plant_id,axis_id",
        "parameter_status": "engineering_heuristic",
        "scientific_scope": (
            "Projected gap-capture and trellis-training proxy; not calibrated "
            "photosynthesis, radiative transfer, or Physalis physiology."
        ),
    }
    for plant in active_plants.values():
        plant.metadata["synchronous_growth"] = {
            "version": GROWTH_COORDINATOR_VERSION,
            "shared_occupancy": shared_occupancy,
            "support_enabled": support_enabled,
            "light_competition_enabled": light_competition_enabled,
            "light_model": (
                "stratified_daily_projected_gap_capture"
                if light_competition_enabled
                else "disabled"
            ),
        }
    return active_plants, report


def _make_proposal(
    plant_id: str,
    axis: Axis,
    parent_axis_id: str,
    origin: Vec3,
    parent_direction: Vec3,
    instance: PlantInstance,
) -> GrowthProposal:
    direction = _axis_direction(
        parent_direction,
        axis.azimuth_deg + instance.rotation_deg,
        axis.branch_angle_deg,
    )
    desired_length = sum(item.length_cm for item in axis.internodes)
    radius_cm = max((item.radius_cm for item in axis.internodes), default=0.04)
    target_region = (
        "upper_canopy" if origin[2] >= 1.6 else "mid_canopy" if origin[2] >= 0.8 else "lower_canopy"
    )
    proposal_id = f"{plant_id}:{axis.id}"
    return GrowthProposal(
        plant_id=plant_id,
        bud_id=f"{axis.parent_node_id}_axillary_bud",
        axis_id=axis.id,
        parent_axis_id=parent_axis_id,
        parent_node_id=axis.parent_node_id or "",
        order=axis.order,
        origin=origin,
        parent_direction=parent_direction,
        desired_direction=direction,
        desired_length=desired_length * CM_TO_SCENE_UNIT * instance.scale,
        radius=max(radius_cm * CM_TO_SCENE_UNIT * instance.scale, 0.008),
        vigor=axis.vigor,
        age=axis.apex_age,
        target_region=target_region,
        provenance=axis.provenance,
        priority_key=(axis.order, -round(axis.vigor, 6), plant_id, axis.id),
        development_step=axis.development_step,
    )


def _resolve_proposal(
    proposal: GrowthProposal,
    axis: Axis,
    occupancy: SpatialOccupancy,
    scene: CultivationScene,
    instance: PlantInstance,
    *,
    shared_occupancy: bool,
    support_enabled: bool,
    tangential_sliding_enabled: bool,
    space_colonization_enabled: bool,
    light_competition: dict[str, Any],
) -> ProposalDecision:
    offsets = [0.0, -18.0, 18.0, -35.0, 35.0]
    training_enabled = _trellis_training_enabled(light_competition)
    if tangential_sliding_enabled and (axis.order >= 2 or training_enabled):
        offsets.extend((-55.0, 55.0, -72.0, 72.0))
    length_fractions = (1.0, 0.84, 0.68, 0.52)
    support_query = (
        scene.support_system.nearest_support(
            proposal.origin,
            include_posts=False,
        )
        if support_enabled and scene.support_system is not None
        else None
    )
    candidate_bases: list[Vec3] = [proposal.desired_direction]
    if training_enabled and support_enabled:
        _initial_cost, _initial_phase, guidance_target = (
            _trellis_training_cost(
                proposal,
                proposal.desired_direction,
                occupancy,
                scene,
                instance,
                light_competition,
            )
        )
        candidate_bases.extend(
            (
                _normalise(
                    _add(
                        _mul(proposal.desired_direction, 0.52),
                        _mul(guidance_target, 0.48),
                    )
                ),
                guidance_target,
            )
        )
    candidate_results: list[
        tuple[
            tuple[float, ...],
            Vec3,
            float,
            list[Any],
            dict[str, float],
            str,
            Vec3 | None,
        ]
    ] = []
    for length_fraction in length_fractions:
        for candidate_base in candidate_bases:
            for offset in offsets:
                direction = _rotate_about_vertical(candidate_base, offset)
                if space_colonization_enabled:
                    direction = _colonization_direction(
                        direction,
                        proposal.origin,
                        occupancy,
                        proposal,
                    )
                candidate_items = _proposal_axis_items(
                    proposal,
                    axis,
                    direction,
                    length_fraction,
                    instance,
                    bend_scale=(
                        TRAINED_AXIS_BEND_SCALE if training_enabled else 1.0
                    ),
                )
                contacts = []
                for item_index, item in enumerate(candidate_items):
                    contacts.extend(
                        result
                        for result in occupancy.query(item)
                        if not (
                            item_index <= 1
                            and _is_attachment_contact(
                                result,
                                occupancy,
                                proposal.plant_id,
                                proposal.origin,
                            )
                        )
                        and (
                            shared_occupancy
                            or _contact_same_plant_or_support(
                                result,
                                occupancy,
                                proposal.plant_id,
                            )
                        )
                    )
                unique_contacts = {
                    (
                        item.item_a,
                        item.item_b,
                        item.classification,
                        item.policy,
                    ): item
                    for item in contacts
                }
                contacts = [
                    unique_contacts[key] for key in sorted(unique_contacts)
                ]
                hard = [
                    result
                    for result in contacts
                    if result.policy == "hard_occupancy"
                    and result.classification
                    in {"proxy_conflict", "clearance_violation"}
                ]
                soft_cost = sum(
                    1.0
                    for result in contacts
                    if result.policy == "soft_occupancy"
                    and result.classification != "separate"
                )
                support_cost = 0.0
                if (
                    support_query is not None
                    and support_query["distance"] < 1.40
                ):
                    support_direction = _normalise(
                        _sub(support_query["point"], proposal.origin)
                    )
                    support_weight = 1.75 * max(
                        0.20,
                        1.0 - support_query["distance"] / 1.40,
                    )
                    support_cost = (
                        max(
                            0.0,
                            1.0 - _dot(direction, support_direction),
                        )
                        * support_weight
                    )
                gravity_cost = max(0.0, -direction[2]) * 3.0
                training_cost, training_phase, training_target = (
                    _trellis_training_cost(
                        proposal,
                        direction,
                        occupancy,
                        scene,
                        instance,
                        light_competition,
                    )
                    if training_enabled and support_enabled
                    else (0.0, "unmodeled", None)
                )
                angular_deformation = _angle_deg(
                    proposal.desired_direction,
                    direction,
                )
                deformation_cost = (
                    angular_deformation / 72.0
                    + (1.0 - length_fraction) * 1.6
                )
                deterministic_noise = _stable_noise(
                    scene.seed,
                    proposal.plant_id,
                    proposal.axis_id,
                    str(offset),
                    str(length_fraction),
                    *(f"{value:.5f}" for value in candidate_base),
                )
                costs = {
                    "hard_occupancy": float(len(hard)),
                    "soft_occupancy": soft_cost,
                    "support": support_cost,
                    "trellis_training": training_cost,
                    "gravity": gravity_cost,
                    "deformation": deformation_cost,
                    "correlated_noise": deterministic_noise,
                }
                score = (
                    float(len(hard)),
                    round(
                        soft_cost
                        + support_cost
                        + training_cost
                        + gravity_cost
                        + deformation_cost
                        + deterministic_noise * 0.04,
                        8,
                    ),
                    round(angular_deformation, 6),
                    1.0 - length_fraction,
                )
                candidate_results.append(
                    (
                        score,
                        direction,
                        length_fraction,
                        contacts,
                        costs,
                        training_phase,
                        training_target,
                    )
                )

    (
        score,
        direction,
        fraction,
        contacts,
        costs,
        training_phase,
        training_target,
    ) = min(
        candidate_results,
        key=lambda item: item[0],
    )
    hard_conflicts = int(score[0])
    if hard_conflicts:
        status = "deferred" if proposal.development_step < 2 and proposal.vigor > 0.75 else "cancelled"
        cause = "no_candidate_satisfies_hard_clearance"
        applied_direction = None
        applied_length = 0.0
        fraction = 0.0
    else:
        angular = _angle_deg(proposal.desired_direction, direction)
        if fraction < 0.999:
            status = "shortened"
            cause = "clearance_or_local_saturation"
        elif angular >= 0.5:
            status = "deviated"
            cause = "shared_space_support_or_gravity_cost"
        else:
            status = "accepted"
            cause = "preferred_growth_path_available"
        applied_direction = direction
        applied_length = proposal.desired_length * fraction
    return ProposalDecision(
        proposal_id=f"{proposal.plant_id}:{proposal.axis_id}",
        plant_id=proposal.plant_id,
        axis_id=proposal.axis_id,
        status=status,
        applied_direction=applied_direction,
        applied_length=round(applied_length, 6),
        angular_deviation_deg=(
            round(_angle_deg(proposal.desired_direction, direction), 4)
            if applied_direction is not None
            else 0.0
        ),
        shortening_fraction=round(fraction, 4),
        cost_terms={key: round(value, 6) for key, value in costs.items()},
        cause=cause,
        contacts=[item.to_dict() for item in contacts],
        development_step=proposal.development_step,
        target_region=proposal.target_region,
        training_phase=training_phase,
        training_target_direction=(
            tuple(round(value, 8) for value in training_target)
            if training_target is not None
            else None
        ),
    )


def _proposal_axis_items(
    proposal: GrowthProposal,
    axis: Axis,
    direction: Vec3,
    length_fraction: float,
    instance: PlantInstance,
    *,
    bend_scale: float = 1.0,
) -> list[SpatialItem]:
    """Simulate every internode rather than one straight proposal capsule."""
    items: list[SpatialItem] = []
    current = proposal.origin
    active_direction = direction
    for index, internode in enumerate(axis.internodes):
        active_direction = _bend_direction(
            active_direction,
            internode.bend_azimuth_deg + instance.rotation_deg,
            internode.bend_angle_deg * bend_scale,
        )
        end = _add(
            current,
            _mul(
                active_direction,
                internode.length_cm
                * CM_TO_SCENE_UNIT
                * instance.scale
                * length_fraction,
            ),
        )
        items.append(
            SpatialItem(
                id=(
                    f"proposal:{proposal.plant_id}:{proposal.axis_id}:"
                    f"internode_{index}"
                ),
                plant_id=proposal.plant_id,
                organ_type="stem",
                start=current,
                end=end,
                radius=max(
                    internode.radius_cm
                    * CM_TO_SCENE_UNIT
                    * instance.scale,
                    0.008,
                )
                + 0.075,
                source_id=internode.id,
            )
        )
        current = end
    return items


def _trellis_training_enabled(light_competition: dict[str, Any]) -> bool:
    return bool(
        light_competition.get("trellis_training", {})
        .get("enabled", {})
        .get("value", False)
    )


def _select_leaf_postures(
    plants: dict[str, Plant],
    instances: dict[str, PlantInstance],
    occupancy: SpatialOccupancy,
    *,
    shared_occupancy: bool,
    light_field: StratifiedLightField | None,
    light_options: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve leaves in developmental/stratum order against one light field."""
    decisions: list[dict[str, Any]] = []
    records: list[tuple[Any, ...]] = []
    for plant_id in sorted(plants):
        plant = plants[plant_id]
        instance = instances[plant_id]
        frames = _node_frames(plant, instance)
        for axis in _walk_axes(plant.axes):
            for node in axis.nodes:
                leaf = node.leaf
                frame = frames.get(node.id)
                if leaf is None or frame is None:
                    continue
                origin, _parent_direction = frame
                stratum_index = (
                    next(
                        (
                            index
                            for index, stratum in enumerate(light_field.strata)
                            if stratum.name
                            == light_field.stratum_for_height(origin[2]).name
                        ),
                        0,
                    )
                    if light_field is not None
                    else 0
                )
                # Interleave individuals at each developmental position.  This
                # keeps competition deterministic without giving one complete
                # plant permanent priority over every neighbour.
                records.append(
                    (
                        stratum_index,
                        axis.development_step,
                        node.position_index,
                        axis.order,
                        plant_id,
                        axis.id,
                        node.id,
                        axis,
                        node,
                        instance,
                        origin,
                    )
                )

    azimuth_offsets = tuple(
        float(value)
        for value in light_options.get(
            "candidate_azimuth_offsets_deg",
            {"values": [0.0, -22.5, 22.5, -45.0, 45.0, -67.5, 67.5]},
        ).get("values", [])
    )
    insertion_offsets = tuple(
        float(value)
        for value in light_options.get(
            "candidate_insertion_offsets_deg",
            {"values": [0.0, -12.0, 12.0]},
        ).get("values", [])
    )
    if not azimuth_offsets:
        azimuth_offsets = (0.0,)
    if not insertion_offsets:
        insertion_offsets = (0.0,)
    coverage_weight = float(
        light_options.get("coverage_cost_weight", {}).get("value", 1.70)
    )
    deformation_weight = float(
        light_options.get("deformation_cost_weight", {}).get("value", 0.24)
    )
    structural_weight = float(
        light_options.get("structural_contact_cost_weight", {}).get(
            "value",
            0.38,
        )
    )

    for record in sorted(records, key=lambda item: item[:7]):
        (
            _stratum_index,
            _development_step,
            _position_index,
            _axis_order,
            plant_id,
            _axis_id,
            _node_id,
            _axis,
            node,
            instance,
            origin,
        ) = record
        leaf = node.leaf
        assert leaf is not None
        preferred_azimuth = (
            leaf.preferred_azimuth_deg
            if leaf.preferred_azimuth_deg is not None
            else leaf.azimuth_deg
        )
        preferred_insertion = (
            leaf.preferred_insertion_angle_deg
            if leaf.preferred_insertion_angle_deg is not None
            else leaf.insertion_angle_deg
        )
        candidates: list[
            tuple[
                tuple[float, ...],
                float,
                float,
                SpatialItem,
                list[Any],
                dict[str, float],
                Any,
            ]
        ] = []
        for azimuth_offset in azimuth_offsets:
            for insertion_offset in insertion_offsets:
                azimuth = (preferred_azimuth + azimuth_offset) % 360.0
                insertion = max(
                    18.0,
                    min(94.0, preferred_insertion + insertion_offset),
                )
                direction = _leaf_direction(
                    azimuth + instance.rotation_deg,
                    insertion,
                )
                length = (
                    leaf.petiole_length_cm + leaf.length_cm * 0.78
                ) * CM_TO_SCENE_UNIT * instance.scale
                width = leaf.width_cm * CM_TO_SCENE_UNIT * instance.scale
                item = SpatialItem(
                    id=f"leaf:{plant_id}:{leaf.id}",
                    plant_id=plant_id,
                    organ_type="leaf",
                    start=origin,
                    end=_add(origin, _mul(direction, length)),
                    radius=max(width * 0.16, 0.018),
                )
                contacts = [
                    result
                    for result in occupancy.query(item)
                    if not _is_attachment_contact(
                        result,
                        occupancy,
                        plant_id,
                        origin,
                    )
                    and (
                        shared_occupancy
                        or _contact_same_plant_or_support(
                            result,
                            occupancy,
                            plant_id,
                        )
                    )
                ]
                hard = sum(
                    result.policy == "hard_occupancy"
                    and result.classification
                    in {"proxy_conflict", "clearance_violation"}
                    for result in contacts
                )
                structural_contacts = sum(
                    result.policy in {"hard_occupancy", "soft_occupancy"}
                    and result.classification
                    in {
                        "proxy_conflict",
                        "clearance_violation",
                        "near_contact",
                    }
                    for result in contacts
                )
                visual_overlap = sum(
                    result.policy == "visual_occlusion"
                    and result.classification != "separate"
                    for result in contacts
                )
                deformation = (
                    abs(azimuth_offset) / 150.0
                    + abs(insertion_offset) / 60.0
                )
                light_evaluation = (
                    light_field.evaluate_leaf(
                        plant_id=plant_id,
                        start=item.start,
                        end=item.end,
                        width=width,
                        include_other_plants=shared_occupancy,
                    )
                    if light_field is not None
                    else None
                )
                if light_evaluation is not None:
                    coverage_cost = (
                        1.0
                        - light_evaluation.daily_light_interception_proxy
                    ) * coverage_weight
                    score = (
                        float(hard),
                        round(
                            coverage_cost
                            + structural_contacts * structural_weight
                            + deformation * deformation_weight,
                            8,
                        ),
                        abs(azimuth_offset),
                        abs(insertion_offset),
                    )
                    costs = {
                        "hard_contact": float(hard),
                        "structural_contact": float(structural_contacts),
                        "visual_occlusion_allowed": float(visual_overlap),
                        "daily_light_gap_cost": coverage_cost,
                        "projected_coverage_gain": (
                            light_evaluation.new_coverage_fraction
                        ),
                        "daily_light_interception_proxy": (
                            light_evaluation.daily_light_interception_proxy
                        ),
                        "intraspecific_shading": (
                            light_evaluation.same_plant_overlap_fraction
                        ),
                        "interspecific_shading": (
                            light_evaluation.other_plant_overlap_fraction
                        ),
                        "deformation": deformation,
                        "support": 0.0,
                    }
                else:
                    saturation = structural_contacts + visual_overlap
                    score = (
                        float(hard),
                        float(saturation) + deformation * 0.65,
                        abs(azimuth_offset),
                        abs(insertion_offset),
                    )
                    costs = {
                        "hard_contact": float(hard),
                        "local_saturation": float(saturation),
                        "deformation": deformation,
                        "support": 0.0,
                    }
                candidates.append(
                    (
                        score,
                        azimuth,
                        insertion,
                        item,
                        contacts,
                        costs,
                        light_evaluation,
                    )
                )
        (
            _score,
            azimuth,
            insertion,
            item,
            contacts,
            costs,
            light_evaluation,
        ) = min(candidates, key=lambda candidate: candidate[0])
        adjustment = math.hypot(
            _signed_angle_delta(preferred_azimuth, azimuth),
            insertion - preferred_insertion,
        )
        leaf.azimuth_deg = round(azimuth, 3)
        leaf.insertion_angle_deg = round(insertion, 3)
        leaf.orientation_adjustment_deg = round(adjustment, 4)
        leaf.orientation_cost_terms = {
            key: round(value, 6) for key, value in costs.items()
        }
        if light_evaluation is not None and light_field is not None:
            leaf.canopy_stratum = light_evaluation.stratum
            leaf.daily_light_interception_proxy = (
                light_evaluation.daily_light_interception_proxy
            )
            leaf.projected_coverage_gain = (
                light_evaluation.new_coverage_fraction
            )
            leaf.intraspecific_shading_fraction = (
                light_evaluation.same_plant_overlap_fraction
            )
            leaf.interspecific_shading_fraction = (
                light_evaluation.other_plant_overlap_fraction
            )
            light_field.register_leaf(
                plant_id=plant_id,
                leaf_id=leaf.id,
                evaluation=light_evaluation,
            )
        occupancy.add(item)
        decisions.append(
            {
                "plant_id": plant_id,
                "leaf_id": leaf.id,
                "canopy_stratum": leaf.canopy_stratum,
                "preferred_azimuth_deg": round(preferred_azimuth, 3),
                "applied_azimuth_deg": leaf.azimuth_deg,
                "preferred_insertion_deg": round(preferred_insertion, 3),
                "applied_insertion_deg": leaf.insertion_angle_deg,
                "adjustment_deg": leaf.orientation_adjustment_deg,
                "cost_terms": leaf.orientation_cost_terms,
                "contacts": [contact.to_dict() for contact in contacts],
            }
        )
    return decisions


def _select_reproductive_postures(
    plant: Plant,
    instance: PlantInstance,
    occupancy: SpatialOccupancy,
    *,
    shared_occupancy: bool,
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    frames = _node_frames(plant, instance)
    for axis in _walk_axes(plant.axes):
        for node in axis.nodes:
            unit = node.reproductive_unit
            if unit is None or unit.calyx is None or node.id not in frames:
                continue
            origin, _ = frames[node.id]
            preferred_azimuth = unit.pedicel.azimuth_deg
            preferred_angle = unit.pedicel.angle_deg
            candidates: list[
                tuple[
                    tuple[float, ...],
                    float,
                    float,
                    list[SpatialItem],
                    list[Any],
                ]
            ] = []
            for azimuth_offset in (
                0.0,
                -25.0,
                25.0,
                -50.0,
                50.0,
                -75.0,
                75.0,
                100.0,
                -100.0,
            ):
                for angle_offset in (0.0, -15.0, 15.0, 28.0):
                    azimuth = (preferred_azimuth + azimuth_offset) % 360.0
                    angle = max(8.0, min(70.0, preferred_angle + angle_offset))
                    direction = _reproductive_direction(
                        azimuth + instance.rotation_deg,
                        angle,
                    )
                    pedicel_end = _add(
                        origin,
                        _mul(
                            direction,
                            unit.pedicel.length_cm
                            * CM_TO_SCENE_UNIT
                            * instance.scale,
                        ),
                    )
                    calyx_length = (
                        unit.calyx.length_cm
                        * CM_TO_SCENE_UNIT
                        * instance.scale
                    )
                    from .reproductive_orientation import organ_direction
                    distal_direction = organ_direction(unit, direction)
                    # organ_direction is stored in plant coordinates; this
                    # layout rotates plants only about the gravity axis.
                    if "reproductive_orientation" in unit.provenance:
                        turn = math.radians(instance.rotation_deg)
                        x, y, z = distal_direction
                        distal_direction = (x*math.cos(turn)-y*math.sin(turn), x*math.sin(turn)+y*math.cos(turn), z)
                    calyx_center = _add(
                        pedicel_end,
                        _mul(distal_direction, calyx_length * 0.50),
                    )
                    items = [
                        SpatialItem(
                            id=(
                                f"reproductive:{instance.plant_id}:"
                                f"{unit.pedicel.id}"
                            ),
                            plant_id=instance.plant_id,
                            organ_type="stem",
                            start=origin,
                            end=pedicel_end,
                            radius=0.018,
                            source_id=unit.pedicel.id,
                        ),
                        SpatialItem(
                            id=(
                                f"reproductive:{instance.plant_id}:"
                                f"{unit.calyx.id}"
                            ),
                            plant_id=instance.plant_id,
                            organ_type="calyx",
                            start=calyx_center,
                            end=calyx_center,
                            radius=max(
                                unit.calyx.radius_cm
                                * CM_TO_SCENE_UNIT
                                * instance.scale,
                                unit.calyx.radius_cm
                                * CM_TO_SCENE_UNIT
                                * instance.scale
                                * unit.calyx.inflation
                                * 1.04,
                                calyx_length * 0.53,
                            ),
                            source_id=unit.calyx.id,
                        ),
                    ]
                    contacts: list[Any] = []
                    for item_index, item in enumerate(items):
                        contacts.extend(
                            result
                            for result in occupancy.query(item)
                            if not (
                                item_index == 0
                                and _is_attachment_contact(
                                    result,
                                    occupancy,
                                    instance.plant_id,
                                    origin,
                                )
                            )
                            and (
                                shared_occupancy
                                or _contact_same_plant_or_support(
                                    result,
                                    occupancy,
                                    instance.plant_id,
                                )
                            )
                        )
                    hard = sum(
                        result.policy == "hard_occupancy"
                        and result.classification
                        in {"proxy_conflict", "clearance_violation"}
                        for result in contacts
                    )
                    deformation = (
                        abs(azimuth_offset) / 100.0
                        + abs(angle_offset) / 56.0
                    )
                    candidates.append(
                        (
                            (float(hard), deformation),
                            azimuth,
                            angle,
                            items,
                            contacts,
                        )
                    )
            score, azimuth, angle, items, contacts = min(
                candidates,
                key=lambda item: item[0],
            )
            if score[0] > 0.0:
                if node.axillary_bud is not None:
                    node.axillary_bud.state = "dormant"
                    node.axillary_bud.reproductive_unit_id = None
                    node.axillary_bud.decision = (
                        "cancelled_hard_clearance"
                    )
                node.reproductive_unit = None
                decisions.append(
                    {
                        "plant_id": instance.plant_id,
                        "reproductive_unit_id": unit.id,
                        "pedicel_id": unit.pedicel.id,
                        "status": "cancelled_hard_clearance",
                        "preferred_azimuth_deg": preferred_azimuth,
                        "preferred_angle_deg": preferred_angle,
                        "hard_conflict_count": int(score[0]),
                        "contacts": [
                            item.to_dict() for item in contacts
                        ],
                    }
                )
                continue
            unit.pedicel.azimuth_deg = round(azimuth, 3)
            unit.pedicel.angle_deg = round(angle, 3)
            unit.pedicel.orientation_adjustment_deg = round(
                math.hypot(
                    _signed_angle_delta(preferred_azimuth, azimuth),
                    angle - preferred_angle,
                ),
                4,
            )
            for item in items:
                occupancy.add(item)
            decisions.append(
                {
                    "plant_id": instance.plant_id,
                    "reproductive_unit_id": unit.id,
                    "pedicel_id": unit.pedicel.id,
                    "status": "accepted",
                    "preferred_azimuth_deg": preferred_azimuth,
                    "applied_azimuth_deg": unit.pedicel.azimuth_deg,
                    "preferred_angle_deg": preferred_angle,
                    "applied_angle_deg": unit.pedicel.angle_deg,
                    "adjustment_deg": unit.pedicel.orientation_adjustment_deg,
                    "hard_conflict_count": int(score[0]),
                    "contacts": [item.to_dict() for item in contacts],
                }
            )
    return decisions


def _root_only_copy(plant: Plant) -> Plant:
    active = deepcopy(plant)
    for axis in active.axes:
        axis.child_axes = []
    return active


def _index_potential_axes(
    plants: dict[str, Plant],
) -> tuple[dict[str, dict[str, Axis]], dict[str, dict[str, str]]]:
    axes_by_plant: dict[str, dict[str, Axis]] = {}
    parent_by_plant: dict[str, dict[str, str]] = {}
    for plant_id, plant in plants.items():
        axes: dict[str, Axis] = {}
        parents: dict[str, str] = {}
        for root in plant.axes:
            for axis, parent_axis_id in _walk_axes_with_parent(root):
                axes[axis.id] = axis
                if parent_axis_id is not None:
                    parents[axis.id] = parent_axis_id
        axes_by_plant[plant_id] = axes
        parent_by_plant[plant_id] = parents
    return axes_by_plant, parent_by_plant


def _walk_axes(axes: Iterable[Axis]) -> Iterable[Axis]:
    for axis in axes:
        yield axis
        yield from _walk_axes(axis.child_axes)


def _walk_axes_with_parent(
    axis: Axis,
    parent_axis_id: str | None = None,
) -> Iterable[tuple[Axis, str | None]]:
    yield axis, parent_axis_id
    for child in axis.child_axes:
        yield from _walk_axes_with_parent(child, axis.id)


def _attach_axis(plant: Plant, parent_axis_id: str, child: Axis) -> None:
    for axis in _walk_axes(plant.axes):
        if axis.id == parent_axis_id:
            axis.child_axes.append(child)
            axis.child_axes.sort(key=lambda item: item.id)
            return
    raise KeyError(f"Active parent axis not found: {parent_axis_id}")


def _record_bud_decision(
    plant: Plant,
    proposal: GrowthProposal,
    decision: ProposalDecision,
) -> None:
    for axis in _walk_axes(plant.axes):
        for node in axis.nodes:
            if node.id != proposal.parent_node_id or node.axillary_bud is None:
                continue
            node.axillary_bud.decision = decision.status
            if decision.status in {"cancelled", "deferred"}:
                node.axillary_bud.state = "dormant"
                node.axillary_bud.branch_id = None
            return


def _node_frames(
    plant: Plant,
    instance: PlantInstance,
) -> dict[str, tuple[Vec3, Vec3]]:
    frames: dict[str, tuple[Vec3, Vec3]] = {}

    def visit(axis: Axis, start: Vec3, parent_direction: Vec3) -> None:
        direction = (
            _rotate_about_vertical(
                tuple(axis.resolved_direction),
                instance.rotation_deg,
            )
            if axis.resolved_direction is not None
            else _axis_direction(
                parent_direction,
                axis.azimuth_deg + instance.rotation_deg,
                axis.branch_angle_deg,
            )
        )
        current = start
        for index, internode in enumerate(axis.internodes):
            direction = _bend_direction(
                direction,
                internode.bend_azimuth_deg + instance.rotation_deg,
                internode.bend_angle_deg,
            )
            end = _add(
                current,
                _mul(
                    direction,
                    internode.length_cm * CM_TO_SCENE_UNIT * instance.scale,
                ),
            )
            if index < len(axis.nodes):
                frames[axis.nodes[index].id] = (end, direction)
            current = end
        for child in axis.child_axes:
            frame = frames.get(child.parent_node_id or "")
            if frame is not None:
                visit(child, frame[0], frame[1])

    base = instance.position
    root_direction = _rotate_about_vertical(
        _normalise((0.05, -0.03, 1.0)),
        instance.rotation_deg,
    )
    for root in plant.axes:
        visit(root, base, root_direction)
    return frames


def _add_axis_items(
    occupancy: SpatialOccupancy,
    plant_id: str,
    instance: PlantInstance,
    axes: Iterable[Axis],
    *,
    start_override: Vec3 | None = None,
    parent_direction_override: Vec3 | None = None,
) -> None:
    def visit(axis: Axis, start: Vec3, parent_direction: Vec3) -> None:
        direction = (
            parent_direction
            if parent_direction_override is not None and axis.id == next_axis_id
            else (
                _rotate_about_vertical(
                    tuple(axis.resolved_direction),
                    instance.rotation_deg,
                )
                if axis.resolved_direction is not None
                else _axis_direction(
                    parent_direction,
                    axis.azimuth_deg + instance.rotation_deg,
                    axis.branch_angle_deg,
                )
            )
        )
        current = start
        frames: dict[str, tuple[Vec3, Vec3]] = {}
        for index, internode in enumerate(axis.internodes):
            direction = _bend_direction(
                direction,
                internode.bend_azimuth_deg + instance.rotation_deg,
                internode.bend_angle_deg,
            )
            end = _add(
                current,
                _mul(
                    direction,
                    internode.length_cm * CM_TO_SCENE_UNIT * instance.scale,
                ),
            )
            item_id = f"axis:{plant_id}:{internode.id}"
            if item_id not in {item.id for item in occupancy.items}:
                occupancy.add(
                    SpatialItem(
                        id=item_id,
                        plant_id=plant_id,
                        organ_type="stem",
                        start=current,
                        end=end,
                        radius=max(
                            internode.radius_cm
                            * CM_TO_SCENE_UNIT
                            * instance.scale,
                            0.008,
                        )
                        + (0.050 if axis.order == 0 else 0.075),
                        source_id=internode.id,
                    )
                )
            if index < len(axis.nodes):
                frames[axis.nodes[index].id] = (end, direction)
            current = end
        for child in axis.child_axes:
            frame = frames.get(child.parent_node_id or "")
            if frame is not None:
                visit(child, frame[0], frame[1])

    axes = list(axes)
    if not axes:
        return
    next_axis_id = axes[0].id
    for axis in axes:
        visit(
            axis,
            start_override if start_override is not None else instance.position,
            parent_direction_override
            if parent_direction_override is not None
            else _rotate_about_vertical(
                _normalise((0.05, -0.03, 1.0)),
                instance.rotation_deg,
            ),
        )


def _add_support_items(
    scene: CultivationScene,
    occupancy: SpatialOccupancy,
) -> None:
    system = scene.support_system
    if system is not None and system.enabled:
        for post in system.posts:
            occupancy.add(
                SpatialItem(
                    id=f"support:{post.id}",
                    plant_id="support",
                    organ_type="support_post",
                    start=post.position,
                    end=(post.position[0], post.position[1], post.position[2] + post.height),
                    radius=math.hypot(
                        post.section_width * 0.5,
                        post.section_depth * 0.5,
                    ),
                    source_id=post.id,
                )
            )
        for line in system.lines:
            occupancy.add(
                SpatialItem(
                    id=f"support:{line.id}",
                    plant_id="support",
                    organ_type="support_line",
                    start=line.start,
                    end=line.end,
                    radius=line.radius,
                    intentional_contact=True,
                    source_id=line.id,
                )
            )
        for tie in system.ties:
            occupancy.add(
                SpatialItem(
                    id=f"support:{tie.id}",
                    plant_id=tie.plant_id,
                    organ_type="support_tie",
                    start=tie.start,
                    end=tie.end,
                    radius=0.008,
                    intentional_contact=True,
                    source_id=tie.id,
                )
            )
    for support in scene.supports:
        occupancy.add(
            SpatialItem(
                id=f"support:{support.support_id}",
                plant_id=support.plant_id,
                organ_type="support_post",
                start=support.position,
                end=(
                    support.position[0],
                    support.position[1],
                    support.position[2] + support.height,
                ),
                radius=math.hypot(
                    support.section_width * 0.5,
                    support.section_depth * 0.5,
                ),
                source_id=support.support_id,
            )
        )


def _register_support_contact(
    scene: CultivationScene,
    proposal: GrowthProposal,
    decision: ProposalDecision,
    axis: Axis,
) -> None:
    system = scene.support_system
    if system is None or not system.enabled or decision.applied_direction is None:
        return
    contacts = [
        item
        for item in decision.contacts
        if item.get("classification") == "intentional_contact"
    ]
    for index, contact in enumerate(contacts):
        other_id = (
            contact["item_b"]
            if contact["item_a"].startswith("proposal:")
            else contact["item_a"]
        )
        support_element_id = other_id.removeprefix("support:")
        contact_id = f"{proposal.plant_id}:{proposal.axis_id}:support_contact_{index}"
        system.contacts.append(
            SupportContact(
                id=contact_id,
                plant_id=proposal.plant_id,
                organ_id=proposal.axis_id,
                support_element_id=support_element_id,
                point=proposal.origin,
            )
        )
        axis.support_contacts.append(contact_id)


def _contact_same_plant_or_support(
    evaluation: Any,
    occupancy: SpatialOccupancy,
    plant_id: str,
) -> bool:
    lookup = {item.id: item for item in occupancy.items}
    other = lookup.get(evaluation.item_b) or lookup.get(evaluation.item_a)
    return other is not None and other.plant_id in {plant_id, "support"}


def _is_attachment_contact(
    evaluation: Any,
    occupancy: SpatialOccupancy,
    plant_id: str,
    origin: Vec3,
) -> bool:
    """Ignore the intended joint where a new organ leaves its parent axis."""
    lookup = {item.id: item for item in occupancy.items}
    other = lookup.get(evaluation.item_b)
    if other is None or other.plant_id != plant_id or other.organ_type != "stem":
        return False
    return min(
        _length(_sub(origin, other.start)),
        _length(_sub(origin, other.end)),
    ) <= max(0.045, other.radius * 2.2)


def _colonization_direction(
    direction: Vec3,
    origin: Vec3,
    occupancy: SpatialOccupancy,
    proposal: GrowthProposal,
) -> Vec3:
    """Small, bounded free-space steering inspired by space colonization."""
    repulsion = (0.0, 0.0, 0.0)
    for item in occupancy.items:
        midpoint = _mul(_add(item.start, item.end), 0.5)
        offset = _sub(origin, midpoint)
        distance = _length(offset)
        if distance <= 1e-9 or distance > 0.75:
            continue
        repulsion = _add(
            repulsion,
            _mul(_normalise(offset), (0.75 - distance) / 0.75),
        )
    if _length(repulsion) <= 1e-9:
        return direction
    return _normalise(_add(_mul(direction, 0.82), _mul(_normalise(repulsion), 0.18)))


def _trellis_training_cost(
    proposal: GrowthProposal,
    direction: Vec3,
    occupancy: SpatialOccupancy,
    scene: CultivationScene,
    instance: PlantInstance,
    light_options: dict[str, Any],
) -> tuple[float, str, Vec3]:
    """Favor stratum expansion before bounded upward trellis guidance.

    This is an explicit crop-training heuristic. It is not presented as a
    measured tropic response of *Physalis peruviana*.
    """
    training = light_options.get("trellis_training", {})
    radius_by_stratum = training.get("target_radius_by_stratum", {})
    stratum_name = {
        "lower_canopy": "lower",
        "mid_canopy": "middle",
        "upper_canopy": "upper",
    }.get(proposal.target_region, "middle")
    target_radius = float(radius_by_stratum.get(stratum_name, 0.68))
    completion_fraction = float(
        training.get("expansion_completion_fraction", {}).get("value", 0.82)
    )
    current_reach = _existing_stratum_reach(
        occupancy,
        instance,
        stratum_name,
        light_options,
    )
    guidance_weight = float(
        training.get("guidance_cost_weight", {}).get("value", 1.45)
    )
    if current_reach < target_radius * completion_fraction:
        arm_count = max(
            1,
            int(training.get("arm_count", {}).get("value", 3)),
        )
        unit_noise = (
            _stable_noise(
                proposal.plant_id,
                proposal.axis_id,
                "inverted_tripod_arm",
            )
            + 1.0
        ) * 0.5
        arm_index = min(arm_count - 1, int(unit_noise * arm_count))
        arm_azimuth = (
            instance.rotation_deg
            + arm_index * (360.0 / arm_count)
        )
        vertical = float(
            training.get("expansion_vertical_component", {}).get(
                "value",
                0.38,
            )
        )
        target = _normalise(
            (
                math.cos(math.radians(arm_azimuth)),
                math.sin(math.radians(arm_azimuth)),
                vertical,
            )
        )
        phase = "stratum_expansion"
    else:
        target = _upper_trellis_target(
            scene,
            proposal.origin,
            instance,
        )
        phase = "apical_lift_to_trellis"
    alignment_cost = max(0.0, 1.0 - _dot(direction, target))
    return alignment_cost * guidance_weight, phase, target


def _existing_stratum_reach(
    occupancy: SpatialOccupancy,
    instance: PlantInstance,
    stratum_name: str,
    light_options: dict[str, Any],
) -> float:
    strata = {
        str(item.get("name")): item
        for item in light_options.get("strata", [])
        if isinstance(item, dict)
    }
    active = strata.get(stratum_name, {})
    minimum = float(active.get("min_height", 0.0))
    maximum = float(active.get("max_height", math.inf))
    reach = 0.0
    for item in occupancy.items:
        if item.plant_id != instance.plant_id or item.organ_type != "stem":
            continue
        for point in (item.start, item.end):
            if not minimum <= point[2] < maximum:
                continue
            reach = max(
                reach,
                math.hypot(
                    point[0] - instance.position[0],
                    point[1] - instance.position[1],
                ),
            )
    return reach


def _upper_trellis_target(
    scene: CultivationScene,
    origin: Vec3,
    instance: PlantInstance,
) -> Vec3:
    system = scene.support_system
    candidates: list[tuple[float, Vec3]] = []
    if system is not None and system.enabled:
        for line in system.lines:
            point = _closest_point_on_segment(origin, line.start, line.end)
            if point[2] <= origin[2] + 0.04:
                continue
            candidates.append((_length(_sub(point, origin)), point))
    if candidates:
        _distance, point = min(candidates, key=lambda item: item[0])
        support_direction = _normalise(_sub(point, origin))
        return _normalise(
            _add(
                _mul((0.0, 0.0, 1.0), 0.72),
                _mul(support_direction, 0.28),
            )
        )
    inward = _normalise(
        (
            instance.position[0] - origin[0],
            instance.position[1] - origin[1],
            0.0,
        )
    )
    return _normalise(
        _add(
            _mul((0.0, 0.0, 1.0), 0.86),
            _mul(inward, 0.14),
        )
    )


def _closest_point_on_segment(point: Vec3, start: Vec3, end: Vec3) -> Vec3:
    segment = _sub(end, start)
    denominator = _dot(segment, segment)
    if denominator <= 1e-12:
        return start
    amount = max(
        0.0,
        min(1.0, _dot(_sub(point, start), segment) / denominator),
    )
    return _add(start, _mul(segment, amount))


def _fit_local_axis_angles(
    world_direction: Vec3,
    parent_direction: Vec3,
    instance: PlantInstance,
    *,
    initial_azimuth: float,
    initial_angle: float,
) -> tuple[float, float]:
    """Invert the grammar's parent-relative branch direction numerically."""
    azimuth = initial_azimuth % 360.0
    angle = max(0.0, min(88.0, initial_angle))
    azimuth_step = 36.0
    angle_step = 18.0
    for _ in range(7):
        candidates: list[tuple[float, float, float]] = []
        for azimuth_delta in (-azimuth_step, 0.0, azimuth_step):
            for angle_delta in (-angle_step, 0.0, angle_step):
                candidate_azimuth = (azimuth + azimuth_delta) % 360.0
                candidate_angle = max(
                    0.0,
                    min(88.0, angle + angle_delta),
                )
                candidate_direction = _axis_direction(
                    parent_direction,
                    candidate_azimuth + instance.rotation_deg,
                    candidate_angle,
                )
                candidates.append(
                    (
                        _angle_deg(
                            world_direction,
                            candidate_direction,
                        ),
                        candidate_azimuth,
                        candidate_angle,
                    )
                )
        _, azimuth, angle = min(
            candidates,
            key=lambda item: (item[0], item[1], item[2]),
        )
        azimuth_step *= 0.5
        angle_step *= 0.5
    return round(azimuth, 3), round(angle, 3)


def _axis_direction(
    parent: Vec3,
    azimuth_deg: float,
    angle_deg: float,
) -> Vec3:
    if abs(angle_deg) < 1e-9:
        return _normalise(parent)
    angle = math.radians(angle_deg)
    azimuth = math.radians(azimuth_deg)
    radial = (math.cos(azimuth), math.sin(azimuth), 0.0)
    return _normalise(
        _add(_mul(parent, math.cos(angle)), _mul(radial, math.sin(angle)))
    )


def _leaf_direction(azimuth_deg: float, insertion_angle_deg: float) -> Vec3:
    """Match the leaf direction used by ``blender_geometry``."""
    azimuth = math.radians(azimuth_deg)
    insertion = math.radians(insertion_angle_deg)
    return _normalise(
        (
            math.cos(azimuth) * math.sin(insertion),
            math.sin(azimuth) * math.sin(insertion),
            math.cos(insertion),
        )
    )


def _bend_direction(direction: Vec3, azimuth_deg: float, angle_deg: float) -> Vec3:
    return _axis_direction(direction, azimuth_deg, angle_deg)


def _rotate_about_vertical(direction: Vec3, angle_deg: float) -> Vec3:
    angle = math.radians(angle_deg)
    return _normalise(
        (
            direction[0] * math.cos(angle) - direction[1] * math.sin(angle),
            direction[0] * math.sin(angle) + direction[1] * math.cos(angle),
            direction[2],
        )
    )


def _reproductive_direction(
    azimuth_deg: float,
    angle_deg: float,
) -> Vec3:
    azimuth = math.radians(azimuth_deg)
    angle = math.radians(max(5.0, min(72.0, angle_deg)))
    return _normalise(
        (
            math.cos(azimuth) * math.cos(angle),
            math.sin(azimuth) * math.cos(angle),
            -math.sin(angle),
        )
    )


def _stable_noise(*parts: Any) -> float:
    digest = hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    return value * 2.0 - 1.0


def _signed_angle_delta(left: float, right: float) -> float:
    return (right - left + 180.0) % 360.0 - 180.0


def _angle_deg(left: Vec3, right: Vec3) -> float:
    return math.degrees(
        math.acos(max(-1.0, min(1.0, _dot(_normalise(left), _normalise(right)))))
    )


def _dot(left: Vec3, right: Vec3) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _add(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] + right[index] for index in range(3))


def _sub(left: Vec3, right: Vec3) -> Vec3:
    return tuple(left[index] - right[index] for index in range(3))


def _mul(value: Vec3, amount: float) -> Vec3:
    return tuple(item * amount for item in value)


def _length(value: Vec3) -> float:
    return math.sqrt(_dot(value, value))


def _normalise(value: Vec3) -> Vec3:
    length = _length(value)
    if length <= 1e-12:
        return (0.0, 0.0, 1.0)
    return tuple(item / length for item in value)
