"""Dataset, provenance and recipe-specific audits for v2."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .geometry import band_rate_delta_percentage_points
from .labels import read_yolo_labels
from .manifest import file_sha256, read_jsonl, verify_record_hashes
from .profiles import label_path_for, read_profile, split_images


def audit_scenario_dataset(dataset_dir: Path, source_root: Path, profile_path: Path, *, expected_derived_count: int) -> dict[str, Any]:
    import cv2

    dataset_dir, source_root = dataset_dir.resolve(), source_root.resolve()
    profile = read_profile(profile_path)
    issues: list[dict[str, str]] = []
    split_counts = {}
    all_output_boxes = []
    for split in ("train", "val", "test"):
        image_dir, label_dir = dataset_dir / "images" / split, dataset_dir / "labels" / split
        images = sorted(path for path in image_dir.iterdir() if path.is_file())
        split_counts[split] = {"images": len(images), "objects": 0}
        for image in images:
            source_image = source_root / "IMAGENES" / split / image.name
            linked_to_validated_source = source_image.is_file() and os.path.samefile(image, source_image)
            if not linked_to_validated_source and cv2.imread(str(image), cv2.IMREAD_COLOR) is None:
                issues.append({"code": "image_decode_failure", "path": str(image)})
                continue
            label = label_dir / f"{image.stem}.txt"
            try:
                boxes = read_yolo_labels(label)
            except (FileNotFoundError, ValueError) as error:
                issues.append({"code": "invalid_label", "path": str(label), "detail": str(error)})
                continue
            split_counts[split]["objects"] += len(boxes)
            if split == "train":
                all_output_boxes.extend(boxes)
    expected_counts = {
        "train": profile["splits"]["train"]["image_count"] + expected_derived_count,
        "val": profile["splits"]["val"]["image_count"],
        "test": profile["splits"]["test"]["image_count"],
    }
    for split, expected in expected_counts.items():
        if split_counts[split]["images"] != expected:
            issues.append({"code": "dataset_count_mismatch", "path": split, "detail": f"{split_counts[split]['images']} != {expected}"})

    manifest_path = dataset_dir / "manifests" / "derived_samples.jsonl"
    records = read_jsonl(manifest_path)
    rejection_path = dataset_dir / "manifests" / "rejections.jsonl"
    rejections = [json.loads(line) for line in rejection_path.read_text(encoding="utf-8").splitlines() if line.strip()] if rejection_path.is_file() else []
    if len(records) != expected_derived_count:
        issues.append({"code": "manifest_count_mismatch", "path": str(manifest_path), "detail": f"{len(records)} != {expected_derived_count}"})
    val_test_hashes = {
        member["image_sha256"]
        for split in ("val", "test")
        for member in profile["splits"][split]["members"]
    }
    verified_donor_hashes: dict[str, str] = {}
    for record in records:
        source_path = source_root / "IMAGENES" / "train" / record.source_image_id
        output_path = dataset_dir / "images" / "train" / record.derived_image_id
        try:
            verify_record_hashes(record, source_path=source_path, output_path=output_path)
        except ValueError as error:
            issues.append({"code": "hash_or_provenance_failure", "path": record.derived_image_id, "detail": str(error)})
        if record.source_sha256 in val_test_hashes:
            issues.append({"code": "split_leakage", "path": record.derived_image_id, "detail": "source content occurs in val/test"})
        source_label_path = source_root / "LABELS" / "train" / f"{Path(record.source_image_id).stem}.txt"
        output_label_path = dataset_dir / "labels" / "train" / f"{Path(record.derived_image_id).stem}.txt"
        actual_source_labels = [asdict(box) for box in read_yolo_labels(source_label_path, missing_is_empty=True)]
        actual_output_labels = [asdict(box) for box in read_yolo_labels(output_label_path)]
        if not _labels_match(actual_source_labels, list(record.source_labels)):
            issues.append({"code": "manifest_source_label_mismatch", "path": record.derived_image_id})
        if not _labels_match(actual_output_labels, list(record.output_labels)):
            issues.append({"code": "manifest_output_label_mismatch", "path": record.derived_image_id})
        for params in record.transform_parameters:
            donor_hash = params.get("donor_sha256")
            if params.get("donor_split") not in (None, "train") or donor_hash in val_test_hashes:
                issues.append({"code": "donor_split_leakage", "path": record.derived_image_id})
            donor_id = params.get("donor_image_id")
            if donor_id:
                donor_path = source_root / "IMAGENES" / "train" / donor_id
                actual_donor_hash = verified_donor_hashes.get(donor_id)
                if actual_donor_hash is None and donor_path.is_file():
                    actual_donor_hash = file_sha256(donor_path)
                    verified_donor_hashes[donor_id] = actual_donor_hash
                if actual_donor_hash != donor_hash:
                    issues.append({"code": "donor_hash_mismatch", "path": record.derived_image_id, "detail": str(donor_id)})

    for split in ("val", "test"):
        for member in profile["splits"][split]["members"]:
            output_image = dataset_dir / "images" / split / member["image"]
            output_label = dataset_dir / "labels" / split / member["label"]
            source_image = source_root / "IMAGENES" / split / member["image"]
            if not (source_image.is_file() and os.path.samefile(output_image, source_image)) and file_sha256(output_image) != member["image_sha256"]:
                issues.append({"code": "frozen_split_image_changed", "path": str(output_image)})
            expected_label_hash = member["label_sha256"]
            if expected_label_hash and file_sha256(output_label) != expected_label_hash:
                issues.append({"code": "frozen_split_label_changed", "path": str(output_label)})

    reference_boxes = []
    for image in split_images(source_root, "train"):
        reference_boxes.extend(read_yolo_labels(label_path_for(source_root, "train", image), missing_is_empty=True))
    band_deltas = band_rate_delta_percentage_points(reference_boxes, all_output_boxes, profile)
    threshold = 5.0
    for band, delta in band_deltas.items():
        if abs(delta) > threshold:
            issues.append({"code": "bbox_size_band_shift", "path": band, "detail": f"{delta:.4f} percentage points > {threshold}"})

    report = {
        "status": "valid" if not issues else "invalid",
        "dataset_dir": str(dataset_dir),
        "expected_derived_count": expected_derived_count,
        "split_counts": split_counts,
        "manifest_count": len(records),
        "bbox_size_band_delta_percentage_points": band_deltas,
        "bbox_size_band_threshold": {"value": threshold, "status": "engineering_heuristic"},
        "source_integrity_basis": "source files are hardlink-identical or SHA-256 identical; derived files are decoded and hash-verified",
        "recipe_diagnostics": {**_recipe_diagnostics(records), "rejections": {"count": len(rejections), "reasons": _count_values(item.get("reason", "unknown") for item in rejections)}},
        "issues": issues,
    }
    return report


def write_audit(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _recipe_diagnostics(records) -> dict[str, Any]:
    visibility = []
    crop_before, crop_after = [], []
    copy_paste_overlap, pasted_scale = [], []
    source_photometry, augmented_photometry = [], []
    for record in records:
        visibility.extend(change.get("visible_fraction_after") for change in record.bbox_visibility_changes if "visible_fraction_after" in change)
        for params in record.transform_parameters:
            crop_before.extend(params.get("bbox_area_before", []))
            crop_after.extend(params.get("bbox_area_after", []))
            if "pairwise_iou_with_anchor" in params:
                copy_paste_overlap.append(params["pairwise_iou_with_anchor"])
            if "pasted_scale_over_anchor_width" in params:
                pasted_scale.append(params["pasted_scale_over_anchor_width"])
            if "accepted_photometry" in params:
                augmented_photometry.append(params["accepted_photometry"])
            if "source_photometry" in params:
                source_photometry.append(params["source_photometry"])
    return {
        "occlusion_visible_fraction": _simple_summary(visibility),
        "crop_bbox_area_before": _simple_summary(crop_before),
        "crop_bbox_area_after": _simple_summary(crop_after),
        "copy_paste_pairwise_overlap": _simple_summary(copy_paste_overlap),
        "copy_paste_scale_ratio": _simple_summary(pasted_scale),
        "photometry_source": _metric_means(source_photometry),
        "photometry_augmented": _metric_means(augmented_photometry),
    }


def _simple_summary(values) -> dict[str, float | int | None]:
    materialized = [float(value) for value in values if value is not None]
    if not materialized:
        return {"count": 0, "min": None, "mean": None, "max": None}
    return {"count": len(materialized), "min": min(materialized), "mean": sum(materialized) / len(materialized), "max": max(materialized)}


def _metric_means(rows) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "means": {}}
    return {"count": len(rows), "means": {key: sum(float(row[key]) for row in rows) / len(rows) for key in rows[0]}}


def _count_values(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _labels_match(first: list[dict[str, Any]], second: list[dict[str, Any]], tolerance: float = 1e-8) -> bool:
    if len(first) != len(second):
        return False
    for left, right in zip(first, second, strict=True):
        if int(left["class_id"]) != int(right["class_id"]):
            return False
        for key in ("x_center", "y_center", "width", "height"):
            if abs(float(left[key]) - float(right[key])) > tolerance:
                return False
    return True
