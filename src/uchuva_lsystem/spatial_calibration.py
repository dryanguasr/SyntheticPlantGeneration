"""Derive a YOLO dataset whose apparent object scale matches real train/val data."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from PIL import Image


CALIBRATION_VERSION = "0.1.0-adaptive-scale-crop"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
AREA_BANDS = (0.01, 0.05)
MIN_VISIBLE_FRACTION = 0.75
ZOOM_CANDIDATES = {
    "under_one_percent": (1.15, 1.25, 1.35, 1.45, 1.55),
    "one_to_five_percent": (1.55, 1.65, 1.75, 1.85, 1.95),
    "at_least_five_percent": (1.0, 1.05, 1.10, 1.15, 1.20, 1.25),
}

Box = tuple[int, float, float, float, float]


def derive_spatially_calibrated_dataset(
    *,
    real_root: str | Path,
    synthetic_root: str | Path,
    output_root: str | Path,
    real_splits: Iterable[str] = ("train", "val"),
    synthetic_fit_splits: Iterable[str] = ("train",),
    min_visible_fraction: float = MIN_VISIBLE_FRACTION,
) -> dict[str, Any]:
    """Crop and resize synthetic images using a train-only fitted scale schedule.

    Natural test labels are never read. The original natural and synthetic datasets
    remain untouched; images and labels are written to a new derived dataset.
    """
    real_root = Path(real_root).resolve()
    synthetic_root = Path(synthetic_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError(f"Spatial calibration output already exists: {output_root}")
    selected_real_splits = tuple(real_splits)
    selected_synthetic_splits = tuple(synthetic_fit_splits)
    if not selected_real_splits or "test" in selected_real_splits:
        raise ValueError("Spatial calibration must use real train/val only.")
    if not selected_synthetic_splits or "test" in selected_synthetic_splits:
        raise ValueError("Spatial calibration fitting must use synthetic train/val only.")
    if not 0.0 < min_visible_fraction <= 1.0:
        raise ValueError("min_visible_fraction must be in (0, 1].")

    real_groups = _load_label_groups(real_root / "LABELS", selected_real_splits)
    synthetic_fit_groups = _load_label_groups(
        synthetic_root / "labels", selected_synthetic_splits
    )
    if not real_groups or not synthetic_fit_groups:
        raise ValueError("Real and synthetic fitting labels are required.")
    reference = _distribution_summary(real_groups)
    source_fit = _distribution_summary(synthetic_fit_groups)
    zoom_factors, fit_summary, fit_score = _fit_zoom_factors(
        reference,
        synthetic_fit_groups,
        min_visible_fraction=min_visible_fraction,
    )

    records: list[dict[str, Any]] = []
    output_groups: list[list[Box]] = []
    for split in ("train", "val", "test"):
        source_images = synthetic_root / "images" / split
        source_labels = synthetic_root / "labels" / split
        destination_images = output_root / "images" / split
        destination_labels = output_root / "labels" / split
        destination_images.mkdir(parents=True, exist_ok=True)
        destination_labels.mkdir(parents=True, exist_ok=True)
        for source_image in _image_paths(source_images):
            source_label = source_labels / f"{source_image.stem}.txt"
            boxes = _read_yolo_boxes(source_label)
            zoom = zoom_factors[_group_band(boxes)]
            destination_image = destination_images / source_image.name
            destination_label = destination_labels / f"{source_image.stem}.txt"
            transformed, crop = _transform_example(
                source_image,
                destination_image,
                boxes,
                zoom=zoom,
                min_visible_fraction=min_visible_fraction,
            )
            _write_yolo_boxes(destination_label, transformed)
            output_groups.append(transformed)
            records.append(
                {
                    "split": split,
                    "image": destination_image.relative_to(output_root).as_posix(),
                    "label": destination_label.relative_to(output_root).as_posix(),
                    "source_image_sha256": _sha256(source_image),
                    "derived_image_sha256": _sha256(destination_image),
                    "source_box_count": len(boxes),
                    "derived_box_count": len(transformed),
                    "dropped_box_count": len(boxes) - len(transformed),
                    "source_median_box_area": _median_box_area(boxes),
                    "source_area_band": _group_band(boxes),
                    "zoom": zoom,
                    "crop_pixels": crop,
                }
            )

    _write_data_yaml(output_root)
    report = {
        "version": CALIBRATION_VERSION,
        "real_root": str(real_root),
        "synthetic_source_root": str(synthetic_root),
        "output_root": str(output_root),
        "real_splits_used": list(selected_real_splits),
        "synthetic_fit_splits_used": list(selected_synthetic_splits),
        "min_visible_fraction": min_visible_fraction,
        "zoom_factors": zoom_factors,
        "fit_score": round(fit_score, 8),
        "reference_distribution": reference,
        "synthetic_fit_distribution_before": source_fit,
        "synthetic_fit_distribution_after_simulation": fit_summary,
        "derived_distribution_all_splits": _distribution_summary(output_groups),
        "image_count": len(records),
        "source_box_count": sum(item["source_box_count"] for item in records),
        "derived_box_count": sum(item["derived_box_count"] for item in records),
        "records": records,
    }
    _write_json(output_root / "spatial_calibration.json", report)
    return report


def _fit_zoom_factors(
    reference: dict[str, Any],
    source_groups: list[list[Box]],
    *,
    min_visible_fraction: float,
) -> tuple[dict[str, float], dict[str, Any], float]:
    best: tuple[float, tuple[float, float, float], dict[str, Any]] | None = None
    for small in ZOOM_CANDIDATES["under_one_percent"]:
        for middle in ZOOM_CANDIDATES["one_to_five_percent"]:
            for large in ZOOM_CANDIDATES["at_least_five_percent"]:
                factors = (small, middle, large)
                transformed = _simulate_groups(
                    source_groups,
                    factors,
                    min_visible_fraction=min_visible_fraction,
                )
                summary = _distribution_summary(transformed)
                score = _distribution_score(reference, summary)
                candidate = (score, factors, summary)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
    assert best is not None
    score, factors, summary = best
    return (
        dict(zip(ZOOM_CANDIDATES, factors)),
        summary,
        score,
    )


def _simulate_groups(
    groups: list[list[Box]],
    factors: tuple[float, float, float],
    *,
    min_visible_fraction: float,
) -> list[list[Box]]:
    factor_map = dict(zip(ZOOM_CANDIDATES, factors))
    transformed: list[list[Box]] = []
    for boxes in groups:
        zoom = factor_map[_group_band(boxes)]
        x0, y0, crop_width, crop_height = _normalized_crop(boxes, zoom)
        transformed.append(
            _transform_boxes(
                boxes,
                x0=x0,
                y0=y0,
                crop_width=crop_width,
                crop_height=crop_height,
                min_visible_fraction=min_visible_fraction,
            )
        )
    return transformed


def _distribution_score(reference: dict[str, Any], candidate: dict[str, Any]) -> float:
    band_gap = mean(
        abs(reference["box_area_band_rates"][key] - candidate["box_area_band_rates"][key])
        for key in ZOOM_CANDIDATES
    )
    quantile_gap = mean(
        abs(math.log(max(reference["box_area_quantiles"][key], 1e-9) / max(candidate["box_area_quantiles"][key], 1e-9)))
        for key in ("p10", "p25", "p50", "p75", "p90")
    )
    count_gap = abs(
        candidate["objects_per_image_mean"] - reference["objects_per_image_mean"]
    ) / max(reference["objects_per_image_mean"], 1e-9)
    boundary_gap = abs(reference["boundary_box_rate"] - candidate["boundary_box_rate"])
    return 2.0 * band_gap + quantile_gap + 0.25 * count_gap + 0.10 * boundary_gap


def _distribution_summary(groups: list[list[Box]]) -> dict[str, Any]:
    areas = [box[3] * box[4] for boxes in groups for box in boxes]
    boundary_count = sum(
        box[1] - box[3] / 2.0 <= 1e-7
        or box[2] - box[4] / 2.0 <= 1e-7
        or box[1] + box[3] / 2.0 >= 1.0 - 1e-7
        or box[2] + box[4] / 2.0 >= 1.0 - 1e-7
        for boxes in groups
        for box in boxes
    )
    bands = {
        "under_one_percent": sum(area < AREA_BANDS[0] for area in areas),
        "one_to_five_percent": sum(AREA_BANDS[0] <= area < AREA_BANDS[1] for area in areas),
        "at_least_five_percent": sum(area >= AREA_BANDS[1] for area in areas),
    }
    total = len(areas)
    return {
        "image_count": len(groups),
        "box_count": total,
        "objects_per_image_mean": mean(len(boxes) for boxes in groups) if groups else 0.0,
        "box_area_quantiles": _quantiles(areas),
        "box_area_band_rates": {
            key: count / total if total else 0.0 for key, count in bands.items()
        },
        "boundary_box_rate": boundary_count / total if total else 0.0,
    }


def _transform_example(
    source: Path,
    destination: Path,
    boxes: list[Box],
    *,
    zoom: float,
    min_visible_fraction: float,
) -> tuple[list[Box], dict[str, int]]:
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        nx0, ny0, ncrop_width, ncrop_height = _normalized_crop(boxes, zoom)
        crop_width = max(1, min(width, round(ncrop_width * width)))
        crop_height = max(1, min(height, round(ncrop_height * height)))
        left = max(0, min(width - crop_width, round(nx0 * width)))
        top = max(0, min(height - crop_height, round(ny0 * height)))
        right = left + crop_width
        bottom = top + crop_height
        transformed = _transform_boxes(
            boxes,
            x0=left / width,
            y0=top / height,
            crop_width=crop_width / width,
            crop_height=crop_height / height,
            min_visible_fraction=min_visible_fraction,
        )
        derived = image.crop((left, top, right, bottom)).resize(
            (width, height), Image.Resampling.LANCZOS
        )
        save_options = (
            {"quality": 95, "subsampling": 0}
            if destination.suffix.lower() in {".jpg", ".jpeg"}
            else {}
        )
        derived.save(destination, **save_options)
    return transformed, {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "source_width": width,
        "source_height": height,
    }


def _normalized_crop(boxes: list[Box], zoom: float) -> tuple[float, float, float, float]:
    crop_width = 1.0 / zoom
    crop_height = 1.0 / zoom
    center_x = median(box[1] for box in boxes) if boxes else 0.5
    center_y = median(box[2] for box in boxes) if boxes else 0.5
    x0 = min(max(center_x - crop_width / 2.0, 0.0), 1.0 - crop_width)
    y0 = min(max(center_y - crop_height / 2.0, 0.0), 1.0 - crop_height)
    return x0, y0, crop_width, crop_height


def _transform_boxes(
    boxes: list[Box],
    *,
    x0: float,
    y0: float,
    crop_width: float,
    crop_height: float,
    min_visible_fraction: float,
) -> list[Box]:
    transformed: list[Box] = []
    for class_id, x, y, width, height in boxes:
        left = max(x - width / 2.0, x0)
        right = min(x + width / 2.0, x0 + crop_width)
        top = max(y - height / 2.0, y0)
        bottom = min(y + height / 2.0, y0 + crop_height)
        intersection = max(0.0, right - left) * max(0.0, bottom - top)
        source_area = width * height
        if source_area <= 0.0 or intersection / source_area < min_visible_fraction:
            continue
        new_left = (left - x0) / crop_width
        new_right = (right - x0) / crop_width
        new_top = (top - y0) / crop_height
        new_bottom = (bottom - y0) / crop_height
        transformed.append(
            (
                class_id,
                (new_left + new_right) / 2.0,
                (new_top + new_bottom) / 2.0,
                new_right - new_left,
                new_bottom - new_top,
            )
        )
    return transformed


def _load_label_groups(root: Path, splits: Iterable[str]) -> list[list[Box]]:
    return [
        _read_yolo_boxes(path)
        for split in splits
        for path in sorted((root / split).glob("*.txt"))
    ]


def _read_yolo_boxes(path: Path) -> list[Box]:
    if not path.is_file():
        return []
    boxes: list[Box] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 5:
            raise ValueError(f"Invalid YOLO row at {path}:{line_number}: {line}")
        boxes.append(
            (
                int(float(fields[0])),
                float(fields[1]),
                float(fields[2]),
                float(fields[3]),
                float(fields[4]),
            )
        )
    return boxes


def _write_yolo_boxes(path: Path, boxes: list[Box]) -> None:
    rows = [
        f"{class_id} {x:.8f} {y:.8f} {width:.8f} {height:.8f}"
        for class_id, x, y, width, height in boxes
    ]
    path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8", newline="\n")


def _median_box_area(boxes: list[Box]) -> float:
    return median(box[3] * box[4] for box in boxes) if boxes else 0.0


def _group_band(boxes: list[Box]) -> str:
    area = _median_box_area(boxes)
    if area < AREA_BANDS[0]:
        return "under_one_percent"
    if area < AREA_BANDS[1]:
        return "one_to_five_percent"
    return "at_least_five_percent"


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {key: 0.0 for key in ("p10", "p25", "p50", "p75", "p90")}
    ordered = sorted(values)
    return {
        key: ordered[round((len(ordered) - 1) * fraction)]
        for key, fraction in (("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90))
    }


def _image_paths(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.glob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_data_yaml(root: Path) -> None:
    (root / "data.yaml").write_text(
        f'path: "{root.as_posix()}"\n'
        "train: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: calyx\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
