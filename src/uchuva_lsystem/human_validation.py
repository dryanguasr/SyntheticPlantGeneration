"""Pure contracts and scheduling for human validation suites.

The module deliberately has no Blender dependency.  It defines the ten stable
review cases, their problem coverage, render profiles, seed-locking rules, and
the manifest contract consumed by the Blender review runner.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Iterable

from .morphology import SerializableMixin


PROTOCOL_VERSION = "1.0"
SUITE_SCHEMA_VERSION = "1.0"
REVIEW_DECISIONS = {"pending", "pass", "minor", "major", "blocker"}
PROBLEM_REVIEW_OUTCOMES = {"improved", "unchanged", "worse"}
SIGNIFICANT_CHANGE_CATEGORIES = {
    "morphology",
    "growth",
    "contacts",
    "support",
    "geometry",
    "materials",
    "lighting",
    "camera",
    "render",
    "annotations",
}


@dataclass
class ProblemRecord(SerializableMixin):
    """One visual or structural issue that must remain visible in the suite."""

    problem_id: str
    title: str
    category: str
    severity: str
    status: str
    observables: list[str] = field(default_factory=list)
    provenance: str = "human_observation"
    introduced_in: str = "historical"
    notes: str = ""
    schema_version: str = SUITE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProblemRecord":
        return cls(**_filtered(cls, payload))


@dataclass
class RenderQualityProfile(SerializableMixin):
    """Serializable render settings shared by every case in a comparison."""

    name: str
    engine: str
    landscape_resolution: tuple[int, int]
    portrait_resolution: tuple[int, int]
    samples: int
    minimum_samples: int
    noise_threshold: float
    adaptive_sampling: bool
    denoising: bool
    denoiser: str
    denoising_input_passes: str
    denoising_prefilter: str
    preferred_devices: list[str]
    color_depth: str = "16"
    image_format: str = "PNG"
    view_transform: str = "AgX"
    look: str = "Medium High Contrast"
    dither_intensity: float = 0.0
    motion_blur: bool = False
    max_bounces: int = 8
    diffuse_bounces: int = 4
    glossy_bounces: int = 4
    transmission_bounces: int = 6
    transparent_bounces: int = 16
    reflective_caustics: bool = False
    refractive_caustics: bool = False
    parameter_status: str = "engineering_heuristic"
    acceptance_evidence: bool = False
    schema_version: str = SUITE_SCHEMA_VERSION

    def resolution_for(self, orientation: str) -> tuple[int, int]:
        if orientation == "portrait":
            return self.portrait_resolution
        if orientation != "landscape":
            raise ValueError("orientation must be 'landscape' or 'portrait'")
        return self.landscape_resolution

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RenderQualityProfile":
        values = _filtered(cls, payload)
        for key in ("landscape_resolution", "portrait_resolution"):
            if key in values:
                values[key] = tuple(int(item) for item in values[key])
        return cls(**values)


@dataclass
class HumanValidationCase(SerializableMixin):
    """One of the ten stable logical cases in the review protocol."""

    case_id: str
    title: str
    scene_preset: str
    plant_count: int
    phenology_profile: str
    lighting_profile: str
    camera_profile: str
    environment_mode: str
    orientation: str
    condition_mode: str
    support_enabled: bool
    problem_ids: list[str]
    expected_observables: list[str]
    eligibility: dict[str, Any]
    seed_candidates: list[int]
    locked_seed: int | None = None
    model_variant: str = "E_plus_contact_policy_clearance"
    morphology_preset: str = "trained_trellis"
    collision_policy: str = "contact_policy_clearance"
    support_mode: str = "continuous_trellis"
    auxiliary_passes: list[str] = field(default_factory=list)
    parameter_status: str = "engineering_heuristic"
    schema_version: str = SUITE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HumanValidationCase":
        return cls(**_filtered(cls, payload))

    def comparison_signature(self) -> str:
        """Hash all conditions that must match baseline and candidate."""
        payload = self.to_dict()
        payload.pop("locked_seed", None)
        return _stable_hash(payload)


@dataclass
class SeedAttempt(SerializableMixin):
    """Auditable result of one deterministic seed eligibility check."""

    seed: int
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SeedAttempt":
        return cls(**_filtered(cls, payload))


@dataclass
class HumanValidationSuite(SerializableMixin):
    """Top-level manifest for one significant-change review."""

    change_id: str
    change_categories: list[str]
    source_fingerprint: str
    render_profile: RenderQualityProfile
    cases: list[HumanValidationCase]
    problems: list[ProblemRecord]
    baseline_manifest: str | None = None
    bootstrap: bool = False
    active_problem_ids: list[str] = field(default_factory=list)
    generated_at: str | None = None
    status: str = "planned"
    artifacts: dict[str, Any] = field(default_factory=dict)
    human_review: dict[str, Any] = field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION
    schema_version: str = SUITE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HumanValidationSuite":
        values = _filtered(cls, payload)
        values["render_profile"] = RenderQualityProfile.from_dict(
            payload["render_profile"]
        )
        values["cases"] = [
            HumanValidationCase.from_dict(item) for item in payload.get("cases", [])
        ]
        values["problems"] = [
            ProblemRecord.from_dict(item) for item in payload.get("problems", [])
        ]
        return cls(**values)


def render_quality_profiles() -> dict[str, RenderQualityProfile]:
    """Return fresh named profiles so callers can safely customize them."""
    return {
        "diagnostic_eevee": RenderQualityProfile(
            name="diagnostic_eevee",
            engine="BLENDER_EEVEE_NEXT",
            landscape_resolution=(960, 540),
            portrait_resolution=(540, 960),
            samples=64,
            minimum_samples=1,
            noise_threshold=0.0,
            adaptive_sampling=False,
            denoising=False,
            denoiser="NONE",
            denoising_input_passes="RGB",
            denoising_prefilter="NONE",
            preferred_devices=["GPU"],
            color_depth="8",
            look="Medium High Contrast",
            acceptance_evidence=False,
        ),
        "standard_eevee": RenderQualityProfile(
            name="standard_eevee",
            engine="BLENDER_EEVEE_NEXT",
            landscape_resolution=(1280, 720),
            portrait_resolution=(720, 1280),
            samples=128,
            minimum_samples=1,
            noise_threshold=0.0,
            adaptive_sampling=False,
            denoising=False,
            denoiser="NONE",
            denoising_input_passes="RGB",
            denoising_prefilter="NONE",
            preferred_devices=["GPU"],
            color_depth="8",
            look="Medium High Contrast",
            acceptance_evidence=True,
        ),
        "photoreal_review": RenderQualityProfile(
            name="photoreal_review",
            engine="CYCLES",
            landscape_resolution=(1280, 720),
            portrait_resolution=(720, 1280),
            samples=256,
            minimum_samples=32,
            noise_threshold=0.01,
            adaptive_sampling=True,
            denoising=True,
            denoiser="OPENIMAGEDENOISE",
            denoising_input_passes="RGB_ALBEDO_NORMAL",
            denoising_prefilter="ACCURATE",
            preferred_devices=["OPTIX", "CUDA", "CPU"],
            acceptance_evidence=False,
        ),
        "photoreal_final": RenderQualityProfile(
            name="photoreal_final",
            engine="CYCLES",
            landscape_resolution=(1920, 1080),
            portrait_resolution=(1440, 1920),
            samples=512,
            minimum_samples=64,
            noise_threshold=0.005,
            adaptive_sampling=True,
            denoising=True,
            denoiser="OPENIMAGEDENOISE",
            denoising_input_passes="RGB_ALBEDO_NORMAL",
            denoising_prefilter="ACCURATE",
            preferred_devices=["OPTIX", "CUDA", "CPU"],
            acceptance_evidence=True,
        ),
    }


def problem_registry() -> dict[str, ProblemRecord]:
    """Return the current recent and historical human-review problem registry."""
    records = [
        ProblemRecord(
            "render_grain",
            "Grano o textura pixelar ajena a la escena",
            "render",
            "blocker",
            "active",
            ["ruido residual", "fireflies", "relieve de material a escala de píxel"],
            introduced_in="current",
        ),
        ProblemRecord(
            "underexposure",
            "Escenas subexpuestas o sin separación tonal",
            "lighting",
            "major",
            "active",
            ["mediana tonal", "clipping oscuro", "lectura de órganos"],
            introduced_in="current",
        ),
        ProblemRecord(
            "camera_inside_canopy",
            "Cámara global dentro de la copa",
            "camera",
            "major",
            "active",
            ["copa completa en cuadro", "margen de terreno", "escala aparente"],
            introduced_in="current",
        ),
        ProblemRecord(
            "normal_strength",
            "Normales de hojas y capachos exageradas",
            "materials",
            "major",
            "active",
            ["venación", "manchas", "terminador de sombra"],
            introduced_in="current",
        ),
        ProblemRecord(
            "sparse_or_congested_architecture",
            "Arquitectura rala o congestionada por correcciones",
            "morphology",
            "blocker",
            "monitoring",
            ["densidad de ejes", "ejes largos sin hijas", "tamaño foliar"],
        ),
        ProblemRecord(
            "collision_vs_occlusion",
            "Confusión entre colisión física y oclusión visual",
            "contacts",
            "blocker",
            "monitoring",
            ["interpenetración", "clearance", "solapamiento proyectivo"],
        ),
        ProblemRecord(
            "support_morphology",
            "Soporte sin efecto morfológico verificable",
            "support",
            "major",
            "monitoring",
            ["contactos intencionales", "decisiones de crecimiento", "ablación"],
        ),
        ProblemRecord(
            "leaf_pose",
            "Ondulación, rizado o torsión foliar artificial",
            "geometry",
            "major",
            "monitoring",
            ["planitud", "torsión", "postura global"],
        ),
        ProblemRecord(
            "calyx_reading",
            "Capacho esférico, tubular o con costillas falsas",
            "geometry",
            "major",
            "monitoring",
            ["silueta lantern_squash", "depresiones", "venación"],
        ),
        ProblemRecord(
            "attachment_and_visibility",
            "Unión axilar, fruto oculto o contrato YOLO incorrectos",
            "annotations",
            "blocker",
            "monitoring",
            ["pedicelo", "capacho cerrado", "fruto oculto", "clase calyx"],
        ),
        ProblemRecord(
            "fake_environment",
            "Fondo sintético falso o borde del terreno visible",
            "lighting",
            "major",
            "monitoring",
            ["HDRI", "suelo", "borde de terreno", "vegetación contextual"],
        ),
    ]
    return {item.problem_id: item for item in records}


def fixed_validation_cases() -> list[HumanValidationCase]:
    """Return the stable ten-case matrix in protocol order."""
    seeds = list(range(20))
    return [
        HumanValidationCase(
            "case_01",
            "Arquitectura global densa",
            "dense_trellis_synchronous",
            20,
            "mixed_balanced",
            "clear_midday",
            "context_wide",
            "open_field_hybrid",
            "landscape",
            "healthy",
            True,
            [
                "sparse_or_congested_architecture",
                "camera_inside_canopy",
                "underexposure",
            ],
            ["copa completa", "densidad por ramificación", "margen de terreno"],
            {"minimum_axes_per_plant": 3.0, "maximum_long_axis_fraction": 0.35},
            seeds,
        ),
        HumanValidationCase(
            "case_02",
            "Ocupación interplanta",
            "dense_trellis_synchronous",
            20,
            "mixed_balanced",
            "overcast_soft",
            "human_oblique_mid",
            "canopy_close",
            "landscape",
            "healthy",
            True,
            ["collision_vs_occlusion", "camera_inside_canopy", "underexposure"],
            ["oclusiones visibles", "clearance duro", "mezcla entre plantas"],
            {"minimum_visual_occlusions": 1, "maximum_proxy_conflicts": 0},
            seeds,
        ),
        HumanValidationCase(
            "case_03",
            "Trellis y contactos intencionales",
            "row_canopy",
            12,
            "mixed_early",
            "clear_morning",
            "robot_close_oblique",
            "open_field_hybrid",
            "landscape",
            "healthy",
            True,
            ["support_morphology", "collision_vs_occlusion"],
            ["amarres", "guía de ejes", "contactos intencionales"],
            {"minimum_intentional_contacts": 1, "maximum_proxy_conflicts": 0},
            seeds,
        ),
        HumanValidationCase(
            "case_04",
            "Ablación del soporte",
            "row_canopy",
            12,
            "mixed_early",
            "clear_morning",
            "robot_close_oblique",
            "open_field_hybrid",
            "landscape",
            "healthy",
            False,
            ["support_morphology", "sparse_or_congested_architecture"],
            ["cambio de decisiones", "porte sin guía", "topología comparable"],
            {"minimum_reproductive_units": 1, "maximum_proxy_conflicts": 0},
            seeds,
        ),
        HumanValidationCase(
            "case_05",
            "Fenología temprana y uniones axilares",
            "row_canopy",
            8,
            "mixed_early",
            "overcast_soft",
            "real_close",
            "canopy_close",
            "portrait",
            "healthy",
            True,
            ["attachment_and_visibility", "underexposure"],
            ["flores", "frutos jóvenes", "pedicelos conectados"],
            {"minimum_flowers": 1, "minimum_reproductive_units": 4},
            seeds,
        ),
        HumanValidationCase(
            "case_06",
            "Fenología tardía y condición seca",
            "row_canopy",
            8,
            "mixed_late",
            "late_afternoon",
            "real_close",
            "ground_tangle",
            "portrait",
            "mixed_drying",
            True,
            ["attachment_and_visibility", "calyx_reading", "normal_strength"],
            ["capachos maduros", "fruto oculto", "variación pajiza y seca"],
            {"minimum_calyxes": 3, "minimum_drying_plants": 1},
            seeds,
        ),
        HumanValidationCase(
            "case_07",
            "Hoja y material en fondo neutral",
            "single_plant_study",
            1,
            "mixed_balanced",
            "clear_morning",
            "real_close",
            "isolated_neutral",
            "portrait",
            "healthy",
            False,
            ["leaf_pose", "render_grain", "normal_strength"],
            ["lámina plana", "detalle UV", "terminador de sombra"],
            {"minimum_leaves": 4},
            seeds,
            support_mode="none",
            auxiliary_passes=["albedo", "normal", "sample_count", "material_override"],
        ),
        HumanValidationCase(
            "case_08",
            "Capacho en iluminación lateral",
            "annotation_foreground_pilot",
            4,
            "mixed_late",
            "clear_midday",
            "robot_close_oblique",
            "isolated_neutral",
            "landscape",
            "mixed_drying",
            True,
            ["calyx_reading", "render_grain", "normal_strength"],
            ["silueta", "costillas discretas", "relieve sin grano"],
            {"minimum_calyxes": 2},
            seeds,
            auxiliary_passes=["albedo", "normal", "sample_count", "material_override"],
        ),
        HumanValidationCase(
            "case_09",
            "Contraluz y convergencia",
            "row_canopy",
            12,
            "mixed_balanced",
            "late_afternoon",
            "human_oblique_mid",
            "canopy_close",
            "landscape",
            "healthy",
            True,
            ["render_grain", "underexposure", "normal_strength"],
            ["fireflies", "tallos finos", "detalle tras denoising"],
            {"minimum_leaves": 20, "maximum_proxy_conflicts": 0},
            seeds,
            auxiliary_passes=["albedo", "normal", "sample_count", "material_override"],
        ),
        HumanValidationCase(
            "case_10",
            "Regresión integral de cultivo y entorno",
            "dense_trellis_synchronous",
            20,
            "mixed_late",
            "overcast_soft",
            "context_wide",
            "ground_tangle",
            "landscape",
            "mixed_drying",
            True,
            [
                "fake_environment",
                "camera_inside_canopy",
                "underexposure",
                "attachment_and_visibility",
            ],
            ["terreno continuo", "sin sustitutos de copa", "regresión YOLO"],
            {
                "minimum_calyxes": 4,
                "minimum_drying_plants": 1,
                "maximum_proxy_conflicts": 0,
            },
            seeds,
        ),
    ]


def validate_protocol(
    cases: Iterable[HumanValidationCase],
    *,
    active_problem_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate the fixed matrix and return an auditable coverage report."""
    active_cases = list(cases)
    errors: list[str] = []
    registry = problem_registry()
    case_ids = [item.case_id for item in active_cases]
    if len(active_cases) != 10:
        errors.append(f"Protocol must contain exactly 10 cases, got {len(active_cases)}.")
    if len(case_ids) != len(set(case_ids)):
        errors.append("Case ids must be unique.")
    if case_ids != [f"case_{index:02d}" for index in range(1, 11)]:
        errors.append("Case ids must remain ordered from case_01 through case_10.")

    coverage = {problem_id: 0 for problem_id in registry}
    for item in active_cases:
        if item.orientation not in {"landscape", "portrait"}:
            errors.append(f"{item.case_id}: unsupported orientation.")
        if not item.seed_candidates:
            errors.append(f"{item.case_id}: seed_candidates cannot be empty.")
        if item.locked_seed is not None and item.locked_seed not in item.seed_candidates:
            errors.append(f"{item.case_id}: locked_seed is outside seed_candidates.")
        for problem_id in item.problem_ids:
            if problem_id not in registry:
                errors.append(f"{item.case_id}: unknown problem id {problem_id!r}.")
                continue
            coverage[problem_id] += 1

    by_id = {item.case_id: item for item in active_cases}
    support_case = by_id.get("case_03")
    ablation_case = by_id.get("case_04")
    if support_case is not None and ablation_case is not None:
        paired_fields = (
            "scene_preset",
            "plant_count",
            "phenology_profile",
            "lighting_profile",
            "camera_profile",
            "environment_mode",
            "orientation",
            "condition_mode",
            "model_variant",
            "morphology_preset",
            "collision_policy",
        )
        drifted = [
            name
            for name in paired_fields
            if getattr(support_case, name) != getattr(ablation_case, name)
        ]
        if drifted:
            errors.append(
                "case_03/case_04 support ablation conditions differ: "
                + ", ".join(drifted)
            )
        if not support_case.support_enabled or ablation_case.support_enabled:
            errors.append(
                "case_03 must enable support and case_04 must ablate it."
            )
        if support_case.seed_candidates != ablation_case.seed_candidates:
            errors.append(
                "case_03/case_04 must share the same seed candidate sequence."
            )
        if (
            support_case.locked_seed is not None
            and ablation_case.locked_seed is not None
            and support_case.locked_seed != ablation_case.locked_seed
        ):
            errors.append(
                "case_03/case_04 must keep the same locked seed."
            )

    active_ids = list(
        active_problem_ids
        if active_problem_ids is not None
        else [
            problem_id
            for problem_id, item in registry.items()
            if item.introduced_in == "current" and item.status == "active"
        ]
    )
    for problem_id in active_ids:
        if problem_id not in registry:
            errors.append(f"Unknown active problem id {problem_id!r}.")
        elif coverage[problem_id] < 3:
            errors.append(
                f"Active problem {problem_id!r} requires at least 3 cases; "
                f"found {coverage[problem_id]}."
            )
    for problem_id, item in registry.items():
        if item.severity == "blocker" and coverage[problem_id] < 1:
            errors.append(f"Historical blocker {problem_id!r} is not covered.")

    phenology = _counts(item.phenology_profile for item in active_cases)
    lighting = _counts(item.lighting_profile for item in active_cases)
    environments = _counts(item.environment_mode for item in active_cases)
    if phenology != {"mixed_balanced": 4, "mixed_early": 3, "mixed_late": 3}:
        errors.append(f"Unexpected phenology distribution: {phenology}.")
    expected_lighting = {
        "clear_midday": 2,
        "clear_morning": 3,
        "late_afternoon": 2,
        "overcast_soft": 3,
    }
    if lighting != expected_lighting:
        errors.append(f"Unexpected lighting distribution: {lighting}.")
    if set(environments) != {
        "canopy_close",
        "ground_tangle",
        "isolated_neutral",
        "open_field_hybrid",
    }:
        errors.append(f"All four environment modes are required: {environments}.")

    return {
        "status": "valid" if not errors else "invalid",
        "protocol_version": PROTOCOL_VERSION,
        "case_count": len(active_cases),
        "problem_coverage": coverage,
        "phenology_distribution": phenology,
        "lighting_distribution": lighting,
        "environment_distribution": environments,
        "errors": errors,
    }


def select_case_seed(
    case: HumanValidationCase,
    evaluator: Callable[
        [HumanValidationCase, int], tuple[bool, list[str], dict[str, Any]]
    ],
) -> tuple[int, list[SeedAttempt]]:
    """Select the first eligible seed, or verify an already locked seed."""
    candidates = (
        [case.locked_seed]
        if case.locked_seed is not None
        else list(case.seed_candidates)
    )
    attempts: list[SeedAttempt] = []
    for seed in candidates:
        if seed is None:
            continue
        eligible, reasons, metrics = evaluator(case, int(seed))
        attempt = SeedAttempt(int(seed), bool(eligible), list(reasons), dict(metrics))
        attempts.append(attempt)
        if eligible:
            return int(seed), attempts
    reason_text = "; ".join(
        f"{item.seed}: {', '.join(item.reasons) or 'ineligible'}" for item in attempts
    )
    raise RuntimeError(
        f"{case.case_id} has no eligible seed in its declared sequence. {reason_text}"
    )


def lock_cases_from_baseline(
    cases: Iterable[HumanValidationCase],
    baseline_payload: dict[str, Any],
) -> list[HumanValidationCase]:
    """Lock candidate cases to accepted baseline seeds and conditions."""
    if baseline_payload.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError(
            "Baseline protocol_version differs; create an explicit bootstrap."
        )
    baseline_cases = {
        item["case_id"]: HumanValidationCase.from_dict(item)
        for item in baseline_payload.get("cases", [])
    }
    result: list[HumanValidationCase] = []
    for item in cases:
        baseline = baseline_cases.get(item.case_id)
        if baseline is None:
            raise ValueError(f"Baseline is missing {item.case_id}.")
        if baseline.comparison_signature() != item.comparison_signature():
            raise ValueError(
                f"{item.case_id} conditions changed; increment protocol_version "
                "and create a new bootstrap."
            )
        if baseline.locked_seed is None:
            raise ValueError(f"Baseline {item.case_id} does not have a locked seed.")
        payload = item.to_dict()
        payload["locked_seed"] = baseline.locked_seed
        result.append(HumanValidationCase.from_dict(payload))
    return result


def build_validation_suite(
    *,
    change_id: str,
    change_categories: Iterable[str],
    source_fingerprint: str,
    render_profile_name: str = "standard_eevee",
    baseline_manifest: str | Path | None = None,
    bootstrap: bool = False,
    active_problem_ids: Iterable[str] | None = None,
) -> HumanValidationSuite:
    """Create and validate a planned suite before any Blender work begins."""
    if not change_id.strip():
        raise ValueError("change_id must be a non-empty identifier.")
    categories = sorted(set(change_categories))
    unknown_categories = sorted(set(categories) - SIGNIFICANT_CHANGE_CATEGORIES)
    if unknown_categories:
        raise ValueError(f"Unknown significant change categories: {unknown_categories}")
    if bootstrap == (baseline_manifest is not None):
        raise ValueError("Pass exactly one of bootstrap=True or baseline_manifest.")
    profiles = render_quality_profiles()
    if render_profile_name not in profiles:
        raise ValueError(f"Unknown render profile {render_profile_name!r}.")

    cases = fixed_validation_cases()
    baseline_path: str | None = None
    if baseline_manifest is not None:
        path = Path(baseline_manifest).resolve()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "accepted_baseline":
            raise ValueError(
                "baseline_manifest must reference a manually promoted "
                "accepted_baseline suite."
            )
        baseline_profile = payload.get("render_profile", {}).get("name")
        if baseline_profile != render_profile_name:
            raise ValueError(
                "baseline_manifest render profile differs from the requested "
                "profile; create a new bootstrap or explicitly select the "
                "baseline profile."
            )
        cases = lock_cases_from_baseline(cases, payload)
        baseline_path = str(path)

    active_ids = list(
        active_problem_ids
        if active_problem_ids is not None
        else [
            problem_id
            for problem_id, item in problem_registry().items()
            if item.introduced_in == "current" and item.status == "active"
        ]
    )
    protocol_report = validate_protocol(cases, active_problem_ids=active_ids)
    if protocol_report["status"] != "valid":
        raise ValueError("; ".join(protocol_report["errors"]))
    return HumanValidationSuite(
        change_id=change_id.strip(),
        change_categories=categories,
        source_fingerprint=source_fingerprint,
        render_profile=profiles[render_profile_name],
        cases=cases,
        problems=list(problem_registry().values()),
        baseline_manifest=baseline_path,
        bootstrap=bootstrap,
        active_problem_ids=active_ids,
        artifacts={"protocol_validation": protocol_report},
        human_review={
            "status": "pending",
            "allowed_decisions": sorted(REVIEW_DECISIONS),
            "acceptance_rule": {
                "minimum_pass": 8,
                "maximum_minor": 2,
                "maximum_major": 0,
                "maximum_blocker": 0,
            },
        },
    )


def build_case_morphologies(
    case: HumanValidationCase,
    seed: int,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build one case without Blender and return scene, plants, report, metrics."""
    from .cultivation import generate_cultivation_morphologies
    from .grammar import generate_morphology_tree
    from .metrics import compute_scene_metrics
    from .parameters import get_morphology_parameters
    from .scene import create_cultivation_scene

    support_mode = case.support_mode if case.support_enabled else "none"
    scene = create_cultivation_scene(
        seed=seed,
        preset_name=case.scene_preset,
        plant_count=case.plant_count,
        collision_policy=case.collision_policy,
        support_mode=support_mode,
    )
    _apply_condition_mode(scene, case.condition_mode)
    params = get_morphology_parameters(case.morphology_preset)
    potential_plants = {
        instance.plant_id: generate_morphology_tree(
            seed=instance.seed,
            params=params,
            phenology_profile=case.phenology_profile,
            condition=instance.condition,
        )
        for instance in scene.plant_instances
    }
    scene, plants_by_id, adaptation = generate_cultivation_morphologies(
        scene,
        params,
        case.model_variant,
        potential_plants=potential_plants,
        support_enabled_override=case.support_enabled,
    )
    scene.metadata["human_validation_case"] = {
        "case_id": case.case_id,
        "phenology_profile": case.phenology_profile,
        "lighting_profile": case.lighting_profile,
        "camera_profile": case.camera_profile,
        "environment_mode": case.environment_mode,
        "condition_mode": case.condition_mode,
        "support_enabled": case.support_enabled,
    }
    metrics = compute_scene_metrics(
        scene,
        plants_by_id,
        model_variant=case.model_variant,
    ).to_dict()
    return scene, plants_by_id, adaptation, metrics


def evaluate_case_seed(
    case: HumanValidationCase,
    seed: int,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Evaluate predeclared pure eligibility predicates for one case seed."""
    scene, _plants, _adaptation, metrics = build_case_morphologies(case, seed)
    morphology = metrics["morphology"]
    counts = morphology["organ_counts"]
    contacts = metrics["contacts"]
    drying_count = sum(
        1 for item in scene.plant_instances if item.condition == "drying"
    )
    observed = {
        "plant_count": counts["plants"],
        "axes_per_plant": morphology["axes_per_plant"],
        "long_axis_fraction": morphology["long_axes_without_children_fraction"],
        "leaves": counts["leaves"],
        "reproductive_units": counts["reproductive_units"],
        "flowers": counts["flowers"],
        "calyxes": counts["calyxes"],
        "drying_plants": drying_count,
        "proxy_conflicts": contacts["proxy_conflicts"],
        "clearance_violations": contacts["clearance_violations"],
        "intentional_contacts": contacts["intentional_contacts"],
        "visual_occlusions": contacts["visual_occlusions"],
    }
    predicates = {
        "minimum_axes_per_plant": (
            observed["axes_per_plant"],
            lambda actual, expected: actual >= expected,
        ),
        "maximum_long_axis_fraction": (
            observed["long_axis_fraction"],
            lambda actual, expected: actual <= expected,
        ),
        "minimum_visual_occlusions": (
            observed["visual_occlusions"],
            lambda actual, expected: actual >= expected,
        ),
        "maximum_proxy_conflicts": (
            observed["proxy_conflicts"],
            lambda actual, expected: actual <= expected,
        ),
        "minimum_intentional_contacts": (
            observed["intentional_contacts"],
            lambda actual, expected: actual >= expected,
        ),
        "minimum_reproductive_units": (
            observed["reproductive_units"],
            lambda actual, expected: actual >= expected,
        ),
        "minimum_flowers": (
            observed["flowers"],
            lambda actual, expected: actual >= expected,
        ),
        "minimum_calyxes": (
            observed["calyxes"],
            lambda actual, expected: actual >= expected,
        ),
        "minimum_drying_plants": (
            observed["drying_plants"],
            lambda actual, expected: actual >= expected,
        ),
        "minimum_leaves": (
            observed["leaves"],
            lambda actual, expected: actual >= expected,
        ),
    }
    reasons: list[str] = []
    for key, expected in case.eligibility.items():
        if key not in predicates:
            reasons.append(f"unsupported eligibility predicate {key}")
            continue
        actual, predicate = predicates[key]
        if not predicate(actual, expected):
            reasons.append(f"{key}: expected {expected}, observed {actual}")
    if contacts["clearance_violations"] > 0:
        reasons.append(
            "clearance_violations: expected 0, observed "
            f"{contacts['clearance_violations']}"
        )
    return not reasons, reasons, observed


def evaluate_human_review(
    rows: Iterable[dict[str, Any]],
    *,
    required_problem_cases: dict[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Evaluate case decisions and, when requested, per-problem outcomes."""
    active_rows = list(rows)
    errors: list[str] = []
    if len(active_rows) != 10:
        errors.append(f"Expected 10 human review rows, got {len(active_rows)}.")
    counts = {decision: 0 for decision in REVIEW_DECISIONS}
    case_ids: set[str] = set()
    for row in active_rows:
        case_id = str(row.get("case_id", ""))
        decision = str(row.get("decision", "pending")).lower()
        if not case_id or case_id in case_ids:
            errors.append(f"Missing or duplicate case_id {case_id!r}.")
        case_ids.add(case_id)
        if decision not in REVIEW_DECISIONS:
            errors.append(f"{case_id}: invalid decision {decision!r}.")
            continue
        counts[decision] += 1
    problem_summary: dict[str, Any] = {}
    if required_problem_cases:
        rows_by_case = {
            str(row.get("case_id", "")): row for row in active_rows
        }
        for problem_id, exposed_case_ids in sorted(
            required_problem_cases.items()
        ):
            exposed = list(dict.fromkeys(str(item) for item in exposed_case_ids))
            outcome_counts = {
                outcome: 0 for outcome in sorted(PROBLEM_REVIEW_OUTCOMES)
            }
            missing: list[str] = []
            for case_id in exposed:
                outcomes = _parse_problem_outcomes(
                    str(rows_by_case.get(case_id, {}).get("problem_outcomes", ""))
                )
                outcome = outcomes.get(problem_id)
                if outcome not in PROBLEM_REVIEW_OUTCOMES:
                    missing.append(case_id)
                    continue
                outcome_counts[outcome] += 1
            required_improvements = len(exposed) // 2 + 1
            problem_passed = (
                not missing
                and outcome_counts["worse"] == 0
                and outcome_counts["improved"] >= required_improvements
            )
            if missing:
                errors.append(
                    f"{problem_id}: missing problem outcome for "
                    f"{', '.join(missing)}."
                )
            if outcome_counts["worse"]:
                errors.append(
                    f"{problem_id}: worsened in "
                    f"{outcome_counts['worse']} exposed case(s)."
                )
            if outcome_counts["improved"] < required_improvements:
                errors.append(
                    f"{problem_id}: requires improvement in "
                    f"{required_improvements}/{len(exposed)} exposed cases; "
                    f"found {outcome_counts['improved']}."
                )
            problem_summary[problem_id] = {
                "exposed_case_ids": exposed,
                "required_improvements": required_improvements,
                "outcome_counts": outcome_counts,
                "missing_case_ids": missing,
                "status": "accepted" if problem_passed else "not_accepted",
            }
    accepted = (
        not errors
        and counts["pending"] == 0
        and counts["major"] == 0
        and counts["blocker"] == 0
        and counts["pass"] >= 8
        and counts["minor"] <= 2
    )
    return {
        "status": "accepted" if accepted else "not_accepted",
        "decision_counts": counts,
        "problem_outcomes": problem_summary,
        "errors": errors,
    }


def _apply_condition_mode(scene: Any, condition_mode: str) -> None:
    if condition_mode == "healthy":
        for instance in scene.plant_instances:
            instance.condition = "healthy"
        return
    if condition_mode == "mixed_drying":
        for index, instance in enumerate(scene.plant_instances):
            instance.condition = "drying" if index % 4 == 0 else "healthy"
        return
    if condition_mode == "drying":
        for instance in scene.plant_instances:
            instance.condition = "drying"
        return
    raise ValueError(f"Unknown condition_mode {condition_mode!r}.")


def _filtered(cls: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    accepted = {item.name for item in fields(cls)}
    return {key: value for key, value in payload.items() if key in accepted}


def _counts(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _parse_problem_outcomes(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in raw.split("|"):
        if "=" not in token:
            continue
        problem_id, outcome = token.split("=", 1)
        problem_id = problem_id.strip()
        outcome = outcome.strip().lower()
        if problem_id:
            result[problem_id] = outcome
    return result


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
