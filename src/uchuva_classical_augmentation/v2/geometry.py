"""Geometry-only recipes with label and size-distribution safeguards."""

from __future__ import annotations

import random
from typing import Any

from .labels import YoloBox
from .profiles import area_band, area_within_robust_train_range


def horizontal_flip(image, boxes: list[YoloBox]):
    import cv2

    return cv2.flip(image, 1), [box.horizontal_flip() for box in boxes]


def scale_preserving_crop(
    image,
    boxes: list[YoloBox],
    rng: random.Random,
    profile: dict[str, Any],
    *,
    crop_fraction_min: float = 0.82,
    crop_fraction_max: float = 0.96,
):
    """Try a moderate target-aware crop and reject out-of-support boxes."""
    import cv2

    if not boxes:
        return None
    height, width = image.shape[:2]
    for _ in range(24):
        target = rng.choice(boxes)
        crop_width = rng.uniform(crop_fraction_min, crop_fraction_max)
        crop_height = rng.uniform(crop_fraction_min, crop_fraction_max)
        jitter_x = rng.uniform(-0.08, 0.08) * crop_width
        jitter_y = rng.uniform(-0.08, 0.08) * crop_height
        center_x = min(max(target.x_center + jitter_x, crop_width / 2.0), 1.0 - crop_width / 2.0)
        center_y = min(max(target.y_center + jitter_y, crop_height / 2.0), 1.0 - crop_height / 2.0)
        window = (
            center_x - crop_width / 2.0,
            center_y - crop_height / 2.0,
            center_x + crop_width / 2.0,
            center_y + crop_height / 2.0,
        )
        transformed = [candidate for box in boxes if (candidate := box.crop(window, min_visible=0.55)) is not None]
        if not transformed or not all(area_within_robust_train_range(box.area_ratio, profile) for box in transformed):
            continue
        x1, y1, x2, y2 = window
        pixel_window = (round(x1 * width), round(y1 * height), round(x2 * width), round(y2 * height))
        px1, py1, px2, py2 = pixel_window
        crop = image[py1:py2, px1:px2]
        if crop.size == 0:
            continue
        output = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LINEAR)
        before = [box.area_ratio for box in boxes]
        after = [box.area_ratio for box in transformed]
        return output, transformed, {
            "crop_window": window,
            "pixel_crop_window": pixel_window,
            "resize_factor": (1.0 / crop_width, 1.0 / crop_height),
            "bbox_area_before": before,
            "bbox_area_after": after,
            "bands_before": [area_band(value, profile) for value in before],
            "bands_after": [area_band(value, profile) for value in after],
            "objects_before": len(boxes),
            "objects_after": len(transformed),
            "border_truncation_rate_before": _border_contact_rate(boxes),
            "border_truncation_rate_after": _border_contact_rate(transformed),
            "status": "accepted",
        }
    return None


def band_rates(boxes: list[YoloBox], profile: dict[str, Any]) -> dict[str, float]:
    counts = {"small": 0, "medium": 0, "large": 0}
    for box in boxes:
        counts[area_band(box.area_ratio, profile)] += 1
    total = max(len(boxes), 1)
    return {name: value / total for name, value in counts.items()}


def band_rate_delta_percentage_points(reference: list[YoloBox], candidate: list[YoloBox], profile: dict[str, Any]) -> dict[str, float]:
    first, second = band_rates(reference, profile), band_rates(candidate, profile)
    return {name: 100.0 * (second[name] - first[name]) for name in first}


def _border_contact_rate(boxes: list[YoloBox]) -> float:
    if not boxes:
        return 0.0
    count = 0
    for box in boxes:
        x1, y1, x2, y2 = box.to_xyxy_normalized()
        count += min(x1, y1, 1.0 - x2, 1.0 - y2) <= 1e-9
    return count / len(boxes)
