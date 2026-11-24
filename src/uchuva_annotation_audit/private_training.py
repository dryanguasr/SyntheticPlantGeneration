"""Private real-image training batches and uncertainty-aware YOLO26 losses.

The versioned annotations remain independent native RLE masks. Projection to
the model grid is a training target, never a replacement for an annotation.
"""

from functools import lru_cache
import random

import cv2
import numpy as np
import torch
from torch.nn import functional as F
from torch.utils.data import Dataset
from ultralytics.utils.loss import v8SegmentationLoss
from ultralytics.utils.ops import crop_mask
from ultralytics.utils.tal import make_anchors

from .masks import checked_runs, decode_mask, mask_bbox
from .store import read


def sampling_order(count, seed, exposures):
    """Shuffle complete passes from a seed before taking the last prefix."""
    if count <= 0 or exposures < count:
        raise ValueError("Every image must be exposed at least once")
    rng = random.Random(seed)
    order = []
    while len(order) < exposures:
        cycle = list(range(count))
        rng.shuffle(cycle)
        order.extend(cycle)
    return order[:exposures]


def pair_supervision(order, fully_uncertain):
    """Keep exposure counts while placing no two fully ignored photos together."""
    order = list(order)
    uncertain_pairs = []
    resolved_pairs = []
    for slot in range(0, len(order), 2):
        left, right = order[slot:slot+2]
        if left in fully_uncertain and right in fully_uncertain:
            uncertain_pairs.append(slot+1)
        elif left not in fully_uncertain and right not in fully_uncertain:
            resolved_pairs.append(slot+1)
    if len(uncertain_pairs) > len(resolved_pairs):
        raise ValueError('Too many fully uncertain exposures for 4,000 supervised batches')
    for a,b in zip(uncertain_pairs, resolved_pairs):
        order[a], order[b] = order[b], order[a]
    return order


def project_mask(segmentation, width, height, left, top, fitted, size, ratio):
    """A grid cell with any positive visible area stays positive."""
    checked_runs(segmentation, width, height)
    binary = np.asarray(decode_mask(segmentation), dtype=np.float32)
    resized = cv2.resize(binary, fitted, interpolation=cv2.INTER_AREA)
    canvas = np.zeros((size, size), dtype=np.float32)
    canvas[top:top + fitted[1], left:left + fitted[0]] = resized
    return cv2.resize(canvas, (size // ratio, size // ratio), interpolation=cv2.INTER_AREA) > 0


class PrivateDataset(Dataset):
    """Deterministic letterbox, native-instance masks, and an explicit ignore grid."""

    def __init__(self, rows, order, seed, size=960, ratio=4):
        if size < 32 or size % 32 or size % ratio:
            raise ValueError("Unsupported model/target grid")
        self.rows = rows
        self.order = order
        self.seed = seed
        self.size = size
        self.ratio = ratio
        # Bounded cache of unaugmented data. A large real bank still decodes on demand.
        self.original = lru_cache(maxsize=24)(self._prepare)

    def __len__(self):
        return len(self.order)

    def _prepare(self, index):
        row = self.rows[index]
        size, ratio = self.size, self.ratio
        width, height = row["width"], row["height"]
        data = np.fromfile(row["image"], dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR | cv2.IMREAD_IGNORE_ORIENTATION)
        if image is None or image.shape[:2] != (height, width):
            raise ValueError(f"Image dimensions changed: {row['id']}")
        annotation = read(row["annotation"])
        scalar = min(size / width, size / height)
        fitted = (round(width * scalar), round(height * scalar))
        left, top = (size - fitted[0]) // 2, (size - fitted[1]) // 2
        canvas = np.full((size, size, 3), 114, dtype=np.uint8)
        canvas[top:top + fitted[1], left:left + fitted[0]] = cv2.resize(
            image, fitted, interpolation=cv2.INTER_LINEAR
        )
        grid = size // ratio
        ignored = np.zeros((grid, grid), dtype=bool)
        positive_masks, classes, boxes = [], [], []
        scale_x, scale_y = fitted[0] / width / size, fitted[1] / height / size

        def project(segmentation):
            return project_mask(segmentation, width, height, left, top, fitted, size, ratio)

        for obj in annotation["objects"]:
            cls = obj["class_id"]
            segmentation = obj["segmentation"]
            projected = project(segmentation)
            x1, y1, x2, y2 = mask_bbox(segmentation)
            if "bbox" in obj and obj["bbox"] != [x1, y1, x2, y2]:
                raise ValueError(f"Box differs from native mask: {row['id']} / {obj['id']}")
            if cls is None:
                ignored |= projected
                continue
            if type(cls) is not int or not 0 <= cls < 3:
                raise ValueError(f"Unknown appearance class: {cls}")
            if not projected.any():
                raise ValueError(f"Positive mask disappeared at model resolution: {row['id']}")
            positive_masks.append(projected)
            classes.append(cls)
            boxes.append([
                (x1 + x2) * scale_x / 2 + left / size,
                (y1 + y2) * scale_y / 2 + top / size,
                (x2 - x1) * scale_x, (y2 - y1) * scale_y,
            ])

        for region in annotation.get("ignore_regions", []):
            ignored |= project(region)
        confirmed_empty = annotation.get("empty_confirmed") is True or annotation.get("verified_empty") is True
        if annotation.get("full_image_uncertain") is True:
            if positive_masks:
                raise ValueError(f"A fully uncertain image contains positive targets: {row['id']}")
            ignored.fill(True)
        elif not annotation["objects"] and not confirmed_empty and not annotation.get('ignore_regions'):
            ignored.fill(True)
        return (
            canvas,
            np.asarray(positive_masks, dtype=bool).reshape(-1, grid, grid),
            np.asarray(classes, dtype=np.int64),
            np.asarray(boxes, dtype=np.float32).reshape(-1, 4),
            ignored,
        )

    def __getitem__(self, slot):
        index = self.order[slot]
        canvas, masks, classes, boxes, ignored = self.original(index)
        rng = random.Random((self.seed << 32) | slot)
        flip, gain = rng.random() < .5, rng.uniform(.9, 1.1)
        if flip:
            canvas, masks, ignored = canvas[:, ::-1], masks[:, :, ::-1], ignored[:, ::-1]
            boxes = boxes.copy()
            boxes[:, 0] = 1 - boxes[:, 0]
        # Apply gain only to image pixels; native geometry is unchanged.
        lookup = np.clip(np.arange(256, dtype=np.float32) * gain, 0, 255).astype(np.uint8)
        rgb = lookup[canvas[:, :, ::-1]].transpose(2, 0, 1)
        return {
            "img": torch.from_numpy(np.ascontiguousarray(rgb)),
            "masks": torch.from_numpy(masks.copy(order="C")),
            "cls": torch.from_numpy(classes.reshape(-1, 1)),
            "bboxes": torch.from_numpy(boxes),
            "ignored": torch.from_numpy(np.ascontiguousarray(ignored)),
            "image_id": self.rows[index]["id"],
            "supervised": bool(len(classes) or not ignored.all()),
            "slot": slot,
            "flip": flip,
            "gain": gain,
        }


def collate_samples(rows):
    """Build independent targets. Entirely abstained photos have no model input."""
    active = [row for row in rows if row["supervised"]]
    if not active:
        return None
    return {
        "img": torch.stack([row["img"] for row in active]),
        "ignored": torch.stack([row["ignored"] for row in active]),
        "masks": torch.cat([row["masks"] for row in active]),
        "cls": torch.cat([row["cls"] for row in active]),
        "bboxes": torch.cat([row["bboxes"] for row in active]),
        "batch_idx": torch.cat([
            torch.full((len(row["cls"]),), index, dtype=torch.long)
            for index, row in enumerate(active)
        ]),
    }


def anchor_negative_exclusions(ignored, features, foreground):
    """Suppress negatives for cells touching an uncertain region."""
    grids = [
        F.adaptive_max_pool2d(ignored[:, None].float(), feature.shape[-2:]).flatten(1).bool()
        for feature in features
    ]
    return torch.cat(grids, dim=1) & ~foreground


def masked_instance_loss(logits, target, ignored, boxes):
    """Crop to the visible target box and mask uncertain negative pixels."""
    valid = (~ignored | target.bool()).float()
    # Include a grid cell that merely intersects a very small box.
    extent = torch.cat((boxes[:, :2].floor(), boxes[:, 2:].ceil()), dim=1)
    valid = crop_mask(valid, extent)
    error = F.binary_cross_entropy_with_logits(logits.float(), target.float(), reduction="none")
    return ((error * valid).sum((1, 2)) / valid.sum((1, 2)).clamp(min=1)).sum()


def masked_semantic_loss(logits, target, ignored):
    """BCE and Dice with all ambiguous negatives excluded from both terms."""
    logits, target = logits.float(), target.float()
    ignored = ignored[:, None]
    if logits.shape[-2:] != target.shape[-2:]:
        output_size = logits.shape[-2:]
        target = (F.adaptive_max_pool2d(target, output_size) > 0).float()
        ignored = F.adaptive_max_pool2d(ignored.float(), output_size).bool()
    valid = (~ignored | target.bool()).float()
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
    bce = (bce * valid).sum() / valid.sum().clamp(min=1)
    probability = logits.sigmoid() * valid
    intersection = (probability * target).sum((2, 3))
    union = probability.sum((2, 3)) + target.sum((2, 3))
    dice = 1 - (2 * intersection + 1) / (union + 1)
    eligible = valid.sum((2, 3)) > 0
    dice = (dice * eligible).sum() / eligible.sum().clamp(min=1)
    return (bce + dice) * .5


class PrivateSegmentationLoss(v8SegmentationLoss):
    """Pinned YOLO26 assignment and gains, with loss exclusions for abstentions."""

    def get_assigned_targets_and_loss(self, preds, batch):
        distributions = preds["boxes"].permute(0, 2, 1).contiguous().float()
        scores = preds["scores"].permute(0, 2, 1).contiguous().float()
        features = preds["feats"]
        anchors, strides = make_anchors(features, self.stride, .5)
        anchors, strides = anchors.float(), strides.float()
        image_size = scores.new_tensor(features[0].shape[-2:]) * self.stride[0]
        targets = torch.cat((batch["batch_idx"][:, None], batch["cls"], batch["bboxes"]), dim=1)
        targets = self.preprocess(targets, len(scores), image_size[[1, 0, 1, 0]])
        labels, boxes = targets.split((1, 4), dim=2)
        predicted_boxes = self.bbox_decode(anchors, distributions)
        _, target_boxes, target_scores, foreground, target_indices = self.assigner(
            scores.detach().sigmoid(), predicted_boxes.detach() * strides,
            anchors * strides, labels, boxes, boxes.sum(dim=2, keepdim=True).gt(0),
        )
        normalizer = target_scores.sum().clamp(min=1)
        excluded = anchor_negative_exclusions(batch["ignored"], features, foreground)
        cls = self.bce(scores, target_scores.float())
        if self.class_weights is not None:
            cls *= self.class_weights
        cls = cls.masked_fill(excluded[:, :, None], 0).sum() / normalizer
        box_loss, distribution_loss = predicted_boxes.sum() * 0, distributions.sum() * 0
        if foreground.any():
            box_loss, distribution_loss = self.bbox_loss(
                distributions, predicted_boxes, anchors, target_boxes / strides, target_scores,
                normalizer, foreground, image_size, strides,
            )
        components = torch.stack([
            box_loss * self.hyp.box, cls * self.hyp.cls, distribution_loss * self.hyp.dfl,
        ])
        return foreground, target_indices, target_boxes, image_size, components

    def loss(self, preds, batch):
        foreground, target_indices, boxes, size, detection = self.get_assigned_targets_and_loss(preds, batch)
        coefficients = preds["mask_coefficient"].permute(0, 2, 1)
        features = preds["proto"]
        proto, semantic = features if isinstance(features, tuple) else (features, None)
        masks, ignored = batch["masks"], batch["ignored"]
        if tuple(proto.shape[-2:]) != tuple(ignored.shape[-2:]):
            proto = F.interpolate(proto, ignored.shape[-2:], mode="bilinear", align_corners=False)
        grid_y, grid_x = ignored.shape[-2:]
        geometry_scale = size.new_tensor([grid_x, grid_y, grid_x, grid_y]) / size[[1, 0, 1, 0]]
        instance = proto.float().sum() * 0 + coefficients.float().sum() * 0
        targets = None if semantic is None else torch.zeros(
            (len(foreground), self.nc, grid_y, grid_x), dtype=torch.bool, device=ignored.device
        )
        for index, active in enumerate(foreground):
            local = batch["batch_idx"] == index
            local_masks = masks[local]
            if active.any():
                # Cast the logits for loss accumulation but limit peak memory
                # when an image contains many assigned anchors.
                for group in active.nonzero().flatten().split(24):
                    selected = target_indices[index, group]
                    logits = torch.einsum("in,nhw->ihw", coefficients[index, group], proto[index])
                    instance = instance + masked_instance_loss(
                        logits, local_masks[selected], ignored[index], boxes[index, group] * geometry_scale
                    )
            if targets is not None and len(local_masks):
                classes = batch["cls"][local, 0]
                for cls in range(self.nc):
                    targets[index, cls] = (local_masks & (classes == cls)[:, None, None]).any(dim=0)
        instance = instance / foreground.sum().clamp(min=1)
        semantic_loss = masked_semantic_loss(semantic, targets, ignored) if targets is not None else instance * 0
        components = torch.stack([
            detection[0], instance * self.hyp.box, detection[1], detection[2], semantic_loss * self.hyp.box,
        ])
        return components * len(foreground), dict(zip(self.loss_names, components.detach()))
