"""Scene-level data structures for cultivation and canopy composition.

The plant L-System remains an individual plant model. This module reserves the
upper layer that will later compose multiple plant instances into rows, beds,
and partially occluding canopies.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .morphology import SerializableMixin
from .support import SupportSystem, build_continuous_trellis


@dataclass
class PlantInstance(SerializableMixin):
    """Placement and agronomic state for one plant in a cultivation scene."""

    plant_id: str
    seed: int
    role: str = "neighbor"
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_deg: float = 0.0
    scale: float = 1.0
    age: str = "to_be_measured"
    phenological_stage: str = "mixed"
    vigor: float = 1.0
    condition: str = "healthy"
    pruning_mode: str = "unmodeled"
    training_mode: str = "individual_stake_with_ties"
    placement_retries: int = 0
    collision_proxy: dict[str, Any] = field(default_factory=dict)


@dataclass
class CultivationSupport(SerializableMixin):
    """Visible stake and intentional tie contacts associated with one plant."""

    support_id: str
    plant_id: str
    position: tuple[float, float, float]
    height: float
    radius: float
    section_width: float = 0.060
    section_depth: float = 0.075
    rotation_deg: float = 0.0
    tie_heights: list[float] = field(default_factory=list)
    kind: str = "wooden_rectangular_stake"
    material_key: str = "stake_wood"
    parameter_status: str = "manual_initial_guess"


@dataclass
class EnvironmentConfig(SerializableMixin):
    """Reproducible outdoor context surrounding the generated plants."""

    preset_name: str = "open_field_hybrid"
    terrain_size: float = 12.0
    terrain_subdivisions: int = 36
    row_spacing: float = 0.82
    background_cluster_count: int = 7
    ground_vegetation_profile: str = "mixed_pasture_and_weeds"
    asset_policy: str = "packed_cc0_with_procedural_fallback"
    parameter_status: str = "manual_initial_guess"


@dataclass
class RenderConfig(SerializableMixin):
    """Small render contract used by the annotation pilot."""

    width: int = 1280
    height: int = 960
    camera_profiles: list[str] = field(
        default_factory=lambda: [
            "robot_close_oblique",
            "human_oblique_mid",
            "context_wide",
        ]
    )
    rgb_engines: list[str] = field(
        default_factory=lambda: ["BLENDER_EEVEE_NEXT"]
    )
    cycles_samples: int = 64
    annotation_engine: str = "BLENDER_EEVEE_NEXT"
    human_validation_profile: str = "standard_eevee"
    adaptive_sampling: bool = True
    noise_threshold: float = 0.005
    minimum_samples: int = 64
    denoiser: str = "OPENIMAGEDENOISE"
    view_transform: str = "AgX"
    parameter_status: str = "manual_initial_guess"


@dataclass
class CultivationScene(SerializableMixin):
    """Future scene/canopy composition above individual plant generation."""

    scene_id: str
    preset_name: str
    seed: int
    plant_instances: list[PlantInstance] = field(default_factory=list)
    supports: list[CultivationSupport] = field(default_factory=list)
    support_system: SupportSystem | None = None
    row_or_bed: dict[str, Any] = field(default_factory=dict)
    camera: dict[str, Any] = field(default_factory=dict)
    background_canopy: dict[str, Any] = field(default_factory=dict)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.1"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CultivationScene":
        """Deserialize additive scene JSON while preserving legacy files."""
        environment = payload.get("environment", {})
        render = payload.get("render", {})
        support_system = payload.get("support_system")
        return cls(
            scene_id=str(payload["scene_id"]),
            preset_name=str(payload["preset_name"]),
            seed=int(payload["seed"]),
            plant_instances=[
                PlantInstance(**_filtered_dataclass_values(PlantInstance, item))
                for item in payload.get("plant_instances", [])
            ],
            supports=[
                CultivationSupport(
                    **_filtered_dataclass_values(CultivationSupport, item)
                )
                for item in payload.get("supports", [])
            ],
            support_system=(
                SupportSystem.from_dict(support_system)
                if isinstance(support_system, dict)
                else None
            ),
            row_or_bed=dict(payload.get("row_or_bed", {})),
            camera=dict(payload.get("camera", {})),
            background_canopy=dict(payload.get("background_canopy", {})),
            environment=EnvironmentConfig(
                **_filtered_dataclass_values(EnvironmentConfig, environment)
            ),
            render=RenderConfig(
                **_filtered_dataclass_values(RenderConfig, render)
            ),
            metadata=dict(payload.get("metadata", {})),
            schema_version=str(payload.get("schema_version", "1.0")),
        )


def create_scene_stub(seed: int, preset_name: str = "single_plant_study") -> CultivationScene:
    """Create a lightweight, serializable scene stub without generating geometry."""
    plant_count = 1 if preset_name == "single_plant_study" else 3
    return create_cultivation_scene(
        seed=seed,
        preset_name=preset_name,
        plant_count=plant_count,
        collision_policy="canopy_permissive",
    )


def create_cultivation_scene(
    seed: int,
    preset_name: str = "foreground_plant_with_neighbors",
    plant_count: int = 10,
    collision_policy: str = "canopy_permissive",
    *,
    support_mode: str | None = None,
) -> CultivationScene:
    """Create a deterministic multi-plant cultivation scene layout."""
    if support_mode not in {
        None,
        "continuous_trellis",
        "individual_stakes",
        "none",
    }:
        raise ValueError(
            "support_mode must be continuous_trellis, individual_stakes, none, "
            "or None."
        )
    rng = random.Random(seed + 10_000)
    if preset_name == "single_plant_study":
        plant_count = 1
    elif preset_name == "annotation_foreground_pilot":
        plant_count = max(3, min(5, plant_count))
    elif preset_name == "annotation_real_matched":
        plant_count = max(1, min(3, plant_count))
    elif preset_name == "foreground_plant_with_neighbors":
        plant_count = max(5, min(10, plant_count))
    elif preset_name == "row_canopy":
        plant_count = max(8, min(20, plant_count))
    elif preset_name == "dense_staked_crop":
        plant_count = 20
    elif preset_name == "dense_trellis_synchronous":
        plant_count = 20

    instances: list[PlantInstance] = []
    physical_collisions: list[dict[str, Any]] = []
    visual_occlusions: list[dict[str, Any]] = []
    placement_retries_total = 0
    unresolved_warnings: list[str] = []

    for index in range(plant_count):
        if preset_name in {"annotation_foreground_pilot", "annotation_real_matched"}:
            instance, collisions, retries = _place_annotation_instance(
                index=index,
                seed=seed,
                rng=rng,
                existing=instances,
                collision_policy=collision_policy,
            )
        else:
            instance, collisions, retries = _place_instance(
                index=index,
                plant_count=plant_count,
                seed=seed,
                rng=rng,
                existing=instances,
                collision_policy=collision_policy,
                preset_name=preset_name,
            )
        placement_retries_total += retries
        physical_collisions.extend(collisions)
        instances.append(instance)

    for left_index in range(len(instances)):
        for right_index in range(left_index + 1, len(instances)):
            left = instances[left_index]
            right = instances[right_index]
            distance = _distance_xy(left.position, right.position)
            canopy_radius = (
                left.collision_proxy["canopy_radius"]
                + right.collision_proxy["canopy_radius"]
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

    if physical_collisions:
        unresolved_warnings.append(
            "Some base-distance warnings remain; canopy policy is permissive but bases should be reviewed."
        )

    uses_continuous_trellis = (
        support_mode == "continuous_trellis"
        or (
            support_mode is None
            and preset_name == "dense_trellis_synchronous"
        )
    )
    supports_disabled = support_mode == "none"
    supports = (
        []
        if uses_continuous_trellis or supports_disabled
        else [_make_support(instance, rng) for instance in instances]
    )
    support_system = (
        build_continuous_trellis(instances, seed=seed)
        if uses_continuous_trellis
        else None
    )

    return CultivationScene(
        scene_id=f"{preset_name}_seed_{seed}",
        preset_name=preset_name,
        seed=seed,
        plant_instances=instances,
        supports=supports,
        support_system=support_system,
        row_or_bed={
            "mode": (
                "foreground_cluster"
                if preset_name in {"annotation_foreground_pilot", "annotation_real_matched"}
                else "two_staggered_rows"
            ),
            "row_count": 2 if plant_count > 1 else 1,
            "plant_count": plant_count,
            "collision_policy": collision_policy,
        },
        camera={
            "mode": (
                "multi_profile_annotation"
                if preset_name in {"annotation_foreground_pilot", "annotation_real_matched", "dense_staked_crop"}
                else "scene_preview"
            ),
            "status": "planned_in_blender_generation",
        },
        background_canopy={
            "mode": "real_morphology_instances_only",
            "visual_occlusions_allowed": True,
        },
        metadata={
            "scope": "CultivationScene composes plant individuals; it does not widen a single plant to mimic a crop row.",
            "collision_policy": collision_policy,
            "physical_collisions": physical_collisions,
            "visual_occlusions": visual_occlusions,
            "placement_retries": placement_retries_total,
            "unresolved_warnings": unresolved_warnings,
            "foreground_plant_id": instances[0].plant_id if instances else None,
            "drying_plant_rate_target": 0.08,
            "support_policy": "one_visible_stake_with_two_or_three_ties_per_plant",
            "support_system_mode": (
                support_system.mode
                if support_system is not None
                else (
                    "none"
                    if supports_disabled
                    else "individual_stake_with_ties"
                )
            ),
        },
    )


def _place_annotation_instance(
    index: int,
    seed: int,
    rng: random.Random,
    existing: list[PlantInstance],
    collision_policy: str,
) -> tuple[PlantInstance, list[dict[str, Any]], int]:
    """Place one focal plant and partially visible neighbors behind it."""
    anchors = [
        (0.0, 0.0),
        (-0.92, 0.66),
        (0.94, 0.72),
        (0.12, 1.34),
        (-1.42, 1.18),
    ]
    center_x, center_y = anchors[min(index, len(anchors) - 1)]
    min_base_distance = 0.46
    collisions: list[dict[str, Any]] = []
    retries = 0
    position = (center_x, center_y, 0.0)

    for attempt in range(25):
        jitter = 0.035 if index == 0 else 0.11
        candidate = (
            center_x + rng.uniform(-jitter, jitter),
            center_y + rng.uniform(-jitter, jitter),
            0.0,
        )
        too_close = [
            other
            for other in existing
            if _distance_xy(candidate, other.position) < min_base_distance
        ]
        retries = attempt
        if not too_close:
            position = candidate
            break
        if attempt == 24:
            position = candidate
            for other in too_close:
                collisions.append(
                    {
                        "type": "base_distance_warning",
                        "plant_a": f"plant_{index + 1:02d}",
                        "plant_b": other.plant_id,
                        "distance": round(_distance_xy(candidate, other.position), 3),
                        "minimum": min_base_distance,
                    }
                )

    role = "foreground" if index == 0 else "neighbor"
    scale = rng.uniform(0.96, 1.06) if index == 0 else rng.uniform(0.78, 0.98)
    canopy_radius = 0.54 * scale if collision_policy == "canopy_permissive" else 0.42 * scale
    base_radius = 0.10 * scale
    return (
        PlantInstance(
            plant_id=f"plant_{index + 1:02d}",
            seed=seed + index * 101,
            role=role,
            position=tuple(round(value, 4) for value in position),
            rotation_deg=round(rng.uniform(-18.0, 18.0) if index == 0 else rng.uniform(-35.0, 35.0), 2),
            scale=round(scale, 3),
            age="adult_initial_guess",
            phenological_stage="mixed",
            vigor=round(rng.uniform(0.88, 1.06), 3),
            condition=_condition_for_instance(seed, index),
            pruning_mode="unmodeled",
            training_mode="individual_stake_with_ties",
            placement_retries=retries,
            collision_proxy={
                "base_radius": round(base_radius, 3),
                "canopy_radius": round(canopy_radius, 3),
                "strict_collision": ["base", "main_stem", "capacho"],
                "allowed_visual_overlap": ["leaf", "background_canopy"],
            },
        ),
        collisions,
        retries,
    )


def _place_instance(
    index: int,
    plant_count: int,
    seed: int,
    rng: random.Random,
    existing: list[PlantInstance],
    collision_policy: str,
    preset_name: str = "foreground_plant_with_neighbors",
) -> tuple[PlantInstance, list[dict[str, Any]], int]:
    if preset_name == "dense_trellis_synchronous":
        row_spacing = 1.65
        plant_spacing = 1.05
        jitter_xy = 0.045
        min_base_distance = 0.48
    else:
        row_spacing = 3.50
        plant_spacing = 2.80
        jitter_xy = 0.08
        min_base_distance = 0.52
    rows = 2
    columns = math.ceil(plant_count / rows)
    row = index % rows
    column = index // rows
    x_center = (column - (columns - 1) / 2.0) * plant_spacing
    y_center = (row - 0.5) * row_spacing
    if row == 1:
        x_center += plant_spacing * 0.32

    collisions: list[dict[str, Any]] = []
    retries = 0
    position = (x_center, y_center, 0.0)
    for attempt in range(25):
        candidate = (
            x_center + rng.uniform(-jitter_xy, jitter_xy),
            y_center + rng.uniform(-jitter_xy, jitter_xy),
            0.0,
        )
        too_close = [
            other
            for other in existing
            if _distance_xy(candidate, other.position) < min_base_distance
        ]
        retries = attempt
        if not too_close:
            position = candidate
            break
        if attempt == 24:
            position = candidate
            for other in too_close:
                collisions.append(
                    {
                        "type": "base_distance_warning",
                        "plant_a": f"plant_{index + 1:02d}",
                        "plant_b": other.plant_id,
                        "distance": round(_distance_xy(candidate, other.position), 3),
                        "minimum": min_base_distance,
                    }
                )

    scale = rng.uniform(0.85, 1.10)
    canopy_radius = 0.54 * scale if collision_policy == "canopy_permissive" else 0.42 * scale
    base_radius = 0.10 * scale
    return (
        PlantInstance(
            plant_id=f"plant_{index + 1:02d}",
            seed=seed + index * 101,
            role="foreground" if index == 0 else "neighbor",
            position=tuple(round(value, 4) for value in position),
            rotation_deg=round(rng.uniform(-28.0, 28.0), 2),
            scale=round(scale, 3),
            age="adult_initial_guess",
            phenological_stage="mixed",
            vigor=round(rng.uniform(0.82, 1.08), 3),
            condition=_condition_for_instance(seed, index),
            pruning_mode="unmodeled",
            training_mode=(
                "continuous_row_trellis"
                if preset_name == "dense_trellis_synchronous"
                else "individual_stake_with_ties"
            ),
            placement_retries=retries,
            collision_proxy={
                "base_radius": round(base_radius, 3),
                "canopy_radius": round(canopy_radius, 3),
                "strict_collision": ["base", "main_stem", "capacho"],
                "allowed_visual_overlap": ["leaf", "background_canopy"],
            },
        ),
        collisions,
        retries,
    )


def _distance_xy(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _condition_for_instance(seed: int, index: int) -> str:
    """Select whole-plant condition without consuming placement RNG state."""
    condition_rng = random.Random(seed * 1_000_003 + index * 97_409 + 41)
    return "drying" if condition_rng.random() < 0.08 else "healthy"


def _make_support(
    instance: PlantInstance,
    rng: random.Random,
) -> CultivationSupport:
    angle = math.radians(instance.rotation_deg + rng.uniform(105.0, 165.0))
    # Start outside the protected stem/root envelope.  Ties bridge the gap;
    # the timber post itself must not occupy the same corridor as the plant.
    offset = rng.uniform(0.38, 0.52) * instance.scale
    position = (
        round(instance.position[0] + math.cos(angle) * offset, 4),
        round(instance.position[1] + math.sin(angle) * offset, 4),
        instance.position[2],
    )
    height = round(rng.uniform(3.05, 3.55) * instance.scale, 3)
    tie_count = 3 if instance.scale >= 0.9 else 2
    fractions = (0.34, 0.61, 0.82)[:tie_count]
    return CultivationSupport(
        support_id=f"{instance.plant_id}_stake",
        plant_id=instance.plant_id,
        position=position,
        height=height,
        radius=round(0.080 * instance.scale, 4),
        section_width=round(0.060 * instance.scale, 4),
        section_depth=round(0.075 * instance.scale, 4),
        rotation_deg=round((instance.rotation_deg + rng.uniform(-12.0, 12.0)) % 360.0, 3),
        tie_heights=[round(height * fraction, 3) for fraction in fractions],
    )


def _filtered_dataclass_values(
    cls: type[Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    accepted = set(getattr(cls, "__dataclass_fields__", {}))
    return {key: value for key, value in payload.items() if key in accepted}
