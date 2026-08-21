"""Serializable configuration for Classical Augmentation v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PROTOCOL_VERSION = "classical_augmentation_v2.0.0"
PROFILE_VERSION = "real_train_profile_v1.0.0"
RECIPE_VERSION = "classical_augmentation_v2_recipes_v1.0.0"


@dataclass(frozen=True)
class ScenarioConfig:
    """One immutable v2 scenario definition."""

    code: str
    name: str
    recipe_id: str
    derived_count: int
    transform_families: tuple[str, ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignConfig:
    """Frozen generation and training contract for the v2 campaign."""

    protocol_version: str = PROTOCOL_VERSION
    recipe_version: str = RECIPE_VERSION
    source_image_dirname: str = "IMAGENES"
    source_label_dirname: str = "LABELS"
    class_names: tuple[str, ...] = ("calyx",)
    source_train_count: int = 1062
    additive_derived_count: int = 532
    size_band_max_delta_percentage_points: float = 5.0
    size_filter_status: str = "engineering_heuristic"
    scenarios: tuple[ScenarioConfig, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_campaign_config() -> CampaignConfig:
    """Return the required v2 scenarios without altering historical E0/E1/E2."""
    count = 532
    scenarios = (
        ScenarioConfig("V2-E0", "Natural baseline", "natural_only", 0, ()),
        ScenarioConfig("V2-E0R", "Size-matched natural control", "natural_resample", count, ("resample",)),
        ScenarioConfig(
            "V2-E2",
            "Failure-guided moderate combination",
            "failure_guided_combination",
            count,
            ("photometric", "object_aware_occlusion"),
            {
                "photometric_probability": 0.65,
                "occlusion_probability": 0.55,
                "max_transform_families": 2,
                "photometric_spec": "V2-E3",
                "occlusion_spec": "V2-E4",
            },
        ),
        ScenarioConfig(
            "V2-E3",
            "Real-matched photometric augmentation",
            "real_matched_photometric",
            count,
            ("photometric",),
            {
                "phenomena": ("exposure", "exposure+soft_directional_shadow", "white_balance", "local_contrast"),
                "exposure_factor_range": (0.86, 1.14),
                "shadow_strength_range": (0.10, 0.24),
                "white_balance_bgr_gain_range": (0.94, 1.06),
                "clahe_clip_limit_range": (1.15, 1.55),
                "clahe_blend_range": (0.18, 0.38),
                "acceptance": "train_global_p01_p99_luminance_saturation_local_contrast",
                "max_transforms": 2,
            },
        ),
        ScenarioConfig(
            "V2-E4",
            "Visibility-consistent object-aware occlusion",
            "visibility_consistent_occlusion",
            count,
            ("object_aware_occlusion",),
            {
                "visible_fraction_min": 0.55,
                "visible_fraction_max": 0.88,
                "target_context_vegetation_min": 0.30,
                "occluder_selected_vegetation_min": 0.60,
                "edge_gaussian_sigma_px": 1.2,
                "opacity_core": 1.0,
            },
        ),
        ScenarioConfig("V2-E5", "Horizontal flip X", "horizontal_flip", count, ("horizontal_flip",)),
        ScenarioConfig(
            "V2-E6",
            "Scale-preserving crop and zoom",
            "scale_preserving_crop",
            count,
            ("crop_zoom",),
            {"crop_fraction_min": 0.82, "crop_fraction_max": 0.96, "box_min_visible_fraction": 0.55, "size_acceptance": "train_bbox_area_p01_p99"},
        ),
        ScenarioConfig(
            "V2-E7",
            "Geometry mix",
            "geometry_mix",
            count,
            ("horizontal_flip", "crop_zoom"),
            {"flip_probability": 0.5, "crop_probability": 0.8, "max_transforms": 2, "crop_spec": "V2-E6"},
        ),
        ScenarioConfig(
            "V2-E8",
            "Same-class cluster Copy-Paste",
            "same_class_cluster_copy_paste",
            count,
            ("copy_paste",),
            {
                "target_overlap_min": 0.02,
                "target_overlap_max": 0.35,
                "pasted_scale_over_anchor_width_range": (0.65, 0.92),
                "target_context_vegetation_min": 0.30,
                "paste_background_vegetation_min": 0.25,
                "occluded_target_visible_fraction_min": 0.55,
                "edge_gaussian_sigma_px": 1.2,
            },
        ),
    )
    return CampaignConfig(scenarios=scenarios)
