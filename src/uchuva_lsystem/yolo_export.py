"""Pure YOLO bounding-box conversion and dataset metadata helpers."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


YOLO_CLASSES: dict[str, int] = {"calyx": 0}


@dataclass(frozen=True)
class DetectionBox:
    instance_id: str
    local_reproductive_id: str
    plant_id: str
    plant_role: str
    class_name: str
    class_id: int
    bbox_xywh: tuple[int, int, int, int]
    yolo_xywh: tuple[float, float, float, float]
    visible_pixels: int
    truncated: bool
    calyx_state: str = ""
    maturity: str = ""
    reproductive_stage: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def global_reproductive_id(plant_id: str, reproductive_id: str) -> str:
    """Namespace a morphology-local reproductive ID by its plant instance."""
    if not reproductive_id:
        return ""
    return f"{plant_id}:{reproductive_id}" if plant_id else reproductive_id


def detection_class_name(semantic_class: str, calyx_state: str = "") -> str | None:
    if semantic_class == "calyx":
        return "calyx"
    return None


def clip_bbox_xywh(
    bbox_xywh: Iterable[int | float], width: int, height: int
) -> tuple[tuple[int, int, int, int] | None, bool]:
    """Clip a top-left XYWH box to image bounds and report truncation."""
    x, y, box_width, box_height = (float(value) for value in bbox_xywh)
    x1 = max(0.0, min(float(width), x))
    y1 = max(0.0, min(float(height), y))
    x2 = max(0.0, min(float(width), x + max(0.0, box_width)))
    y2 = max(0.0, min(float(height), y + max(0.0, box_height)))
    if x2 <= x1 or y2 <= y1:
        return None, True
    clipped = (
        int(round(x1)),
        int(round(y1)),
        max(1, int(round(x2 - x1))),
        max(1, int(round(y2 - y1))),
    )
    truncated = (
        x < 0.0
        or y < 0.0
        or x + box_width > width
        or y + box_height > height
        or clipped[0] == 0
        or clipped[1] == 0
        or clipped[0] + clipped[2] >= width
        or clipped[1] + clipped[3] >= height
    )
    return clipped, truncated


def bbox_xywh_to_yolo(
    bbox_xywh: Iterable[int | float], width: int, height: int
) -> tuple[float, float, float, float]:
    x, y, box_width, box_height = (float(value) for value in bbox_xywh)
    return (
        (x + box_width / 2.0) / width,
        (y + box_height / 2.0) / height,
        box_width / width,
        box_height / height,
    )


def detections_from_mask_items(
    items: dict[str, dict[str, Any]],
    *,
    width: int,
    height: int,
    min_visible_pixels: int = 24,
    min_box_size: int = 6,
) -> list[DetectionBox]:
    detections: list[DetectionBox] = []
    for identifier, item in items.items():
        if identifier == "0" or not item.get("bbox_xywh"):
            continue
        class_name = detection_class_name(
            str(item.get("semantic_class", "")),
            str(item.get("calyx_state", "")),
        )
        if class_name is None:
            continue
        if int(item.get("visible_pixels", 0)) < min_visible_pixels:
            continue
        clipped, truncated = clip_bbox_xywh(item["bbox_xywh"], width, height)
        if clipped is None or clipped[2] < min_box_size or clipped[3] < min_box_size:
            continue
        instance_id = str(item.get("name") or item.get("instance_id") or identifier)
        yolo_box = bbox_xywh_to_yolo(clipped, width, height)
        detections.append(
            DetectionBox(
                instance_id=instance_id,
                local_reproductive_id=str(item.get("local_reproductive_id", "")),
                plant_id=str(item.get("plant_id", "")),
                plant_role=str(item.get("plant_role", "")),
                class_name=class_name,
                class_id=YOLO_CLASSES[class_name],
                bbox_xywh=clipped,
                yolo_xywh=yolo_box,
                visible_pixels=int(item.get("visible_pixels", 0)),
                truncated=truncated,
                calyx_state=str(item.get("calyx_state", "")),
                maturity=str(item.get("maturity", "")),
                reproductive_stage=str(item.get("reproductive_stage", "")),
            )
        )
    return sorted(detections, key=lambda item: (item.class_id, item.instance_id))


def format_yolo_line(detection: DetectionBox) -> str:
    x_center, y_center, width, height = detection.yolo_xywh
    return (
        f"{detection.class_id} {x_center:.8f} {y_center:.8f} "
        f"{width:.8f} {height:.8f}"
    )


def write_yolo_file(path: str | Path, detections: Iterable[DetectionBox]) -> Path:
    output_path = Path(path)
    content = "\n".join(format_yolo_line(item) for item in detections)
    if content:
        content += "\n"
    _atomic_write_text(output_path, content)
    return output_path


def write_dataset_descriptor(root: str | Path) -> None:
    root_path = Path(root)
    ordered = sorted(YOLO_CLASSES.items(), key=lambda item: item[1])
    _atomic_write_text(root_path / "labels.txt", "\n".join(name for name, _ in ordered) + "\n")
    yaml_lines = [
        "path: .",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    yaml_lines.extend(f"  {identifier}: {name}" for name, identifier in ordered)
    _atomic_write_text(root_path / "data.yaml", "\n".join(yaml_lines) + "\n")


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
