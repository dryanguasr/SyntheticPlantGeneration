"""Initial parameter ranges for morphology-first uchuva generation.

The values below are not presented as measured botanical constants. They are
explicitly tagged as manual initial guesses or to-be-measured placeholders so
future work can replace them with measured or literature-reported values.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .provenance import normalise_parameter_provenance


INITIAL_PARAMETER_PRESET: dict[str, Any] = {
    "preset_name": "initial_migration_manual_guess",
    "evidence_policy": {
        "literature_reported": "Value copied from a cited source.",
        "manual_initial_guess": "Tentative engineering value for early tests.",
        "to_be_measured": "Needs local measurement or literature review.",
    },
    "axis": {
        "main_node_count": {
            "value": 9,
            "status": "manual_initial_guess",
            "note": "Moderate individual plant for JSON, validation, and Blender scene tests.",
        },
        "max_branch_order": {
            "value": 2,
            "status": "manual_initial_guess",
            "note": "Allows moderate individual branching without replacing scene-level density.",
        },
        "branch_node_count_range": {
            "min": 3,
            "max": 5,
            "status": "manual_initial_guess",
        },
    },
    "phyllotaxis": {
        "divergence_angle_deg": {
            "value": 137.5,
            "status": "manual_initial_guess",
            "note": "Used only as an initial spiral placement heuristic.",
        },
    },
    "internode": {
        "length_cm_range": {
            "min": 3.0,
            "max": 8.0,
            "status": "manual_initial_guess",
        },
        "radius_cm_by_order": {
            "0": {"min": 0.18, "max": 0.35, "status": "manual_initial_guess"},
            "1": {"min": 0.08, "max": 0.18, "status": "manual_initial_guess"},
            "2": {"min": 0.035, "max": 0.075, "status": "manual_initial_guess"},
        },
        "bend_angle_deg_by_order": {
            "0": {"min": 0.5, "max": 3.5, "status": "manual_initial_guess"},
            "1": {"min": 1.5, "max": 6.5, "status": "manual_initial_guess"},
        },
        "pigmentation_range": {
            "min": -0.06,
            "max": 0.06,
            "status": "manual_initial_guess",
            "note": "Small within-plant shade delta; the color family is selected once per plant.",
        },
    },
    "leaf": {
        "length_cm_range": {
            "min": 5.0,
            "max": 11.0,
            "status": "manual_initial_guess",
        },
        "width_to_length_ratio_range": {
            "min": 0.58,
            "max": 0.86,
            "status": "dataset_inferred_collision_calibrated_v3",
            "note": "Broad ovate blades without the oversized rectangular footprint of the early preview.",
        },
        "petiole_length_cm_range": {
            "min": 1.2,
            "max": 5.2,
            "status": "literature_reported_kew_range_local_distribution_to_be_measured",
        },
        "shapes": {
            "values": ["ovate_cordate", "ovate", "deltoid_ovate"],
            "status": "to_be_measured",
        },
        "margins": {
            "values": ["entire", "slightly_toothed", "irregular"],
            "status": "to_be_measured",
        },
        "curl_range": {
            "min": -0.10,
            "max": 0.16,
            "status": "literature_bounded_engineering_heuristic",
        },
        "twist_deg_range": {
            "min": -8.0,
            "max": 8.0,
            "status": "engineering_heuristic_to_be_measured",
        },
        "edge_damage_range": {"min": 0.0, "max": 0.05, "status": "dataset_inferred_manual_initial_guess"},
        "senescence_range": {"min": 0.0, "max": 0.34, "status": "to_be_measured"},
        "pubescence_range": {"min": 0.35, "max": 0.85, "status": "to_be_measured"},
    },
    "branching": {
        "branch_probability": {
            "value": 0.35,
            "status": "manual_initial_guess",
        },
        "branch_angle_deg_range": {
            "min": 38.0,
            "max": 78.0,
            "status": "manual_initial_guess",
        },
    },
    "growth": {
        "mode": {
            "value": "legacy_recursive",
            "status": "implementation_constraint",
        },
        "length_budget_cm_by_order": {
            "0": {"min": 42.0, "max": 58.0, "status": "manual_initial_guess"},
            "1": {"min": 15.0, "max": 32.0, "status": "manual_initial_guess"},
            "2": {"min": 10.0, "max": 24.0, "status": "manual_initial_guess"},
            "3": {"min": 7.0, "max": 16.0, "status": "manual_initial_guess"},
        },
        "max_internodes_by_order": {
            "0": {"value": 10, "status": "manual_initial_guess"},
            "1": {"value": 6, "status": "manual_initial_guess"},
            "2": {"value": 5, "status": "manual_initial_guess"},
            "3": {"value": 4, "status": "manual_initial_guess"},
        },
        "vigor_decay_by_order": {
            "value": 0.78,
            "status": "engineering_heuristic",
        },
        "apical_dominance": {
            "value": 0.62,
            "status": "manual_initial_guess",
        },
        "branch_probability_by_order": {
            "0": {"value": 0.35, "status": "manual_initial_guess"},
            "1": {"value": 0.35, "status": "manual_initial_guess"},
            "2": {"value": 0.0, "status": "manual_initial_guess"},
        },
        "internode_length_scale_by_order": {
            "0": {"value": 1.0, "status": "manual_initial_guess"},
            "1": {"value": 0.92, "status": "manual_initial_guess"},
            "2": {"value": 0.78, "status": "manual_initial_guess"},
            "3": {"value": 0.68, "status": "manual_initial_guess"},
        },
        "leaf_length_scale_by_order": {
            "0": {"value": 1.0, "status": "manual_initial_guess"},
            "1": {"value": 0.92, "status": "manual_initial_guess"},
            "2": {"value": 0.82, "status": "manual_initial_guess"},
            "3": {"value": 0.74, "status": "manual_initial_guess"},
        },
        "correlated_noise_strength_deg": {
            "value": 5.5,
            "status": "engineering_heuristic",
        },
        "synchronous_steps": {
            "value": 4,
            "status": "engineering_heuristic",
        },
        "max_final_axis_correction_deg": {
            "value": 12.0,
            "status": "engineering_heuristic",
        },
        "space_colonization_enabled": {
            "value": False,
            "status": "implementation_constraint",
        },
    },
    "light_competition": {
        "enabled": {
            "value": False,
            "status": "implementation_constraint",
            "note": "Enabled only by morphology presets that explicitly model a shared crop canopy.",
        },
        "status": "engineering_heuristic",
        "model": "stratified_daily_projected_gap_capture",
        "interpretation": (
            "Projected coverage proxy for canopy plasticity; not a calibrated "
            "photosynthesis or radiative-transfer model."
        ),
        "strata": [
            {
                "name": "lower",
                "min_height": 0.0,
                "max_height": 0.95,
            },
            {
                "name": "middle",
                "min_height": 0.95,
                "max_height": 1.75,
            },
            {
                "name": "upper",
                "min_height": 1.75,
                "max_height": 3.60,
            },
        ],
        "daily_sun_samples": [
            {"azimuth_deg": 82.0, "elevation_deg": 24.0, "weight": 0.75},
            {"azimuth_deg": 118.0, "elevation_deg": 43.0, "weight": 1.00},
            {"azimuth_deg": 180.0, "elevation_deg": 66.0, "weight": 1.15},
            {"azimuth_deg": 242.0, "elevation_deg": 43.0, "weight": 1.00},
            {"azimuth_deg": 278.0, "elevation_deg": 24.0, "weight": 0.75},
        ],
        "projected_cell_size": {
            "value": 0.18,
            "status": "engineering_heuristic",
        },
        "coverage_cost_weight": {
            "value": 1.70,
            "status": "engineering_heuristic",
        },
        "deformation_cost_weight": {
            "value": 0.24,
            "status": "engineering_heuristic",
        },
        "structural_contact_cost_weight": {
            "value": 0.38,
            "status": "engineering_heuristic",
        },
        "candidate_azimuth_offsets_deg": {
            "values": [
                0.0,
                -30.0,
                30.0,
                -60.0,
                60.0,
                -90.0,
                90.0,
                120.0,
                -120.0,
                150.0,
                -150.0,
            ],
            "status": "engineering_heuristic",
        },
        "candidate_insertion_offsets_deg": {
            "values": [0.0, -18.0, 18.0, -30.0, 30.0],
            "status": "engineering_heuristic",
        },
        "trellis_training": {
            "enabled": {
                "value": False,
                "status": "implementation_constraint",
            },
            "arm_count": {
                "value": 3,
                "status": "engineering_heuristic",
                "note": "Coarse inverted-tripod training proxy from the agronomic field observation.",
            },
            "target_radius_by_stratum": {
                "lower": 0.48,
                "middle": 0.68,
                "upper": 0.84,
                "status": "manual_initial_guess",
            },
            "expansion_completion_fraction": {
                "value": 0.82,
                "status": "engineering_heuristic",
            },
            "expansion_vertical_component": {
                "value": 0.38,
                "status": "engineering_heuristic",
            },
            "guidance_cost_weight": {
                "value": 1.45,
                "status": "engineering_heuristic",
            },
        },
    },
    "reproduction": {
        "reproductive_probability": {
            "value": 0.58,
            "status": "manual_initial_guess",
        },
        "target_reproductive_units_range": {
            "min": 4,
            "max": 8,
            "status": "manual_initial_guess",
            "note": "Per individual plant; crop density is handled by CultivationScene.",
        },
        "stages": {
            "values": [
                "flower",
                "young_fruit_with_calyx",
                "mature_fruit_with_calyx",
                "exposed_fruit",
            ],
            "status": "manual_initial_guess",
        },
        "stage_weights": {
            "flower": 0.12,
            "young_fruit_with_calyx": 0.43,
            "mature_fruit_with_calyx": 0.37,
            "exposed_fruit": 0.08,
            "status": "manual_initial_guess",
            "note": "Closed-calyx iteration: exposed_fruit is temporarily mapped to a closed dry/deteriorated capacho with hidden fruit.",
        },
        "pedicel_length_cm_range": {
            "min": 1.0,
            "max": 3.5,
            "status": "manual_initial_guess",
        },
        "pedicel_angle_deg_range": {
            "min": 20.0,
            "max": 55.0,
            "status": "manual_initial_guess",
        },
        "fruit_radius_cm_range": {
            "min": 1.0,
            "max": 1.55,
            "status": "manual_initial_guess",
        },
        "calyx_to_fruit_radius_ratio_range": {
            "min": 1.35,
            "max": 1.85,
            "status": "manual_initial_guess",
        },
        "calyx_ribs_range": {
            "min": 5,
            "max": 5,
            "status": "dataset_inferred_manual_initial_guess",
            "note": "Five structural sepal ribs; ten vascular lines belong to material/texture.",
        },
        "calyx_inflation_range": {
            "min": 0.96,
            "max": 1.08,
            "status": "dataset_inferred_manual_initial_guess",
        },
        "calyx_height_to_width_ratio_range": {
            "min": 1.15,
            "max": 1.55,
            "status": "dataset_inferred_camera_bbox",
            "note": "Reference images 0007, 0022, 0062, and 0079; target median about 1.35.",
        },
        "calyx_profile": {
            "value": "lantern_squash",
            "status": "dataset_inferred_manual_initial_guess",
        },
        "calyx_tip_length_ratio_range": {
            "min": 0.09,
            "max": 0.17,
            "status": "to_be_measured",
        },
        "calyx_wrinkle_by_state": {
            "inflated_green": {"min": 0.00, "max": 0.015},
            "transitioning_yellow": {"min": 0.00, "max": 0.025},
            "straw_yellow": {"min": 0.00, "max": 0.04},
            "dry_deteriorated": {"min": 0.03, "max": 0.14},
            "status": "literature_bounded_engineering_heuristic",
        },
        "calyx_asymmetry_range": {
            "min": 0.01,
            "max": 0.09,
            "status": "to_be_measured",
        },
        "calyx_pubescence_by_state": {
            "inflated_green": 0.72,
            "transitioning_yellow": 0.58,
            "straw_yellow": 0.44,
            "dry_deteriorated": 0.24,
            "status": "manual_initial_guess",
        },
        "fruit_visibility_by_stage": {
            "young_fruit_with_calyx": "hidden",
            "mature_fruit_with_calyx": "hidden",
            "exposed_fruit": "hidden",
            "status": "manual_initial_guess",
        },
        "maturity_by_stage": {
            "young_fruit_with_calyx": "young",
            "mature_fruit_with_calyx": "mature",
            "exposed_fruit": "overripe",
            "status": "manual_initial_guess",
        },
        "calyx_state_by_stage": {
            "young_fruit_with_calyx": "inflated_green",
            "mature_fruit_with_calyx": "straw_yellow",
            "exposed_fruit": "dry_deteriorated",
            "status": "manual_initial_guess",
        },
        "calyx_openness_by_state": {
            "inflated_green": 0.0,
            "transitioning_yellow": 0.0,
            "straw_yellow": 0.0,
            "dry_deteriorated": 0.0,
            "status": "manual_initial_guess",
            "note": "All capachos are intentionally closed in this iteration.",
        },
        "calyx_material_by_state": {
            "inflated_green": "calyx_inflated_green",
            "transitioning_yellow": "calyx_transitioning_yellow",
            "straw_yellow": "calyx_straw_yellow",
            "dry_deteriorated": "calyx_dry_deteriorated",
            "status": "manual_initial_guess",
        },
    },
    "individual_scope": {
        "max_width_to_height_ratio": {
            "value": 1.15,
            "status": "manual_initial_guess",
            "note": "If exceeded, prefer a CultivationScene with neighbors rather than widening one plant.",
        }
    },
    "scene_presets": {
        "single_plant_study": {
            "plant_instances": 1,
            "status": "manual_initial_guess",
            "use": "Morphology debugging for one individual plant.",
        },
        "foreground_plant_with_neighbors": {
            "plant_instances": {"min": 5, "max": 10, "default": 10},
            "status": "manual_initial_guess",
            "use": "One target plant plus partial neighbors for robotics perception.",
            "row_spacing": 0.78,
            "plant_spacing": 0.62,
            "jitter_xy": 0.12,
            "min_base_distance": 0.38,
            "collision_policy": "canopy_permissive",
        },
        "annotation_foreground_pilot": {
            "plant_instances": {"min": 3, "max": 5, "default": 4},
            "status": "manual_initial_guess",
            "use": "One foreground plant plus partial neighbors for an annotation-ready outdoor pilot.",
            "collision_policy": "canopy_permissive",
            "environment": "open_field_hybrid",
            "camera_profiles": [
                "robot_close_oblique",
                "human_oblique_mid",
                "context_wide",
            ],
        },
        "annotation_real_matched": {
            "plant_instances": {"min": 1, "max": 3, "default": 1},
            "status": "manual_initial_guess",
            "use": "Calibrated close, medium, and context captures matched to the original dataset.",
            "collision_policy": "canopy_permissive",
            "environment": "reference_scheduled",
            "camera_profiles": ["real_close", "real_mid", "real_context"],
        },
        "row_canopy": {
            "plant_instances": {"min": 8, "max": 20},
            "status": "manual_initial_guess",
            "use": "Future dense row/canopy scenes; not for early morphology calibration.",
        },
        "dense_trellis_synchronous": {
            "plant_instances": {"min": 20, "max": 20, "default": 20},
            "status": "engineering_heuristic",
            "use": "Twenty morphology-backed plants coordinated against a continuous row trellis.",
            "row_spacing": 1.65,
            "plant_spacing": 1.05,
            "collision_policy": "contact_policy_clearance",
            "support_mode": "continuous_row_trellis",
        },
    },
}


PHENOLOGY_PROFILES: dict[str, dict[str, Any]] = {
    "mixed_early": {
        "stage_weights": {
            "flower": 0.20,
            "young_fruit_with_calyx": 0.60,
            "mature_fruit_with_calyx": 0.18,
            "exposed_fruit": 0.02,
        },
        "status": "manual_initial_guess",
    },
    "mixed_balanced": {
        "stage_weights": {
            "flower": 0.12,
            "young_fruit_with_calyx": 0.43,
            "mature_fruit_with_calyx": 0.37,
            "exposed_fruit": 0.08,
        },
        "status": "manual_initial_guess",
    },
    "mixed_late": {
        "stage_weights": {
            "flower": 0.08,
            "young_fruit_with_calyx": 0.20,
            "mature_fruit_with_calyx": 0.52,
            "exposed_fruit": 0.20,
        },
        "status": "manual_initial_guess",
    },
}


MORPHOLOGY_PRESET_OVERRIDES: dict[str, dict[str, Any]] = {
    "initial_migration_manual_guess": {},
    "natural_unpruned": {
        "preset_name": "natural_unpruned",
        "axis": {
            "main_node_count": {"value": 11},
            "max_branch_order": {"value": 3},
            "branch_node_count_range": {"min": 3, "max": 6},
        },
        "growth": {
            "mode": {"value": "incremental_budgeted"},
            "branch_probability_by_order": {
                "0": {"value": 0.52},
                "1": {"value": 0.44},
                "2": {"value": 0.22},
            },
            "apical_dominance": {"value": 0.56},
        },
    },
    "trained_trellis": {
        "preset_name": "trained_trellis",
        "axis": {
            "main_node_count": {"value": 11},
            "max_branch_order": {"value": 3},
            "branch_node_count_range": {"min": 3, "max": 5},
        },
        "growth": {
            "mode": {"value": "incremental_budgeted"},
            "length_budget_cm_by_order": {
                "0": {"min": 46.0, "max": 62.0},
                "1": {"min": 17.0, "max": 34.0},
                "2": {"min": 11.0, "max": 25.0},
                "3": {"min": 7.0, "max": 16.0},
            },
            "max_internodes_by_order": {
                "0": {"value": 11},
                "1": {"value": 6},
                "2": {"value": 5},
                "3": {"value": 4},
            },
            "branch_probability_by_order": {
                "0": {"value": 0.74},
                "1": {"value": 0.62},
                "2": {"value": 0.34},
            },
            "apical_dominance": {"value": 0.58},
        },
        "leaf": {
            "length_cm_range": {"min": 4.6, "max": 9.2},
            "petiole_length_cm_range": {"min": 2.0, "max": 5.2},
        },
        "light_competition": {
            "enabled": {"value": True},
            "trellis_training": {
                "enabled": {"value": True},
            },
        },
    },
    "compact_research_reference": {
        "preset_name": "compact_research_reference",
        "axis": {
            "main_node_count": {"value": 8},
            "max_branch_order": {"value": 2},
            "branch_node_count_range": {"min": 3, "max": 4},
        },
        "growth": {
            "mode": {"value": "incremental_budgeted"},
            "branch_probability_by_order": {
                "0": {"value": 0.46},
                "1": {"value": 0.30},
                "2": {"value": 0.0},
            },
            "apical_dominance": {"value": 0.68},
        },
        "leaf": {
            "length_cm_range": {"min": 4.5, "max": 8.4},
            "petiole_length_cm_range": {"min": 1.2, "max": 4.8},
        },
    },
}


def get_initial_parameters() -> dict[str, Any]:
    """Return a mutable copy of the initial migration preset."""
    return normalise_parameter_provenance(deepcopy(INITIAL_PARAMETER_PRESET))


def get_morphology_parameters(name: str) -> dict[str, Any]:
    """Return one morphology preset with additive canonical provenance."""
    if name not in MORPHOLOGY_PRESET_OVERRIDES:
        raise ValueError(f"Unknown morphology preset: {name}")
    parameters = deepcopy(INITIAL_PARAMETER_PRESET)
    _deep_update(parameters, deepcopy(MORPHOLOGY_PRESET_OVERRIDES[name]))
    return normalise_parameter_provenance(parameters)


def get_phenology_profile(name: str) -> dict[str, Any]:
    """Return a mutable phenology profile without changing the base preset."""
    if name not in PHENOLOGY_PROFILES:
        raise ValueError(f"Unknown phenology profile: {name}")
    return deepcopy(PHENOLOGY_PROFILES[name])


def _deep_update(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _deep_update(target[key], value)
        else:
            target[key] = value
