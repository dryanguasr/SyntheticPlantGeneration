"""Initial parameter ranges for morphology-first uchuva generation.

The values below are not presented as measured botanical constants. They are
explicitly tagged as manual initial guesses or to-be-measured placeholders so
future work can replace them with measured or literature-reported values.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .provenance import normalise_parameter_provenance, override_parameter


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
    if name == "trained_trellis_nodal_repulsion_v8":
        parameters = get_morphology_parameters("trained_trellis_pendulous_audit_v7")
        parameters['preset_name'] = name
        parameters['growth']['nodal_repulsion'] = {
            'value':'bottom_up_lower_first_v1', 'status':'engineering_heuristic',
            'sweeps':6, 'step_deg':6., 'max_active_seconds':600., 'proxy_margin_bu':.003,
            'branch_rotation_limit_deg':35., 'leaf_rotation_limit_deg':120., 'pedicel_rotation_limit_deg':75.,
            'mesh_main_axis_rotation_limit_deg':35.,
            'priority':['lower','raise','lateral'],
            'note':'Nodal pose changes only; immutable topology, dimensions, class and pendulous capacho axis. Proxy convergence does not certify meshes. Numerical priors are unmeasured.'}
        return normalise_parameter_provenance(parameters)
    if name == "trained_trellis_pendulous_audit_v7":
        parameters = _audit_lower_crown_parameters()
        parameters["preset_name"] = name
        parameters["reproduction"]["organ_orientation"] = {
            "value": "gravity_pendulous_v1", "status": "engineering_heuristic",
            "inclination_from_down_deg_range": [0., 25.], "mode_deg": 8.,
            "note": "Local review requests predominantly downward capachos. Separate gravity-referenced organ axis from axillary pedicel; numerical cone is unmeasured, not a botanical norm.",
        }
        return normalise_parameter_provenance(parameters)
    if name == "trained_trellis_lower_crown_audit_v6":
        return _audit_lower_crown_parameters()
    if name == "trained_trellis_broad_crown_audit_v5":
        return _audit_broad_crown_parameters()
    if name == "trained_trellis_bush_pose_audit_v4":
        return _audit_bush_pose_parameters()
    if name == "trained_trellis_bush_audit_v3":
        return _audit_bush_parameters()
    if name == "trained_trellis_audit_v2":
        return _audit_trellis_parameters()
    if name not in MORPHOLOGY_PRESET_OVERRIDES:
        raise ValueError(f"Unknown morphology preset: {name}")
    parameters = deepcopy(INITIAL_PARAMETER_PRESET)
    _deep_update(parameters, deepcopy(MORPHOLOGY_PRESET_OVERRIDES[name]))
    return normalise_parameter_provenance(parameters)


def _audit_trellis_parameters() -> dict[str, Any]:
    """Versioned, image-independent plant policy; ranges are not field facts."""
    parameters = get_morphology_parameters("trained_trellis")
    parameters["preset_name"] = "trained_trellis_audit_v2"
    parameters["morphology_contract_version"] = "audit-morphology/2"
    # Adult development hypothesis reused from the existing sparse-crown
    # preset. This is fixed before camera planning, not a visible-fruit quota.
    adult_method = "adult_stage_budget_reused_from_sparse_overhead_dense_crown_v2"
    override_parameter(parameters["axis"]["main_node_count"], value=16,
                       status="engineering_heuristic", method=adult_method)
    override_parameter(parameters["growth"]["max_internodes_by_order"]["0"], value=16,
                       status="engineering_heuristic", method=adult_method)
    override_parameter(parameters["growth"]["length_budget_cm_by_order"]["0"], min=78.0, max=92.0,
                       status="engineering_heuristic", method=adult_method)
    parameters["reproduction"]["load_policy"] = {
        "value": "architecture_driven", "status": "implementation_constraint",
        "note": "Nodal sites and development determine load, independently of camera targets.",
    }
    parameters["reproduction"]["target_reproductive_units_range"]["active"] = False
    parameters["reproduction"]["target_reproductive_units_range"]["note"] = (
        "Inactive historical compatibility value; not a plant minimum/maximum."
    )
    radii = parameters["internode"]["radius_cm_by_order"]
    # Extrapolate each bound from the previous reduction. This is an explicit
    # engineering prior, not a newly asserted anatomical measurement.
    radii["3"] = {
        key: radii["2"][key] * radii["2"][key] / radii["1"][key]
        for key in ("min", "max")
    }
    radii["3"].update(
        status="engineering_heuristic",
        note="Order-3 bound = order-2 bound * (order-2 bound / order-1 bound).",
    )
    parameters["internode"]["radius_policy"] = {
        "value": "complete_order_table_with_parent_insertion_continuity",
        "status": "implementation_constraint",
    }
    # Preset overrides had inherited evidence from the base parameter record.
    # Record the effective trained range as a local hypothesis instead.
    petiole = parameters["leaf"]["petiole_length_cm_range"]
    override_parameter(
        petiole, min=petiole["min"], max=petiole["max"],
        status="manual_initial_guess",
        method="trained_trellis_override_reclassified_by_audit_20261026",
    )
    return normalise_parameter_provenance(parameters)


def _audit_bush_parameters() -> dict[str, Any]:
    """Adult lateral development hypothesis after round-01 human rejection.

    The earlier preset extended only the main axis; its short 3--5-node
    laterals retained a juvenile-looking apical crown. This version adds nodal
    development on the same botanical grammar. None of these engineering
    ranges is an inferred field measurement, a visible-fruit target, or a
    camera-conditioned density. Dimensions of individual organs are inherited.
    """
    parameters = _audit_trellis_parameters()
    parameters["preset_name"] = "trained_trellis_bush_audit_v3"
    parameters["architecture_profile_version"] = "adult-bush-development/3"
    method = "adult_nodal_development_hypothesis_after_round01_human_rejection"
    override_parameter(parameters["axis"]["main_node_count"], value=20,
                       status="engineering_heuristic", method=method)
    override_parameter(parameters["axis"]["branch_node_count_range"], min=6, max=8,
                       status="engineering_heuristic", method=method)
    for order, bounds, cap in (
        ("0", (100.0, 116.0), 20),
        ("1", (28.0, 44.0), 8),
        ("2", (18.0, 30.0), 7),
        ("3", (10.0, 19.0), 5),
    ):
        override_parameter(parameters["growth"]["length_budget_cm_by_order"][order],
                           min=bounds[0], max=bounds[1], status="engineering_heuristic", method=method)
        override_parameter(parameters["growth"]["max_internodes_by_order"][order],
                           value=cap, status="engineering_heuristic", method=method)
    parameters["architecture_review"] = {
        "status": "engineering_heuristic",
        "basis": "human rejection of round-01 architecture; qualitative real-training context only",
        "development_stage": "adult_branching_hypothesis_pending_visual_and_mesh_validation",
        "branching_policy": "existing nodal axillary decisions and order probabilities unchanged",
        "first_bifurcation_policy": "existing literature-bounded 8--12-node cohort sample unchanged",
        "organ_dimensions": "unchanged from trained_trellis_audit_v2; additional nodes are not larger organs",
        "reproductive_load": "emergent from nodal decisions, never a global minimum or maximum",
        "camera_dependency": "none",
        "uncertainty": "Training photographs do not establish whole-plant node, leaf or fruit counts.",
    }
    return normalise_parameter_provenance(parameters)


def _audit_bush_pose_parameters() -> dict[str, Any]:
    """Opt-in pose diagnostic, preserving v3 organ sizes and nodal decisions.

    A low-elevation view exposed a predominantly horizontal blade population.
    The wider insertion range is a camera-independent hypothesis for leaf
    posture, not a distribution measured from photographs or a visibility
    quota. The orthogonal frame enforces the stated angle to the local axis.
    """
    parameters = _audit_bush_parameters()
    parameters["preset_name"] = "trained_trellis_bush_pose_audit_v4"
    parameters["leaf_pose_profile_version"] = "orthogonal-leaf-posture/4"
    parameters["leaf"]["insertion_angle_deg_range"] = {
        "min": 30.0, "max": 80.0, "status": "engineering_heuristic",
        "note": "Unmeasured posture hypothesis after round-02 edge-on leaf diagnosis; no camera input.",
    }
    parameters["leaf"]["insertion_frame"] = {
        "value": "orthogonal_local_v1", "status": "implementation_constraint",
        "note": "Leaf angle is relative to the local stem tangent, using the shared existing frame.",
    }
    parameters["leaf_pose_review"] = {
        "status": "engineering_heuristic",
        "observation": "Round-02 plant 00 has 145 leaves; 83.2% of lateral leaf AABBs have Z extent below one quarter of their maximum XY extent.",
        "limitations": "AABB ratios describe evaluated orientation, not visible leaf area, physical collision or biological correctness.",
        "scope": "Leaf insertion angle and frame only; no larger organs, additional organs or camera-conditioned rotations.",
        "human_validation": "pending_structural_preview",
    }
    return normalise_parameter_provenance(parameters)


def _audit_broad_crown_parameters() -> dict[str, Any]:
    """Adult crown hypothesis; lateral development is not an image quota.

    The v4 axes remained short and the length of every lateral blade was
    reduced both by order and by axis vigor. V5 separates mature blade size
    from the axis resource proxy and develops longer nodal lateral modules.
    Its dimensions require local biological and evaluated-mesh validation.
    """
    parameters = _audit_bush_pose_parameters()
    parameters["preset_name"] = "trained_trellis_broad_crown_audit_v5"
    parameters["architecture_profile_version"] = "adult-broad-crown/5"
    method = "adult_lateral_crown_hypothesis_after_v4_human_rejection"
    override_parameter(parameters["axis"]["branch_node_count_range"], min=10, max=14,
                       status="engineering_heuristic", method=method)
    for order, bounds, cap in (
        ("1", (52.0, 78.0), 14),
        ("2", (32.0, 48.0), 10),
        ("3", (18.0, 30.0), 7),
    ):
        override_parameter(parameters["growth"]["length_budget_cm_by_order"][order],
                           min=bounds[0], max=bounds[1], status="engineering_heuristic", method=method)
        override_parameter(parameters["growth"]["max_internodes_by_order"][order],
                           value=cap, status="engineering_heuristic", method=method)
    for order, value in (("0",1.0),("1",.98),("2",.95),("3",.90)):
        override_parameter(parameters["growth"]["leaf_length_scale_by_order"][order], value=value,
                           status="engineering_heuristic", method="adult_blade_development_not_axis_resource_proxy")
    parameters["growth"]["leaf_vigor_scaling"] = {
        "value": "adult_independent", "status": "engineering_heuristic",
        "note": "Remove the additional axis-vigor shrinkage of adult blades; retain the base 4.6--9.2 cm range and declared order factors.",
    }
    parameters["branching"]["frame"] = {
        "value": "local_cone_v1", "status": "implementation_constraint",
        "note": "Existing branch_direction_3d shared by Blender and collision proxies.",
    }
    angle_table = {}
    for order, low, high in (("1",52.,78.),("2",30.,65.),("3",20.,55.)):
        angle_table[order] = deepcopy(parameters["branching"]["branch_angle_deg_range"])
        override_parameter(angle_table[order], min=low, max=high, status="engineering_heuristic",
                           method="adult_lateral_opening_by_child_order_local_cone")
    parameters["branching"]["branch_angle_deg_by_order"] = angle_table
    override_parameter(parameters["leaf"]["insertion_frame"], value="local_cone_v2",
                       status="implementation_constraint", method="full_local_cone_without_horizontal_axis_azimuth_collapse")
    parameters["leaf_pose_profile_version"] = "full-local-cone-leaf-posture/5"
    parameters["broad_crown_review"] = {
        "status": "engineering_heuristic",
        "basis": "human rejection of thin v4 crown and qualitative real-training shrub structure",
        "main_axis": "unchanged from v4; wider crown comes from longer lateral development",
        "adult_blades": "same base range; no duplicate leaves, global scaling or camera-conditioned dimensions",
        "reproductive_load": "emergent nodal outcome, not a selected minimum, maximum or target",
        "validation": "pending human structural preview and evaluated-mesh audit",
        "uncertainty": "Photographs cannot identify whole-plant organ counts or supply calibrated physical dimensions.",
    }
    return normalise_parameter_provenance(parameters)


def _audit_lower_crown_parameters() -> dict[str, Any]:
    """Separate adult vegetative laterals from the reproductive landmark.

    Node three is an explicit engineering hypothesis, not a measured onset.
    It enables existing axillary buds; it neither guarantees a branch nor
    changes branching probabilities, organ dimensions or reproductive load.
    """
    parameters = _audit_broad_crown_parameters()
    parameters["preset_name"] = "trained_trellis_lower_crown_audit_v6"
    parameters["architecture_profile_version"] = "independent-vegetative-lower-crown/6"
    parameters["branching"]["activation_policy"] = {
        "value": "vegetative_onset_independent_v1",
        "status": "engineering_heuristic",
        "note": "Do not use the cohort first-bifurcation landmark as a prohibition on every adult vegetative axillary branch.",
    }
    parameters["branching"]["vegetative_first_main_node"] = {
        "value": 3, "status": "engineering_heuristic",
        "note": "One-based first eligible main-axis node; stochastic branching still applies, so this is not a required branch or crown-density target.",
    }
    parameters["lower_crown_review"] = {
        "status": "engineering_heuristic",
        "basis": "human review of v5 requested lower adult foliage; v5 delayed all primary laterals to nodes 8--12",
        "reproductive_landmark": "Retain the existing cohort sample for main-axis reproductive eligibility; interpreting it independently of vegetative lateral onset is a modelling hypothesis, not a new bibliographic claim.",
        "unchanged": "v5 probabilities, nodal and length budgets, organ dimensions, leaf posture and architecture-driven reproductive load",
        "uncertainty": "Node-three vegetative eligibility requires local architectural measurement; no guarantee of a branch at that node or fixed reproductive count.",
        "validation": "pending fixed-camera visual review and evaluated-mesh contact audit",
    }
    return normalise_parameter_provenance(parameters)


def leaf_length_factor(params: dict[str, Any], order: int, axis_vigor: float) -> float:
    """Shared generation/validation factor; old presets retain exact behavior."""
    growth = params.get("growth", {})
    if growth.get("mode", {}).get("value") != "incremental_budgeted":
        return 1.0
    factor = float(growth.get("leaf_length_scale_by_order", {})
                   .get(str(order), {"value":.74}).get("value",1.0))
    policy = growth.get("leaf_vigor_scaling", {}).get("value", "legacy_axis_vigor")
    if policy == "legacy_axis_vigor":
        return factor * max(.72, min(1.04, axis_vigor))
    if policy == "adult_independent":
        return factor
    raise ValueError(f"Unknown leaf vigor scaling policy: {policy}")


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
