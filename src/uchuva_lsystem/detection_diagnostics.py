"""Deterministic, validation-only detector error decomposition."""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


Box = tuple[float, float, float, float]


def box_iou(left: Box, right: Box) -> float:
    lx0, ly0, lx1, ly1 = _corners(left)
    rx0, ry0, rx1, ry1 = _corners(right)
    intersection = max(0.0, min(lx1, rx1) - max(lx0, rx0)) * max(
        0.0, min(ly1, ry1) - max(ly0, ry0)
    )
    union = left[2] * left[3] + right[2] * right[3] - intersection
    return intersection / union if union > 0.0 else 0.0


def deterministic_iou_match(
    ground_truth: list[Box],
    predictions: list[dict[str, Any]],
    *,
    threshold: float = 0.50,
) -> dict[str, Any]:
    """Greedily match highest-IoU pairs with stable index tie-breaks."""
    candidates = []
    for gt_index, gt_box in enumerate(ground_truth):
        for prediction_index, prediction in enumerate(predictions):
            iou = box_iou(gt_box, tuple(prediction["box"]))
            if iou >= threshold:
                candidates.append((-iou, gt_index, prediction_index))
    candidates.sort()
    used_gt: set[int] = set()
    used_predictions: set[int] = set()
    matches = []
    for negative_iou, gt_index, prediction_index in candidates:
        if gt_index in used_gt or prediction_index in used_predictions:
            continue
        used_gt.add(gt_index)
        used_predictions.add(prediction_index)
        matches.append(
            {
                "gt_index": gt_index,
                "prediction_index": prediction_index,
                "iou": round(-negative_iou, 8),
            }
        )
    return {
        "matches": matches,
        "unmatched_gt": [
            index for index in range(len(ground_truth)) if index not in used_gt
        ],
        "unmatched_predictions": [
            index for index in range(len(predictions)) if index not in used_predictions
        ],
    }


def analyze_image_errors(
    ground_truth: list[Box],
    predictions: list[dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    mean_luminance: float,
) -> dict[str, Any]:
    matched = deterministic_iou_match(ground_truth, predictions)
    gt_events: list[dict[str, Any]] = []
    fp_events: list[dict[str, Any]] = []
    match_by_gt = {item["gt_index"]: item for item in matched["matches"]}
    object_count_band = _object_count_band(len(ground_truth))
    image_orientation = _orientation(image_width, image_height)
    luminance_band = _luminance_band(mean_luminance)
    for gt_index, gt_box in enumerate(ground_truth):
        common = _box_groups(gt_box)
        common.update(
            {
                "object_count_band": object_count_band,
                "image_orientation": image_orientation,
                "luminance_band": luminance_band,
                "mean_luminance": round(mean_luminance, 3),
            }
        )
        if gt_index in match_by_gt:
            match = match_by_gt[gt_index]
            prediction = predictions[match["prediction_index"]]
            iou = float(match["iou"])
            common.update(
                {
                    "outcome": "true_positive_iou_ge_075" if iou >= 0.75 else "localized_iou_050_075",
                    "iou": iou,
                    "confidence": float(prediction.get("confidence", 0.0)),
                    **_relative_localization_errors(gt_box, tuple(prediction["box"])),
                }
            )
        else:
            best_iou = max(
                (box_iou(gt_box, tuple(prediction["box"])) for prediction in predictions),
                default=0.0,
            )
            common.update(
                {
                    "outcome": "localization_error_iou_010_050" if best_iou >= 0.10 else "false_negative_absent",
                    "iou": round(best_iou, 8),
                }
            )
        gt_events.append(common)
    for prediction_index in matched["unmatched_predictions"]:
        prediction = predictions[prediction_index]
        prediction_box = tuple(prediction["box"])
        best_iou = max(
            (box_iou(prediction_box, gt_box) for gt_box in ground_truth),
            default=0.0,
        )
        common = _box_groups(prediction_box)
        common.update(
            {
                "object_count_band": object_count_band,
                "image_orientation": image_orientation,
                "luminance_band": luminance_band,
                "mean_luminance": round(mean_luminance, 3),
                "outcome": "unmatched_localization_or_duplicate" if best_iou >= 0.10 else "false_positive_background",
                "iou": round(best_iou, 8),
                "confidence": float(prediction.get("confidence", 0.0)),
            }
        )
        fp_events.append(common)
    return {"ground_truth_events": gt_events, "false_positive_events": fp_events}


def aggregate_error_report(
    image_reports: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    gt_events = [
        event
        for report in image_reports
        for event in report["ground_truth_events"]
    ]
    fp_events = [
        event
        for report in image_reports
        for event in report["false_positive_events"]
    ]
    outcome_counts = Counter(event["outcome"] for event in gt_events + fp_events)
    grouped: dict[str, Any] = {}
    for dimension in (
        "area_band",
        "boundary_contact",
        "box_orientation",
        "image_orientation",
        "object_count_band",
        "luminance_band",
    ):
        dimension_groups: dict[str, Counter[str]] = defaultdict(Counter)
        for event in gt_events:
            dimension_groups[str(event[dimension])][str(event["outcome"])] += 1
        grouped[dimension] = {
            key: dict(sorted(counts.items()))
            for key, counts in sorted(dimension_groups.items())
        }
    matched_events = [event for event in gt_events if event["outcome"].startswith(("true_positive", "localized"))]
    return {
        "ground_truth_count": len(gt_events),
        "unmatched_prediction_count": len(fp_events),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "localization_error_quantiles": {
            key: _quantiles(
                event[key]
                for event in matched_events
                if key in event
            )
            for key in (
                "center_error_x_relative",
                "center_error_y_relative",
                "width_error_relative",
                "height_error_relative",
            )
        },
        "groups": grouped,
    }


def validate_real_val_only(image_paths: Iterable[str | Path]) -> list[Path]:
    paths = [Path(path).resolve() for path in image_paths]
    if len(paths) != 133:
        raise ValueError(f"Expected exactly 133 validation images; found {len(paths)}.")
    for path in paths:
        normalized = str(path).lower().replace("\\", "/")
        if "/images/val/" not in normalized:
            raise ValueError(f"Non-validation image in diagnostic: {path}")
        if "synthetic" in path.stem.lower() or not path.stem.lower().startswith("real_val_"):
            raise ValueError(f"Non-real validation image in diagnostic: {path}")
        if "/test/" in normalized:
            raise ValueError(f"Test image is forbidden in detector diagnostic: {path}")
    if len({path.name for path in paths}) != len(paths):
        raise ValueError("Duplicate validation image names detected.")
    return sorted(paths)


def selection_pairs(selection_lock: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(selection_lock).read_text(encoding="utf-8"))
    if payload.get("selection_split") != "val" or payload.get("selection_domain") != "real_only":
        raise ValueError("Selection lock is not real-only validation.")
    baseline = {int(item["seed"]): item for item in payload["baseline"]}
    selected = {int(item["seed"]): item for item in payload["selected"]}
    if set(baseline) != set(selected):
        raise ValueError("Baseline and selected checkpoints do not share seeds.")
    return [
        {
            "seed": seed,
            "baseline": baseline[seed],
            "selected": selected[seed],
        }
        for seed in sorted(baseline)
    ]


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _box_groups(box: Box) -> dict[str, Any]:
    x, y, width, height = box
    area = width * height
    boundary = (
        x - width / 2.0 <= 1e-7
        or y - height / 2.0 <= 1e-7
        or x + width / 2.0 >= 1.0 - 1e-7
        or y + height / 2.0 >= 1.0 - 1e-7
    )
    return {
        "area_band": (
            "under_one_percent"
            if area < 0.01
            else "one_to_five_percent"
            if area < 0.05
            else "at_least_five_percent"
        ),
        "boundary_contact": "boundary" if boundary else "interior",
        "box_orientation": _orientation(width, height),
    }


def _relative_localization_errors(gt: Box, prediction: Box) -> dict[str, float]:
    return {
        "center_error_x_relative": round(abs(prediction[0] - gt[0]) / max(gt[2], 1e-9), 8),
        "center_error_y_relative": round(abs(prediction[1] - gt[1]) / max(gt[3], 1e-9), 8),
        "width_error_relative": round((prediction[2] - gt[2]) / max(gt[2], 1e-9), 8),
        "height_error_relative": round((prediction[3] - gt[3]) / max(gt[3], 1e-9), 8),
    }


def _corners(box: Box) -> tuple[float, float, float, float]:
    x, y, width, height = box
    return (x - width / 2.0, y - height / 2.0, x + width / 2.0, y + height / 2.0)


def _object_count_band(count: int) -> str:
    if count <= 1:
        return "one"
    if count <= 5:
        return "two_to_five"
    if count <= 10:
        return "six_to_ten"
    return "more_than_ten"


def _luminance_band(value: float) -> str:
    if value < 85.0:
        return "low_lt_85"
    if value <= 170.0:
        return "mid_85_170"
    return "high_gt_170"


def _orientation(width: float, height: float) -> str:
    if width > height:
        return "landscape"
    if height > width:
        return "portrait"
    return "square"


def _quantiles(values: Iterable[float]) -> dict[str, float | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {key: None for key in ("p25", "p50", "p75", "p90")}
    return {
        key: round(ordered[round((len(ordered) - 1) * position)], 8)
        for key, position in (("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90))
    }
