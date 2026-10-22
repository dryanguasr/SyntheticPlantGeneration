"""Native Ultralytics augmentation of RGB plus exact instance-ID rasters.

This adapter deliberately uses a small subset of the installed native transforms.
The raster travels through RandomFlip's semantic-mask channel, which only permutes
pixels. It is NOT a semantic class map and is never converted to polygons. Call
before downsampling supervision masks; the caller retains class/ID associations.

Only training samples are augmented. Canonical rasters and evaluation truth remain
unchanged. This is a new adapter, not a modification to historical frozen loaders.
"""

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np
import ultralytics
from ultralytics.data.augment import RandomFlip, RandomHSV
from ultralytics.utils.instance import Instances


VERSION = "multiscale-native-augmentation/1"


@dataclass(frozen=True)
class NativeAugmentationConfig:
    """Conservative appearance-label preserving engineering settings."""

    hsv_h: float = 0.0
    hsv_s: float = 0.0
    hsv_v: float = 0.1
    fliplr: float = 0.5
    flipud: float = 0.0
    degrees: float = 0.0
    translate: float = 0.0
    scale: float = 0.0
    shear: float = 0.0
    perspective: float = 0.0
    mosaic: float = 0.0
    mixup: float = 0.0
    copy_paste: float = 0.0
    cutmix: float = 0.0
    bgr: float = 0.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            if not np.isfinite(value):
                raise ValueError(f"Nonfinite augmentation setting: {name}")
            if name not in ("hsv_v", "fliplr") and value != 0:
                raise ValueError(f"Unsupported or appearance-changing augmentation: {name}")
        if not 0 <= self.hsv_v <= 0.1 or not 0 <= self.fliplr <= 1:
            raise ValueError("Require hsv_v in [0, .1] and fliplr in [0, 1]")


@dataclass
class NativeAugmentationResult:
    image_bgr: np.ndarray
    instance_raster: np.ndarray
    bboxes_xywh: np.ndarray
    trace: dict


class _RecordedRandomFlip(RandomFlip):
    """Record the native decision without duplicating its random draw or warp."""

    def get_params(self, labels):
        params = super().get_params(labels)
        self.applied = bool(params["flip"])
        return params


def augmentation_contract(config=None):
    config = config or NativeAugmentationConfig()
    return {
        "version": VERSION,
        "ultralytics_version": ultralytics.__version__,
        "settings": asdict(config),
        "native_transforms": ["RandomHSV", "RandomFlip(horizontal)"],
        "scope": "train_only; physical camera distances supplied by dataset generation",
        "mask_policy": "exact instance IDs through native RandomFlip semantic_mask channel",
        "disabled_reasons": {
            "hue_saturation_bgr": "Preserve calyx-appearance class cues; no artificial class-color changes",
            "mosaic_mixup_cutmix_copy_paste": "Avoid composite identities and invented visible instance boundaries",
            "affine_vertical_flip": "Not implemented for exact rasters; physical distances/angles are rendered",
        },
        "marker_scope": "Horizontal flip may mirror ArUco; augmented RGB is for calyx training, never pose estimation",
    }


def augment_raster_sample(
    image_bgr: np.ndarray,
    instance_raster: np.ndarray,
    bboxes_xywh: np.ndarray,
    *,
    mask_ids: Sequence[int],
    training: bool,
    config: NativeAugmentationConfig | None = None,
) -> NativeAugmentationResult:
    """Augment a BGR uint8 image and its exact raster with one native flip draw.

    Boxes use normalized xywh, in the same order as ``mask_ids`` and the caller's
    class rows. IDs are positive and zero denotes background. Empty negatives are
    supported. The function never mutates input arrays or seeds global RNG state.
    Reproducibility uses the trainer/worker Python and NumPy RNG seeds.
    """
    config = config or NativeAugmentationConfig()
    image = np.asarray(image_bgr)
    raster = np.asarray(instance_raster)
    boxes = np.asarray(bboxes_xywh, dtype=np.float32)
    ids = [int(value) for value in mask_ids]
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("Expected a BGR uint8 image with three channels")
    if raster.shape != image.shape[:2] or raster.dtype not in (np.uint8, np.uint16):
        raise ValueError("Expected aligned uint8/uint16 instance-ID raster")
    if boxes.shape != (len(ids), 4) or not np.isfinite(boxes).all():
        raise ValueError("Expected finite normalized xywh box for every mask ID")
    if (boxes < 0).any() or (boxes > 1).any():
        raise ValueError("Boxes must use normalized xywh coordinates")
    if any(value <= 0 for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Mask IDs must be unique and positive")
    visible_ids = set(int(value) for value in np.unique(raster) if value != 0)
    if visible_ids != set(ids):
        raise ValueError("Raster IDs and instance annotations disagree")

    labels = {
        "img": image.copy(),
        "semantic_mask": raster.copy(),
        "instances": Instances(
            boxes.copy(), segments=np.zeros((0, 0, 2), np.float32),
            bbox_format="xywh", normalized=True,
        ),
    }
    applied = False
    native_calls = []
    if training:
        labels = RandomHSV(config.hsv_h, config.hsv_s, config.hsv_v)(labels)
        native_calls.append("RandomHSV")
        flip = _RecordedRandomFlip(p=config.fliplr, direction="horizontal")
        labels = flip(labels)
        native_calls.append("RandomFlip")
        applied = flip.applied
    return NativeAugmentationResult(
        np.ascontiguousarray(labels["img"]),
        np.ascontiguousarray(labels["semantic_mask"]),
        np.ascontiguousarray(labels["instances"].bboxes),
        {
            "version": VERSION,
            "ultralytics_version": ultralytics.__version__,
            "training": bool(training),
            "native_calls": native_calls,
            "horizontal_flip": applied,
            "settings": asdict(config),
            "mask_ids": ids,
        },
    )
