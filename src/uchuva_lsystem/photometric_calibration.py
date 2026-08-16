"""Derive a synthetic YOLO dataset with train/val-grounded color calibration."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from PIL import Image, ImageStat


CALIBRATION_VERSION = "0.2.0-robust-luminance-affine"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def derive_photometrically_calibrated_dataset(
    *,
    real_root: str | Path,
    synthetic_root: str | Path,
    output_root: str | Path,
    real_splits: Iterable[str] = ("train", "val"),
) -> dict[str, Any]:
    """Match robust RGB statistics without reading real test or changing labels."""
    real_root = Path(real_root).resolve()
    synthetic_root = Path(synthetic_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError(f"Calibration output already exists: {output_root}")
    selected_real_splits = tuple(real_splits)
    if not selected_real_splits or "test" in selected_real_splits:
        raise ValueError("Photometric calibration must use real train/val only.")

    real_images = [
        path
        for split in selected_real_splits
        for path in _image_paths(real_root / "IMAGENES" / split)
    ]
    synthetic_reference = _image_paths(synthetic_root / "images" / "train")
    if not real_images or not synthetic_reference:
        raise ValueError("Real calibration images and synthetic train images are required.")

    real_stats = _luminance_statistics(real_images)
    synthetic_stats = _luminance_statistics(synthetic_reference)
    transform = _fit_luminance_transform(real_stats, synthetic_stats)

    records: list[dict[str, Any]] = []
    for split in ("train", "val", "test"):
        source_images = synthetic_root / "images" / split
        source_labels = synthetic_root / "labels" / split
        destination_images = output_root / "images" / split
        destination_labels = output_root / "labels" / split
        destination_images.mkdir(parents=True, exist_ok=True)
        destination_labels.mkdir(parents=True, exist_ok=True)
        for source in _image_paths(source_images):
            destination = destination_images / source.name
            _apply_transform(source, destination, transform)
            records.append(
                {
                    "split": split,
                    "image": destination.relative_to(output_root).as_posix(),
                    "source_image_sha256": _sha256(source),
                    "derived_image_sha256": _sha256(destination),
                }
            )
        for source in sorted(source_labels.glob("*.txt")):
            _hardlink_or_copy(source, destination_labels / source.name)

    for name in ("data.yaml", "labels.txt"):
        source = synthetic_root / name
        if source.is_file():
            shutil.copy2(source, output_root / name)
    _write_data_yaml(output_root)
    report = {
        "version": CALIBRATION_VERSION,
        "real_root": str(real_root),
        "synthetic_source_root": str(synthetic_root),
        "output_root": str(output_root),
        "real_splits_used": list(selected_real_splits),
        "real_luminance_statistics": real_stats,
        "synthetic_luminance_statistics": synthetic_stats,
        "transform": transform,
        "image_count": len(records),
        "records": records,
    }
    _write_json(output_root / "photometric_calibration.json", report)
    return report


def _luminance_statistics(paths: list[Path]) -> dict[str, float]:
    values: list[float] = []
    for path in paths:
        with Image.open(path) as image:
            image = image.convert("L")
            image.thumbnail((96, 96))
            values.append(float(ImageStat.Stat(image).mean[0]))
    return {
        "p10": _quantile(values, 0.10),
        "p50": median(values),
        "p90": _quantile(values, 0.90),
    }


def _fit_luminance_transform(
    real_stats: dict[str, float],
    synthetic_stats: dict[str, float],
) -> dict[str, float]:
    denominator = max(1e-6, synthetic_stats["p90"] - synthetic_stats["p10"])
    scale = (real_stats["p90"] - real_stats["p10"]) / denominator
    scale = min(2.25, max(0.5, scale))
    offset = real_stats["p50"] - scale * synthetic_stats["p50"]
    return {"scale": round(scale, 8), "offset": round(offset, 8)}


def _apply_transform(
    source: Path,
    destination: Path,
    transform: dict[str, float],
) -> None:
    with Image.open(source) as image:
        luminance, blue_difference, red_difference = image.convert("YCbCr").split()
        scale = transform["scale"]
        offset = transform["offset"]
        lut = [max(0, min(255, round(scale * value + offset))) for value in range(256)]
        calibrated = Image.merge(
            "YCbCr",
            (luminance.point(lut), blue_difference, red_difference),
        ).convert("RGB")
        save_options = {"quality": 95, "subsampling": 0} if destination.suffix.lower() in {".jpg", ".jpeg"} else {}
        calibrated.save(destination, **save_options)


def _image_paths(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.glob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]


def _hardlink_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


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
