"""Operational confidence sweep and reproducible difficulty stratification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .labels import YoloBox, pairwise_iou
from .profiles import area_band


@dataclass(frozen=True)
class Prediction:
    box: YoloBox
    confidence: float


def confidence_sweep(ground_truth_by_image: dict[str, list[YoloBox]], predictions_by_image: dict[str, list[Prediction]], *, iou_threshold: float = 0.5) -> dict[str, Any]:
    confidences = sorted({prediction.confidence for values in predictions_by_image.values() for prediction in values}, reverse=True)
    thresholds = [1.0, *confidences, 0.0]
    rows = []
    for threshold in thresholds:
        rows.append(
            detection_metrics_at_confidence(
                ground_truth_by_image,
                predictions_by_image,
                confidence=threshold,
                iou_threshold=iou_threshold,
            )
        )
    feasible = [row for row in rows if row["precision"] >= 0.98 and row["tp"] > 0]
    if feasible:
        selected = max(feasible, key=lambda row: (row["recall"], -row["confidence"]))
        rule = "maximum_recall_subject_to_precision_ge_0.98"
    else:
        nonempty = [row for row in rows if row["tp"] > 0]
        selected = max(nonempty, key=lambda row: (row["precision"], row["recall"])) if nonempty else rows[0]
        rule = "no_point_at_precision_ge_0.98; maximum_precision_available"
    return {"selection_rule": rule, "selected": selected, "point_count": len(rows), "curve": rows}


def detection_metrics_at_confidence(
    ground_truth_by_image: dict[str, list[YoloBox]],
    predictions_by_image: dict[str, list[Prediction]],
    *,
    confidence: float,
    iou_threshold: float = 0.5,
) -> dict[str, float | int]:
    """Compute fixed-threshold detection metrics without selecting a threshold."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("Confidence must be within [0, 1].")
    tp = fp = fn = 0
    all_image_ids = set(ground_truth_by_image) | set(predictions_by_image)
    for image_id in all_image_ids:
        ground_truth = ground_truth_by_image.get(image_id, [])
        predictions = [
            item
            for item in predictions_by_image.get(image_id, [])
            if item.confidence >= confidence
        ]
        matched, unmatched_predictions = match_predictions(
            ground_truth, predictions, iou_threshold=iou_threshold
        )
        tp += len(matched)
        fp += len(unmatched_predictions)
        fn += len(ground_truth) - len(matched)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "confidence": confidence,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def match_predictions(ground_truth: list[YoloBox], predictions: list[Prediction], *, iou_threshold: float = 0.5):
    """Match detections by descending confidence, then best unmatched IoU.

    This mirrors the ordering used by standard detector evaluation. A global
    IoU-first greedy can give a low-confidence detection priority over a
    higher-confidence one and distort a confidence sweep.
    """
    used_truth = set()
    matches = []
    prediction_order = sorted(
        range(len(predictions)),
        key=lambda index: (-predictions[index].confidence, index),
    )
    for prediction_index in prediction_order:
        prediction = predictions[prediction_index]
        candidates = [
            (pairwise_iou(prediction.box, truth), truth_index)
            for truth_index, truth in enumerate(ground_truth)
            if truth_index not in used_truth
        ]
        candidates = [item for item in candidates if item[0] >= iou_threshold]
        if not candidates:
            continue
        iou, truth_index = max(candidates, key=lambda item: (item[0], -item[1]))
        used_truth.add(truth_index)
        matches.append({"prediction_index": prediction_index, "truth_index": truth_index, "iou": iou, "confidence": prediction.confidence})
    matched_predictions = {item["prediction_index"] for item in matches}
    unmatched = [prediction for index, prediction in enumerate(predictions) if index not in matched_predictions]
    return matches, unmatched


def stratified_recall(
    ground_truth_by_image: dict[str, list[YoloBox]],
    predictions_by_image: dict[str, list[Prediction]],
    profile: dict[str, Any],
    *,
    confidence: float,
    iou_threshold: float = 0.5,
) -> dict[str, Any]:
    strata: dict[str, dict[str, int]] = {}
    image_quantiles = profile["geometry"]["image_metrics"]["metrics"]["objects_per_image"]
    count_low, count_high = float(image_quantiles["p33"] if "p33" in image_quantiles else image_quantiles["p25"]), float(image_quantiles["p67"] if "p67" in image_quantiles else image_quantiles["p75"])
    for image_id, truths in ground_truth_by_image.items():
        predictions = [item for item in predictions_by_image.get(image_id, []) if item.confidence >= confidence]
        matches, _ = match_predictions(truths, predictions, iou_threshold=iou_threshold)
        matched_truth = {item["truth_index"] for item in matches}
        count_band = "low" if len(truths) <= count_low else "medium" if len(truths) <= count_high else "high"
        for index, box in enumerate(truths):
            x1, y1, x2, y2 = box.to_xyxy_normalized()
            overlapping = any(pairwise_iou(box, other) > 0.05 for other_index, other in enumerate(truths) if other_index != index)
            labels = (
                f"size:{area_band(box.area_ratio, profile)}",
                f"object_count:{count_band}",
                f"border_contact:{min(x1, y1, 1.0 - x2, 1.0 - y2) <= 0.01}",
                f"clustered:{overlapping}",
            )
            for label in labels:
                bucket = strata.setdefault(label, {"ground_truth": 0, "true_positive": 0, "false_negative": 0})
                bucket["ground_truth"] += 1
                if index in matched_truth:
                    bucket["true_positive"] += 1
                else:
                    bucket["false_negative"] += 1
    for bucket in strata.values():
        bucket["recall"] = bucket["true_positive"] / bucket["ground_truth"] if bucket["ground_truth"] else 0.0
    return {
        "thresholds": {"border_contact_normalized": 0.01, "cluster_iou": 0.05, "status": "engineering_heuristic"},
        "strata": strata,
    }
