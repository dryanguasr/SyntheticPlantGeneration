"""Same-class cluster Copy-Paste based only on train images and GrabCut masks."""

from __future__ import annotations

import random
from dataclasses import asdict

from .labels import YoloBox, bbox_from_binary_mask, pairwise_iou
from .occlusion import GrabCutMaskError, estimate_object_mask
from .profiles import area_within_robust_train_range


def apply_cluster_copy_paste(target_image, target_boxes: list[YoloBox], donor_image, donor_boxes: list[YoloBox], rng: random.Random, profile):
    import cv2
    import numpy as np

    if not target_boxes or not donor_boxes:
        return None
    height, width = target_image.shape[:2]
    donor_box = rng.choice(donor_boxes)
    anchor_index = rng.randrange(len(target_boxes))
    anchor = target_boxes[anchor_index]
    if _vegetation_context_rate(target_image, anchor) < 0.30:
        return None
    try:
        donor_mask = estimate_object_mask(donor_image, donor_box)
    except GrabCutMaskError:
        return None
    dy, dx = np.nonzero(donor_mask)
    if len(dx) == 0:
        return None
    sx1, sx2, sy1, sy2 = int(dx.min()), int(dx.max()) + 1, int(dy.min()), int(dy.max()) + 1
    object_crop = donor_image[sy1:sy2, sx1:sx2]
    mask_crop = donor_mask[sy1:sy2, sx1:sx2]
    target_scale = rng.uniform(0.65, 0.92)
    pasted_width = max(8, round(anchor.width * width * target_scale))
    pasted_height = max(8, round(pasted_width * (object_crop.shape[0] / object_crop.shape[1])))
    if pasted_width >= width or pasted_height >= height:
        return None
    object_crop = cv2.resize(object_crop, (pasted_width, pasted_height), interpolation=cv2.INTER_LINEAR)
    mask_crop = cv2.resize(mask_crop, (pasted_width, pasted_height), interpolation=cv2.INTER_NEAREST)
    anchor_x, anchor_y = anchor.x_center * width, anchor.y_center * height
    for _ in range(30):
        angle = rng.uniform(0.0, 2.0 * np.pi)
        distance = rng.uniform(0.35, 0.75) * max(anchor.width * width, anchor.height * height)
        center_x = round(anchor_x + np.cos(angle) * distance)
        center_y = round(anchor_y + np.sin(angle) * distance)
        x1, y1 = center_x - pasted_width // 2, center_y - pasted_height // 2
        x2, y2 = x1 + pasted_width, y1 + pasted_height
        if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
            continue
        placed_mask = np.zeros((height, width), dtype=np.uint8)
        placed_mask[y1:y2, x1:x2] = mask_crop
        background_selection = mask_crop.astype(bool)
        for existing in target_boxes:
            ex1, ey1, ex2, ey2 = existing.to_xyxy_pixels(width, height)
            ix1, iy1, ix2, iy2 = max(x1, ex1), max(y1, ey1), min(x2, ex2), min(y2, ey2)
            if ix2 > ix1 and iy2 > iy1:
                background_selection[iy1 - y1 : iy2 - y1, ix1 - x1 : ix2 - x1] = False
        if not np.any(background_selection) or _vegetation_rate(target_image[y1:y2, x1:x2], background_selection.astype("uint8")) < 0.25:
            continue
        new_box = bbox_from_binary_mask(placed_mask, class_id=donor_box.class_id, image_width=width, image_height=height)
        if new_box is None or not area_within_robust_train_range(new_box.area_ratio, profile):
            continue
        overlap = pairwise_iou(new_box, anchor)
        if not 0.02 <= overlap <= 0.35:
            continue
        updated_boxes: list[YoloBox] = []
        changes = []
        valid = True
        for index, existing in enumerate(target_boxes):
            if pairwise_iou(new_box, existing) <= 0.0:
                updated_boxes.append(existing)
                continue
            try:
                existing_mask = estimate_object_mask(target_image, existing)
            except GrabCutMaskError:
                valid = False
                break
            visible_mask = np.logical_and(existing_mask, np.logical_not(placed_mask)).astype("uint8")
            visible_fraction = int(visible_mask.sum()) / max(int(existing_mask.sum()), 1)
            visible_box = bbox_from_binary_mask(visible_mask, class_id=existing.class_id, image_width=width, image_height=height)
            if visible_box is None or visible_fraction < 0.55:
                valid = False
                break
            updated_boxes.append(visible_box)
            changes.append(
                {
                    "index": index,
                    "visible_fraction_before": 1.0,
                    "visible_fraction_after": visible_fraction,
                    "old_bbox": asdict(existing),
                    "new_bbox": asdict(visible_box),
                }
            )
        if not valid:
            continue
        output = target_image.copy()
        adjusted = _match_luminance(object_crop, target_image[y1:y2, x1:x2], mask_crop)
        region = output[y1:y2, x1:x2].astype("float32")
        alpha = cv2.GaussianBlur(mask_crop.astype("float32"), (0, 0), 1.2)[:, :, None]
        output[y1:y2, x1:x2] = np.clip(adjusted.astype("float32") * alpha + region * (1.0 - alpha), 0, 255).astype("uint8")
        output_boxes = updated_boxes + [new_box]
        parameters = {
            "donor_bbox": asdict(donor_box),
            "anchor_index": anchor_index,
            "paste_window_pixels": [x1, y1, x2, y2],
            "pasted_scale_over_anchor_width": pasted_width / max(anchor.width * width, 1.0),
            "pairwise_iou_with_anchor": overlap,
            "luminance_adaptation": "masked_mean_ratio_clipped_0.85_1.15",
            "objects_before": len(target_boxes),
            "objects_after": len(output_boxes),
        }
        changes.append({"operation": "add_same_class_target", "new_bbox": asdict(new_box), "anchor_bbox": asdict(anchor)})
        return output, output_boxes, changes, parameters
    return None


def _match_luminance(source, destination, mask):
    import cv2
    import numpy as np

    source_gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    destination_gray = cv2.cvtColor(destination, cv2.COLOR_BGR2GRAY)
    selected = mask > 0
    source_mean = float(source_gray[selected].mean()) if np.any(selected) else 1.0
    destination_mean = float(destination_gray[selected].mean()) if np.any(selected) else source_mean
    gain = min(max(destination_mean / max(source_mean, 1.0), 0.85), 1.15)
    return np.clip(source.astype("float32") * gain, 0, 255).astype("uint8")


def _vegetation_context_rate(image, box: YoloBox) -> float:
    import numpy as np

    height, width = image.shape[:2]
    x1, y1, x2, y2 = box.to_xyxy_pixels(width, height)
    pad_x, pad_y = max(4, x2 - x1), max(4, y2 - y1)
    x1, x2 = max(0, x1 - pad_x), min(width, x2 + pad_x)
    y1, y2 = max(0, y1 - pad_y), min(height, y2 + pad_y)
    region = image[y1:y2, x1:x2]
    if region.size == 0:
        return 0.0
    ring = np.ones(region.shape[:2], dtype=np.uint8)
    original_x1, original_y1, original_x2, original_y2 = box.to_xyxy_pixels(width, height)
    ring[original_y1 - y1 : original_y2 - y1, original_x1 - x1 : original_x2 - x1] = 0
    return _vegetation_rate(region, ring)


def _vegetation_rate(image, mask) -> float:
    import cv2
    import numpy as np

    if image.size == 0:
        return 0.0
    b, g, r = cv2.split(image.astype("float32"))
    vegetation = (g > b * 1.03) & (g > r * 0.90)
    if mask is not None:
        selected = mask > 0
        return float(np.mean(vegetation[selected])) if np.any(selected) else 0.0
    return float(np.mean(vegetation))
