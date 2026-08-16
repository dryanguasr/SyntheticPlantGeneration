"""Generate the ten-case human-validation suite inside Blender.

Example:

    blender --background --python scripts/generate_human_validation_suite.py -- \
      --change-id render_photoreal_v1 --change-category render --bootstrap

The default is the standard Eevee acceptance profile. Cycles profiles remain
available only through an explicit ``--render-profile`` selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_environment import (
    apply_lighting_profile,
    create_outdoor_environment,
    pack_environment_assets,
)
from uchuva_lsystem.blender_geometry import (
    audit_scene_mesh_collisions,
    build_geometry_from_morphology,
    create_cultivation_supports,
)
from uchuva_lsystem.blender_review import (
    compose_before_after,
    compose_suite_contact_sheet,
    configure_render_profile,
    create_case_camera,
    lock_camera_to_report,
    render_auxiliary_diagnostics,
    render_beauty_with_preflight,
)
from uchuva_lsystem.blender_scene import (
    cleanup_scene,
    create_project_materials,
    save_blend_file,
)
from uchuva_lsystem.collisions import audit_proxy_contacts
from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.human_validation import (
    HumanValidationCase,
    build_case_morphologies,
    build_validation_suite,
    evaluate_case_seed,
    render_quality_profiles,
    select_case_seed,
)
from uchuva_lsystem.metrics import compute_scene_metrics, source_tree_fingerprint
from uchuva_lsystem.validation import (
    validate_cultivation_scene,
    validate_morphology_tree,
)
from uchuva_lsystem.yolo_export import YOLO_CLASSES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a reproducible ten-case human validation suite."
    )
    parser.add_argument("--change-id", required=True)
    parser.add_argument(
        "--change-category",
        action="append",
        required=True,
        dest="change_categories",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bootstrap", action="store_true")
    mode.add_argument("--baseline-manifest", type=Path)
    parser.add_argument(
        "--render-profile",
        choices=sorted(render_quality_profiles()),
        default="standard_eevee",
    )
    parser.add_argument(
        "--focus-problem",
        action="append",
        dest="focus_problems",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--audit-mode",
        choices=("full_mesh", "proxy"),
        default="full_mesh",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Generate a subset for smoke/debug; repeat for multiple cases.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use diagnostic Eevee and proxy audit; never acceptance evidence.",
    )
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--organ-texture-dir", type=Path)
    parser.add_argument("--environment-asset-dir", type=Path)
    parser.add_argument("--environment-asset-blend", type=Path)
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    output_dir = (
        _repo_path(args.output_dir)
        if args.output_dir is not None
        else REPO_ROOT / "outputs" / "human_validation" / args.change_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_manifest = (
        _repo_path(args.baseline_manifest)
        if args.baseline_manifest is not None
        else None
    )
    source_fingerprint = source_tree_fingerprint(REPO_ROOT)
    profile_name = "diagnostic_eevee" if args.smoke else args.render_profile
    audit_mode = "proxy" if args.smoke else args.audit_mode
    suite = build_validation_suite(
        change_id=args.change_id,
        change_categories=args.change_categories,
        source_fingerprint=source_fingerprint,
        render_profile_name=profile_name,
        baseline_manifest=baseline_manifest,
        bootstrap=args.bootstrap,
        active_problem_ids=args.focus_problems,
    )
    if (
        not args.smoke
        and not args.skip_render
        and not suite.render_profile.acceptance_evidence
        and not args.case_ids
    ):
        raise ValueError(
            "A full human-validation run requires an acceptance profile. "
            "Use standard_eevee (default), or --smoke for a diagnostic subset."
        )

    selected_case_ids = (
        list(dict.fromkeys(args.case_ids))
        if args.case_ids
        else [item.case_id for item in suite.cases]
    )
    known_case_ids = {item.case_id for item in suite.cases}
    unknown_case_ids = sorted(set(selected_case_ids) - known_case_ids)
    if unknown_case_ids:
        raise ValueError(f"Unknown case ids: {unknown_case_ids}")

    environment_carrier = _environment_carrier(args.environment_asset_blend)
    organ_texture_dir = (
        _repo_path(args.organ_texture_dir)
        if args.organ_texture_dir is not None
        else REPO_ROOT / "assets" / "textures" / "current"
    )
    environment_asset_dir = (
        _repo_path(args.environment_asset_dir)
        if args.environment_asset_dir is not None
        else None
    )
    baseline_payload = (
        json.loads(baseline_manifest.read_text(encoding="utf-8"))
        if baseline_manifest is not None
        else None
    )
    manifest_path = output_dir / "suite_manifest.json"
    suite.generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    suite.status = "running"
    suite.artifacts.update(
        {
            "output_directory": str(output_dir),
            "audit_mode": audit_mode,
            "smoke": bool(args.smoke),
            "skip_render": bool(args.skip_render),
            "environment_asset_blend": (
                _file_record(environment_carrier)
                if environment_carrier
                else None
            ),
            "organ_texture_source": _directory_record(organ_texture_dir),
            "environment_asset_source": (
                _directory_record(environment_asset_dir)
                if environment_asset_dir
                else None
            ),
            "manifest_sha256_sidecar": "suite_manifest.json.sha256",
            "cases": {},
        }
    )
    _write_manifest(suite, manifest_path)

    total_started = time.perf_counter()
    comparison_paths: list[Path] = []
    for case in suite.cases:
        if case.case_id not in selected_case_ids:
            continue
        print(f"[human-validation] starting {case.case_id}: {case.title}")
        case_report = _generate_case(
            case,
            suite=suite,
            output_dir=output_dir,
            baseline_payload=baseline_payload,
            baseline_manifest=baseline_manifest,
            audit_mode=audit_mode,
            render_enabled=not args.skip_render,
            organ_texture_dir=organ_texture_dir,
            environment_asset_dir=environment_asset_dir,
            environment_carrier=environment_carrier,
        )
        suite.artifacts["cases"][case.case_id] = case_report
        comparison = case_report.get("comparison", {}).get("path")
        if comparison:
            comparison_paths.append(Path(comparison))
        _write_manifest(suite, manifest_path)
        print(f"[human-validation] completed {case.case_id}")

    full_suite = len(selected_case_ids) == 10
    if full_suite and len(comparison_paths) == 10:
        contact_sheet = compose_suite_contact_sheet(
            [str(path) for path in comparison_paths],
            output_dir / "contact_sheet_10_cases.png",
        )
        suite.artifacts["contact_sheet"] = _file_record(
            contact_sheet, root=output_dir
        )
    _write_review_form(suite, output_dir / "human_review.csv")
    suite.artifacts["elapsed_seconds"] = round(
        time.perf_counter() - total_started, 4
    )
    acceptance_attempt = (
        full_suite
        and not args.smoke
        and not args.skip_render
        and audit_mode == "full_mesh"
        and suite.render_profile.acceptance_evidence
    )
    acceptance_ready = (
        acceptance_attempt
        and all(
            item.get("generation_status") == "complete"
            and not item.get("acceptance_blockers")
            for item in suite.artifacts["cases"].values()
        )
    )
    suite.status = (
        "complete_pending_human_review"
        if acceptance_ready
        else "complete_with_acceptance_blockers"
        if acceptance_attempt
        else "smoke_complete"
    )
    _write_markdown_report(suite, output_dir / "report.md")
    _write_manifest(suite, manifest_path)
    print(f"Wrote human validation manifest: {manifest_path}")
    print(f"Suite status: {suite.status}")


def _generate_case(
    case: HumanValidationCase,
    *,
    suite: Any,
    output_dir: Path,
    baseline_payload: dict[str, Any] | None,
    baseline_manifest: Path | None,
    audit_mode: str,
    render_enabled: bool,
    organ_texture_dir: Path | None,
    environment_asset_dir: Path | None,
    environment_carrier: Path | None,
) -> dict[str, Any]:
    case_dir = output_dir / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    if case.case_id == "case_04":
        support_case = next(
            item for item in suite.cases if item.case_id == "case_03"
        )
        if support_case.locked_seed is None:
            support_seed, _support_attempts = select_case_seed(
                support_case,
                evaluate_case_seed,
            )
            support_case.locked_seed = support_seed
        if (
            case.locked_seed is not None
            and case.locked_seed != support_case.locked_seed
        ):
            raise RuntimeError(
                "case_04 seed differs from the locked case_03 support seed."
            )
        case.locked_seed = support_case.locked_seed
    if case.locked_seed is None:
        selected_seed, attempts = select_case_seed(case, evaluate_case_seed)
        case.locked_seed = selected_seed
    else:
        selected_seed, attempts = select_case_seed(case, evaluate_case_seed)
    seed_report = {
        "locked_seed": selected_seed,
        "attempts": [item.to_dict() for item in attempts],
        "selection_policy": "first_predeclared_eligible_seed_no_visual_selection",
    }

    case_started = time.perf_counter()
    scene_data, plants_by_id, adaptation_report, _eligibility_metrics = (
        build_case_morphologies(case, selected_seed)
    )

    baseline_report: dict[str, Any] = {"status": "unavailable"}
    bootstrap_camera_report: dict[str, Any] | None = None
    locked_exposure = _baseline_exposure(baseline_payload, case.case_id)
    if suite.bootstrap and render_enabled:
        baseline_report = _generate_bootstrap_baseline(
            case,
            seed=selected_seed,
            suite=suite,
            case_dir=case_dir,
            organ_texture_dir=organ_texture_dir,
            environment_asset_dir=environment_asset_dir,
            environment_carrier=environment_carrier,
        )
        bootstrap_camera_report = dict(baseline_report["camera"])
        locked_exposure = float(
            baseline_report["preflight"]["applied_exposure_ev"]
        )

    cleanup_scene()
    materials = create_project_materials(
        seed=selected_seed + 3000,
        texture_asset_dir=organ_texture_dir,
    )
    geometry_reports, morphology_reports, support_report = (
        _build_case_geometry(scene_data, plants_by_id, materials)
    )
    if audit_mode == "full_mesh":
        mesh_audit = audit_scene_mesh_collisions()
    else:
        proxy = audit_proxy_contacts(scene_data, plants_by_id)
        mesh_audit = {
            **proxy,
            "status": "proxy_only",
            "authority": "full_mesh_required_for_acceptance",
            "physical_collision_count": len(proxy.get("proxy_conflicts", [])),
            "clearance_violation_count": len(
                proxy.get("clearance_violations", [])
            ),
        }
    scene_data.metadata["plant_morphology_reports"] = morphology_reports
    scene_data.metadata["geometry_reports"] = geometry_reports
    scene_data.metadata["cultivation_adaptation"] = adaptation_report
    scene_data.metadata["support_geometry"] = support_report
    scene_data.metadata["mesh_collision_audit"] = mesh_audit
    scene_validation = validate_cultivation_scene(scene_data)
    scene_data.metadata["scene_validation_status"] = scene_validation["status"]
    metrics = compute_scene_metrics(
        scene_data,
        plants_by_id,
        model_variant=case.model_variant,
        performance={
            "pure_and_geometry_elapsed_seconds": round(
                time.perf_counter() - case_started, 4
            )
        },
        source_fingerprint=suite.source_fingerprint,
    )
    annotation_contract = _verify_annotation_contract(
        scene_data,
        plants_by_id,
        geometry_reports,
    )

    center_x, center_y, radius = _scene_center_radius(scene_data)
    environment = create_outdoor_environment(
        seed=selected_seed,
        scene_radius=radius,
        terrain_size=scene_data.environment.terrain_size,
        terrain_subdivisions=scene_data.environment.terrain_subdivisions,
        background_cluster_count=scene_data.environment.background_cluster_count,
        asset_dir=environment_asset_dir,
        packed_asset_blend=environment_carrier,
        mode=case.environment_mode,
    )
    lighting = apply_lighting_profile(case.lighting_profile, selected_seed)
    camera, camera_report = create_case_camera(
        case, scene_data, geometry_reports
    )
    baseline_camera_report = (
        bootstrap_camera_report
        if bootstrap_camera_report is not None
        else _baseline_camera_report(baseline_payload, case.case_id)
    )
    if baseline_camera_report is not None:
        camera_report = lock_camera_to_report(
            camera,
            baseline_camera_report,
            camera_report,
        )
    render_configuration = configure_render_profile(
        suite.render_profile,
        orientation=case.orientation,
    )

    beauty_report: dict[str, Any] = {"status": "skipped"}
    comparison_report: dict[str, Any] = {"status": "unavailable"}
    auxiliary_report: dict[str, Any] = {}
    if render_enabled:
        if not suite.bootstrap:
            baseline_path = _baseline_beauty_path(
                baseline_payload,
                baseline_manifest,
                case.case_id,
            )
            baseline_report = {
                "status": "reused_accepted_baseline",
                **_file_record(baseline_path),
            }

        candidate_path = case_dir / "candidate.png"
        beauty_report = {
            "status": "rendered",
            **render_beauty_with_preflight(
                camera,
                candidate_path,
                suite.render_profile,
                orientation=case.orientation,
                locked_exposure=locked_exposure,
            ),
        }
        if case.auxiliary_passes:
            auxiliary_report = render_auxiliary_diagnostics(
                camera,
                case_dir / "diagnostics",
                suite.render_profile,
            )
        baseline_path = Path(baseline_report["path"])
        comparison_path = compose_before_after(
            baseline_path,
            candidate_path,
            case_dir / "comparison_before_after.png",
        )
        comparison_report = {
            "status": "rendered",
            **_file_record(comparison_path),
        }

    acceptance_blockers = _case_acceptance_blockers(
        mesh_audit=mesh_audit,
        scene_validation=scene_validation,
        beauty_report=beauty_report,
        baseline_report=baseline_report,
        comparison_report=comparison_report,
        environment=environment,
        annotation_contract=annotation_contract,
        render_enabled=render_enabled,
    )
    scene_data.metadata["human_validation_render"] = {
        "render_configuration": render_configuration,
        "environment": environment,
        "lighting": lighting,
        "camera": camera_report,
        "beauty": beauty_report,
        "baseline": baseline_report,
    }
    scene_data.metadata["human_validation_seed_selection"] = seed_report
    _stamp_blender_case_metadata(case, suite, selected_seed)
    packed_assets = pack_environment_assets()
    blend_path = save_blend_file(case_dir / "candidate.blend")
    scene_path = export_json(scene_data, case_dir / "scene.json")
    validation_path = export_json(
        scene_validation, case_dir / "scene_validation.json"
    )
    metrics_path = export_json(metrics, case_dir / "metrics.json")
    morphology_path = export_json(
        {key: value.to_dict() for key, value in sorted(plants_by_id.items())},
        case_dir / "morphologies.json",
    )
    result = {
        "generation_status": "complete",
        "case": case.to_dict(),
        "seed_selection": seed_report,
        "scene_validation": {
            "status": scene_validation["status"],
            "summary": scene_validation["summary"],
        },
        "render": render_configuration,
        "camera": camera_report,
        "environment": environment,
        "lighting": lighting,
        "beauty": beauty_report,
        "baseline": baseline_report,
        "comparison": comparison_report,
        "auxiliary_diagnostics": auxiliary_report,
        "annotation_contract": annotation_contract,
        "mesh_audit": {
            "status": mesh_audit.get("status"),
            "physical_collision_count": mesh_audit.get(
                "physical_collision_count", 0
            ),
            "clearance_violation_count": mesh_audit.get(
                "clearance_violation_count", 0
            ),
            "intentional_contact_count": mesh_audit.get(
                "intentional_contact_count", 0
            ),
        },
        "acceptance_blockers": acceptance_blockers,
        "packed_environment_assets": packed_assets,
        "files": {
            "blend": _file_record(blend_path, root=output_dir),
            "scene": _file_record(scene_path, root=output_dir),
            "validation": _file_record(validation_path, root=output_dir),
            "metrics": _file_record(metrics_path, root=output_dir),
            "morphologies": _file_record(morphology_path, root=output_dir),
        },
        "yolo_contract": dict(YOLO_CLASSES),
        "elapsed_seconds": round(time.perf_counter() - case_started, 4),
    }
    export_json(result, case_dir / "case_manifest.json")
    return result


def _build_case_geometry(
    scene_data: Any,
    plants_by_id: dict[str, Any],
    materials: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    geometry_reports: list[dict[str, Any]] = []
    morphology_reports: list[dict[str, Any]] = []
    for instance in scene_data.plant_instances:
        plant = plants_by_id[instance.plant_id]
        validation = validate_morphology_tree(plant)
        geometry = build_geometry_from_morphology(
            plant,
            materials,
            instance_id=instance.plant_id,
            instance_role=instance.role,
            position=instance.position,
            rotation_deg=instance.rotation_deg,
            plant_scale=instance.scale,
            add_ground=False,
        )
        morphology_reports.append(
            {
                "plant_id": instance.plant_id,
                "status": validation["status"],
                "summary": validation["summary"],
                "warnings": validation["warnings"],
            }
        )
        geometry_reports.append(
            {
                "plant_id": instance.plant_id,
                "seed": instance.seed,
                **geometry,
            }
        )
    support_report = create_cultivation_supports(
        scene_data,
        materials,
        geometry_reports,
    )
    return geometry_reports, morphology_reports, support_report


def _generate_bootstrap_baseline(
    case: HumanValidationCase,
    *,
    seed: int,
    suite: Any,
    case_dir: Path,
    organ_texture_dir: Path | None,
    environment_asset_dir: Path | None,
    environment_carrier: Path | None,
) -> dict[str, Any]:
    """Render the retained post-hoc model with the same photographic settings."""
    baseline_payload = case.to_dict()
    baseline_payload["model_variant"] = "A_baseline_independent"
    baseline_payload["morphology_preset"] = "initial_migration_manual_guess"
    baseline_case = HumanValidationCase.from_dict(baseline_payload)
    scene_data, plants_by_id, adaptation, metrics = build_case_morphologies(
        baseline_case,
        seed,
    )

    cleanup_scene()
    materials = create_project_materials(
        seed=seed + 3000,
        texture_asset_dir=organ_texture_dir,
    )
    geometry_reports, morphology_reports, support_report = _build_case_geometry(
        scene_data,
        plants_by_id,
        materials,
    )
    scene_data.metadata["plant_morphology_reports"] = morphology_reports
    scene_data.metadata["geometry_reports"] = geometry_reports
    scene_data.metadata["cultivation_adaptation"] = adaptation
    scene_data.metadata["support_geometry"] = support_report
    scene_validation = validate_cultivation_scene(scene_data)

    _center_x, _center_y, radius = _scene_center_radius(scene_data)
    environment = create_outdoor_environment(
        seed=seed,
        scene_radius=radius,
        terrain_size=scene_data.environment.terrain_size,
        terrain_subdivisions=scene_data.environment.terrain_subdivisions,
        background_cluster_count=scene_data.environment.background_cluster_count,
        asset_dir=environment_asset_dir,
        packed_asset_blend=environment_carrier,
        mode=case.environment_mode,
    )
    lighting = apply_lighting_profile(case.lighting_profile, seed)
    camera, camera_report = create_case_camera(
        case,
        scene_data,
        geometry_reports,
    )
    render_configuration = configure_render_profile(
        suite.render_profile,
        orientation=case.orientation,
    )
    beauty = render_beauty_with_preflight(
        camera,
        case_dir / "baseline_bootstrap.png",
        suite.render_profile,
        orientation=case.orientation,
    )

    scene_data.metadata["human_validation_bootstrap_baseline"] = {
        "source_model_variant": baseline_case.model_variant,
        "morphology_preset": baseline_case.morphology_preset,
        "render_configuration": render_configuration,
        "camera": camera_report,
        "lighting": lighting,
        "environment": environment,
    }
    _stamp_blender_case_metadata(case, suite, seed)
    import bpy

    bpy.context.scene["uchuva_human_validation_side"] = "bootstrap_baseline"
    packed_assets = pack_environment_assets()
    blend_path = save_blend_file(case_dir / "baseline_bootstrap.blend")
    scene_path = export_json(scene_data, case_dir / "baseline_scene.json")
    validation_path = export_json(
        scene_validation,
        case_dir / "baseline_scene_validation.json",
    )
    metrics_path = export_json(metrics, case_dir / "baseline_metrics.json")
    morphology_path = export_json(
        {key: value.to_dict() for key, value in sorted(plants_by_id.items())},
        case_dir / "baseline_morphologies.json",
    )
    return {
        "status": "bootstrap_posthoc_reference_render",
        "source_model_variant": baseline_case.model_variant,
        "morphology_preset": baseline_case.morphology_preset,
        **beauty,
        "camera": camera_report,
        "render": render_configuration,
        "environment": environment,
        "lighting": lighting,
        "packed_environment_assets": packed_assets,
        "files": {
            "blend": _file_record(blend_path, root=case_dir),
            "scene": _file_record(scene_path, root=case_dir),
            "validation": _file_record(validation_path, root=case_dir),
            "metrics": _file_record(metrics_path, root=case_dir),
            "morphologies": _file_record(morphology_path, root=case_dir),
        },
    }


def _case_acceptance_blockers(
    *,
    mesh_audit: dict[str, Any],
    scene_validation: dict[str, Any],
    beauty_report: dict[str, Any],
    baseline_report: dict[str, Any],
    comparison_report: dict[str, Any],
    environment: dict[str, Any],
    annotation_contract: dict[str, Any],
    render_enabled: bool,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    physical_count = int(mesh_audit.get("physical_collision_count", 0))
    clearance_count = int(mesh_audit.get("clearance_violation_count", 0))
    scene_physical = int(
        scene_validation.get("summary", {}).get("physical_collision_count", 0)
    )
    if physical_count or scene_physical:
        blockers.append(
            {
                "type": "non_intentional_mesh_intersection",
                "count": max(physical_count, scene_physical),
            }
        )
    if clearance_count:
        blockers.append(
            {
                "type": "hard_clearance_violation",
                "count": clearance_count,
            }
        )
    missing_assets = list(
        environment.get("assets", {}).get("missing", [])
    )
    if missing_assets:
        blockers.append(
            {
                "type": "missing_environment_assets",
                "assets": sorted(str(item) for item in missing_assets),
            }
        )
    if annotation_contract.get("status") != "valid":
        blockers.append(
            {
                "type": "annotation_contract_violation",
                "errors": annotation_contract.get("errors", []),
            }
        )
    if not render_enabled:
        return blockers
    if beauty_report.get("status") != "rendered" or not beauty_report.get("bytes"):
        blockers.append({"type": "candidate_render_missing_or_empty"})
    for warning in beauty_report.get("preflight", {}).get("warnings", []):
        blockers.append({"type": "candidate_render_preflight", "warning": warning})
    for warning in baseline_report.get("preflight", {}).get("warnings", []):
        blockers.append({"type": "baseline_render_preflight", "warning": warning})
    if (
        comparison_report.get("status") != "rendered"
        or not comparison_report.get("bytes")
    ):
        blockers.append({"type": "comparison_missing_or_empty"})
    return blockers


def _verify_annotation_contract(
    scene_data: Any,
    plants_by_id: dict[str, Any],
    geometry_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    instance_ids = [item.plant_id for item in scene_data.plant_instances]
    if len(instance_ids) != len(set(instance_ids)):
        errors.append("plant instance ids are not unique")
    if set(instance_ids) != set(plants_by_id):
        errors.append("plant instance ids differ from morphology ids")
    geometry_ids = [str(item.get("plant_id", "")) for item in geometry_reports]
    if sorted(geometry_ids) != sorted(instance_ids):
        errors.append("geometry reports do not preserve plant ids")
    if YOLO_CLASSES != {"calyx": 0}:
        errors.append(f"YOLO class contract changed: {YOLO_CLASSES}")

    fruit_count = 0
    closed_calyx_count = 0
    for plant_id, plant in sorted(plants_by_id.items()):
        stack = list(plant.axes)
        while stack:
            axis = stack.pop()
            stack.extend(axis.child_axes)
            for node in axis.nodes:
                unit = node.reproductive_unit
                if unit is None or unit.fruit is None:
                    continue
                fruit_count += 1
                if unit.fruit.visibility != "hidden":
                    errors.append(
                        f"{plant_id}/{unit.id}: fruit visibility is "
                        f"{unit.fruit.visibility!r}"
                    )
                if unit.calyx is None or float(unit.calyx.openness) != 0.0:
                    errors.append(f"{plant_id}/{unit.id}: calyx is not closed")
                else:
                    closed_calyx_count += 1
    return {
        "status": "valid" if not errors else "invalid",
        "yolo_classes": dict(YOLO_CLASSES),
        "plant_id_count": len(instance_ids),
        "fruit_count": fruit_count,
        "closed_calyx_count": closed_calyx_count,
        "hidden_fruit_count": fruit_count
        - sum("fruit visibility" in item for item in errors),
        "errors": errors,
    }


def _stamp_blender_case_metadata(
    case: HumanValidationCase,
    suite: Any,
    seed: int,
) -> None:
    import bpy

    scene = bpy.context.scene
    scene["uchuva_human_validation"] = True
    scene["uchuva_human_validation_protocol"] = suite.protocol_version
    scene["uchuva_human_validation_change_id"] = suite.change_id
    scene["uchuva_human_validation_case_id"] = case.case_id
    scene["uchuva_human_validation_seed"] = seed
    scene["uchuva_human_validation_render_profile"] = suite.render_profile.name


def _scene_center_radius(scene_data: Any) -> tuple[float, float, float]:
    positions = [item.position for item in scene_data.plant_instances]
    center_x = sum(item[0] for item in positions) / max(len(positions), 1)
    center_y = sum(item[1] for item in positions) / max(len(positions), 1)
    radius = max(
        (
            ((item[0] - center_x) ** 2 + (item[1] - center_y) ** 2) ** 0.5
            + float(instance.collision_proxy.get("canopy_radius", 0.5))
            for item, instance in zip(positions, scene_data.plant_instances)
        ),
        default=1.0,
    )
    return center_x, center_y, radius


def _baseline_exposure(
    baseline_payload: dict[str, Any] | None,
    case_id: str,
) -> float | None:
    if baseline_payload is None:
        return None
    case = baseline_payload.get("artifacts", {}).get("cases", {}).get(case_id, {})
    preflight = case.get("beauty", {}).get("preflight", {})
    value = preflight.get("applied_exposure_ev")
    return float(value) if value is not None else None


def _baseline_camera_report(
    baseline_payload: dict[str, Any] | None,
    case_id: str,
) -> dict[str, Any] | None:
    if baseline_payload is None:
        return None
    case = baseline_payload.get("artifacts", {}).get("cases", {}).get(case_id, {})
    report = case.get("camera")
    if not isinstance(report, dict):
        raise ValueError(f"Accepted baseline {case_id} has no camera report.")
    for key in ("location", "target", "lens_mm", "fstop"):
        if key not in report:
            raise ValueError(
                f"Accepted baseline {case_id} camera is missing {key!r}."
            )
    return report


def _baseline_beauty_path(
    baseline_payload: dict[str, Any] | None,
    baseline_manifest: Path | None,
    case_id: str,
) -> Path:
    if baseline_payload is None or baseline_manifest is None:
        raise ValueError("A non-bootstrap comparison requires a baseline manifest.")
    case = baseline_payload.get("artifacts", {}).get("cases", {}).get(case_id)
    if not isinstance(case, dict):
        raise ValueError(f"Baseline has no completed artifact for {case_id}.")
    raw_path = case.get("beauty", {}).get("path")
    if not raw_path:
        raise ValueError(f"Baseline {case_id} has no beauty path.")
    path = Path(raw_path)
    if not path.is_absolute():
        path = baseline_manifest.parent / path
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.resolve()


def _write_manifest(suite: Any, path: Path) -> None:
    export_json(suite, path)
    digest = _sha256(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="ascii",
    )


def _write_review_form(suite: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "case_id",
                "title",
                "problem_ids",
                "problem_outcomes",
                "morphology",
                "contacts",
                "materials_render",
                "lighting_camera",
                "regression",
                "decision",
                "notes",
            ],
        )
        writer.writeheader()
        for case in suite.cases:
            writer.writerow(
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "problem_ids": "|".join(case.problem_ids),
                    "problem_outcomes": "|".join(
                        f"{problem_id}=pending"
                        for problem_id in case.problem_ids
                        if problem_id in suite.active_problem_ids
                    ),
                    "morphology": "",
                    "contacts": "",
                    "materials_render": "",
                    "lighting_camera": "",
                    "regression": "",
                    "decision": "pending",
                    "notes": "",
                }
            )


def _write_markdown_report(suite: Any, path: Path) -> None:
    lines = [
        f"# Validación humana: {suite.change_id}",
        "",
        f"- Protocolo: `{suite.protocol_version}`",
        f"- Estado: `{suite.status}`",
        f"- Perfil: `{suite.render_profile.name}`",
        f"- Huella fuente: `{suite.source_fingerprint}`",
        f"- Baseline: `{suite.baseline_manifest or 'bootstrap posthoc reproducible'}`",
        "",
        "## Casos",
        "",
        "| Caso | Semilla | Problemas | Auditoría | Render candidato (s) | Total (s) | Bloqueos |",
        "|---|---:|---|---|---:|---:|---|",
    ]
    case_artifacts = suite.artifacts.get("cases", {})
    for case in suite.cases:
        artifact = case_artifacts.get(case.case_id, {})
        status = artifact.get("generation_status", "pending")
        seed = artifact.get("seed_selection", {}).get("locked_seed", "—")
        audit = artifact.get("mesh_audit", {}).get("status", "—")
        render_seconds = artifact.get("beauty", {}).get(
            "elapsed_seconds", "—"
        )
        elapsed = artifact.get("elapsed_seconds", "—")
        blockers = artifact.get("acceptance_blockers", [])
        blocker_text = (
            ", ".join(str(item.get("type", "unknown")) for item in blockers)
            if blockers
            else "ninguno"
            if status != "pending"
            else "—"
        )
        lines.append(
            f"| {case.case_id} | {seed} | {', '.join(case.problem_ids)} | "
            f"{audit} | {render_seconds} | {elapsed} | {blocker_text} |"
        )
    lines.extend(
        [
            "",
            f"Tiempo total registrado: "
            f"`{suite.artifacts.get('elapsed_seconds', 'pendiente')}` s.",
            "",
            "La configuración solicitada y la aplicada, dispositivo, memoria, "
            "fallbacks, exposición, cámara y hashes permanecen en el manifest "
            "y en cada `case_manifest.json`.",
            "",
            "## Regla humana",
            "",
            "Se requieren diez decisiones completas, al menos ocho `pass`, "
            "máximo dos `minor` y cero `major` o `blocker`.",
            "",
            "El perfil Eevee y las ejecuciones `--smoke` son diagnósticos; "
            "no constituyen evidencia de aceptación fotográfica.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _file_record(path: str | Path, root: Path | None = None) -> dict[str, Any]:
    active = Path(path).resolve()
    display_path: str
    if root is not None:
        try:
            display_path = active.relative_to(root.resolve()).as_posix()
        except ValueError:
            display_path = str(active)
    else:
        display_path = str(active)
    return {
        "path": display_path,
        "bytes": active.stat().st_size if active.is_file() else 0,
        "sha256": _sha256(active) if active.is_file() else None,
    }


def _directory_record(path: Path) -> dict[str, Any]:
    active = path.resolve()
    if not active.is_dir():
        raise FileNotFoundError(active)
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    for item in sorted(
        (candidate for candidate in active.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(active).as_posix().lower(),
    ):
        relative = item.relative_to(active).as_posix()
        size = item.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with item.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
        file_count += 1
        total_bytes += size
    return {
        "path": str(active),
        "file_count": file_count,
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _environment_carrier(requested: Path | None) -> Path | None:
    if requested is not None:
        path = _repo_path(requested)
        if not path.is_file():
            raise FileNotFoundError(path)
        return path
    archived = (
        REPO_ROOT
        / "outputs"
        / "archive"
        / "pre_synchronized_growth"
        / "blender_files"
        / "uchuva_annotation_pilot_seed_0.blend"
    )
    return archived if archived.is_file() else None


def _repo_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


if __name__ == "__main__":
    main()
