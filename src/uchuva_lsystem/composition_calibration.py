"""Pure calibration of camera scheduling from observed synthetic box yields."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


AREA_BANDS = (
    "under_one_percent",
    "one_to_five_percent",
    "at_least_five_percent",
)
CAMERA_PROFILES = ("real_context", "real_mid", "real_close")
CAMERA_TO_AREA_BAND = dict(zip(CAMERA_PROFILES, AREA_BANDS))


def calibrate_camera_mixture(
    manifest_path: str | Path,
    reference_profile_path: str | Path,
    *,
    reference_split: str = "train",
    manifest_split: str = "train",
) -> dict[str, Any]:
    """Find a deterministic 1%-grid camera mix matching real box-area bands."""
    manifest = Path(manifest_path)
    reference_path = Path(reference_profile_path)
    reference_payload = json.loads(reference_path.read_text(encoding="utf-8"))
    if "reference" in reference_payload:
        reference_payload = reference_payload["reference"]
    if reference_split == "overall":
        reference = reference_payload["overall"]
    else:
        reference = reference_payload.get("splits", {}).get(reference_split)
        if reference is None:
            raise ValueError(f"Reference split {reference_split!r} is unavailable.")
    target = {
        band: float(reference["box_area_band_rates_pct"].get(band, 0.0))
        for band in AREA_BANDS
    }
    records = list(_read_jsonl(manifest))
    matrix = camera_yield_matrix(records, split=manifest_split)
    mixture, predicted, objective = optimize_camera_mixture(matrix, target)
    schedule_rates = {
        CAMERA_TO_AREA_BAND[camera]: rate for camera, rate in mixture.items()
    }
    return {
        "version": "1.0.0-deterministic-camera-yield-grid",
        "status": "valid",
        "method": "one_percent_simplex_grid_minimum_mean_absolute_band_gap",
        "reference_split": reference_split,
        "manifest_split": manifest_split,
        "inputs": {
            "synthetic_manifest": str(manifest.resolve()),
            "synthetic_manifest_sha256": _sha256(manifest),
            "reference_profile": str(reference_path.resolve()),
            "reference_profile_sha256": _sha256(reference_path),
        },
        "target_box_area_band_rates_pct": target,
        "camera_yield_matrix": matrix,
        "recommended_camera_profile_rates_pct": mixture,
        "recommended_image_schedule_rates_pct": schedule_rates,
        "predicted_box_area_band_rates_pct": predicted,
        "predicted_mean_absolute_gap_pct_points": objective,
        "parameter_status": "dataset_inferred_train_only",
        "test_split_consulted": False,
    }


def camera_yield_matrix(
    records: Iterable[dict[str, Any]],
    *,
    split: str = "train",
) -> dict[str, dict[str, Any]]:
    """Count actual box bands yielded per capture for each camera profile."""
    capture_counts: Counter[str] = Counter()
    band_counts: dict[str, Counter[str]] = {
        camera: Counter() for camera in CAMERA_PROFILES
    }
    for record in records:
        if split and str(record.get("split")) != split:
            continue
        camera = str(record.get("camera_profile", ""))
        if camera not in band_counts:
            continue
        capture_counts[camera] += 1
        for detection in record.get("detections", []):
            box = detection.get("yolo_xywh") or []
            if len(box) == 4:
                band_counts[camera][_area_band(float(box[2]) * float(box[3]))] += 1
    matrix: dict[str, dict[str, Any]] = {}
    for camera in CAMERA_PROFILES:
        captures = int(capture_counts[camera])
        counts = {band: int(band_counts[camera][band]) for band in AREA_BANDS}
        matrix[camera] = {
            "capture_count": captures,
            "actual_box_counts": counts,
            "boxes_per_capture_by_band": {
                band: round(counts[band] / captures, 8) if captures else 0.0
                for band in AREA_BANDS
            },
            "total_boxes_per_capture": (
                round(sum(counts.values()) / captures, 8) if captures else 0.0
            ),
        }
    if any(matrix[camera]["capture_count"] == 0 for camera in CAMERA_PROFILES):
        missing = [
            camera
            for camera in CAMERA_PROFILES
            if matrix[camera]["capture_count"] == 0
        ]
        raise ValueError(f"Calibration manifest lacks camera profiles: {missing}")
    return matrix


def optimize_camera_mixture(
    matrix: dict[str, dict[str, Any]],
    target_rates_pct: dict[str, float],
) -> tuple[dict[str, float], dict[str, float], float]:
    """Search the complete 1%-resolution three-camera simplex."""
    best: tuple[
        tuple[float, float, tuple[int, int, int]],
        dict[str, float],
    ] | None = None
    for context in range(101):
        for mid in range(101 - context):
            close = 100 - context - mid
            weights = (context, mid, close)
            predicted = _predict_box_rates(matrix, weights)
            gap = sum(
                abs(predicted[band] - float(target_rates_pct.get(band, 0.0)))
                for band in AREA_BANDS
            ) / len(AREA_BANDS)
            # Deterministic tie-break: prefer the less extreme distribution,
            # then lexical camera order.
            extremity = sum(abs(value - 100.0 / 3.0) for value in weights)
            candidate_key = (round(gap, 12), round(extremity, 12), weights)
            if best is None or candidate_key < best[0]:
                best = (candidate_key, predicted)
    assert best is not None
    weights = best[0][2]
    mixture = {
        camera: float(weight)
        for camera, weight in zip(CAMERA_PROFILES, weights)
    }
    return mixture, best[1], round(best[0][0], 6)


def write_composition_calibration(
    report: dict[str, Any], output_path: str | Path
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def load_schedule_rates(path: str | Path) -> dict[str, float]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rates = payload.get("recommended_image_schedule_rates_pct")
    if not isinstance(rates, dict) or set(rates) != set(AREA_BANDS):
        raise ValueError("Invalid composition calibration schedule rates.")
    return {band: float(rates[band]) for band in AREA_BANDS}


def _predict_box_rates(
    matrix: dict[str, dict[str, Any]],
    weights_pct: tuple[int, int, int],
) -> dict[str, float]:
    expected = {band: 0.0 for band in AREA_BANDS}
    for camera, weight in zip(CAMERA_PROFILES, weights_pct):
        for band in AREA_BANDS:
            expected[band] += (
                weight
                / 100.0
                * float(matrix[camera]["boxes_per_capture_by_band"][band])
            )
    total = sum(expected.values())
    return {
        band: round(100.0 * expected[band] / total, 6) if total else 0.0
        for band in AREA_BANDS
    }


def _area_band(area: float) -> str:
    if area < 0.01:
        return "under_one_percent"
    if area < 0.05:
        return "one_to_five_percent"
    return "at_least_five_percent"


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            yield json.loads(line)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
