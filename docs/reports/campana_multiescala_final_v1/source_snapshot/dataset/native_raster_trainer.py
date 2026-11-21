"""Versioned raster loader for the multiscale campaign; native train augmentation.

Derived from the frozen pilot's train_raster_segmentation.py. Canonical instance
rasters remain the label source; no contour conversion or frozen-file edits.
"""
from copy import copy
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import torch
from ultralytics.models.yolo.segment import SegmentationTrainer, SegmentationValidator

CAMPAIGN = Path(__file__).resolve().parent
REPOSITORY = CAMPAIGN.parents[1]
FROZEN_ROOT = CAMPAIGN.parent / "frozen_field_pilot_20261019" / "frozen"
sys.path.insert(0, str(FROZEN_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY / "scripts"))
from multiscale_native_augmentation import NativeAugmentationConfig, augment_raster_sample

_spec = importlib.util.spec_from_file_location(
    "multiscale_frozen_raster_base", FROZEN_ROOT / "scripts/train_raster_segmentation.py")
_frozen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_frozen)
coverage_masks = _frozen.coverage_masks

VERSION = "multiscale-native-raster-trainer/1"


class RasterDataset(_frozen.RasterDataset):
    """Historical exact-raster contract with native transforms before resizing."""

    def __init__(self, root, split, size, augment=False, ratio=2,
                 supervision_policy="legacy_nearest", native_config=None):
        if split != "train" and augment:
            raise ValueError("Augmentation is permitted only in training")
        super().__init__(root, split, size, augment, ratio, supervision_policy)
        for label in self.labels:
            label["cls"] = label["cls"].reshape(-1, 1)
        self.native_config = native_config or NativeAugmentationConfig()
        self.last_augmentation_trace = None
        self.native_call_counts = {"RandomHSV": 0, "RandomFlip": 0, "samples": 0}

    def __getitem__(self, index):
        row = self.rows[index]
        size = self.imgsz
        image = cv2.imread(str(self.root / row["image"]))
        if image is None:
            raise ValueError("Missing RGB image")
        h, w = image.shape[:2]
        mask = cv2.imread(str(self.root / row["mask"]), cv2.IMREAD_UNCHANGED)
        if mask is not None and mask.ndim == 3 and mask.shape[2] == 1:
            mask = mask[:, :, 0]
        if mask is None or mask.shape != (h, w):
            raise ValueError("Missing/misaligned exact raster")
        boxes = self.labels[index]["bboxes"].copy()
        native = augment_raster_sample(
            image, mask, boxes, mask_ids=[x["mask_id"] for x in row["instances"]],
            training=self.augment, config=self.native_config)
        image, mask, boxes = native.image_bgr, native.instance_raster, native.bboxes_xywh
        self.last_augmentation_trace = native.trace
        self.native_call_counts["samples"] += 1
        for method in native.trace["native_calls"]:
            self.native_call_counts[method] += 1

        scale = min(size / w, size / h)
        nw, nh = round(w * scale), round(h * scale)
        left, top = (size - nw) // 2, (size - nh) // 2
        canvas = np.full((size, size, 3), 114, np.uint8)
        canvas[top:top + nh, left:left + nw] = cv2.resize(
            image, (nw, nh), interpolation=cv2.INTER_LINEAR)
        mask_canvas = np.zeros((size, size), np.uint16)
        mask_canvas[top:top + nh, left:left + nw] = cv2.resize(
            mask, (nw, nh), interpolation=cv2.INTER_NEAREST)
        boxes[:, 0] = (boxes[:, 0] * w * scale + left) / size
        boxes[:, 1] = (boxes[:, 1] * h * scale + top) / size
        boxes[:, 2] *= w * scale / size
        boxes[:, 3] *= h * scale / size

        small = cv2.resize(mask_canvas, (size // self.ratio, size // self.ratio),
                           interpolation=cv2.INTER_NEAREST)
        masks = np.asarray([small == x["mask_id"] for x in row["instances"]],
                           dtype=np.uint8).reshape(-1, *small.shape)
        if self.supervision_policy == "any_coverage":
            # Raster already transformed natively; no second horizontal flip.
            masks = coverage_masks(mask, row["instances"], size, self.ratio, flipped=False)
        semantic = np.zeros(small.shape, np.float32)
        if self.supervision_policy == "any_coverage":
            for i in sorted(range(len(row["instances"])),
                            key=lambda j: row["instances"][j]["mask_id"], reverse=True):
                semantic[masks[i].astype(bool)] = row["instances"][i]["class_id"]
        else:
            for item in row["instances"]:
                semantic[small == item["mask_id"]] = item["class_id"]
        return dict(
            img=torch.from_numpy(canvas[:, :, ::-1].transpose(2, 0, 1).copy()),
            cls=torch.tensor([[x["class_id"]] for x in row["instances"]],
                             dtype=torch.float32).reshape(-1, 1),
            bboxes=torch.from_numpy(boxes), masks=torch.from_numpy(masks),
            sem_masks=torch.from_numpy(semantic), batch_idx=torch.zeros(len(boxes)),
            im_file=str(self.root / row["image"]), ori_shape=(h, w),
            resized_shape=(size, size), ratio_pad=((scale, scale), (left, top)))


def _native_config(args):
    return NativeAugmentationConfig(**{key: getattr(args, key)
                                      for key in NativeAugmentationConfig.__dataclass_fields__})


class RasterValidator(SegmentationValidator):
    def build_dataset(self, img_path, mode="val", batch=None):
        return RasterDataset(self.data["path"], "val", self.args.imgsz, False,
                             self.args.mask_ratio)


class CoverageRasterTrainer(SegmentationTrainer):
    def build_dataset(self, img_path, mode="train", batch=None):
        return RasterDataset(self.data["path"], mode, self.args.imgsz, mode == "train",
                             self.args.mask_ratio,
                             "any_coverage" if mode == "train" else "legacy_nearest",
                             _native_config(self.args))

    def get_validator(self):
        return RasterValidator(self.test_loader, save_dir=self.save_dir,
                               args=copy(self.args), _callbacks=self.callbacks)
