"""Visibility-consistent, object-aware occlusion using train-only textures."""

from __future__ import annotations

import random
from dataclasses import asdict
from typing import Any

from .labels import YoloBox, bbox_from_binary_mask


class GrabCutMaskError(ValueError):
    """Raised when an approximate fruit mask is not credible enough to use."""


def estimate_object_mask(image, box: YoloBox):
    """Estimate a single connected foreground mask inside ``box`` with GrabCut."""
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    x1, y1, x2, y2 = box.to_xyxy_pixels(width, height)
    if x2 - x1 < 8 or y2 - y1 < 8:
        raise GrabCutMaskError("bbox_too_small_for_grabcut")
    crop = image[y1:y2, x1:x2]
    crop_height, crop_width = crop.shape[:2]
    scale = min(1.0, 384.0 / max(crop_height, crop_width))
    working = (
        cv2.resize(crop, (max(8, round(crop_width * scale)), max(8, round(crop_height * scale))), interpolation=cv2.INTER_AREA)
        if scale < 1.0
        else crop
    )
    working_height, working_width = working.shape[:2]
    inset_x = max(1, round(working_width * 0.03))
    inset_y = max(1, round(working_height * 0.03))
    rect = (inset_x, inset_y, max(2, working_width - 2 * inset_x), max(2, working_height - 2 * inset_y))
    local_mask = np.zeros((working_height, working_width), dtype=np.uint8)
    background = np.zeros((1, 65), dtype=np.float64)
    foreground = np.zeros((1, 65), dtype=np.float64)
    try:
        cv2.grabCut(working, local_mask, rect, background, foreground, 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error as error:
        raise GrabCutMaskError("grabcut_opencv_failure") from error
    local_binary = ((local_mask == cv2.GC_FGD) | (local_mask == cv2.GC_PR_FGD)).astype(np.uint8)
    count, components, stats, _ = cv2.connectedComponentsWithStats(local_binary, 8)
    if count <= 1:
        raise GrabCutMaskError("grabcut_empty_mask")
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    local_binary = (components == largest).astype(np.uint8)
    if local_binary.shape != (crop_height, crop_width):
        local_binary = cv2.resize(local_binary, (crop_width, crop_height), interpolation=cv2.INTER_NEAREST)
    binary = np.zeros((height, width), dtype=np.uint8)
    binary[y1:y2, x1:x2] = local_binary
    pixels = int(local_binary.sum())
    box_pixels = max((x2 - x1) * (y2 - y1), 1)
    fraction = pixels / box_pixels
    if pixels < 80 or not 0.12 <= fraction <= 0.96:
        raise GrabCutMaskError(f"grabcut_implausible_mask_fraction:{fraction:.6f}")
    return binary


def apply_visibility_consistent_occlusion(
    image,
    boxes: list[YoloBox],
    donor_image,
    rng: random.Random,
    *,
    visible_fraction_min: float = 0.55,
    visible_fraction_max: float = 0.88,
):
    """Occlude one fruit and recompute every affected visible bounding box."""
    import cv2
    import numpy as np

    if not boxes:
        return None
    height, width = image.shape[:2]
    target_index = rng.randrange(len(boxes))
    if _vegetation_context_rate(image, boxes[target_index]) < 0.30:
        return None
    try:
        target_mask = estimate_object_mask(image, boxes[target_index])
    except GrabCutMaskError:
        return None
    target_pixels = int(target_mask.sum())
    ys, xs = np.nonzero(target_mask)
    for _ in range(24):
        center_pos = rng.randrange(len(xs))
        center = (int(xs[center_pos]), int(ys[center_pos]))
        x1, y1, x2, y2 = boxes[target_index].to_xyxy_pixels(width, height)
        radius_x = max(3, round((x2 - x1) * rng.uniform(0.22, 0.43)))
        radius_y = max(3, round((y2 - y1) * rng.uniform(0.14, 0.34)))
        occluder = _irregular_ellipse_mask((height, width), center, (radius_x, radius_y), rng)
        visible_fraction = int(np.logical_and(target_mask, np.logical_not(occluder)).sum()) / target_pixels
        if not visible_fraction_min <= visible_fraction <= visible_fraction_max:
            continue
        oy, ox = np.nonzero(occluder)
        ox1, ox2, oy1, oy2 = int(ox.min()), int(ox.max()) + 1, int(oy.min()), int(oy.max()) + 1
        local_mask = occluder[oy1:oy2, ox1:ox2].astype("float32")
        texture_patch = _vegetation_texture(donor_image, (oy2 - oy1, ox2 - ox1, 3), rng, local_mask)
        if texture_patch is None:
            return None
        output = image.copy()
        alpha = cv2.GaussianBlur(local_mask, (0, 0), 1.2)[:, :, None]
        target_region = output[oy1:oy2, ox1:ox2].astype("float32")
        blended = texture_patch.astype("float32") * alpha + target_region * (1.0 - alpha)
        output[oy1:oy2, ox1:ox2] = np.clip(blended, 0, 255).astype("uint8")
        output_boxes: list[YoloBox] = []
        changes: list[dict[str, Any]] = []
        valid = True
        for index, box in enumerate(boxes):
            bx1, by1, bx2, by2 = box.to_xyxy_pixels(width, height)
            if not np.any(occluder[by1:by2, bx1:bx2]):
                output_boxes.append(box)
                changes.append({"index": index, "visible_fraction_before": 1.0, "visible_fraction_after": 1.0, "old_bbox": asdict(box), "new_bbox": asdict(box)})
                continue
            try:
                original_mask = target_mask if index == target_index else estimate_object_mask(image, box)
            except GrabCutMaskError:
                valid = False
                break
            visible = np.logical_and(original_mask, np.logical_not(occluder)).astype("uint8")
            fraction = int(visible.sum()) / max(int(original_mask.sum()), 1)
            new_box = bbox_from_binary_mask(visible, class_id=box.class_id, image_width=width, image_height=height)
            if new_box is None or fraction < visible_fraction_min:
                valid = False
                break
            output_boxes.append(new_box)
            changes.append({"index": index, "visible_fraction_before": 1.0, "visible_fraction_after": fraction, "old_bbox": asdict(box), "new_bbox": asdict(new_box)})
        if valid:
            return output, output_boxes, changes, {
                "target_index": target_index,
                "visible_fraction_after": visible_fraction,
                "occluder_pixel_count": int(occluder.sum()),
                "occluder_source": "train_only_vegetation_patch",
                "opacity": 1.0,
                "edge_softening": "gaussian_sigma_1.2_px; opaque_core",
            }
    return None


def _irregular_ellipse_mask(shape: tuple[int, int], center: tuple[int, int], radii: tuple[int, int], rng: random.Random):
    import cv2
    import numpy as np

    height, width = shape
    points = []
    count = 12
    for index in range(count):
        angle = 2.0 * np.pi * index / count
        jitter = rng.uniform(0.72, 1.18)
        x = round(center[0] + np.cos(angle) * radii[0] * jitter)
        y = round(center[1] + np.sin(angle) * radii[1] * jitter)
        points.append((min(max(x, 0), width - 1), min(max(y, 0), height - 1)))
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.asarray(points, dtype=np.int32)], 1)
    return mask


def _vegetation_texture(donor, target_shape: tuple[int, int, int], rng: random.Random, selection_mask):
    import cv2
    import numpy as np

    target_height, target_width = target_shape[:2]
    donor_height, donor_width = donor.shape[:2]
    for _ in range(20):
        patch_width = max(16, round(target_width * rng.uniform(0.8, 1.6)))
        patch_height = max(16, round(target_height * rng.uniform(0.8, 1.6)))
        if patch_width > donor_width or patch_height > donor_height:
            continue
        x = rng.randrange(0, donor_width - patch_width + 1)
        y = rng.randrange(0, donor_height - patch_height + 1)
        patch = donor[y : y + patch_height, x : x + patch_width]
        b, g, r = cv2.split(patch.astype("float32"))
        vegetation_rate = float(np.mean((g > b * 1.03) & (g > r * 0.90)))
        texture_std = float(patch.std())
        if vegetation_rate >= 0.55 and texture_std >= 8.0:
            resized = cv2.resize(patch, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
            selected = selection_mask > 0
            rb, rg, rr = cv2.split(resized.astype("float32"))
            selected_vegetation = (rg > rb * 1.03) & (rg > rr * 0.90)
            selected_rate = float(np.mean(selected_vegetation[selected])) if np.any(selected) else 0.0
            selected_luminance = float(cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)[selected].mean()) if np.any(selected) else 0.0
            if selected_rate >= 0.60 and 35.0 <= selected_luminance <= 220.0:
                return resized
    return None


def _vegetation_context_rate(image, box: YoloBox) -> float:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    x1, y1, x2, y2 = box.to_xyxy_pixels(width, height)
    pad_x, pad_y = max(4, x2 - x1), max(4, y2 - y1)
    rx1, rx2 = max(0, x1 - pad_x), min(width, x2 + pad_x)
    ry1, ry2 = max(0, y1 - pad_y), min(height, y2 + pad_y)
    region = image[ry1:ry2, rx1:rx2]
    if region.size == 0:
        return 0.0
    ring = np.ones(region.shape[:2], dtype=bool)
    ring[y1 - ry1 : y2 - ry1, x1 - rx1 : x2 - rx1] = False
    b, g, r = cv2.split(region.astype("float32"))
    vegetation = (g > b * 1.03) & (g > r * 0.90)
    return float(np.mean(vegetation[ring])) if np.any(ring) else 0.0
