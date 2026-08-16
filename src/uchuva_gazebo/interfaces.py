"""Pure Gazebo export plans derived from the serializable morphology tree.

The module defines a stable hand-off for the planned Gazebo spikes.  It does
not emit SDF yet because the current morphology tree intentionally contains no
measured world poses, masses, stiffnesses, or detachment thresholds.  Those
values must remain explicit engineering heuristics or to-be-measured inputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from uchuva_lsystem.morphology import Axis, Plant, SerializableMixin


GAZEBO_EXPORT_SCHEMA_VERSION = "0.1"
VALID_LODS = (0, 1, 2)
CONTACT_POLICY_MAPPING = {
    "hard_occupancy": "physical_collider",
    "soft_occupancy": "simplified_or_soft_contact",
    "visual_occlusion": "visual_only",
    "intentional_support": "trellis_constraint",
    "near_contact": "diagnostic_only",
}


@dataclass(frozen=True)
class GazeboExportConfig(SerializableMixin):
    """Configuration of a non-runtime Gazebo interpretation plan."""

    lod: int = 1
    visual_representation: str = "simplified_procedural_mesh"
    physics_parameter_status: str = "engineering_heuristic"
    detachment_parameter_status: str = "to_be_measured"
    schema_version: str = GAZEBO_EXPORT_SCHEMA_VERSION

    def validate(self) -> None:
        if self.lod not in VALID_LODS:
            raise ValueError(f"lod must be one of {VALID_LODS}, got {self.lod!r}")
        if self.physics_parameter_status not in {
            "engineering_heuristic",
            "to_be_measured",
        }:
            raise ValueError("physics_parameter_status must declare uncertainty")
        if self.detachment_parameter_status not in {
            "engineering_heuristic",
            "to_be_measured",
        }:
            raise ValueError("detachment_parameter_status must declare uncertainty")


@dataclass(frozen=True)
class GazeboVisualItem(SerializableMixin):
    """A visual element and its semantic identity for simulated sensors."""

    id: str
    source_morphology_id: str
    kind: str
    semantic_class: str
    semantic_role: str


@dataclass(frozen=True)
class GazeboPhysicsItem(SerializableMixin):
    """A deliberately simplified future physical element."""

    id: str
    source_morphology_id: str
    kind: str
    contact_policy: str
    parameter_status: str
    parent_id: str | None = None
    detachable: bool = False


@dataclass
class GazeboExportPlan(SerializableMixin):
    """Portable plan consumed later by an SDF writer or Gazebo integration."""

    source_species: str
    source_seed: int
    source_schema_version: str
    config: GazeboExportConfig
    visual_items: list[GazeboVisualItem] = field(default_factory=list)
    physics_items: list[GazeboPhysicsItem] = field(default_factory=list)
    contact_policy_mapping: dict[str, str] = field(
        default_factory=lambda: dict(CONTACT_POLICY_MAPPING)
    )
    limitations: tuple[str, ...] = (
        "No SDF is emitted in the reorganisation spike.",
        "World poses and physical coefficients are not inferred from morphology.",
        "Leaves remain visual-only in LOD 0, 1 and 2.",
    )
    schema_version: str = GAZEBO_EXPORT_SCHEMA_VERSION


def build_gazebo_export_plan(
    plant: Plant,
    config: GazeboExportConfig | None = None,
) -> GazeboExportPlan:
    """Map a ``Plant`` to a deterministic Gazebo-facing semantic plan.

    The plan preserves IDs for RGB, depth, segmentation, boxes, and future
    attachment/detachment logic while keeping the physical model intentionally
    simple and explicitly uncertain.
    """
    active_config = config or GazeboExportConfig()
    active_config.validate()
    plan = GazeboExportPlan(
        source_species=plant.species,
        source_seed=plant.seed,
        source_schema_version=plant.schema_version,
        config=active_config,
    )
    for axis in _walk_axes(plant.axes):
        _append_axis_items(plan, axis, active_config)
    return plan


def write_gazebo_export_plan(plan: GazeboExportPlan, output_path: str | Path) -> Path:
    """Write a UTF-8 JSON plan without requiring Blender or Gazebo."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _walk_axes(axes: Iterable[Axis]) -> Iterable[Axis]:
    for axis in axes:
        yield axis
        yield from _walk_axes(axis.child_axes)


def _append_axis_items(
    plan: GazeboExportPlan,
    axis: Axis,
    config: GazeboExportConfig,
) -> None:
    for internode in axis.internodes:
        plan.visual_items.append(
            GazeboVisualItem(
                id=f"visual_{internode.id}",
                source_morphology_id=internode.id,
                kind="stem",
                semantic_class="background",
                semantic_role="plant_structure",
            )
        )
        if config.lod >= 1:
            plan.physics_items.append(
                GazeboPhysicsItem(
                    id=f"collider_{internode.id}",
                    source_morphology_id=internode.id,
                    kind="cylinder_link",
                    contact_policy="hard_occupancy",
                    parameter_status=config.physics_parameter_status,
                    parent_id=axis.parent_node_id,
                )
            )
    for node in axis.nodes:
        if node.leaf is not None:
            plan.visual_items.append(
                GazeboVisualItem(
                    id=f"visual_{node.leaf.id}",
                    source_morphology_id=node.leaf.id,
                    kind="leaf",
                    semantic_class="background",
                    semantic_role="visual_only",
                )
            )
        unit = node.reproductive_unit
        if unit is None or unit.calyx is None:
            continue
        plan.visual_items.append(
            GazeboVisualItem(
                id=f"visual_{unit.calyx.id}",
                source_morphology_id=unit.calyx.id,
                kind="calyx",
                semantic_class="calyx",
                semantic_role="target",
            )
        )
        if config.lod == 2:
            plan.physics_items.extend(
                (
                    GazeboPhysicsItem(
                        id=f"collider_{unit.calyx.id}",
                        source_morphology_id=unit.calyx.id,
                        kind="simplified_calyx_collider",
                        contact_policy="soft_occupancy",
                        parameter_status=config.physics_parameter_status,
                        parent_id=unit.pedicel.id,
                    ),
                    GazeboPhysicsItem(
                        id=f"joint_{unit.pedicel.id}",
                        source_morphology_id=unit.pedicel.id,
                        kind="detachable_pedicel_joint",
                        contact_policy="hard_occupancy",
                        parameter_status=config.detachment_parameter_status,
                        parent_id=node.id,
                        detachable=True,
                    ),
                )
            )
