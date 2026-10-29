"""Deterministic MakeSense/YOLO dataset generation inside Blender."""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .blender_annotations import (
    camera_metadata,
    render_detection_preview,
    render_reproductive_annotations,
    render_rgb_image,
)
from .blender_environment import (
    LIGHTING_PROFILES,
    apply_lighting_profile,
    audit_calyx_ground_clearance,
    create_outdoor_environment,
)
from .blender_geometry import (
    audit_scene_mesh_collisions,
    build_geometry_from_morphology,
    create_cultivation_supports,
)
from .blender_scene import (
    ANNOTATION_CAMERA_PROFILES,
    cleanup_scene,
    create_annotation_camera,
    create_project_materials,
    save_blend_file,
    setup_render_settings,
)
from .grammar import SCRIPT_VERSION, generate_morphology_tree
from .cultivation import generate_cultivation_morphologies
from .composition_calibration import load_schedule_rates
from .domain_analysis import load_reference_profile
from .parameters import get_morphology_parameters
from .provenance import override_parameter
from .scene import create_cultivation_scene
from .validation import validate_cultivation_scene, validate_morphology_tree
from .yolo_export import (
    YOLO_CLASSES,
    append_jsonl,
    detection_class_name,
    detections_from_mask_items,
    write_dataset_descriptor,
    write_yolo_file,
)


DATASET_VERSION = "0.7.1-virtual-fidelity-v2-unique-instance-palette"

# The source profile reports box-level proportions. Scheduling those numbers
# directly as image-level camera proportions produced roughly twice too many
# tiny boxes. These deterministic multipliers compensate for the observed
# number and scale of detections yielded by each camera band in the 100-image
# baseline and the papery-calyx pilot. This is an engineering calibration, not
# a botanical claim.
AREA_IMAGE_RATE_MULTIPLIERS = {
    "under_one_percent": 0.30,
    "one_to_five_percent": 0.77,
    "at_least_five_percent": 1.64,
}
PHENOLOGY_ORDER = ("mixed_early", "mixed_balanced", "mixed_late")
LIGHTING_ORDER = tuple(LIGHTING_PROFILES)
CAMERA_ORDER = tuple(ANNOTATION_CAMERA_PROFILES)
REAL_MATCHED_CAMERA_PROFILES = ("real_close", "real_mid", "real_context")


@dataclass
class DatasetConfig:
    output_dir: str | Path
    seed: int = 0
    image_count: int = 100
    captures_per_scene: int = 1
    width: int = 1280
    height: int = 960
    cycles_qa_count: int = 0
    cycles_samples: int = 64
    neighbor_count_min: int = 0
    neighbor_count_max: int = 2
    max_seed_candidates: int = 1000
    capture_pose_retries: int = 8
    min_visible_pixels: int = 24
    min_box_size: int = 6
    asset_dir: str | Path | None = None
    reference_profile_path: str | Path | None = None
    reference_split: str = "train"
    composition_calibration_path: str | Path | None = None
    phenology_model: str = "literature_cohort_v1"
    background_style: str = "layered_understory_v2"
    label_mode: str = "calyx_single_class"
    composition_profile: str = "real_matched"
    image_format: str = "JPEG"
    resume: bool = False
    keep_masks: bool = False
    inspection_blend_path: str | Path | None = None
    annotation_palette_version: str = "rgb_lattice_4095_v1"
    morphology_preset: str | None = None

    def validate(self) -> None:
        if self.morphology_preset is not None:
            get_morphology_parameters(self.morphology_preset)
        if self.annotation_palette_version != "rgb_lattice_4095_v1":
            raise ValueError("Unsupported annotation palette version")
        if self.image_count <= 0 or self.captures_per_scene <= 0:
            raise ValueError("image_count and captures_per_scene must be positive.")
        if self.image_count % self.captures_per_scene:
            raise ValueError("image_count must be divisible by captures_per_scene.")
        if not 1 <= self.captures_per_scene <= len(LIGHTING_ORDER):
            raise ValueError("captures_per_scene must remain within 1..4.")
        if self.width < 64 or self.height < 64:
            raise ValueError("Dataset images must be at least 64x64 pixels.")
        if self.capture_pose_retries < 1:
            raise ValueError("capture_pose_retries must be at least 1.")
        if not 0 <= self.neighbor_count_min <= self.neighbor_count_max <= 4:
            raise ValueError("Neighbor count range must remain within 0..4.")
        if self.cycles_qa_count < 0 or self.cycles_qa_count > min(12, self.image_count):
            raise ValueError("cycles_qa_count must be between 0 and min(12, image_count).")
        if self.label_mode != "calyx_single_class":
            raise ValueError("Only label_mode='calyx_single_class' is supported.")
        if self.composition_profile not in {"real_matched", "legacy_pilot"}:
            raise ValueError("Unknown composition_profile.")
        if self.image_format not in {"JPEG", "PNG"}:
            raise ValueError("image_format must be JPEG or PNG.")
        if self.reference_profile_path is not None and not Path(self.reference_profile_path).is_file():
            raise FileNotFoundError(self.reference_profile_path)
        if self.reference_split not in {"train", "val", "test", "overall"}:
            raise ValueError("reference_split must be train, val, test, or overall.")
        if self.composition_calibration_path is not None and not Path(
            self.composition_calibration_path
        ).is_file():
            raise FileNotFoundError(self.composition_calibration_path)
        if self.phenology_model not in {"legacy_independent", "literature_cohort_v1"}:
            raise ValueError("Unknown phenology_model.")
        if self.background_style not in {"legacy_green_carpet", "layered_understory_v2"}:
            raise ValueError("Unknown background_style.")

    @property
    def scene_count(self) -> int:
        return self.image_count // self.captures_per_scene

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if self.morphology_preset is None:
            # Retain the serialized historical config when no new route was
            # requested; explicit new presets participate in resume checks.
            result.pop("morphology_preset")
        result["output_dir"] = str(self.output_dir)
        result["asset_dir"] = str(self.asset_dir) if self.asset_dir is not None else None
        result["reference_profile_path"] = (
            str(self.reference_profile_path)
            if self.reference_profile_path is not None
            else None
        )
        result["composition_calibration_path"] = (
            str(self.composition_calibration_path)
            if self.composition_calibration_path is not None
            else None
        )
        result["inspection_blend_path"] = (
            str(self.inspection_blend_path)
            if self.inspection_blend_path is not None
            else None
        )
        result["scene_count"] = self.scene_count
        return result


def _composition_schedule(
    config: DatasetConfig,
    reference_profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    total = config.image_count
    profile = reference_profile or {}
    reference = (
        profile.get("splits", {}).get(config.reference_split, {})
        if config.reference_split != "overall"
        else profile.get("overall", {})
    )
    if not reference:
        reference = profile.get("overall", {})
    object_rates = dict(
        reference.get(
            "objects_per_image_band_rates_pct",
            {
                "zero": 0.0,
                "one_to_five": 89.0,
                "six_to_ten": 10.0,
                "more_than_ten": 1.0,
            },
        )
    )
    object_rates["one_to_five"] = float(object_rates.get("one_to_five", 0.0)) + float(
        object_rates.pop("zero", 0.0)
    )
    orientation_rates = reference.get(
        "orientation_rates_pct", {"portrait": 59.0, "landscape": 41.0}
    )
    box_area_rates = reference.get(
        "box_area_band_rates_pct",
        {
            "under_one_percent": 16.0,
            "one_to_five_percent": 51.0,
            "at_least_five_percent": 33.0,
        },
    )
    area_rates = (
        load_schedule_rates(config.composition_calibration_path)
        if config.composition_calibration_path is not None
        else _image_level_area_rates(box_area_rates)
    )
    boundary_rate = float(reference.get("boundary_box_rate_pct", 10.0))
    count_schedule = _weighted_schedule(total, object_rates, config.seed + 101)
    orientation_schedule = _weighted_schedule(total, orientation_rates, config.seed + 211)
    area_schedule = _weighted_schedule(total, area_rates, config.seed + 307)
    area_schedule = _couple_area_to_object_counts(count_schedule, area_schedule)
    boundary_schedule = _weighted_schedule(
        total,
        {"boundary": boundary_rate, "interior": max(0.0, 100.0 - boundary_rate)},
        config.seed + 401,
    )
    environment_schedule = _weighted_schedule(
        total,
        {"canopy_close": 50.0, "ground_tangle": 35.0, "open_field_hybrid": 15.0},
        config.seed + 503,
    )
    result: list[dict[str, Any]] = []
    for index in range(total):
        orientation = orientation_schedule[index]
        area_band = area_schedule[index]
        if area_band == "at_least_five_percent":
            camera_profile = "real_close"
        elif area_band == "one_to_five_percent":
            camera_profile = "real_mid"
        else:
            camera_profile = "real_context"
        if orientation == "portrait":
            width, height = ((720, 1280) if index % 4 == 0 else (960, 1280))
        else:
            width, height = ((1280, 720) if index % 5 == 0 else (1280, 960))
        result.append(
            {
                "schedule_index": index,
                "object_count_band": count_schedule[index],
                "orientation": orientation,
                "box_area_band": area_band,
                "boundary_mode": boundary_schedule[index],
                "environment_mode": environment_schedule[index],
                "camera_profile": camera_profile,
                "frame_profile": f"{orientation}_{width}x{height}",
                "width": width,
                "height": height,
            }
        )
    return result


def _image_level_area_rates(box_area_rates: dict[str, Any]) -> dict[str, float]:
    """Convert box-level reference rates into camera/image scheduling rates."""
    weighted = {
        key: max(0.0, float(box_area_rates.get(key, 0.0))) * multiplier
        for key, multiplier in AREA_IMAGE_RATE_MULTIPLIERS.items()
    }
    total = sum(weighted.values())
    if total <= 0.0:
        return {
            "under_one_percent": 5.0,
            "one_to_five_percent": 39.0,
            "at_least_five_percent": 56.0,
        }
    return {key: value * 100.0 / total for key, value in weighted.items()}


def _couple_area_to_object_counts(
    count_schedule: list[str], area_schedule: list[str]
) -> list[str]:
    """Avoid implausible many-object macro shots while preserving all marginals."""
    count_priority = {"more_than_ten": 0, "six_to_ten": 1, "one_to_five": 2}
    area_priority = {
        "one_to_five_percent": 0,
        "under_one_percent": 1,
        "at_least_five_percent": 2,
    }
    target_indices = sorted(
        range(len(count_schedule)),
        key=lambda index: (count_priority.get(count_schedule[index], 3), index),
    )
    ordered_areas = sorted(
        area_schedule,
        key=lambda value: area_priority.get(value, 3),
    )
    coupled = ["one_to_five_percent"] * len(count_schedule)
    for index, area_band in zip(target_indices, ordered_areas):
        coupled[index] = area_band
    return coupled


def _weighted_schedule(
    total: int,
    weights: dict[str, float],
    seed: int,
) -> list[str]:
    positive = {key: max(0.0, float(value)) for key, value in weights.items()}
    weight_sum = sum(positive.values())
    if total <= 0 or weight_sum <= 0.0:
        return []
    raw = {key: total * value / weight_sum for key, value in positive.items()}
    counts = {key: int(math.floor(value)) for key, value in raw.items()}
    remaining = total - sum(counts.values())
    order = sorted(raw, key=lambda key: (raw[key] - counts[key], key), reverse=True)
    for key in order[:remaining]:
        counts[key] += 1
    tokens = [
        (key, occurrence)
        for key in sorted(counts)
        for occurrence in range(counts[key])
    ]
    tokens.sort(
        key=lambda item: hashlib.sha256(
            f"{seed}:{item[0]}:{item[1]}".encode("utf-8")
        ).digest()
    )
    return [key for key, _ in tokens]


def morphology_parameters_for_capture(
    target: dict[str, Any] | None = None,
    *,
    preset_name: str = "trained_trellis_audit_v2",
) -> dict[str, Any]:
    """Select plant parameters independently of count/area/camera targets.

    ``target`` is accepted to make migration explicit, but is not consumed.
    Cameras and view selection may change; nodal architecture and load may not.
    """
    params = get_morphology_parameters(preset_name)
    policy = params.get("reproduction", {}).get("load_policy", {}).get("value")
    if policy != "architecture_driven":
        raise ValueError("Independent capture route requires architecture_driven plant policy")
    return params


def _morphology_params_for_target(target: dict[str, Any]) -> dict[str, Any]:
    """Historical frame-coupled route, retained only for old dataset configs."""
    params = get_morphology_parameters("trained_trellis")
    # Dense dataset-facing canopy: compact internodes, more active nodal
    # branches, broader blades, and shorter petioles keep foliage layered
    # around the trained axes. These remain explicit manual initial guesses.
    # The literature cohort model defers the first main-axis bifurcation to
    # nodes 8--12. A fixed, explicit 16-node render budget leaves enough
    # post-bifurcation sites for a dense trained canopy; this is a dataset
    # composition choice, not an automatic consequence of the thermal prior.
    params["axis"]["main_node_count"]["value"] = 16
    params["axis"]["branch_node_count_range"].update({"min": 5, "max": 7})
    params["internode"]["length_cm_range"].update({"min": 1.15, "max": 2.35})
    params["branching"]["branch_probability"]["value"] = 0.66
    params["growth"]["max_internodes_by_order"]["0"]["value"] = 16
    params["growth"]["branch_probability_by_order"]["0"]["value"] = 0.84
    params["growth"]["branch_probability_by_order"]["1"]["value"] = 0.68
    params["leaf"]["length_cm_range"].update({"min": 5.4, "max": 10.2})
    params["leaf"]["width_to_length_ratio_range"].update(
        {"min": 0.64, "max": 0.90}
    )
    override_parameter(
        params["leaf"]["petiole_length_cm_range"], min=3.5, max=5.8,
        status="manual_initial_guess",
        method="legacy_dataset_canopy_petiole_override_not_a_Kew_measurement",
    )
    params["leaf"]["senescence_range"].update({"min": 0.0, "max": 0.16})
    band = target["object_count_band"]
    ranges = {
        "one_to_five": (2, 4),
        # Higher-count frames use several real morphology trees. The larger
        # potential budget compensates for deterministic branch competition,
        # collision cancellation, and camera occlusion; it does not force
        # visible annotations after those filters.
        "six_to_ten": (10, 13),
        "more_than_ten": (16, 20),
    }
    minimum, maximum = ranges.get(band, (2, 4))
    if band == "one_to_five" and target.get("box_area_band") == "at_least_five_percent":
        minimum, maximum = 4, 5
        params["axis"]["main_node_count"]["value"] = 17
        params["axis"]["branch_node_count_range"].update({"min": 5, "max": 7})
        params["internode"]["length_cm_range"].update({"min": 1.05, "max": 2.15})
        params["branching"]["branch_probability"]["value"] = 0.70
        params["growth"]["max_internodes_by_order"]["0"]["value"] = 17
        params["growth"]["branch_probability_by_order"]["0"]["value"] = 0.88
    elif target.get("box_area_band") == "one_to_five_percent":
        params["axis"]["main_node_count"]["value"] = 16
        params["axis"]["branch_node_count_range"].update({"min": 5, "max": 7})
        params["internode"]["length_cm_range"].update({"min": 1.15, "max": 2.30})
        params["branching"]["branch_probability"]["value"] = 0.68
    params["reproduction"]["target_reproductive_units_range"].update(
        {"min": minimum, "max": maximum}
    )
    params["preset_name"] = "real_matched_stratified_light_schedule"
    return params


def _neighbor_count_for_target(target: dict[str, Any]) -> int:
    if target["object_count_band"] == "one_to_five":
        return 1 if target.get("box_area_band") == "one_to_five_percent" else 0
    return {
        "one_to_five": 0,
        "six_to_ten": 1,
        "more_than_ten": 2,
    }.get(target["object_count_band"], 0)


def generate_annotation_dataset(config: DatasetConfig) -> dict[str, Any]:
    """Generate, annotate, preview, split, and validate a YOLO pilot dataset."""
    config.validate()
    root = Path(config.output_dir).resolve()
    manifest_path = root / "manifest.jsonl"
    rejected_path = root / "rejected_scenes.jsonl"
    if manifest_path.exists() and not config.resume:
        raise FileExistsError(
            f"Dataset manifest already exists: {manifest_path}. Use --resume or a new output directory."
        )
    if manifest_path.exists() and config.resume:
        _validate_resume_configuration(root, config)
    root.mkdir(parents=True, exist_ok=True)
    write_dataset_descriptor(root)
    reference_profile = load_reference_profile(config.reference_profile_path)
    composition_schedule = (
        _composition_schedule(config, reference_profile)
        if config.composition_profile == "real_matched"
        else []
    )
    generation_config = config.to_dict()
    generation_config["reference_profile_name"] = (
        reference_profile.get("name") if reference_profile else None
    )
    generation_config["composition_schedule"] = composition_schedule
    _write_json(root / "generation_config.json", generation_config)
    if not config.resume:
        _rewrite_jsonl(rejected_path, [])
    existing_records = _prepare_resume_records(root, config) if config.resume else []
    completed_scene_indices = {
        int(record["scene_index"]) for record in existing_records
    }
    if config.resume:
        _rewrite_jsonl(manifest_path, existing_records)

    split_counts = _split_scene_counts(config.scene_count)
    phenology_schedule = _phenology_schedule(config.scene_count)
    rejected_records = _read_jsonl(rejected_path) if config.resume else []
    used_seeds = {int(record["scene_seed"]) for record in existing_records}
    used_seeds.update(
        int(record["scene_seed"])
        for record in rejected_records
        if "scene_seed" in record
    )
    candidate_seed = max(used_seeds, default=config.seed - 1) + 1
    candidate_limit = config.seed + config.max_seed_candidates
    qa_combinations = {
        f"{record['camera_profile']}:{record['lighting_profile']}"
        for record in existing_records
        if record.get("qa_cycles_path")
    }
    records = list(existing_records)
    scene_reports: list[dict[str, Any]] = []
    staging_root = root / ".staging"
    setup_render_settings(width=config.width, height=config.height)

    for scene_index in range(config.scene_count):
        if scene_index in completed_scene_indices:
            continue
        split = _split_for_scene(scene_index, split_counts)
        phenology_profile = phenology_schedule[scene_index]
        scene_targets = composition_schedule[
            scene_index * config.captures_per_scene :
            (scene_index + 1) * config.captures_per_scene
        ]
        scene_target = scene_targets[0] if scene_targets else {
            "object_count_band": "one_to_five",
            "environment_mode": "canopy_close",
        }
        morphology_params = (
            morphology_parameters_for_capture(scene_target, preset_name=config.morphology_preset)
            if config.morphology_preset is not None
            else _morphology_params_for_target(scene_target)
        )
        accepted = False
        while candidate_seed < candidate_limit:
            scene_seed = candidate_seed
            candidate_seed += 1
            foreground = generate_morphology_tree(
                scene_seed,
                params=morphology_params,
                phenology_profile=phenology_profile,
                phenology_model=config.phenology_model,
            )
            foreground_validation = validate_morphology_tree(foreground)
            if config.composition_profile != "real_matched" and not _phenology_is_acceptable(
                foreground_validation["summary"], phenology_profile
            ):
                _record_rejection(
                    rejected_path,
                    scene_index,
                    scene_seed,
                    phenology_profile,
                    "phenology_coverage",
                    foreground_validation["summary"],
                )
                continue

            if config.composition_profile == "real_matched":
                neighbor_count = _neighbor_count_for_target(scene_target)
            else:
                neighbor_rng = random.Random(config.seed + scene_index * 7919)
                neighbor_count = neighbor_rng.randint(
                    config.neighbor_count_min, config.neighbor_count_max
                )
            build = _build_dataset_scene(
                scene_seed=scene_seed,
                neighbor_count=neighbor_count,
                phenology_profile=phenology_profile,
                asset_dir=config.asset_dir,
                composition_target=scene_target,
                morphology_params=morphology_params,
                phenology_model=config.phenology_model,
                background_style=config.background_style,
            )
            if build["scene_validation"]["summary"]["physical_collision_count"]:
                _record_rejection(
                    rejected_path,
                    scene_index,
                    scene_seed,
                    phenology_profile,
                    "physical_collision",
                    build["scene_validation"],
                )
                continue
            if build["open_calyx_count"] or build["visible_hidden_fruit_count"]:
                _record_rejection(
                    rejected_path,
                    scene_index,
                    scene_seed,
                    phenology_profile,
                    "closed_calyx_policy",
                    {
                        "open_calyx_count": build["open_calyx_count"],
                        "visible_hidden_fruit_count": build["visible_hidden_fruit_count"],
                    },
                )
                continue

            staging_scene = staging_root / f"scene_{scene_index:04d}"
            if staging_scene.exists():
                shutil.rmtree(staging_scene)
            staging_scene.mkdir(parents=True, exist_ok=True)
            capture_records: list[dict[str, Any]] = []
            capture_failed = False
            qa_combinations_before_scene = set(qa_combinations)
            for capture_index in range(config.captures_per_scene):
                schedule_index = scene_index * config.captures_per_scene + capture_index
                composition_target = (
                    composition_schedule[schedule_index]
                    if composition_schedule
                    else {
                        "schedule_index": schedule_index,
                        "width": config.width,
                        "height": config.height,
                        "camera_profile": CAMERA_ORDER[schedule_index % len(CAMERA_ORDER)],
                        "boundary_mode": "interior",
                        "box_area_band": "unconstrained",
                        "object_count_band": "unconstrained",
                        "orientation": "landscape" if config.width >= config.height else "portrait",
                        "environment_mode": "canopy_close",
                        "frame_profile": f"legacy_{config.width}x{config.height}",
                    }
                )
                lighting_profile = LIGHTING_ORDER[schedule_index % len(LIGHTING_ORDER)]
                camera_profile = str(composition_target["camera_profile"])
                capture = _render_dataset_capture(
                    config=config,
                    root=root,
                    staging_scene=staging_scene,
                    scene_index=scene_index,
                    scene_seed=scene_seed,
                    split=split,
                    capture_index=capture_index,
                    camera_profile=camera_profile,
                    lighting_profile=lighting_profile,
                    phenology_profile=phenology_profile,
                    build=build,
                    qa_combinations=qa_combinations,
                    composition_target=composition_target,
                )
                if capture is None:
                    capture_failed = True
                    break
                capture_records.append(capture)

            if capture_failed:
                qa_combinations.clear()
                qa_combinations.update(qa_combinations_before_scene)
                shutil.rmtree(staging_scene, ignore_errors=True)
                _record_rejection(
                    rejected_path,
                    scene_index,
                    scene_seed,
                    phenology_profile,
                    "no_valid_boxes_after_camera_retries",
                    {
                        "capture_pose_retries": config.capture_pose_retries,
                        "capture_diagnostics": build.get(
                            "last_capture_diagnostics", []
                        ),
                    },
                )
                continue

            for record in capture_records:
                _promote_capture_files(root, record)
                record["checksums"] = {
                    "image_sha256": _sha256(root / record["image_path"]),
                    "label_sha256": _sha256(root / record["label_path"]),
                    "preview_sha256": _sha256(root / record["preview_path"]),
                }
                if record.get("qa_cycles_path"):
                    record["checksums"]["qa_cycles_sha256"] = _sha256(
                        root / record["qa_cycles_path"]
                    )
                    qa_combinations.add(
                        f"{record['camera_profile']}:{record['lighting_profile']}"
                    )
                append_jsonl(manifest_path, record)
                records.append(record)
            shutil.rmtree(staging_scene, ignore_errors=True)
            scene_reports.append(
                {
                    "scene_index": scene_index,
                    "scene_seed": scene_seed,
                    "split": split,
                    "phenology_profile": phenology_profile,
                    "plant_count": build["plant_count"],
                    "physical_collision_count": 0,
                    "capture_count": len(capture_records),
                }
            )
            if config.inspection_blend_path is not None:
                save_blend_file(config.inspection_blend_path)
            accepted = True
            break

        if not accepted:
            report = _validate_dataset(root, config, records, split_counts)
            report["status"] = "incomplete"
            report["errors"].append(
                f"Could not accept {config.scene_count} scenes within {config.max_seed_candidates} candidates."
            )
            _write_json(root / "dataset_report.json", report)
            raise RuntimeError(report["errors"][-1])

    report = _validate_dataset(root, config, records, split_counts)
    report["dataset_version"] = DATASET_VERSION
    report["morphology_script_version"] = SCRIPT_VERSION
    report["scene_reports_generated_this_run"] = scene_reports
    report["reference_profile_name"] = (
        reference_profile.get("name") if reference_profile else None
    )
    alignment = _reference_alignment(
        records,
        reference_profile,
        reference_split=config.reference_split,
    )
    report["reference_alignment"] = alignment
    for metric, details in alignment.get("metrics", {}).items():
        if details.get("within_five_percentage_points") is False:
            report["warnings"].append(
                f"Reference alignment for {metric} exceeds five percentage points."
            )
    _write_json(root / "dataset_report.json", report)
    if report["status"] != "valid":
        raise RuntimeError(
            f"Dataset generation finished with validation errors; see {root / 'dataset_report.json'}"
        )
    shutil.rmtree(staging_root, ignore_errors=True)
    return report


def _build_dataset_scene(
    *,
    scene_seed: int,
    neighbor_count: int,
    phenology_profile: str,
    asset_dir: str | Path | None,
    composition_target: dict[str, Any],
    morphology_params: dict[str, Any],
    phenology_model: str,
    background_style: str,
) -> dict[str, Any]:
    import bpy

    scene_data = create_cultivation_scene(
        seed=scene_seed,
        preset_name="annotation_real_matched",
        plant_count=neighbor_count + 1,
        collision_policy="contact_policy_clearance",
    )
    plants_by_id = {
        instance.plant_id: generate_morphology_tree(
            instance.seed,
            params=morphology_params,
            phenology_profile=phenology_profile,
            phenology_model=phenology_model,
            condition=instance.condition,
        )
        for instance in scene_data.plant_instances
    }
    scene_data, plants_by_id, adaptation_report = generate_cultivation_morphologies(
        scene_data,
        morphology_params,
        "E_plus_contact_policy_clearance",
        potential_plants=plants_by_id,
    )
    cleanup_scene()
    materials = create_project_materials(seed=scene_seed + 3000)
    geometry_reports: list[dict[str, Any]] = []
    morphology_reports: list[dict[str, Any]] = []
    max_height = 0.0
    for instance in scene_data.plant_instances:
        instance.phenological_stage = phenology_profile
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
                "seed": instance.seed,
                "summary": morphology_report["summary"],
                "status": morphology_report["status"],
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
        max_height = max(max_height, float(geometry_report["height"]))
    support_report = create_cultivation_supports(scene_data, materials, geometry_reports)
    mesh_collision_audit = audit_scene_mesh_collisions()
    scene_data.metadata["geometry_reports"] = geometry_reports
    scene_data.metadata["plant_morphology_reports"] = morphology_reports
    scene_data.metadata["cultivation_adaptation"] = adaptation_report
    scene_data.metadata["support_geometry"] = support_report
    center_x, center_y, scene_radius = _scene_center_and_radius(scene_data)
    environment = create_outdoor_environment(
        seed=scene_seed,
        scene_radius=scene_radius,
        terrain_size=scene_data.environment.terrain_size,
        terrain_subdivisions=scene_data.environment.terrain_subdivisions,
        background_cluster_count=scene_data.environment.background_cluster_count,
        asset_dir=asset_dir,
        mode=str(composition_target.get("environment_mode", "canopy_close")),
        background_style=background_style,
    )
    ground_clearance_audit = audit_calyx_ground_clearance(
        seed=scene_seed,
        terrain_object=bpy.data.objects.get(environment["terrain_object"]),
    )
    mesh_collision_audit["physical_collisions"].extend(
        ground_clearance_audit["physical_collisions"]
    )
    mesh_collision_audit["physical_collision_count"] = len(
        mesh_collision_audit["physical_collisions"]
    )
    if ground_clearance_audit["physical_collision_count"]:
        mesh_collision_audit["status"] = "invalid"
    scene_data.metadata["mesh_collision_audit"] = mesh_collision_audit
    scene_data.metadata["ground_clearance_audit"] = ground_clearance_audit
    validation = validate_cultivation_scene(scene_data)
    foreground = next(report for report in geometry_reports if report["role"] == "foreground")
    plant_target = (
        center_x,
        center_y,
        max(0.45, float(foreground["height"]) * 0.50),
    )
    target, focal_calyx_count = _select_render_target(
        plant_target=plant_target,
        composition_target=composition_target,
        scene_seed=scene_seed,
    )
    open_calyx_count = sum(
        1
        for obj in bpy.context.scene.objects
        if "uchuva_calyx_openness" in obj
        and float(obj.get("uchuva_calyx_openness", 1.0)) > 0.001
    )
    visible_hidden_fruit_count = sum(
        1
        for obj in bpy.context.scene.objects
        if obj.get("uchuva_hidden_inside_closed_calyx") and not obj.hide_render
    )
    return {
        "scene_data": scene_data,
        "scene_validation": validation,
        "environment": environment,
        "ground_clearance_audit": ground_clearance_audit,
        "geometry_reports": geometry_reports,
        "morphology_reports": morphology_reports,
        "target": target,
        "plant_target": plant_target,
        "focal_calyx_count": focal_calyx_count,
        "plant_height": max(max_height, 2.4),
        "scene_radius": scene_radius,
        "plant_count": len(scene_data.plant_instances),
        "open_calyx_count": open_calyx_count,
        "visible_hidden_fruit_count": visible_hidden_fruit_count,
    }


def _select_render_target(
    *,
    plant_target: tuple[float, float, float],
    composition_target: dict[str, Any],
    scene_seed: int,
) -> tuple[tuple[float, float, float], int]:
    import bpy

    calyx_objects = sorted(
        (
            obj
            for obj in bpy.context.scene.objects
            if "uchuva_calyx_profile" in obj
            and not obj.hide_render
        ),
        key=lambda obj: obj.name,
    )
    if not calyx_objects:
        return plant_target, 0
    camera_profile = composition_target.get("camera_profile")
    if camera_profile in {"real_close", "real_mid"}:
        foreground_objects = [
            obj
            for obj in calyx_objects
            if str(obj.get("uchuva_plant_role", "")) == "foreground"
        ]
        target_candidates = foreground_objects or calyx_objects
        selected_object = target_candidates[scene_seed % len(target_candidates)]
        selected = selected_object.matrix_world.translation
        weight = 1.0 if camera_profile == "real_close" else 0.94
    else:
        selected = calyx_objects[scene_seed % len(calyx_objects)].matrix_world.translation
        weight = 0.35
    target = tuple(
        (1.0 - weight) * float(plant_target[index]) + weight * float(selected[index])
        for index in range(3)
    )
    return target, len(calyx_objects)


def _render_dataset_capture(
    *,
    config: DatasetConfig,
    root: Path,
    staging_scene: Path,
    scene_index: int,
    scene_seed: int,
    split: str,
    capture_index: int,
    camera_profile: str,
    lighting_profile: str,
    phenology_profile: str,
    build: dict[str, Any],
    qa_combinations: set[str],
    composition_target: dict[str, Any],
) -> dict[str, Any] | None:
    import bpy

    stem = f"uchuva_s{scene_index:04d}_c{capture_index:02d}"
    capture_dir = staging_scene / stem
    capture_dir.mkdir(parents=True, exist_ok=True)
    capture_seed = scene_seed * 1000 + capture_index * 31
    width = int(composition_target.get("width", config.width))
    height = int(composition_target.get("height", config.height))
    sensor = _sensor_profile(capture_seed)
    lighting = apply_lighting_profile(lighting_profile, capture_seed)
    selected_camera = None
    annotation = None
    detections = []
    capture_diagnostics: list[dict[str, Any]] = []
    selected_retry = 0
    camera_plant_height = float(build["plant_height"])
    if composition_target.get("object_count_band") == "one_to_five":
        if camera_profile == "real_close":
            camera_plant_height = min(camera_plant_height, 2.4)
        elif camera_profile == "real_mid":
            camera_plant_height = min(camera_plant_height, 4.0)
    elif camera_profile == "real_mid":
        camera_plant_height = min(camera_plant_height, 4.5)
    for retry in range(config.capture_pose_retries):
        camera_seed = capture_seed + retry * 104729
        camera = create_annotation_camera(
            profile_name=camera_profile,
            target=build["target"],
            plant_height=camera_plant_height,
            scene_radius=build["scene_radius"],
            seed=camera_seed,
            name_suffix=f"s{scene_index:04d}_c{capture_index:02d}_r{retry}",
            target_offset=_target_offset(composition_target, build, retry),
        )
        annotation = render_reproductive_annotations(
            camera,
            capture_dir,
            width=width,
            height=height,
        )
        detections = detections_from_mask_items(
            annotation["items"],
            width=width,
            height=height,
            min_visible_pixels=config.min_visible_pixels,
            min_box_size=config.min_box_size,
        )
        target_match = _detection_target_diagnostics(
            detections,
            composition_target,
            width=width,
            height=height,
        )
        target_match["retry"] = retry
        capture_diagnostics.append(target_match)
        if target_match["accepted"]:
            selected_camera = camera
            selected_retry = retry
            break
        _remove_camera(camera)
    if selected_camera is None or annotation is None:
        build["last_capture_diagnostics"] = capture_diagnostics
        return None

    image_suffix = ".jpg" if config.image_format == "JPEG" else ".png"
    staged_image = capture_dir / f"{stem}{image_suffix}"
    staged_label = capture_dir / f"{stem}.txt"
    staged_preview = capture_dir / f"{stem}_annotated.png"
    render_rgb_image(
        selected_camera,
        staged_image,
        width=width,
        height=height,
        engine="BLENDER_EEVEE_NEXT",
        cycles_samples=config.cycles_samples,
        image_format=config.image_format,
        **sensor,
    )
    write_yolo_file(staged_label, detections)
    render_detection_preview(staged_image, staged_preview, detections)

    combination = f"{camera_profile}:{lighting_profile}"
    staged_cycles = None
    if len(qa_combinations) < config.cycles_qa_count and combination not in qa_combinations:
        staged_cycles = capture_dir / f"{stem}_cycles.png"
        render_rgb_image(
            selected_camera,
            staged_cycles,
            width=width,
            height=height,
            engine="CYCLES",
            cycles_samples=config.cycles_samples,
            image_format="PNG",
            exposure_ev=sensor["exposure_ev"],
            gamma=sensor["gamma"],
            filter_size=sensor["filter_size"],
            dither_intensity=sensor["dither_intensity"],
            white_balance_temperature=sensor["white_balance_temperature"],
            white_balance_tint=sensor["white_balance_tint"],
        )
        qa_combinations.add(combination)

    mask_path = Path(annotation["path"])
    visibility = _annotation_visibility_summary(annotation["items"], detections)
    record = {
        "dataset_version": DATASET_VERSION,
        "scene_index": scene_index,
        "scene_seed": scene_seed,
        "scene_id": build["scene_data"].scene_id,
        "split": split,
        "capture_index": capture_index,
        "capture_seed": capture_seed,
        "capture_pose_retry": selected_retry,
        "image_name": staged_image.name,
        "camera_profile": camera_profile,
        "camera": camera_metadata(selected_camera, width, height),
        "frame": {
            "width": width,
            "height": height,
            "orientation": composition_target.get("orientation"),
            "profile": composition_target.get("frame_profile"),
        },
        "composition_target": composition_target,
        "sensor_profile": sensor,
        "lighting_profile": lighting_profile,
        "lighting": lighting,
        "phenology_profile": phenology_profile,
        "phenology_model": config.phenology_model,
        "background_style": config.background_style,
        "composition_calibration_path": (
            str(Path(config.composition_calibration_path).resolve())
            if config.composition_calibration_path is not None
            else None
        ),
        "reference_split": config.reference_split,
        "plant_count": build["plant_count"],
        "neighbor_count": build["plant_count"] - 1,
        "collision_policy": "contact_policy_clearance",
        "physical_collision_count": build["scene_validation"]["summary"][
            "physical_collision_count"
        ],
        "open_calyx_count": build["open_calyx_count"],
        "visible_hidden_fruit_count": build["visible_hidden_fruit_count"],
        **visibility,
        "detections": [detection.to_dict() for detection in detections],
        "capture_target_diagnostics": capture_diagnostics[-1],
        "class_counts": _class_counts(detections),
        "image_path": f"images/{split}/{staged_image.name}",
        "label_path": f"labels/{split}/{staged_label.name}",
        "preview_path": f"previews/{split}/{staged_preview.name}",
        "qa_cycles_path": (
            f"qa_cycles/{split}/{staged_cycles.name}" if staged_cycles is not None else None
        ),
        "mask_path": (
            f"masks/{split}/{stem}.png" if config.keep_masks else None
        ),
        "staged_paths": {
            "image": str(staged_image),
            "label": str(staged_label),
            "preview": str(staged_preview),
            "cycles": str(staged_cycles) if staged_cycles is not None else None,
            "mask": str(mask_path),
        },
    }
    if not config.keep_masks:
        mask_path.unlink(missing_ok=True)
    if config.inspection_blend_path is None:
        _remove_camera(selected_camera)
    else:
        bpy.context.scene.camera = selected_camera
    return record


def _sensor_profile(seed: int) -> dict[str, Any]:
    """Return a reproducible camera-processing profile close to field JPEGs."""
    rng = random.Random(seed + 80_003)
    return {
        "jpeg_quality": rng.randint(76, 94),
        "exposure_ev": round(rng.uniform(0.38, 1.03), 4),
        "gamma": round(rng.uniform(0.96, 1.07), 4),
        "filter_size": round(rng.uniform(0.65, 1.55), 4),
        "dither_intensity": round(rng.uniform(0.15, 0.60), 4),
        "white_balance_temperature": round(rng.uniform(4900.0, 7200.0), 2),
        "white_balance_tint": round(rng.uniform(-0.06, 0.06), 4),
    }


def _target_offset(
    target: dict[str, Any],
    build: dict[str, Any],
    retry: int,
) -> tuple[float, float, float]:
    if target.get("boundary_mode") != "boundary":
        return (0.0, 0.0, 0.0)
    direction = -1.0 if retry % 2 else 1.0
    magnitude = float(build["scene_radius"]) * (0.30 + 0.035 * min(retry, 4))
    vertical = float(build["plant_height"]) * (0.06 if retry % 3 == 0 else -0.03)
    return (direction * magnitude, 0.0, vertical)


def _detections_match_target(
    detections: list[object],
    target: dict[str, Any],
    *,
    width: int,
    height: int,
) -> bool:
    return bool(
        _detection_target_diagnostics(
            detections,
            target,
            width=width,
            height=height,
        )["accepted"]
    )


def _detection_target_diagnostics(
    detections: list[object],
    target: dict[str, Any],
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    count = len(detections)
    reasons: list[str] = []
    count_band = target.get("object_count_band")
    if count_band == "one_to_five" and not 1 <= count <= 5:
        reasons.append("object_count_not_one_to_five")
    if count_band == "six_to_ten" and not 6 <= count <= 10:
        reasons.append("object_count_not_six_to_ten")
    if count_band == "more_than_ten" and count <= 10:
        reasons.append("object_count_not_more_than_ten")
    if target.get("boundary_mode") == "boundary" and not any(
        bool(item.truncated) for item in detections
    ):
        reasons.append("missing_boundary_truncation")
    if (
        target.get("boundary_mode") == "interior"
        and int(target.get("schedule_index", 0)) % 10 != 0
        and any(bool(item.truncated) for item in detections)
    ):
        reasons.append("unexpected_boundary_truncation")

    areas = [float(item.bbox_xywh[2] * item.bbox_xywh[3]) / (width * height) for item in detections]
    area_band = target.get("box_area_band")
    if area_band == "under_one_percent" and (not areas or statistics.median(areas) >= 0.01):
        reasons.append("median_area_not_under_one_percent")
    middle_fraction = (
        sum(0.01 <= area < 0.05 for area in areas) / len(areas)
        if areas else 0.0
    )
    if area_band == "one_to_five_percent" and middle_fraction < 0.50:
        reasons.append("insufficient_one_to_five_percent_boxes")
    large_fraction = (
        sum(area >= 0.05 for area in areas) / len(areas)
        if areas else 0.0
    )
    required_large_fraction = 0.50
    if area_band == "at_least_five_percent" and (
        not areas or large_fraction < required_large_fraction
    ):
        reasons.append("insufficient_large_boxes")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "detection_count": count,
        "bbox_area_fractions": [round(area, 6) for area in areas],
        "middle_fraction": round(middle_fraction, 6),
        "large_fraction": round(large_fraction, 6),
    }


def _promote_capture_files(root: Path, record: dict[str, Any]) -> None:
    mapping = {
        "image": "image_path",
        "label": "label_path",
        "preview": "preview_path",
        "cycles": "qa_cycles_path",
        "mask": "mask_path",
    }
    for staged_key, final_key in mapping.items():
        source_value = record["staged_paths"].get(staged_key)
        destination_value = record.get(final_key)
        if not source_value or not destination_value:
            continue
        source = Path(source_value)
        destination = root / destination_value
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.replace(destination)
    record.pop("staged_paths", None)


def _remove_camera(camera: object) -> None:
    import bpy

    focus = getattr(camera.data.dof, "focus_object", None)
    camera_data = camera.data
    bpy.data.objects.remove(camera, do_unlink=True)
    if focus is not None and focus.name in bpy.data.objects:
        bpy.data.objects.remove(focus, do_unlink=True)
    if camera_data.users == 0:
        bpy.data.cameras.remove(camera_data)


def _phenology_is_acceptable(summary: dict[str, Any], profile: str) -> bool:
    states = summary.get("calyx_state_counts", {})
    if summary.get("fruiting_reproductive_unit_count", 0) < 4:
        return False
    if profile == "mixed_early":
        return summary.get("flower_count", 0) >= 1 and states.get("inflated_green", 0) >= 2
    if profile == "mixed_balanced":
        return (
            states.get("inflated_green", 0) + states.get("transitioning_yellow", 0) >= 1
            and states.get("transitioning_yellow", 0) + states.get("straw_yellow", 0) >= 1
        )
    if profile == "mixed_late":
        return (
            states.get("transitioning_yellow", 0) + states.get("straw_yellow", 0) >= 1
            and states.get("dry_deteriorated", 0) >= 1
        )
    return False


def _phenology_schedule(scene_count: int) -> list[str]:
    if scene_count == 50:
        remaining = {"mixed_early": 17, "mixed_balanced": 17, "mixed_late": 16}
    else:
        base, remainder = divmod(scene_count, len(PHENOLOGY_ORDER))
        remaining = {
            name: base + (1 if index < remainder else 0)
            for index, name in enumerate(PHENOLOGY_ORDER)
        }
    schedule: list[str] = []
    while len(schedule) < scene_count:
        for name in PHENOLOGY_ORDER:
            if remaining[name] > 0:
                schedule.append(name)
                remaining[name] -= 1
    return schedule


def _split_scene_counts(scene_count: int) -> dict[str, int]:
    if scene_count == 50:
        return {"train": 40, "val": 5, "test": 5}
    train = max(1, int(round(scene_count * 0.8)))
    val = int(round(scene_count * 0.1)) if scene_count >= 10 else 0
    if train + val > scene_count:
        val = max(0, scene_count - train)
    return {"train": train, "val": val, "test": scene_count - train - val}


def _split_for_scene(scene_index: int, counts: dict[str, int]) -> str:
    if scene_index < counts["train"]:
        return "train"
    if scene_index < counts["train"] + counts["val"]:
        return "val"
    return "test"


def _scene_center_and_radius(scene_data: object) -> tuple[float, float, float]:
    positions = [instance.position for instance in scene_data.plant_instances]
    center_x = sum(position[0] for position in positions) / len(positions)
    center_y = sum(position[1] for position in positions) / len(positions)
    radius = max(
        math.hypot(position[0] - center_x, position[1] - center_y)
        + instance.collision_proxy.get("canopy_radius", 0.5)
        for position, instance in zip(positions, scene_data.plant_instances)
    )
    return center_x, center_y, max(radius, 1.4)


def _class_counts(detections: list[object]) -> dict[str, int]:
    counts = {name: 0 for name in YOLO_CLASSES}
    for detection in detections:
        counts[detection.class_name] += 1
    return counts


def _annotation_visibility_summary(
    items: dict[str, dict[str, Any]], detections: list[object]
) -> dict[str, Any]:
    visible_items = [
        item
        for identifier, item in items.items()
        if identifier != "0"
        and int(item.get("visible_pixels", 0)) > 0
        and item.get("bbox_xywh")
    ]
    accepted_ids = {detection.instance_id for detection in detections}
    ignored_ids = [
        str(item.get("name", ""))
        for item in visible_items
        if str(item.get("semantic_class", "")) == "flower"
    ]
    unknown_ids = [
        str(item.get("name", ""))
        for item in visible_items
        if str(item.get("semantic_class", "")) != "flower"
        if detection_class_name(
            str(item.get("semantic_class", "")),
            str(item.get("calyx_state", "")),
        )
        is None
    ]
    filtered_ids = [
        str(item.get("name", ""))
        for item in visible_items
        if str(item.get("name", "")) not in accepted_ids
        and str(item.get("name", "")) not in unknown_ids
        and str(item.get("name", "")) not in ignored_ids
    ]
    return {
        "visible_reproductive_instance_count": len(visible_items),
        "accepted_detection_count": len(detections),
        "filtered_below_annotation_threshold_count": len(filtered_ids),
        "filtered_reproductive_instance_ids": filtered_ids,
        "unknown_visible_reproductive_instance_count": len(unknown_ids),
        "unknown_visible_reproductive_instance_ids": unknown_ids,
        "ignored_flower_instance_count": len(ignored_ids),
        "ignored_flower_instance_ids": ignored_ids,
    }


def _validate_dataset(
    root: Path,
    config: DatasetConfig,
    records: list[dict[str, Any]],
    split_scene_counts: dict[str, int],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    unique_records = {(record["scene_index"], record["capture_index"]): record for record in records}
    records = list(unique_records.values())
    if len(records) != config.image_count:
        errors.append(f"Expected {config.image_count} records, found {len(records)}.")
    split_images = {name: 0 for name in ("train", "val", "test")}
    split_classes = {
        split: {name: 0 for name in YOLO_CLASSES}
        for split in ("train", "val", "test")
    }
    scene_splits: dict[int, set[str]] = {}
    qa_count = 0
    physical_collision_count = 0
    open_calyx_count = 0
    visible_hidden_fruit_count = 0
    visible_reproductive_instance_count = 0
    accepted_detection_count = 0
    filtered_below_threshold_count = 0
    unknown_visible_count = 0
    for record in records:
        split = record["split"]
        split_images[split] += 1
        scene_splits.setdefault(int(record["scene_index"]), set()).add(split)
        physical_collision_count += int(record.get("physical_collision_count", 0))
        open_calyx_count += int(record.get("open_calyx_count", 0))
        visible_hidden_fruit_count += int(
            record.get("visible_hidden_fruit_count", 0)
        )
        visible_reproductive_instance_count += int(
            record.get("visible_reproductive_instance_count", 0)
        )
        accepted_detection_count += int(record.get("accepted_detection_count", 0))
        filtered_below_threshold_count += int(
            record.get("filtered_below_annotation_threshold_count", 0)
        )
        unknown_visible_count += int(
            record.get("unknown_visible_reproductive_instance_count", 0)
        )
        for class_name, count in record["class_counts"].items():
            split_classes[split][class_name] += int(count)
        for path_key in ("image_path", "label_path", "preview_path"):
            path = root / record[path_key]
            if not path.exists() or path.stat().st_size <= 0:
                errors.append(f"Missing or empty {path_key}: {path}")
        image_path = root / record["image_path"]
        preview_path = root / record["preview_path"]
        label_path = root / record["label_path"]
        expected_dimensions = (
            int(record.get("frame", {}).get("width", config.width)),
            int(record.get("frame", {}).get("height", config.height)),
        )
        for image_kind, candidate_path in (("image", image_path), ("preview", preview_path)):
            if candidate_path.is_file() and _image_dimensions(candidate_path) != expected_dimensions:
                errors.append(
                    f"Unexpected {image_kind} dimensions for {candidate_path}: "
                    f"{_image_dimensions(candidate_path)}"
                )
        if image_path.stem != label_path.stem:
            errors.append(
                f"Image/label basename mismatch: {image_path.name}, {label_path.name}"
            )
        detection_ids = [
            str(detection.get("instance_id", ""))
            for detection in record.get("detections", [])
        ]
        if len(detection_ids) != len(set(detection_ids)):
            errors.append(f"Duplicate reproductive instance IDs in {image_path.name}.")
        if record.get("qa_cycles_path"):
            qa_count += 1
            qa_path = root / record["qa_cycles_path"]
            if not qa_path.exists():
                errors.append(f"Missing QA Cycles image: {record['qa_cycles_path']}")
            elif _image_dimensions(qa_path) != expected_dimensions:
                errors.append(
                    f"Unexpected QA Cycles dimensions for {qa_path}: "
                    f"{_image_dimensions(qa_path)}"
                )
        if label_path.exists():
            for line_number, line in enumerate(
                label_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                fields = line.split()
                if len(fields) != 5:
                    errors.append(f"Invalid YOLO row {label_path}:{line_number}")
                    continue
                if int(fields[0]) not in YOLO_CLASSES.values():
                    errors.append(f"Invalid class ID in {label_path}:{line_number}")
                if any(not 0.0 <= float(value) <= 1.0 for value in fields[1:]):
                    errors.append(f"Out-of-range YOLO value in {label_path}:{line_number}")
    if any(len(splits) > 1 for splits in scene_splits.values()):
        errors.append("At least one scene appears in more than one split.")
    expected_images = {
        split: count * config.captures_per_scene
        for split, count in split_scene_counts.items()
    }
    if split_images != expected_images:
        errors.append(f"Split image counts are {split_images}, expected {expected_images}.")
    require_all_split_classes = config.scene_count >= 10
    if require_all_split_classes:
        for split, class_counts in split_classes.items():
            missing = [name for name, count in class_counts.items() if count <= 0]
            if missing:
                errors.append(f"Split {split} is missing classes: {missing}")
    if qa_count != config.cycles_qa_count:
        errors.append(f"Expected {config.cycles_qa_count} QA Cycles images, found {qa_count}.")
    if any(not record.get("detections") for record in records):
        errors.append("At least one dataset image has no accepted detection boxes.")
    if physical_collision_count:
        errors.append(f"Found {physical_collision_count} physical collisions.")
    if open_calyx_count:
        errors.append(f"Found {open_calyx_count} open calyx observations.")
    if visible_hidden_fruit_count:
        errors.append(
            f"Found {visible_hidden_fruit_count} fruit objects visible inside closed calyxes."
        )
    if unknown_visible_count:
        errors.append(
            f"Found {unknown_visible_count} visible reproductive instances without a class mapping."
        )
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "image_count": len(records),
            "scene_count": len(scene_splits),
            "preview_count": len(records),
            "label_count": len(records),
            "qa_cycles_count": qa_count,
            "split_images": split_images,
            "class_counts_by_split": split_classes,
            "camera_counts": _count_records(records, "camera_profile"),
            "lighting_counts": _count_records(records, "lighting_profile"),
            "phenology_counts": _count_records(records, "phenology_profile"),
            "physical_collision_count": physical_collision_count,
            "open_calyx_count": open_calyx_count,
            "visible_hidden_fruit_count": visible_hidden_fruit_count,
            "visible_reproductive_instance_count": visible_reproductive_instance_count,
            "accepted_detection_count": accepted_detection_count,
            "filtered_below_annotation_threshold_count": filtered_below_threshold_count,
            "unknown_visible_reproductive_instance_count": unknown_visible_count,
        },
    }


def _validate_resume_configuration(root: Path, config: DatasetConfig) -> None:
    """Reject mixed generation settings before overwriting any existing metadata.

    This checks the recorded configuration, not the contents of referenced
    files or the source revision. Those require a separate provenance lock.
    """
    path = root / "generation_config.json"
    if not path.is_file():
        raise ValueError("Cannot resume without generation_config.json; use a new output directory.")
    previous = json.loads(path.read_text(encoding="utf-8-sig"))
    operational = {"resume", "output_dir", "max_seed_candidates", "inspection_blend_path"}
    changed = sorted(
        key for key, value in config.to_dict().items()
        if key not in operational and (key not in previous or previous[key] != value)
    )
    if changed:
        raise ValueError(
            "Resume configuration changed: " + ", ".join(changed)
            + ". Use a new output directory to preserve the existing experiment."
        )


def _prepare_resume_records(root: Path, config: DatasetConfig) -> list[dict[str, Any]]:
    records = _read_jsonl(root / "manifest.jsonl")
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(int(record.get("scene_index", -1)), []).append(record)
    valid: list[dict[str, Any]] = []
    for scene_records in grouped.values():
        if len(scene_records) != config.captures_per_scene:
            continue
        if all(
            _resume_record_is_valid(root, record)
            and _stored_record_matches_target(record)
            for record in scene_records
        ):
            valid.extend(scene_records)
    return valid


def _resume_record_is_valid(root: Path, record: dict[str, Any]) -> bool:
    checksums = record.get("checksums", {})
    for key, checksum_key in (
        ("image_path", "image_sha256"),
        ("label_path", "label_sha256"),
        ("preview_path", "preview_sha256"),
    ):
        path = root / str(record.get(key, ""))
        if not path.is_file() or _sha256(path) != checksums.get(checksum_key):
            return False
    if record.get("qa_cycles_path"):
        path = root / record["qa_cycles_path"]
        if not path.is_file() or _sha256(path) != checksums.get("qa_cycles_sha256"):
            return False
    return True


def _stored_record_matches_target(record: dict[str, Any]) -> bool:
    target = record.get("composition_target", {})
    detections = record.get("detections", [])
    count = len(detections)
    count_band = target.get("object_count_band")
    if count_band == "one_to_five" and not 1 <= count <= 5:
        return False
    if count_band == "six_to_ten" and not 6 <= count <= 10:
        return False
    if count_band == "more_than_ten" and count <= 10:
        return False
    truncated = [bool(item.get("truncated", False)) for item in detections]
    if target.get("boundary_mode") == "boundary" and not any(truncated):
        return False
    if (
        target.get("boundary_mode") == "interior"
        and int(target.get("schedule_index", 0)) % 10 != 0
        and any(truncated)
    ):
        return False
    areas = [
        float(item.get("yolo_xywh", [0.0, 0.0, 0.0, 0.0])[2])
        * float(item.get("yolo_xywh", [0.0, 0.0, 0.0, 0.0])[3])
        for item in detections
    ]
    if not areas:
        return False
    area_band = target.get("box_area_band")
    if area_band == "under_one_percent" and statistics.median(areas) >= 0.01:
        return False
    if area_band == "one_to_five_percent" and (
        sum(0.01 <= area < 0.05 for area in areas) / len(areas) < 0.50
    ):
        return False
    if area_band == "at_least_five_percent" and (
        sum(area >= 0.05 for area in areas) / len(areas) < 0.50
    ):
        return False
    return True


def _record_rejection(
    path: Path,
    scene_index: int,
    scene_seed: int,
    phenology_profile: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    append_jsonl(
        path,
        {
            "scene_index": scene_index,
            "scene_seed": scene_seed,
            "phenology_profile": phenology_profile,
            "reason": reason,
            "details": details,
        },
    )


def _count_records(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record[key])
        counts[value] = counts.get(value, 0) + 1
    return counts


def _reference_alignment(
    records: list[dict[str, Any]],
    reference_profile: dict[str, Any] | None,
    *,
    reference_split: str = "train",
) -> dict[str, Any]:
    orientations = {"portrait": 0, "landscape": 0, "square": 0}
    object_bands = {
        "zero": 0,
        "one_to_five": 0,
        "six_to_ten": 0,
        "more_than_ten": 0,
    }
    area_bands = {
        "under_one_percent": 0,
        "one_to_five_percent": 0,
        "at_least_five_percent": 0,
    }
    boundary_count = 0
    box_count = 0
    for record in records:
        frame = record.get("frame", {})
        width = int(frame.get("width", 1))
        height = int(frame.get("height", 1))
        orientation = "portrait" if height > width else "landscape" if width > height else "square"
        orientations[orientation] += 1
        detections = record.get("detections", [])
        count = len(detections)
        if count == 0:
            object_bands["zero"] += 1
        elif count <= 5:
            object_bands["one_to_five"] += 1
        elif count <= 10:
            object_bands["six_to_ten"] += 1
        else:
            object_bands["more_than_ten"] += 1
        for detection in detections:
            yolo = detection.get("yolo_xywh", (0.0, 0.0, 0.0, 0.0))
            area = float(yolo[2]) * float(yolo[3])
            if area < 0.01:
                area_bands["under_one_percent"] += 1
            elif area < 0.05:
                area_bands["one_to_five_percent"] += 1
            else:
                area_bands["at_least_five_percent"] += 1
            boundary_count += int(bool(detection.get("truncated", False)))
            box_count += 1
    image_count = len(records)
    actual = {
        "orientation_rates_pct": _percentage_rates(orientations, image_count),
        "objects_per_image_band_rates_pct": _percentage_rates(object_bands, image_count),
        "box_area_band_rates_pct": _percentage_rates(area_bands, box_count),
        "boundary_box_rate_pct": round(100.0 * boundary_count / box_count, 3) if box_count else 0.0,
    }
    if not reference_profile:
        return {"reference_available": False, "actual": actual, "metrics": {}}
    reference = (
        reference_profile.get("splits", {}).get(reference_split, {})
        if reference_split != "overall"
        else reference_profile.get("overall", {})
    )
    if not reference:
        reference = reference_profile.get("overall", {})
    metrics = {
        "orientation": _rate_gap(
            reference.get("orientation_rates_pct", {}), actual["orientation_rates_pct"]
        ),
        "objects_per_image": _rate_gap(
            reference.get("objects_per_image_band_rates_pct", {}),
            actual["objects_per_image_band_rates_pct"],
        ),
        "box_area": _rate_gap(
            reference.get("box_area_band_rates_pct", {}), actual["box_area_band_rates_pct"]
        ),
        "boundary_boxes": {
            "maximum_gap_pct_points": round(
                abs(float(reference.get("boundary_box_rate_pct", 0.0)) - actual["boundary_box_rate_pct"]),
                3,
            ),
        },
    }
    metrics["boundary_boxes"]["within_five_percentage_points"] = (
        metrics["boundary_boxes"]["maximum_gap_pct_points"] <= 5.0
    )
    return {
        "reference_available": True,
        "reference_name": reference_profile.get("name"),
        "reference_split": reference_split,
        "actual": actual,
        "reference": {
            "orientation_rates_pct": reference.get("orientation_rates_pct", {}),
            "objects_per_image_band_rates_pct": reference.get("objects_per_image_band_rates_pct", {}),
            "box_area_band_rates_pct": reference.get("box_area_band_rates_pct", {}),
            "boundary_box_rate_pct": reference.get("boundary_box_rate_pct"),
        },
        "metrics": metrics,
    }


def _percentage_rates(counts: dict[str, int], denominator: int) -> dict[str, float]:
    return {
        key: round(100.0 * value / denominator, 3) if denominator else 0.0
        for key, value in sorted(counts.items())
    }


def _rate_gap(reference: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    gaps = {
        key: round(abs(float(reference.get(key, 0.0)) - float(actual.get(key, 0.0))), 3)
        for key in sorted(set(reference) | set(actual))
    }
    maximum = max(gaps.values(), default=0.0)
    return {
        "gaps_pct_points": gaps,
        "maximum_gap_pct_points": maximum,
        "within_five_percentage_points": maximum <= 5.0,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return (
        int.from_bytes(header[16:20], "big"),
        int.from_bytes(header[20:24], "big"),
    )


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    if path.suffix.lower() == ".png":
        return _png_dimensions(path)
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return _jpeg_dimensions(path)
    return None


def _jpeg_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            return None
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                return None
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                return None
            segment_length = int.from_bytes(length_bytes, "big")
            if marker and marker[0] in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                payload = handle.read(5)
                if len(payload) != 5:
                    return None
                return (
                    int.from_bytes(payload[3:5], "big"),
                    int.from_bytes(payload[1:3], "big"),
                )
            handle.seek(max(0, segment_length - 2), 1)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _rewrite_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)
