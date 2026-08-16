"""Build a read-only, stratified calibration/evaluation manifest.

The original dataset is never written.  Only derived label measurements are
stored under ``outputs/reference_measurements`` by default; ``test`` remains
excluded from this morphology iteration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPO_ROOT / "Dataset Original"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a read-only train/val measurement manifest."
    )
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT
        / "outputs"
        / "reference_measurements"
        / "uchuva_reference_manifest.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    output = args.output.resolve()
    entries: list[dict[str, Any]] = []
    split_counts: dict[str, int] = {}
    for split in ("train", "val", "test"):
        label_dir = dataset_root / "LABELS" / split
        labels = sorted(label_dir.glob("*.txt"))
        split_counts[split] = len(labels)
        if split == "test":
            continue
        role = "calibration" if split == "train" else "evaluation"
        for label_path in labels:
            image_path = _find_image(
                dataset_root / "IMAGENES" / split,
                label_path.stem,
            )
            measurements = _measure_label(label_path)
            entries.append(
                {
                    "sample_id": label_path.stem,
                    "split": split,
                    "role": role,
                    "stratum": _stratum(measurements),
                    "image_path": (
                        image_path.relative_to(dataset_root).as_posix()
                        if image_path is not None
                        else None
                    ),
                    "label_path": label_path.relative_to(dataset_root).as_posix(),
                    "measurements": measurements,
                    "label_sha256": _sha256(label_path),
                }
            )
    payload = {
        "schema_version": "1.0",
        "dataset_root": str(dataset_root),
        "policy": {
            "train": "calibration_only",
            "val": "evaluation_for_current_iteration",
            "test": "untouched_and_excluded",
            "writes_to_original_dataset": False,
        },
        "split_label_counts": split_counts,
        "entries": entries,
        "manifest_sha256": _manifest_digest(entries),
        "parameter_status": "real_dataset_measured",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote read-only reference manifest: {output}")
    print(json.dumps(split_counts, ensure_ascii=False, sort_keys=True))


def _measure_label(path: Path) -> dict[str, Any]:
    areas: list[float] = []
    aspects: list[float] = []
    boundary_count = 0
    invalid_count = 0
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            invalid_count += 1
            continue
        try:
            _, x, y, width, height = (float(value) for value in fields)
        except ValueError:
            invalid_count += 1
            continue
        areas.append(width * height)
        if height > 0.0:
            aspects.append(width / height)
        if (
            x - width * 0.5 <= 1e-7
            or y - height * 0.5 <= 1e-7
            or x + width * 0.5 >= 1.0 - 1e-7
            or y + height * 0.5 >= 1.0 - 1e-7
        ):
            boundary_count += 1
    return {
        "object_count": len(areas),
        "box_area_median": (
            round(statistics.median(areas), 8) if areas else None
        ),
        "box_area_mean": (
            round(statistics.fmean(areas), 8) if areas else None
        ),
        "box_aspect_median": (
            round(statistics.median(aspects), 8) if aspects else None
        ),
        "boundary_box_count": boundary_count,
        "invalid_row_count": invalid_count,
    }


def _stratum(measurements: dict[str, Any]) -> str:
    count = int(measurements["object_count"])
    count_band = (
        "zero"
        if count == 0
        else "one_to_five"
        if count <= 5
        else "six_to_ten"
        if count <= 10
        else "more_than_ten"
    )
    median_area = measurements["box_area_median"]
    area_band = (
        "no_boxes"
        if median_area is None
        else "small"
        if median_area < 0.01
        else "medium"
        if median_area < 0.05
        else "large"
    )
    return f"{count_band}__{area_band}"


def _find_image(directory: Path, stem: str) -> Path | None:
    for suffix in IMAGE_SUFFIXES:
        candidate = directory / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
        candidate = directory / f"{stem}{suffix.upper()}"
        if candidate.exists():
            return candidate
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        entries,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


if __name__ == "__main__":
    main()
