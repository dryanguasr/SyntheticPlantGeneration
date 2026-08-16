"""End-to-end annotation foreground pilot shared by CLI and embedded runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .blender_annotations import SEMANTIC_CLASSES, render_camera_outputs
from .blender_environment import (
    ASSET_MANIFEST,
    create_outdoor_environment,
    pack_environment_assets,
)
from .blender_geometry import (
    audit_scene_mesh_collisions,
    build_geometry_from_morphology,
    create_cultivation_supports,
)
from .blender_scene import (
    cleanup_scene,
    create_annotation_cameras,
    create_project_materials,
    save_blend_file,
    setup_render_settings,
)
from .exporters import export_json
from .grammar import SCRIPT_VERSION, generate_morphology_tree
from .cultivation import adapt_cultivation_morphologies
from .scene import CultivationScene, create_cultivation_scene
from .validation import validate_cultivation_scene, validate_morphology_tree
from .yolo_export import YOLO_CLASSES, detections_from_mask_items, write_yolo_file


PILOT_VERSION = "0.3.1-dense-strict-cultivation"


def select_annotation_foreground_seed(
    seed_start: int = 0,
    max_candidates: int = 20,
) -> tuple[int, dict[str, Any]]:
    """Select the first morphology seed satisfying the pilot coverage contract."""
    attempts: list[dict[str, Any]] = []
    for seed in range(seed_start, seed_start + max_candidates):
        plant = generate_morphology_tree(seed=seed)
        report = validate_morphology_tree(plant)
        summary = report["summary"]
        states = summary["calyx_state_counts"]
        accepted = (
            report["status"] in {"valid", "valid_with_warnings"}
            and summary["fruiting_reproductive_unit_count"] >= 4
            and summary["flower_count"] >= 1
            and states.get("inflated_green", 0) >= 1
            and states.get("straw_yellow", 0) >= 1
        )
        attempts.append(
            {
                "seed": seed,
                "accepted": accepted,
                "validation_status": report["status"],
                "summary": summary,
            }
        )
        if accepted:
            return seed, {
                "seed_start": seed_start,
                "max_candidates": max_candidates,
                "selected_seed": seed,
                "attempts": attempts,
                "selection_policy": {
                    "minimum_closed_calyxes": 4,
                    "minimum_flowers": 1,
                    "required_calyx_states": ["inflated_green", "straw_yellow"],
                    "grammar_forcing": False,
                },
            }
    raise RuntimeError(
        f"No annotation-ready foreground seed found in {seed_start}..{seed_start + max_candidates - 1}."
    )


def generate_annotation_pilot(
    *,
    seed_start: int = 0,
    plant_count: int = 20,
    neighbor_count: int | None = None,
    output_dir: str | Path,
    output_blend: str | Path | None = None,
    asset_dir: str | Path | None = None,
    camera_profiles: list[str] | None = None,
    width: int = 1280,
    height: int = 960,
    cycles_samples: int = 64,
    render_rgb: bool = True,
    render_cycles: bool = False,
    fail_on_physical_collision: bool = True,
    max_scene_attempts: int = 20,
) -> dict[str, Any]:
    """Generate one fail-closed pilot, retrying derived seeds after BVH failure."""
    if max_scene_attempts < 1:
        raise ValueError("max_scene_attempts must be at least 1")
    rejected: list[dict[str, Any]] = []
    for attempt in range(max_scene_attempts):
        candidate_start = seed_start + attempt
        try:
            report = _generate_annotation_pilot_once(
                seed_start=candidate_start,
                plant_count=plant_count,
                neighbor_count=neighbor_count,
                output_dir=output_dir,
                output_blend=output_blend,
                asset_dir=asset_dir,
                camera_profiles=camera_profiles,
                width=width,
                height=height,
                cycles_samples=cycles_samples,
                render_rgb=render_rgb,
                render_cycles=render_cycles,
                fail_on_physical_collision=fail_on_physical_collision,
            )
        except RuntimeError as error:
            if "unresolved physical collisions" not in str(error):
                raise
            rejected.append(
                {
                    "attempt": attempt + 1,
                    "seed_start": candidate_start,
                    "reason": "mesh_bvh_physical_collision",
                }
            )
            continue
        report["scene_seed_retry"] = {
            "max_attempts": max_scene_attempts,
            "accepted_attempt": attempt + 1,
            "accepted_seed": report["selected_seed"],
            "rejected": rejected,
        }
        output_path = Path(output_dir)
        export_json(report, output_path / "annotations.json")
        _write_text_block("uchuva_pilot_report.json", report)
        if output_blend is not None:
            save_blend_file(output_blend)
        return report
    raise RuntimeError(
        f"No collision-free annotation pilot found in {max_scene_attempts} deterministic attempts."
    )


def _generate_annotation_pilot_once(
    *,
    seed_start: int = 0,
    plant_count: int = 20,
    neighbor_count: int | None = None,
    output_dir: str | Path,
    output_blend: str | Path | None = None,
    asset_dir: str | Path | None = None,
    camera_profiles: list[str] | None = None,
    width: int = 1280,
    height: int = 960,
    cycles_samples: int = 64,
    render_rgb: bool = True,
    render_cycles: bool = False,
    fail_on_physical_collision: bool = True,
) -> dict[str, Any]:
    """Build, render, annotate, validate, and optionally save one pilot scene."""
    import bpy

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    selected_seed, selection_report = select_annotation_foreground_seed(seed_start)
    effective_plant_count = neighbor_count + 1 if neighbor_count is not None else plant_count
    scene_preset_name = (
        "dense_staked_crop" if effective_plant_count >= 20 else "annotation_foreground_pilot"
    )
    scene_data = create_cultivation_scene(
        seed=selected_seed,
        preset_name=scene_preset_name,
        plant_count=effective_plant_count,
        collision_policy="canopy_permissive",
    )
    scene_data.render.width = width
    scene_data.render.height = height
    scene_data.render.cycles_samples = cycles_samples
    if camera_profiles is not None:
        scene_data.render.camera_profiles = list(camera_profiles)

    plants_by_id = {
        instance.plant_id: generate_morphology_tree(
            seed=instance.seed,
            condition=instance.condition,
        )
        for instance in scene_data.plant_instances
    }
    scene_data, plants_by_id, adaptation_report = adapt_cultivation_morphologies(
        scene_data, plants_by_id
    )
    morphology_dir = output_path / "morphologies"
    morphology_dir.mkdir(parents=True, exist_ok=True)
    morphology_paths: dict[str, str] = {}
    for plant_id, plant in sorted(plants_by_id.items()):
        morphology_path = morphology_dir / f"{plant_id}.json"
        export_json(plant, morphology_path)
        morphology_paths[plant_id] = str(morphology_path.relative_to(output_path))

    cleanup_scene()
    materials = create_project_materials(seed=selected_seed + 3000)
    geometry_reports: list[dict[str, Any]] = []
    morphology_reports: list[dict[str, Any]] = []
    max_height = 0.0

    for instance in scene_data.plant_instances:
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
            add_ground=False,
        )
        morphology_reports.append(
            {
                "plant_id": instance.plant_id,
                "role": instance.role,
                "seed": instance.seed,
                "status": morphology_report["status"],
                "summary": morphology_report["summary"],
                "warnings": morphology_report["warnings"],
            }
        )
        geometry_reports.append(
            {
                "plant_id": instance.plant_id,
                "role": instance.role,
                "seed": instance.seed,
                **geometry_report,
            }
        )
        max_height = max(max_height, geometry_report["height"])

    support_report = create_cultivation_supports(scene_data, materials, geometry_reports)
    mesh_collision_audit = audit_scene_mesh_collisions()

    scene_data.metadata["seed_selection"] = selection_report
    scene_data.metadata["plant_morphology_reports"] = morphology_reports
    scene_data.metadata["geometry_reports"] = geometry_reports
    scene_data.metadata["cultivation_adaptation"] = adaptation_report
    scene_data.metadata["support_geometry"] = support_report
    scene_data.metadata["mesh_collision_audit"] = mesh_collision_audit
    scene_data.metadata["adapted_morphology_files"] = morphology_paths
    scene_validation = validate_cultivation_scene(scene_data)
    scene_data.metadata["scene_validation_status"] = scene_validation["status"]
    if fail_on_physical_collision and scene_validation["summary"]["physical_collision_count"]:
        export_json(scene_validation, output_path / "validation_failed_physical_collision.json")
        raise RuntimeError(
            "The annotation pilot has unresolved physical collisions; see validation_failed_physical_collision.json."
        )

    center_x, center_y, scene_radius = _scene_center_and_radius(scene_data)
    environment_report = create_outdoor_environment(
        seed=selected_seed,
        scene_radius=scene_radius,
        terrain_size=scene_data.environment.terrain_size,
        terrain_subdivisions=scene_data.environment.terrain_subdivisions,
        background_cluster_count=scene_data.environment.background_cluster_count,
        asset_dir=asset_dir,
    )
    scene_data.metadata["environment_report"] = environment_report
    scene_data.metadata["asset_manifest"] = ASSET_MANIFEST

    foreground_report = next(
        report for report in geometry_reports if report["role"] == "foreground"
    )
    target = (
        center_x,
        center_y,
        max(0.45, foreground_report["height"] * 0.50),
    )
    cameras = create_annotation_cameras(
        target=target,
        plant_height=max(max_height, 2.4),
        scene_radius=scene_radius,
        seed=selected_seed,
    )
    setup_render_settings(width=width, height=height)

    frame_reports: list[dict[str, Any]] = []
    for profile_name in scene_data.render.camera_profiles:
        if profile_name not in cameras:
            raise ValueError(f"Unknown annotation camera profile: {profile_name}")
        frame_report = render_camera_outputs(
            cameras[profile_name],
            profile_name,
            output_path,
            width=width,
            height=height,
            cycles_samples=cycles_samples,
            render_rgb=render_rgb,
            render_cycles=render_cycles,
        )
        detections = detections_from_mask_items(
            frame_report["annotations"]["reproductive_instance"]["items"],
            width=width,
            height=height,
        )
        labels_path = write_yolo_file(
            output_path / profile_name / "labels_yolo.txt",
            detections,
        )
        frame_report["yolo"] = {
            "classes": YOLO_CLASSES,
            "labels_path": str(labels_path),
            "detection_count": len(detections),
            "detections": [item.to_dict() for item in detections],
        }
        frame_reports.append(frame_report)

    packed_assets = pack_environment_assets()
    report = {
        "pilot_version": PILOT_VERSION,
        "morphology_script_version": SCRIPT_VERSION,
        "selected_seed": selected_seed,
        "preset": scene_preset_name,
        "plant_count": len(scene_data.plant_instances),
        "neighbor_count": len(scene_data.plant_instances) - 1,
        "semantic_classes": SEMANTIC_CLASSES,
        "seed_selection": selection_report,
        "frames": frame_reports,
        "scene_validation": scene_validation,
        "packed_assets": packed_assets,
        "asset_manifest": ASSET_MANIFEST,
        "occlusion_metric": (
            "bbox_occupancy_proxy: 1 - visible_pixels / visible_bbox_area; "
            "this is not an amodal ground-truth occlusion fraction"
        ),
    }
    annotation_validation = validate_annotation_pilot(
        report,
        scene_data,
        require_cycles=render_rgb and render_cycles,
    )
    report["annotation_validation"] = annotation_validation
    scene_data.metadata["annotation_validation_status"] = annotation_validation["status"]

    export_json(scene_data, output_path / "scene.json")
    export_json(scene_validation, output_path / "scene_validation.json")
    export_json(report, output_path / "annotations.json")
    _write_text_block("uchuva_pilot_report.json", report)
    _write_text_block("uchuva_pilot_validation.json", annotation_validation)

    bpy.context.scene["uchuva_generator_seed"] = selected_seed
    bpy.context.scene["uchuva_generator_preset"] = scene_preset_name
    bpy.context.scene["uchuva_annotation_status"] = annotation_validation["status"]
    if output_blend is not None:
        save_blend_file(output_blend)
    return report


def validate_annotation_pilot(
    report: dict[str, Any],
    scene_data: CultivationScene,
    *,
    require_cycles: bool,
) -> dict[str, Any]:
    """Check mask registries, closed calyx policy, and portable assets."""
    import bpy

    errors: list[str] = []
    warnings: list[str] = []
    expected_profiles = scene_data.render.camera_profiles
    if [frame["profile"] for frame in report["frames"]] != expected_profiles:
        errors.append("Rendered camera profiles do not match RenderConfig order.")

    for frame in report["frames"]:
        camera = frame["camera"]
        if camera["width"] != scene_data.render.width or camera["height"] != scene_data.render.height:
            errors.append(f"{frame['profile']} has inconsistent image dimensions.")
        if require_cycles and "cycles" not in frame["rgb"]:
            errors.append(f"{frame['profile']} is missing its Cycles RGB render.")
        for pass_name in ("semantic", "plant_instance", "reproductive_instance"):
            annotation_pass = frame["annotations"].get(pass_name)
            if annotation_pass is None:
                errors.append(f"{frame['profile']} is missing {pass_name}.")
                continue
            for identifier, item in annotation_pass["items"].items():
                bbox = item.get("bbox_xywh")
                if bbox is None:
                    continue
                x, y, width, height = bbox
                if x < 0 or y < 0 or x + width > camera["width"] or y + height > camera["height"]:
                    errors.append(
                        f"{frame['profile']} {pass_name} id {identifier} has an out-of-frame bbox."
                    )
        yolo = frame.get("yolo")
        if yolo is None:
            errors.append(f"{frame['profile']} is missing its YOLO export.")
        else:
            if yolo.get("classes") != YOLO_CLASSES:
                errors.append(f"{frame['profile']} changed the single-class YOLO contract.")
            if any(item.get("class_id") != 0 for item in yolo.get("detections", [])):
                errors.append(f"{frame['profile']} contains a non-calyx YOLO class.")

    calyx_objects = [
        obj for obj in bpy.context.scene.objects if "uchuva_calyx_openness" in obj
    ]
    open_calyxes = [
        obj.name
        for obj in calyx_objects
        if float(obj.get("uchuva_calyx_openness", 1.0)) > 0.001
    ]
    if open_calyxes:
        errors.append(f"Open calyx objects found: {open_calyxes[:5]}")

    visible_fruits = [
        obj.name
        for obj in bpy.context.scene.objects
        if obj.get("uchuva_semantic_class") == "ignore"
        and obj.get("uchuva_hidden_inside_closed_calyx")
        and not obj.hide_render
    ]
    if visible_fruits:
        errors.append(f"Fruit inside closed calyx is render-visible: {visible_fruits[:5]}")

    unpacked = [name for name, packed in report["packed_assets"].items() if not packed]
    if unpacked:
        errors.append(f"External images are not packed: {unpacked}")
    missing_assets = report.get("asset_manifest", {}).keys() - {
        str(image.get("uchuva_asset_key"))
        for image in bpy.data.images
        if image.get("uchuva_asset_key")
    }
    if missing_assets:
        warnings.append(f"CC0 assets missing; procedural fallback used: {sorted(missing_assets)}")

    physical_collisions = report["scene_validation"]["summary"]["physical_collision_count"]
    if physical_collisions:
        errors.append(f"Scene has {physical_collisions} physical collisions.")
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "frame_count": len(report["frames"]),
            "expected_rgb_count": len(report["frames"]) * (2 if require_cycles else 1),
            "closed_calyx_count": len(calyx_objects),
            "visible_hidden_fruit_count": len(visible_fruits),
            "physical_collision_count": physical_collisions,
            "packed_asset_count": sum(1 for packed in report["packed_assets"].values() if packed),
        },
    }


def _scene_center_and_radius(scene_data: CultivationScene) -> tuple[float, float, float]:
    positions = [instance.position for instance in scene_data.plant_instances]
    center_x = sum(position[0] for position in positions) / len(positions)
    center_y = sum(position[1] for position in positions) / len(positions)
    radius = max(
        (
            ((position[0] - center_x) ** 2 + (position[1] - center_y) ** 2) ** 0.5
            for position in positions
        ),
        default=1.0,
    ) + 1.35
    return center_x, center_y, radius


def _write_text_block(name: str, payload: Any) -> None:
    import bpy

    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear()
    text.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
