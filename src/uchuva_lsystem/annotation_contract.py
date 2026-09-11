"""Versioned observation sidecar; no inferred real fruit maturity or YOLO relabeling."""

from __future__ import annotations

import math
from typing import Any

OBSERVATION_SCHEMA = "uchuva.instance_observation/0.1"
CALYX_APPEARANCES = (
    "inflated_green", "transitioning_yellow", "straw_yellow", "dry_deteriorated",
)


def mask_visibility_metrics(
    visible_pixels: int, bbox_area: int, *, isolated_pixels: int | None = None,
) -> dict[str, float | None]:
    """Separate mask occupancy in its box from occlusion of an isolated silhouette.

    isolated_pixels must use the same camera, geometry and clipping, with other
    objects hidden. This estimates inter-object occlusion inside the frame only.
    A round unoccluded silhouette does not fill its rectangular bounding box.
    """
    if type(visible_pixels) is not int or type(bbox_area) is not int:
        raise ValueError("Pixel counts must be integers.")
    if visible_pixels < 0 or bbox_area < visible_pixels:
        raise ValueError("Require 0 <= visible_pixels <= bbox_area.")
    if isolated_pixels is not None:
        if type(isolated_pixels) is not int or isolated_pixels < visible_pixels or isolated_pixels <= 0:
            raise ValueError("Isolated silhouette must be positive and contain visible pixels.")
    return {
        "mask_fill_ratio": visible_pixels / bbox_area if bbox_area else None,
        "occluded_fraction_in_frame": (
            1.0 - visible_pixels / isolated_pixels if isolated_pixels is not None else None
        ),
    }


def instance_observation(item: dict[str, Any], *, source_domain: str) -> dict[str, Any]:
    """Build a review record from an existing detection, leaving human labels empty."""
    if source_domain not in {"synthetic", "real"}:
        raise ValueError("source_domain must be synthetic or real.")
    instance_id = str(item.get("instance_id", ""))
    if not instance_id:
        raise ValueError("A stable instance_id is required.")
    box = item.get("bbox_xywh")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("Expected pixel bbox_xywh.")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in box) or min(box[2:]) <= 0:
        raise ValueError("Bounding box must be finite with positive width and height.")
    state = item.get("calyx_state")
    if source_domain == "synthetic" and state not in CALYX_APPEARANCES:
        raise ValueError("Unknown synthetic calyx state; do not silently assign a class.")
    metrics = {"mask_fill_ratio": None, "occluded_fraction_in_frame": None}
    if source_domain == "synthetic" and "visible_pixels" in item:
        metrics = mask_visibility_metrics(item["visible_pixels"], int(box[2] * box[3]))
    return {
        "schema_version": OBSERVATION_SCHEMA,
        "instance_id": instance_id,
        "source_domain": source_domain,
        "bbox_xywh": list(box),
        "bbox_convention": "visible_mask_extent" if source_domain == "synthetic" else "source_annotation_unverified",
        "synthetic_appearance_candidate": state if source_domain == "synthetic" else None,
        "observed_calyx_appearance": None,
        "agronomic_maturity": None,
        "review_status": "pending",
        "training_class_id": None,
        "truncated": bool(item.get("truncated", False)),
        **metrics,
    }
