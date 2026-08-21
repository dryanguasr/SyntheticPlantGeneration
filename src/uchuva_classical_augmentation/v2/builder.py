"""Materialize reproducible v2 datasets independently from model training."""

from __future__ import annotations

import json
import os
import random
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import CampaignConfig, RECIPE_VERSION, ScenarioConfig, default_campaign_config
from .copy_paste import apply_cluster_copy_paste
from .geometry import horizontal_flip, scale_preserving_crop
from .labels import YoloBox, read_yolo_labels, write_yolo_labels
from .manifest import DerivedSampleRecord, file_sha256, write_jsonl
from .occlusion import apply_visibility_consistent_occlusion
from .photometric import augment_photometric
from .profiles import image_photometry, label_path_for, read_profile, split_images


def build_scenario_dataset(
    dataset_root: Path,
    output_root: Path,
    profile_path: Path,
    scenario: ScenarioConfig,
    *,
    seed: int,
    derived_count: int | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build one scenario using only immutable train parents for derivations."""
    import cv2

    dataset_root = dataset_root.resolve()
    output_root = output_root.resolve()
    profile = read_profile(profile_path)
    requested = scenario.derived_count if derived_count is None else derived_count
    scenario_dir = output_root / f"{scenario.code}_seed_{seed:04d}_n{requested:04d}"
    completion_path = scenario_dir / "build_summary.json"
    if completion_path.is_file() and not overwrite:
        existing = json.loads(completion_path.read_text(encoding="utf-8"))
        if existing.get("completion_status") == "complete":
            return existing
    if scenario_dir.exists() and overwrite:
        shutil.rmtree(scenario_dir)
    scenario_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        (scenario_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (scenario_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    train_images = split_images(dataset_root, "train")
    source_hashes = {path.name: file_sha256(path) for path in train_images}
    for split in ("train", "val", "test"):
        _link_source_split(dataset_root, scenario_dir, split)

    rng = random.Random(seed)
    records: list[DerivedSampleRecord] = []
    rejections: list[dict[str, Any]] = []
    accepted = 0
    attempts = 0
    max_attempts = max(requested * 80, 80)
    while accepted < requested and attempts < max_attempts:
        attempts += 1
        source = rng.choice(train_images)
        source_labels = read_yolo_labels(label_path_for(dataset_root, "train", source), missing_is_empty=True)
        donor = rng.choice(train_images)
        donor_labels = read_yolo_labels(label_path_for(dataset_root, "train", donor), missing_is_empty=True)
        source_image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        donor_image = cv2.imread(str(donor), cv2.IMREAD_COLOR)
        if source_image is None or donor_image is None:
            rejections.append({"attempt": attempts, "source": source.name, "reason": "decode_failure"})
            continue
        result = _apply_recipe(scenario, source_image, source_labels, donor_image, donor_labels, rng, profile)
        if result is None:
            rejections.append({"attempt": attempts, "source": source.name, "donor": donor.name, "reason": "recipe_candidate_rejected"})
            continue
        output_image, output_labels, sequence, parameters, visibility = result
        image_id = f"{scenario.code.lower().replace('-', '_')}_s{seed:04d}_{accepted:05d}"
        image_name = f"{image_id}.jpg"
        output_image_path = scenario_dir / "images" / "train" / image_name
        output_label_path = scenario_dir / "labels" / "train" / f"{image_id}.txt"
        if scenario.code == "V2-E0R":
            _link_or_copy(source, output_image_path)
            source_label_path = label_path_for(dataset_root, "train", source)
            if source_label_path.is_file():
                _link_or_copy(source_label_path, output_label_path)
            else:
                output_label_path.write_text("", encoding="utf-8")
        else:
            success, encoded = cv2.imencode(".jpg", output_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not success:
                rejections.append({"attempt": attempts, "source": source.name, "reason": "jpeg_encode_failure"})
                continue
            output_image_path.write_bytes(encoded.tobytes())
            write_yolo_labels(output_label_path, output_labels)
        donor_provenance = {"donor_image_id": donor.name, "donor_sha256": source_hashes[donor.name], "donor_split": "train"}
        parameters = list(parameters)
        uses_donor = any(item in sequence for item in ("visibility_consistent_occlusion", "same_class_cluster_copy_paste"))
        if uses_donor:
            if parameters:
                parameters[-1] = {**parameters[-1], **donor_provenance}
            else:
                parameters = [donor_provenance]
        record = DerivedSampleRecord(
            derived_image_id=image_name,
            source_image_id=source.name,
            source_sha256=source_hashes[source.name],
            recipe_id=scenario.recipe_id,
            recipe_version=RECIPE_VERSION,
            augmentation_seed=seed,
            transform_sequence=tuple(sequence),
            transform_parameters=tuple(parameters),
            source_labels=tuple(asdict(box) for box in source_labels),
            output_labels=tuple(asdict(box) for box in output_labels),
            bbox_visibility_changes=tuple(visibility),
            source_domain_if_known=None,
            output_sha256=file_sha256(output_image_path),
        )
        records.append(record)
        accepted += 1

    if accepted != requested:
        raise RuntimeError(f"{scenario.code}: generated {accepted}/{requested} samples after {attempts} attempts")
    write_jsonl(scenario_dir / "manifests" / "derived_samples.jsonl", records)
    (scenario_dir / "manifests" / "rejections.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "manifests" / "rejections.jsonl").write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in rejections),
        encoding="utf-8",
        newline="\n",
    )
    config_payload = {
        "scenario": scenario.to_dict(),
        "seed": seed,
        "derived_count": requested,
        "profile_path": str(profile_path.resolve()),
        "profile_sha256": profile["profile_sha256"],
        "source_split_fingerprints": {name: value["fingerprint_sha256"] for name, value in profile["splits"].items()},
    }
    (scenario_dir / "build_config.json").write_text(json.dumps(config_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    _write_data_yaml(scenario_dir)
    summary = {
        "completion_status": "complete",
        "scenario": scenario.code,
        "seed": seed,
        "derived_count": accepted,
        "attempt_count": attempts,
        "rejection_count": len(rejections),
        "train_image_count": len(train_images) + accepted,
        "val_image_count": profile["splits"]["val"]["image_count"],
        "test_image_count": profile["splits"]["test"]["image_count"],
        "dataset_dir": str(scenario_dir),
    }
    completion_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return summary


def build_campaign_config(path: Path, config: CampaignConfig | None = None) -> None:
    config = config or default_campaign_config()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _apply_recipe(scenario: ScenarioConfig, image, boxes, donor_image, donor_boxes, rng, profile):
    code = scenario.code
    if code == "V2-E0R":
        return image.copy(), list(boxes), ("natural_resample",), ({"pixel_transform": "none"},), ()
    if code == "V2-E3":
        result = augment_photometric(image, rng, profile)
        if result is None:
            return None
        output, sequence, params, metrics = result
        return output, list(boxes), sequence, (*params, {"source_photometry": image_photometry(image), "accepted_photometry": metrics}), ()
    if code == "V2-E4":
        result = apply_visibility_consistent_occlusion(image, boxes, donor_image, rng)
        if result is None:
            return None
        output, labels, changes, params = result
        return output, labels, ("visibility_consistent_occlusion",), (params,), tuple(changes)
    if code == "V2-E5":
        output, labels = horizontal_flip(image, boxes)
        return output, labels, ("horizontal_flip",), ({"x_center_new": "1-x_center_old"},), ()
    if code == "V2-E6":
        result = scale_preserving_crop(image, boxes, rng, profile)
        if result is None:
            return None
        output, labels, params = result
        return output, labels, ("scale_preserving_crop",), (params,), ()
    if code == "V2-E7":
        output, labels = image, list(boxes)
        sequence, params = [], []
        if rng.random() < 0.8:
            crop = scale_preserving_crop(output, labels, rng, profile)
            if crop is None:
                return None
            output, labels, crop_params = crop
            sequence.append("scale_preserving_crop")
            params.append(crop_params)
        if rng.random() < 0.5 or not sequence:
            output, labels = horizontal_flip(output, labels)
            sequence.append("horizontal_flip")
            params.append({"x_center_new": "1-x_center_old"})
        return output, labels, tuple(sequence), tuple(params), ()
    if code == "V2-E8":
        result = apply_cluster_copy_paste(image, boxes, donor_image, donor_boxes, rng, profile)
        if result is None:
            return None
        output, labels, changes, params = result
        return output, labels, ("same_class_cluster_copy_paste",), (params,), tuple(changes)
    if code == "V2-E2":
        output, labels = image, list(boxes)
        sequence, params, changes = [], [], []
        use_photo = rng.random() < 0.65
        use_occlusion = rng.random() < 0.55
        if not use_photo and not use_occlusion:
            use_photo = True
        if use_photo:
            photo = augment_photometric(output, rng, profile)
            if photo is None:
                return None
            output, photo_sequence, photo_params, metrics = photo
            sequence.extend(photo_sequence)
            params.extend(photo_params)
            params.append({"source_photometry": image_photometry(image), "accepted_photometry": metrics})
        if use_occlusion:
            occlusion = apply_visibility_consistent_occlusion(output, labels, donor_image, rng)
            if occlusion is None:
                return None
            output, labels, occ_changes, occ_params = occlusion
            sequence.append("visibility_consistent_occlusion")
            params.append(occ_params)
            changes.extend(occ_changes)
        if len(sequence) > 3:
            return None
        return output, labels, tuple(sequence), tuple(params), tuple(changes)
    if code == "V2-E0":
        raise ValueError("V2-E0 has no derived samples")
    raise KeyError(f"Unknown v2 scenario: {code}")


def _link_source_split(dataset_root: Path, scenario_dir: Path, split: str) -> None:
    for image in split_images(dataset_root, split):
        _link_or_copy(image, scenario_dir / "images" / split / image.name)
        source_label = label_path_for(dataset_root, split, image)
        target_label = scenario_dir / "labels" / split / f"{image.stem}.txt"
        if source_label.is_file():
            _link_or_copy(source_label, target_label)
        else:
            target_label.write_text("", encoding="utf-8")


def _link_or_copy(source: Path, target: Path) -> None:
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _write_data_yaml(scenario_dir: Path) -> None:
    content = "\n".join(
        [
            f"path: {scenario_dir.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:",
            "  0: calyx",
            "nc: 1",
            "",
        ]
    )
    (scenario_dir / "data.yaml").write_text(content, encoding="utf-8", newline="\n")
