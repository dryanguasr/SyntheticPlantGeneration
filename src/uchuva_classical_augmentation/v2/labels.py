"""Pure YOLO label geometry used by every v2 recipe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class YoloBox:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float

    @property
    def area_ratio(self) -> float:
        return self.width * self.height

    def validate(self, class_count: int = 1) -> None:
        if not 0 <= self.class_id < class_count:
            raise ValueError(f"Invalid class id: {self.class_id}")
        values = (self.x_center, self.y_center, self.width, self.height)
        if not all(0.0 <= value <= 1.0 for value in values):
            raise ValueError(f"YOLO values outside [0, 1]: {values}")
        if self.width <= 0.0 or self.height <= 0.0:
            raise ValueError(f"Non-positive box extent: {values}")
        x1, y1, x2, y2 = self.to_xyxy_normalized()
        if x1 < -1e-9 or y1 < -1e-9 or x2 > 1.0 + 1e-9 or y2 > 1.0 + 1e-9:
            raise ValueError(f"YOLO box extends outside image: {values}")

    def to_xyxy_normalized(self) -> tuple[float, float, float, float]:
        return (
            self.x_center - self.width / 2.0,
            self.y_center - self.height / 2.0,
            self.x_center + self.width / 2.0,
            self.y_center + self.height / 2.0,
        )

    def to_xyxy_pixels(self, image_width: int, image_height: int) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = self.to_xyxy_normalized()
        return (
            max(0, min(image_width, round(x1 * image_width))),
            max(0, min(image_height, round(y1 * image_height))),
            max(0, min(image_width, round(x2 * image_width))),
            max(0, min(image_height, round(y2 * image_height))),
        )

    def horizontal_flip(self) -> "YoloBox":
        return YoloBox(self.class_id, 1.0 - self.x_center, self.y_center, self.width, self.height)

    def crop(self, window: tuple[float, float, float, float], *, min_visible: float = 0.25) -> "YoloBox | None":
        """Crop using a normalized source window and return clipped output coordinates."""
        wx1, wy1, wx2, wy2 = window
        if not (0.0 <= wx1 < wx2 <= 1.0 and 0.0 <= wy1 < wy2 <= 1.0):
            raise ValueError(f"Invalid crop window: {window}")
        x1, y1, x2, y2 = self.to_xyxy_normalized()
        ix1, iy1 = max(x1, wx1), max(y1, wy1)
        ix2, iy2 = min(x2, wx2), min(y2, wy2)
        if ix2 <= ix1 or iy2 <= iy1:
            return None
        visible = ((ix2 - ix1) * (iy2 - iy1)) / max(self.area_ratio, 1e-12)
        if visible < min_visible:
            return None
        crop_width, crop_height = wx2 - wx1, wy2 - wy1
        return YoloBox.from_xyxy_normalized(
            self.class_id,
            ((ix1 - wx1) / crop_width, (iy1 - wy1) / crop_height, (ix2 - wx1) / crop_width, (iy2 - wy1) / crop_height),
        )

    @classmethod
    def from_xyxy_normalized(cls, class_id: int, xyxy: tuple[float, float, float, float]) -> "YoloBox":
        x1, y1, x2, y2 = xyxy
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(1.0, x2), min(1.0, y2)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"Empty box after clipping: {xyxy}")
        return cls(class_id, (x1 + x2) / 2.0, (y1 + y2) / 2.0, x2 - x1, y2 - y1)

    def to_line(self) -> str:
        return f"{self.class_id} {self.x_center:.10f} {self.y_center:.10f} {self.width:.10f} {self.height:.10f}"


def read_yolo_labels(path: Path, *, missing_is_empty: bool = False) -> list[YoloBox]:
    if not path.is_file():
        if missing_is_empty:
            return []
        raise FileNotFoundError(path)
    boxes: list[YoloBox] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 5:
            raise ValueError(f"{path}:{line_number}: expected 5 fields")
        box = YoloBox(int(float(fields[0])), *(float(value) for value in fields[1:]))
        box.validate()
        boxes.append(box)
    return boxes


def write_yolo_labels(path: Path, boxes: Iterable[YoloBox]) -> None:
    materialized = list(boxes)
    for box in materialized:
        box.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(box.to_line() for box in materialized)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8", newline="\n")


def bbox_from_binary_mask(mask, *, class_id: int, image_width: int, image_height: int) -> YoloBox | None:
    """Return the tight YOLO box of a NumPy-like nonzero mask."""
    import numpy as np

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    return YoloBox.from_xyxy_normalized(
        class_id,
        (x1 / image_width, y1 / image_height, x2 / image_width, y2 / image_height),
    )


def pairwise_iou(first: YoloBox, second: YoloBox) -> float:
    ax1, ay1, ax2, ay2 = first.to_xyxy_normalized()
    bx1, by1, bx2, by2 = second.to_xyxy_normalized()
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    union = first.area_ratio + second.area_ratio - intersection
    return intersection / union if union > 0.0 else 0.0
