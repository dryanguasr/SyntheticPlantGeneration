"""Serializable morphology data model for uchuva plants.

This module is intentionally independent from Blender. It represents the
botanical structure first: axes, internodes, nodes, leaves, axillary buds,
pedicels, calyxes, and fruits.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any


def _to_plain_value(value: Any) -> Any:
    """Convert nested dataclasses and containers into JSON-ready values."""
    if is_dataclass(value):
        return {
            field_name: _to_plain_value(field_value)
            for field_name, field_value in value.__dict__.items()
        }
    if isinstance(value, list):
        return [_to_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_plain_value(item) for key, item in value.items()}
    return value


class SerializableMixin:
    """Mixin for dataclasses that need explicit JSON serialization."""

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_value(self)


@dataclass
class Internode(SerializableMixin):
    """Stem segment between two nodes."""

    id: str
    order: int
    length_cm: float
    radius_cm: float
    bend_angle_deg: float = 0.0
    bend_azimuth_deg: float = 0.0
    pigmentation: float = 0.0
    parameter_status: str = "manual_initial_guess"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Leaf(SerializableMixin):
    """Leaf associated with a node."""

    id: str
    node_id: str
    length_cm: float
    width_cm: float
    petiole_length_cm: float
    shape: str = "ovate"
    margin: str = "variable"
    insertion_angle_deg: float = 45.0
    azimuth_deg: float = 0.0
    curl: float = 0.0
    twist_deg: float = 0.0
    edge_damage: float = 0.0
    senescence: float = 0.0
    pubescence: float = 0.5
    parameter_status: str = "manual_initial_guess"
    preferred_insertion_angle_deg: float | None = None
    preferred_azimuth_deg: float | None = None
    orientation_adjustment_deg: float = 0.0
    orientation_cost_terms: dict[str, float] = field(default_factory=dict)
    clearance_lift_cm: float = 0.0
    clearance_lift_reason: str | None = None
    canopy_stratum: str = "unassigned"
    daily_light_interception_proxy: float | None = None
    projected_coverage_gain: float | None = None
    intraspecific_shading_fraction: float = 0.0
    interspecific_shading_fraction: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    # Engineering shape control; independent of fine surface texture.
    transverse_arch_ratio: float = 0.0


@dataclass
class Pedicel(SerializableMixin):
    """Connection between an axil/node and a reproductive unit."""

    id: str
    node_id: str
    length_cm: float
    angle_deg: float
    azimuth_deg: float = 0.0
    connects_from: str = "axil"
    connects_to: str | None = None
    parameter_status: str = "manual_initial_guess"
    orientation_adjustment_deg: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Calyx(SerializableMixin):
    """Persistent inflated calyx/capacho associated with flowers or fruits."""

    id: str
    length_cm: float
    radius_cm: float
    inflated: bool = True
    covers_fruit_fraction: float = 0.8
    ribs: int = 6
    openness: float = 0.08
    inflation: float = 1.0
    state: str = "inflated_green"
    material_key: str = "calyx_inflated_green"
    profile: str = "lantern_squash"
    tip_length_ratio: float = 0.12
    wrinkle: float = 0.0
    asymmetry: float = 0.0
    pubescence: float = 0.5
    texture_variant: str = "calyx_green_v0"
    vein_contrast: float = 0.5
    apical_darkening: float = 0.0
    maturity_progress: float = 0.0
    projected_area_scale: float = 1.0
    circularity_target: float | None = None
    turgor: float = 1.0
    parameter_status: str = "manual_initial_guess"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Fruit(SerializableMixin):
    """Cape gooseberry fruit inside, hidden by, or exposed from the calyx."""

    id: str
    radius_cm: float
    maturity_stage: str
    visibility: str = "partially_visible"
    parameter_status: str = "manual_initial_guess"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReproductiveUnit(SerializableMixin):
    """Solitary axillary flower or fruit plus its pedicel/calyx context."""

    id: str
    node_id: str
    stage: str
    pedicel: Pedicel
    fruit_visibility: str | None = None
    maturity: str | None = None
    calyx_state: str | None = None
    calyx: Calyx | None = None
    fruit: Fruit | None = None
    phenology_model: str = "legacy_independent"
    flowering_cohort: int | None = None
    estimated_days_after_anthesis: float | None = None
    days_after_anthesis_range: tuple[float, float] | None = None
    bbch_principal_stage: int | None = None
    ontogenetic_rank: float | None = None
    parameter_status: str = "manual_initial_guess"
    synthetic_reference_grade: int | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class AxillaryBud(SerializableMixin):
    """Axillary bud state at a node."""

    id: str
    node_id: str
    order: int
    state: str = "dormant"
    branch_id: str | None = None
    reproductive_unit_id: str | None = None
    vigor: float = 1.0
    development_step: int = 0
    remaining_length_budget_cm: float = 0.0
    decision: str = "unresolved"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Node(SerializableMixin):
    """A node carrying a leaf, an axillary bud, and optional reproduction."""

    id: str
    order: int
    age: int
    position_index: int
    leaf: Leaf | None = None
    axillary_bud: AxillaryBud | None = None
    reproductive_unit: ReproductiveUnit | None = None


@dataclass
class Axis(SerializableMixin):
    """Main axis or lateral branch."""

    id: str
    order: int
    parent_node_id: str | None = None
    branch_angle_deg: float = 0.0
    azimuth_deg: float = 0.0
    internodes: list[Internode] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    child_axes: list["Axis"] = field(default_factory=list)
    apex_age: int = 0
    vigor: float = 1.0
    reproductive_load: float = 0.0
    neighbor_influence: float = 0.0
    support_influence: float = 0.0
    mechanical_deflection_deg: float = 0.0
    growth_budget_length_cm: float = 0.0
    remaining_budget_length_cm: float = 0.0
    max_internodes: int = 0
    development_step: int = 0
    correlated_noise_phase: float = 0.0
    resolved_direction: tuple[float, float, float] | None = None
    canopy_stratum: str = "unassigned"
    training_phase: str = "unmodeled"
    training_target_direction: tuple[float, float, float] | None = None
    support_contacts: list[str] = field(default_factory=list)
    growth_events: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plant(SerializableMixin):
    """Full morphology tree for one generated uchuva plant."""

    species: str
    common_name: str
    seed: int
    script_version: str
    parameter_preset: str
    condition: str = "healthy"
    axes: list[Axis] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.2"

    def node_count(self) -> int:
        return sum(_count_axis_nodes(axis) for axis in self.axes)

    def reproductive_unit_count(self) -> int:
        return sum(_count_axis_reproductive_units(axis) for axis in self.axes)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Plant":
        """Deserialize current or additive legacy morphology JSON."""
        plant_values = _filtered_values(cls, payload, exclude={"axes"})
        plant_values["axes"] = [_axis_from_dict(item) for item in payload.get("axes", [])]
        return cls(**plant_values)


def _count_axis_nodes(axis: Axis) -> int:
    return len(axis.nodes) + sum(_count_axis_nodes(child) for child in axis.child_axes)


def _count_axis_reproductive_units(axis: Axis) -> int:
    own_count = sum(1 for node in axis.nodes if node.reproductive_unit is not None)
    return own_count + sum(
        _count_axis_reproductive_units(child) for child in axis.child_axes
    )


def _filtered_values(
    cls: type[Any],
    payload: dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    excluded = exclude or set()
    accepted = {item.name for item in fields(cls)} - excluded
    return {key: value for key, value in payload.items() if key in accepted}


def _axis_from_dict(payload: dict[str, Any]) -> Axis:
    values = _filtered_values(
        Axis,
        payload,
        exclude={"internodes", "nodes", "child_axes"},
    )
    values["internodes"] = [
        Internode(**_filtered_values(Internode, item))
        for item in payload.get("internodes", [])
    ]
    values["nodes"] = [_node_from_dict(item) for item in payload.get("nodes", [])]
    values["child_axes"] = [
        _axis_from_dict(item) for item in payload.get("child_axes", [])
    ]
    return Axis(**values)


def _node_from_dict(payload: dict[str, Any]) -> Node:
    values = _filtered_values(
        Node,
        payload,
        exclude={"leaf", "axillary_bud", "reproductive_unit"},
    )
    leaf = payload.get("leaf")
    bud = payload.get("axillary_bud")
    unit = payload.get("reproductive_unit")
    values["leaf"] = (
        Leaf(**_filtered_values(Leaf, leaf)) if isinstance(leaf, dict) else None
    )
    values["axillary_bud"] = (
        AxillaryBud(**_filtered_values(AxillaryBud, bud))
        if isinstance(bud, dict)
        else None
    )
    values["reproductive_unit"] = (
        _reproductive_unit_from_dict(unit) if isinstance(unit, dict) else None
    )
    return Node(**values)


def _reproductive_unit_from_dict(payload: dict[str, Any]) -> ReproductiveUnit:
    values = _filtered_values(
        ReproductiveUnit,
        payload,
        exclude={"pedicel", "calyx", "fruit"},
    )
    values["pedicel"] = Pedicel(
        **_filtered_values(Pedicel, payload.get("pedicel", {}))
    )
    calyx = payload.get("calyx")
    fruit = payload.get("fruit")
    values["calyx"] = (
        Calyx(**_filtered_values(Calyx, calyx)) if isinstance(calyx, dict) else None
    )
    values["fruit"] = (
        Fruit(**_filtered_values(Fruit, fruit)) if isinstance(fruit, dict) else None
    )
    return ReproductiveUnit(**values)
