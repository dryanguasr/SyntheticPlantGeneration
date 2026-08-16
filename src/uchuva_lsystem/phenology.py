"""Pure, literature-bounded phenology helpers for cape gooseberry.

The functions in this module deliberately remain independent from Blender and
from the morphology dataclasses.  They turn a topological ordering of
reproductive sites into coherent cohorts and continuous calyx maturity traits.
The numeric priors are site-specific literature anchors, not universal crop
constants.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import random
from typing import Any, Mapping


PHENOLOGY_MODELS = ("legacy_independent", "literature_cohort_v1")

STAGE_ORDER = (
    "flower",
    "young_fruit_with_calyx",
    "mature_fruit_with_calyx",
    "exposed_fruit",
)

PROFILE_THERMAL_TIME_RANGES_CD = {
    "mixed_early": (700.0, 1100.0),
    "mixed_balanced": (950.0, 1350.0),
    "mixed_late": (1200.0, 1700.0),
}

SALAZAR_NODE_PRIOR = {
    "base_temperature_c": 6.29,
    "breakpoint_degree_days": 1039.5,
    "node_rate_before_breakpoint_per_degree_day": 0.023,
    "node_rate_after_breakpoint_per_degree_day": 0.008,
    "rmse_nodes": 2.1,
    "status": "literature_reported_site_specific",
    "source": "salazar_2008_nodes_cape_gooseberry",
}

DINIZ_CALYX_PRIOR = {
    "reference_days_after_anthesis": [45.0, 60.0, 75.0, 90.0],
    "projected_area_relative_45_to_90": [1.0, 0.86],
    "circularity_45_to_90": [0.59, 0.39],
    "status": "literature_reported_site_year_bounded",
    "source": "diniz_2025_development_maturation_cape_gooseberry",
}


@dataclass(frozen=True)
class PhenologySnapshot:
    """Plant-level developmental context retained in morphology metadata."""

    model: str
    profile: str
    thermal_time_degree_days: float
    expected_main_axis_nodes: float
    rendered_main_axis_nodes: int
    first_bifurcation_node: int
    node_count_geometry_policy: str
    parameter_status: str
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReproductivePhenology:
    """One coherent reproductive cohort assignment and its calyx traits."""

    stage: str
    flowering_cohort: int
    ontogenetic_rank: float
    bbch_principal_stage: int
    estimated_days_after_anthesis: float | None
    days_after_anthesis_range: tuple[float, float] | None
    maturity_progress: float
    calyx_state: str | None
    projected_area_scale: float | None
    circularity_target: float | None
    turgor: float | None
    texture_variant: str | None
    vein_contrast: float | None
    apical_darkening: float | None
    parameter_status: str
    provenance: dict[str, Any]


def build_phenology_snapshot(
    profile: str,
    rng: random.Random,
    *,
    rendered_main_axis_nodes: int,
) -> PhenologySnapshot:
    """Sample an auditable developmental snapshot without inflating geometry."""
    low, high = PROFILE_THERMAL_TIME_RANGES_CD.get(
        profile,
        PROFILE_THERMAL_TIME_RANGES_CD["mixed_balanced"],
    )
    degree_days = rng.uniform(low, high)
    breakpoint = float(SALAZAR_NODE_PRIOR["breakpoint_degree_days"])
    first_rate = float(
        SALAZAR_NODE_PRIOR["node_rate_before_breakpoint_per_degree_day"]
    )
    second_rate = float(
        SALAZAR_NODE_PRIOR["node_rate_after_breakpoint_per_degree_day"]
    )
    expected_nodes = first_rate * min(degree_days, breakpoint)
    expected_nodes += second_rate * max(0.0, degree_days - breakpoint)
    return PhenologySnapshot(
        model="literature_cohort_v1",
        profile=profile,
        thermal_time_degree_days=round(degree_days, 2),
        expected_main_axis_nodes=round(expected_nodes, 2),
        rendered_main_axis_nodes=int(rendered_main_axis_nodes),
        first_bifurcation_node=rng.randint(8, 12),
        node_count_geometry_policy=(
            "literature_prior_recorded_only_render_budget_unchanged"
        ),
        parameter_status="literature_bounded_engineering_snapshot",
        provenance={
            "node_prior": dict(SALAZAR_NODE_PRIOR),
            "bbch_source": "ramirez_2013_bbch_physalis",
            "uncertainty": (
                "Thermal and bifurcation priors are not calibrated to the local crop."
            ),
        },
    )


def coherent_stage_sequence(
    unit_count: int,
    stage_weights: Mapping[str, Any],
    rng: random.Random,
) -> list[str]:
    """Return stages ordered oldest-to-youngest with only adjacent overlap."""
    if unit_count <= 0:
        return []
    weights = {
        stage: max(0.0, float(stage_weights.get(stage, 0.0)))
        for stage in STAGE_ORDER
    }
    weight_sum = sum(weights.values()) or 1.0
    raw = {stage: unit_count * value / weight_sum for stage, value in weights.items()}
    counts = {stage: int(math.floor(value)) for stage, value in raw.items()}
    remaining = unit_count - sum(counts.values())
    for stage in sorted(
        STAGE_ORDER,
        key=lambda item: (raw[item] - counts[item], -STAGE_ORDER.index(item)),
        reverse=True,
    )[:remaining]:
        counts[stage] += 1

    # A visible developmental snapshot should retain at least one flower when
    # there are enough reproductive sites, while never sacrificing the four
    # fruiting capachos required by the annotation pipeline.
    if unit_count >= 5 and counts["flower"] == 0:
        donor = max(
            STAGE_ORDER[1:],
            key=lambda item: (counts[item], -STAGE_ORDER.index(item)),
        )
        if counts[donor] > 0:
            counts[donor] -= 1
            counts["flower"] = 1

    ordered: list[str] = []
    for stage in reversed(STAGE_ORDER):
        ordered.extend([stage] * counts[stage])

    # A small seeded adjacent swap represents overlapping cohorts. Swaps are
    # permitted only between neighbouring stages, so a distal flower can never
    # jump directly past a mature/dry cohort.
    for index in range(len(ordered) - 1):
        left = STAGE_ORDER.index(ordered[index])
        right = STAGE_ORDER.index(ordered[index + 1])
        if abs(left - right) == 1 and rng.random() < 0.14:
            ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]
    return ordered


def reproductive_phenology(
    stage: str,
    *,
    cohort_index: int,
    unit_count: int,
    rng: random.Random,
) -> ReproductivePhenology:
    """Derive DAA, BBCH, calyx state, and continuous traits jointly."""
    if stage not in STAGE_ORDER:
        raise ValueError(f"Unknown reproductive stage: {stage}")
    if unit_count <= 1:
        oldness = 1.0
    else:
        oldness = 1.0 - cohort_index / (unit_count - 1)
    oldness = max(0.0, min(1.0, oldness))
    provenance = {
        "bbch_source": "ramirez_2013_bbch_physalis",
        "calyx_prior": dict(DINIZ_CALYX_PRIOR),
        "assignment": "topological_age_rank_with_adjacent_cohort_overlap",
        "uncertainty": (
            "DAA is an inferred literature-bounded range, not a local observation."
        ),
    }
    if stage == "flower":
        return ReproductivePhenology(
            stage=stage,
            flowering_cohort=cohort_index,
            ontogenetic_rank=round(oldness, 4),
            bbch_principal_stage=6,
            estimated_days_after_anthesis=None,
            days_after_anthesis_range=None,
            maturity_progress=0.0,
            calyx_state=None,
            projected_area_scale=None,
            circularity_target=None,
            turgor=None,
            texture_variant=None,
            vein_contrast=None,
            apical_darkening=None,
            parameter_status="literature_bounded_topological_inference",
            provenance=provenance,
        )

    ranges = {
        "young_fruit_with_calyx": (45.0, 59.0, 7),
        "mature_fruit_with_calyx": (60.0, 84.0, 8),
        "exposed_fruit": (85.0, 90.0, 8),
    }
    low, high, bbch = ranges[stage]
    # Older members of a stage occupy its later DAA portion. The jitter is
    # deliberately small and cannot leave the literature-bounded interval.
    local = max(0.0, min(1.0, oldness + rng.uniform(-0.07, 0.07)))
    daa = low + (high - low) * local
    progress = max(0.0, min(1.0, (daa - 45.0) / 45.0))
    if daa < 60.0:
        state = "inflated_green"
    elif daa < 75.0:
        state = "transitioning_yellow"
    elif daa < 85.0:
        state = "straw_yellow"
    else:
        state = "dry_deteriorated"

    area_scale = 1.0 - 0.14 * progress
    circularity = 0.59 - 0.20 * progress
    turgor = 1.0 - 0.24 * progress
    texture_variant, vein_contrast, apical_darkening = _conditioned_texture(
        state,
        daa,
        rng,
    )
    return ReproductivePhenology(
        stage=stage,
        flowering_cohort=cohort_index,
        ontogenetic_rank=round(oldness, 4),
        bbch_principal_stage=bbch,
        estimated_days_after_anthesis=round(daa, 2),
        days_after_anthesis_range=(low, high),
        maturity_progress=round(progress, 4),
        calyx_state=state,
        projected_area_scale=round(area_scale, 4),
        circularity_target=round(circularity, 4),
        turgor=round(turgor, 4),
        texture_variant=texture_variant,
        vein_contrast=vein_contrast,
        apical_darkening=apical_darkening,
        parameter_status="literature_bounded_topological_inference",
        provenance=provenance,
    )


def _conditioned_texture(
    state: str,
    daa: float,
    rng: random.Random,
) -> tuple[str, float, float]:
    variants = {
        "inflated_green": (
            ("calyx_green_v0", 0.58, 0.00),
            ("calyx_green_v1", 0.70, 0.08),
            ("calyx_green_v2", 0.82, 0.24),
            ("calyx_green_v3", 0.94, 0.45),
        ),
        "transitioning_yellow": (
            ("calyx_transition_v0", 0.68, 0.05),
            ("calyx_transition_v1", 0.78, 0.10),
        ),
        "straw_yellow": (
            ("calyx_straw_v0", 0.58, 0.00),
            ("calyx_straw_v1", 0.72, 0.04),
            ("calyx_straw_v2", 0.86, 0.10),
        ),
        "dry_deteriorated": (
            ("calyx_dry_v0", 0.64, 0.00),
            ("calyx_dry_v1", 0.78, 0.06),
            ("calyx_dry_v2", 0.90, 0.12),
        ),
    }
    state_ranges = {
        "inflated_green": (45.0, 60.0),
        "transitioning_yellow": (60.0, 75.0),
        "straw_yellow": (75.0, 85.0),
        "dry_deteriorated": (85.0, 90.0),
    }
    choices = variants[state]
    low, high = state_ranges[state]
    local = (daa - low) / max(high - low, 1e-6)
    local = max(0.0, min(1.0, local + rng.uniform(-0.08, 0.08)))
    index = min(len(choices) - 1, int(round(local * (len(choices) - 1))))
    return choices[index]
