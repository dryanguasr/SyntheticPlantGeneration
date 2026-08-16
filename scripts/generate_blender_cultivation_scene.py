"""Generate the current multi-plant uchuva cultivation scene in Blender."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_geometry import (
    audit_scene_mesh_collisions,
    build_geometry_from_morphology,
    create_cultivation_supports,
)
from uchuva_lsystem.blender_scene import (
    cleanup_scene,
    create_project_materials,
    save_blend_file,
    setup_camera_and_lights,
    setup_render_settings,
)
from uchuva_lsystem.collisions import audit_proxy_contacts
from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.cultivation import generate_cultivation_morphologies
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.scene import create_cultivation_scene
from uchuva_lsystem.validation import (
    validate_cultivation_scene,
    validate_morphology_tree,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a multi-plant uchuva cultivation scene."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible scene seed.")
    parser.add_argument(
        "--plant-count",
        type=int,
        default=20,
        help="Number of plant instances for the scene.",
    )
    parser.add_argument(
        "--preset",
        default="dense_trellis_synchronous",
        choices=[
            "single_plant_study",
            "foreground_plant_with_neighbors",
            "annotation_foreground_pilot",
            "row_canopy",
            "dense_staked_crop",
            "dense_trellis_synchronous",
        ],
        help="Scene preset.",
    )
    parser.add_argument(
        "--model-variant",
        default="E_plus_contact_policy_clearance",
        choices=[
            "A_baseline_independent",
            "B_morphology_calibrated",
            "C_plus_structural_support",
            "D_plus_synchronous_multi_plant",
            "E_plus_contact_policy_clearance",
            "F_plus_space_colonization_optional",
        ],
        help="Ablation variant used to generate morphology.",
    )
    parser.add_argument(
        "--collision-policy",
        default="contact_policy_clearance",
        choices=[
            "canopy_permissive",
            "strict_base",
            "contact_policy_clearance",
        ],
        help="Scene placement collision policy.",
    )
    parser.add_argument(
        "--output-blend",
        type=Path,
        default=None,
        help="Output .blend path.",
    )
    parser.add_argument(
        "--scene-output",
        type=Path,
        default=None,
        help="Output scene JSON path.",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=None,
        help="Output scene validation JSON path.",
    )
    parser.add_argument(
        "--audit-mode",
        choices=("full_mesh", "proxy", "skip"),
        default="full_mesh",
        help=(
            "Collision audit stored in the scene. Use proxy for an economical "
            "review Blend; full_mesh remains the final geometry authority."
        ),
    )
    parser.add_argument(
        "--preview-output",
        type=Path,
        default=None,
        help="Optional PNG preview rendered from the saved review camera.",
    )
    parser.add_argument("--preview-width", type=int, default=640)
    parser.add_argument("--preview-height", type=int, default=480)
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    variant_slug = {
        "A_baseline_independent": "variant_a_legacy_posthoc",
        "B_morphology_calibrated": "variant_b_morphology",
        "C_plus_structural_support": "variant_c_support",
        "D_plus_synchronous_multi_plant": "variant_d_synchronized",
        "E_plus_contact_policy_clearance": "variant_e_contact_clearance",
        "F_plus_space_colonization_optional": "variant_f_space_colonization",
    }[args.model_variant]
    review_stem = (
        f"uchuva_multiplant_{variant_slug}_seed_{args.seed:03d}"
    )
    review_directory = REPO_ROOT / "outputs" / "current_review"
    output_blend = args.output_blend or (
        review_directory / f"{review_stem}.blend"
    )
    scene_output = args.scene_output or (
        review_directory / f"{review_stem}_scene.json"
    )
    validation_output = args.validation_output or (
        review_directory / f"{review_stem}_validation.json"
    )
    output_blend = _repository_relative_path(output_blend)
    scene_output = _repository_relative_path(scene_output)
    validation_output = _repository_relative_path(validation_output)
    preview_output = (
        _repository_relative_path(args.preview_output)
        if args.preview_output is not None
        else None
    )

    scene = create_cultivation_scene(
        seed=args.seed,
        preset_name=args.preset,
        plant_count=args.plant_count,
        collision_policy=args.collision_policy,
    )
    morphology_parameters = get_morphology_parameters(
        "initial_migration_manual_guess"
        if args.model_variant == "A_baseline_independent"
        else "trained_trellis"
    )

    plants_by_id = {
        instance.plant_id: generate_morphology_tree(
            seed=instance.seed,
            params=morphology_parameters,
            condition=instance.condition,
        )
        for instance in scene.plant_instances
    }
    scene, plants_by_id, adaptation_report = generate_cultivation_morphologies(
        scene,
        morphology_parameters,
        args.model_variant,
        potential_plants=plants_by_id,
    )

    cleanup_scene()
    materials = create_project_materials(seed=args.seed + 3000)
    geometry_reports = []
    morphology_reports = []
    max_height = 0.0

    for index, instance in enumerate(scene.plant_instances):
        plant = plants_by_id[instance.plant_id]
        morphology_report = validate_morphology_tree(plant)
        geometry_report = build_geometry_from_morphology(
            plant,
            materials,
            instance_id=instance.plant_id,
            instance_role=instance.role,
            position=instance.position,
            rotation_deg=instance.rotation_deg,
            plant_scale=instance.scale,
            add_ground=index == 0,
        )
        morphology_reports.append(
            {
                "plant_id": instance.plant_id,
                "seed": instance.seed,
                "status": morphology_report["status"],
                "summary": morphology_report["summary"],
                "warnings": morphology_report["warnings"],
            }
        )
        geometry_reports.append(
            {
                "plant_id": instance.plant_id,
                "seed": instance.seed,
                **geometry_report,
            }
        )
        max_height = max(max_height, geometry_report["height"])

    support_report = create_cultivation_supports(scene, materials, geometry_reports)
    if args.audit_mode == "full_mesh":
        mesh_collision_audit = audit_scene_mesh_collisions()
    elif args.audit_mode == "proxy":
        mesh_collision_audit = audit_proxy_contacts(scene, plants_by_id)
        mesh_collision_audit = {
            **mesh_collision_audit,
            "status": "proxy_only",
            "authority": (
                "Pure morphology proxy audit; run full_mesh before final "
                "dataset acceptance."
            ),
        }
    else:
        mesh_collision_audit = {
            "status": "not_run",
            "reason": "Explicit --audit-mode skip",
            "physical_collision_count": None,
            "clearance_violation_count": None,
        }

    scene.metadata["plant_morphology_reports"] = morphology_reports
    scene.metadata["geometry_reports"] = geometry_reports
    scene.metadata["cultivation_adaptation"] = adaptation_report
    scene.metadata["support_geometry"] = support_report
    scene.metadata["mesh_collision_audit"] = mesh_collision_audit
    scene_validation = validate_cultivation_scene(scene)
    scene.metadata["scene_validation_status"] = scene_validation["status"]

    _setup_scene_camera_and_lighting(scene, max_height)
    setup_render_settings(args.preview_width, args.preview_height)
    stamp_review_metadata(
        seed=args.seed,
        plant_count=len(scene.plant_instances),
        preset=args.preset,
        model_variant=args.model_variant,
        audit_mode=args.audit_mode,
        validation_status=scene_validation["status"],
        scene_id=scene.scene_id,
        decision_counts=adaptation_report.get("decision_counts", {}),
    )
    if preview_output is not None:
        import bpy

        preview_output.parent.mkdir(parents=True, exist_ok=True)
        bpy.context.scene.render.image_settings.file_format = "PNG"
        bpy.context.scene.render.filepath = str(preview_output)
        bpy.ops.render.render(write_still=True)
    save_blend_file(output_blend)

    export_json(scene, scene_output)
    export_json(scene_validation, validation_output)

    print(f"Wrote cultivation scene: {scene_output}")
    print(f"Wrote scene validation: {validation_output}")
    print(f"Wrote Blender file: {output_blend}")
    if preview_output is not None:
        print(f"Wrote preview image: {preview_output}")
    print(f"Plant instances: {len(scene.plant_instances)}")
    print(f"Scene validation status: {scene_validation['status']}")


def _repository_relative_path(path: Path) -> Path:
    """Resolve user-provided relative outputs against the repository root."""
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def stamp_review_metadata(
    *,
    seed: int,
    plant_count: int,
    preset: str,
    model_variant: str,
    audit_mode: str,
    validation_status: str,
    scene_id: str,
    decision_counts: dict[str, int],
) -> None:
    """Make the active model version unmistakable inside the review Blend."""
    import bpy

    blender_scene = bpy.context.scene
    blender_scene["uchuva_current_model"] = True
    blender_scene["uchuva_scene_id"] = scene_id
    blender_scene["uchuva_seed"] = seed
    blender_scene["uchuva_plant_count"] = plant_count
    blender_scene["uchuva_preset"] = preset
    blender_scene["uchuva_model_variant"] = model_variant
    blender_scene["uchuva_audit_mode"] = audit_mode
    blender_scene["uchuva_validation_status"] = validation_status

    default_collection = bpy.data.collections.get("Collection")
    if default_collection is not None:
        default_collection.name = "uchuva_support_and_environment"

    summary = {
        "status": "current_review_scene",
        "scene_id": scene_id,
        "seed": seed,
        "plant_count": plant_count,
        "preset": preset,
        "model_variant": model_variant,
        "audit_mode": audit_mode,
        "validation_status": validation_status,
        "decision_counts": dict(decision_counts),
        "legacy_warning": (
            "This scene was generated from src/uchuva_lsystem, not from "
            "legacy/prototypes."
        ),
    }
    _replace_text_block(
        "CURRENT_UCHUVA_SCENE_SUMMARY.json",
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    _replace_text_block(
        "README_CURRENT_UCHUVA_SCENE.txt",
        (
            "ESCENA VIGENTE DE REVISIÓN\n"
            "==========================\n\n"
            f"Modelo: {model_variant}\n"
            f"Preset: {preset}\n"
            f"Semilla: {seed}\n"
            f"Plantas: {plant_count}\n"
            f"Auditoría: {audit_mode}\n"
            f"Validación: {validation_status}\n\n"
            "Cada planta está en su propia colección uchuva_plant_XX.\n"
            "El soporte y el entorno están en "
            "uchuva_support_and_environment.\n"
            "Los prototipos históricos no participan en esta escena.\n"
        ),
    )


def _replace_text_block(name: str, content: str) -> None:
    import bpy

    text_block = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text_block.clear()
    text_block.write(content)


def _setup_scene_camera_and_lighting(scene, max_height: float) -> None:
    positions = [instance.position for instance in scene.plant_instances]
    center_x = sum(position[0] for position in positions) / len(positions)
    center_y = sum(position[1] for position in positions) / len(positions)
    scene_radius = max(
        (
            ((position[0] - center_x) ** 2 + (position[1] - center_y) ** 2) ** 0.5
            for position in positions
        ),
        default=2.0,
    ) + 1.5
    setup_camera_and_lights(
        plant_height=max(max_height, 2.4),
        target=(center_x, center_y, max_height * 0.48),
        seed=scene.seed,
        scene_radius=scene_radius,
    )
    scene.metadata["lighting"] = {
        "mode": "distant_randomized_area_light",
        "seed": scene.seed,
        "scene_radius": round(scene_radius, 3),
    }


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


if __name__ == "__main__":
    main()
