"""Measure the real dataset before defining augmentation intensities."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .config import PROFILE_VERSION
from .labels import YoloBox, pairwise_iou, read_yolo_labels
from .manifest import file_sha256


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def source_split_paths(dataset_root: Path, split: str) -> tuple[Path, Path]:
    image_dir = dataset_root / "IMAGENES" / split
    label_dir = dataset_root / "LABELS" / split
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise FileNotFoundError(f"Missing source split directories for {split}: {dataset_root}")
    return image_dir, label_dir


def split_images(dataset_root: Path, split: str) -> list[Path]:
    image_dir, _ = source_split_paths(dataset_root, split)
    return sorted(path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES)


def label_path_for(dataset_root: Path, split: str, image: Path) -> Path:
    return dataset_root / "LABELS" / split / f"{image.stem}.txt"


def analyze_real_training_domain(dataset_root: Path) -> dict[str, Any]:
    """Build a train-only statistical profile plus immutable split fingerprints."""
    dataset_root = dataset_root.resolve()
    split_manifests = {split: _split_manifest(dataset_root, split) for split in ("train", "val", "test")}
    train_images = split_images(dataset_root, "train")
    geometry_rows: list[dict[str, float]] = []
    image_geometry_rows: list[dict[str, float]] = []
    global_photo_rows: list[dict[str, float]] = []
    box_photo_rows: list[dict[str, float]] = []
    missing_labels: list[str] = []

    for image_path in train_images:
        label_path = label_path_for(dataset_root, "train", image_path)
        if not label_path.is_file():
            missing_labels.append(image_path.name)
        boxes = read_yolo_labels(label_path, missing_is_empty=True)
        image_geometry_rows.append(_image_geometry(boxes))
        geometry_rows.extend(_box_geometry(box, boxes) for box in boxes)
        image, luminance, hsv = _load_photo_arrays(image_path)
        global_photo_rows.append(_photo_metrics(luminance, hsv))
        for box in boxes:
            crop_luminance, crop_hsv = _box_crop(luminance, hsv, box)
            if crop_luminance.size:
                box_photo_rows.append(_photo_metrics(crop_luminance, crop_hsv))

    area_values = [row["bbox_area_ratio"] for row in geometry_rows]
    if not area_values:
        raise ValueError("Training split contains no valid boxes")
    area_quantiles = _quantiles(area_values)
    q33, q67 = _percentile(area_values, 1 / 3), _percentile(area_values, 2 / 3)
    profile = {
        "profile_version": PROFILE_VERSION,
        "dataset_root": str(dataset_root),
        "source_domain_metadata": {
            "status": "unknown_not_available",
            "reason": "No reliable laboratory/semi-field metadata was found; filenames were not used as a proxy.",
        },
        "split_policy": {
            "source_of_truth": "Dataset Original/IMAGENES and Dataset Original/LABELS",
            "train_only_augmentation_source": True,
            "val_augmented": False,
            "test_augmented": False,
            "test_holdout_status": "frozen_but_historically_consulted",
        },
        "splits": split_manifests,
        "train_missing_label_files_interpreted_as_empty": missing_labels,
        "geometry": {
            "box_count": len(geometry_rows),
            "image_count": len(image_geometry_rows),
            "box_metrics": _summarize_rows(geometry_rows),
            "image_metrics": _summarize_rows(image_geometry_rows),
            "bbox_area_ratio_quantiles": area_quantiles,
            "bbox_area_robust_range": [area_quantiles["p01"], area_quantiles["p99"]],
            "bbox_area_bands": {
                "definition": "empirical_train_tertiles",
                "small": [area_quantiles["min"], q33],
                "medium": [q33, q67],
                "large": [q67, area_quantiles["max"]],
            },
        },
        "photometry": {
            "global": _summarize_rows(global_photo_rows),
            "around_boxes": _summarize_rows(box_photo_rows),
            "acceptance_support": {
                "status": "engineering_heuristic",
                "global_mean_luminance_p01_p99": _range_from_rows(global_photo_rows, "mean_luminance"),
                "global_saturation_mean_p01_p99": _range_from_rows(global_photo_rows, "saturation_mean"),
                "global_local_contrast_p01_p99": _range_from_rows(global_photo_rows, "local_contrast"),
            },
        },
    }
    profile["profile_sha256"] = _payload_sha256(profile)
    return profile


def write_profile(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def read_profile(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("profile_sha256", None)
    actual = _payload_sha256(payload)
    payload["profile_sha256"] = expected
    if not expected or expected != actual:
        raise ValueError(f"Profile hash mismatch: {path}")
    return payload


def area_band(area_ratio: float, profile: dict[str, Any]) -> str:
    bands = profile["geometry"]["bbox_area_bands"]
    if area_ratio < float(bands["small"][1]):
        return "small"
    if area_ratio < float(bands["medium"][1]):
        return "medium"
    return "large"


def area_within_robust_train_range(area_ratio: float, profile: dict[str, Any]) -> bool:
    low, high = profile["geometry"]["bbox_area_robust_range"]
    return float(low) <= area_ratio <= float(high)


def photometry_within_train_support(metrics: dict[str, float], profile: dict[str, Any]) -> bool:
    support = profile["photometry"]["acceptance_support"]
    mappings = {
        "mean_luminance": "global_mean_luminance_p01_p99",
        "saturation_mean": "global_saturation_mean_p01_p99",
        "local_contrast": "global_local_contrast_p01_p99",
    }
    return all(float(support[key][0]) <= metrics[name] <= float(support[key][1]) for name, key in mappings.items())


def image_photometry(image) -> dict[str, float]:
    import cv2

    height, width = image.shape[:2]
    scale = min(1.0, 512.0 / max(height, width))
    working = (
        cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else image
    )
    lab = cv2.cvtColor(working, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(working, cv2.COLOR_BGR2HSV)
    return _photo_metrics(lab[:, :, 0].astype("float32") / 255.0, hsv)


def _split_manifest(dataset_root: Path, split: str) -> dict[str, Any]:
    images = split_images(dataset_root, split)
    records = []
    object_count = 0
    missing_labels = []
    fingerprint = hashlib.sha256()
    for image in images:
        label = label_path_for(dataset_root, split, image)
        boxes = read_yolo_labels(label, missing_is_empty=True)
        object_count += len(boxes)
        image_hash = file_sha256(image)
        label_hash = file_sha256(label) if label.is_file() else None
        if label_hash is None:
            missing_labels.append(image.name)
        record = {"image": image.name, "image_sha256": image_hash, "label": label.name, "label_sha256": label_hash, "object_count": len(boxes)}
        records.append(record)
        fingerprint.update(json.dumps(record, sort_keys=True).encode("utf-8"))
    return {
        "image_count": len(images),
        "object_count": object_count,
        "missing_label_count": len(missing_labels),
        "missing_labels": missing_labels,
        "fingerprint_sha256": fingerprint.hexdigest(),
        "members": records,
    }


def _box_geometry(box: YoloBox, peers: list[YoloBox]) -> dict[str, float]:
    x1, y1, x2, y2 = box.to_xyxy_normalized()
    overlaps = [pairwise_iou(box, other) for other in peers if other is not box]
    return {
        "bbox_area_ratio": box.area_ratio,
        "bbox_width_ratio": box.width,
        "bbox_height_ratio": box.height,
        "aspect_ratio": box.width / box.height,
        "distance_to_border": min(x1, y1, 1.0 - x2, 1.0 - y2),
        "overlap_between_boxes": max(overlaps, default=0.0),
    }


def _image_geometry(boxes: list[YoloBox]) -> dict[str, float]:
    overlaps = [pairwise_iou(boxes[i], boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]
    return {"objects_per_image": float(len(boxes)), "mean_pairwise_overlap": sum(overlaps) / len(overlaps) if overlaps else 0.0}


def _load_photo_arrays(path: Path):
    import cv2

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"OpenCV could not decode {path}")
    height, width = image.shape[:2]
    scale = min(1.0, 512.0 / max(height, width))
    if scale < 1.0:
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    return image, lab[:, :, 0].astype("float32") / 255.0, hsv


def _box_crop(luminance, hsv, box: YoloBox):
    height, width = luminance.shape[:2]
    x1, y1, x2, y2 = box.to_xyxy_pixels(width, height)
    return luminance[y1:y2, x1:x2], hsv[y1:y2, x1:x2]


def _photo_metrics(luminance, hsv) -> dict[str, float]:
    import cv2
    import numpy as np

    values = luminance.reshape(-1)
    blurred = cv2.GaussianBlur(luminance, (0, 0), 3.0)
    return {
        "mean_luminance": float(values.mean()),
        "luminance_std": float(values.std()),
        "percentile_05": float(np.percentile(values, 5)),
        "percentile_95": float(np.percentile(values, 95)),
        "saturation_mean": float(hsv[:, :, 1].mean() / 255.0),
        "local_contrast": float(np.mean(np.abs(luminance - blurred))),
    }


def _summarize_rows(rows: list[dict[str, float]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "metrics": {}}
    return {"count": len(rows), "metrics": {key: _quantiles([row[key] for row in rows]) for key in rows[0]}}


def _range_from_rows(rows: list[dict[str, float]], key: str) -> list[float]:
    values = [row[key] for row in rows]
    return [_percentile(values, 0.01), _percentile(values, 0.99)]


def _quantiles(values: Iterable[float]) -> dict[str, float]:
    materialized = sorted(float(value) for value in values)
    return {
        "min": materialized[0], "p01": _percentile(materialized, 0.01), "p05": _percentile(materialized, 0.05),
        "p10": _percentile(materialized, 0.10), "p25": _percentile(materialized, 0.25), "p50": _percentile(materialized, 0.50),
        "p75": _percentile(materialized, 0.75), "p90": _percentile(materialized, 0.90), "p95": _percentile(materialized, 0.95),
        "p99": _percentile(materialized, 0.99), "max": materialized[-1], "mean": sum(materialized) / len(materialized),
    }


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * fraction
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def _payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
