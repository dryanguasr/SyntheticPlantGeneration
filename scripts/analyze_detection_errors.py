"""Compare three baseline and three selected hybrid checkpoints on real val only."""

from __future__ import annotations

import argparse
import csv
import ctypes
import gc
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.detection_diagnostics import (
    aggregate_error_report,
    analyze_image_errors,
    file_sha256,
    selection_pairs,
    validate_real_val_only,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--nms-iou", type=float, default=0.70)
    parser.add_argument("--device", default=None)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(output_dir / "ultralytics_config"))
    pairs = selection_pairs(args.selection_lock)
    checkpoint_entries = []
    for pair in pairs:
        checkpoint_entries.extend(
            [
                ("baseline", pair["seed"], pair["baseline"]),
                ("selected_hybrid", pair["seed"], pair["selected"]),
            ]
        )

    canonical_images: list[Path] | None = None
    model_reports: list[dict[str, Any]] = []
    for role, seed, entry in checkpoint_entries:
        checkpoint = Path(entry["checkpoint"]).resolve()
        if file_sha256(checkpoint) != entry["checkpoint_sha256"]:
            raise RuntimeError(f"Checkpoint hash mismatch: {checkpoint}")
        images = validate_real_val_only(_resolve_val_images(Path(entry["data_yaml"])))
        if canonical_images is None:
            canonical_images = images
        elif [item.name for item in images] != [item.name for item in canonical_images]:
            raise RuntimeError("Validation image membership differs between checkpoints.")
        prediction_path = output_dir / "predictions" / f"{role}_seed_{seed}.jsonl"
        predictions = _predict_checkpoint(
            checkpoint,
            images,
            prediction_path,
            imgsz=args.imgsz,
            confidence=args.confidence,
            nms_iou=args.nms_iou,
            device=args.device,
            resume=args.resume,
        )
        image_reports = []
        for image in images:
            ground_truth = _read_yolo_labels(_label_for_image(image))
            width, height, luminance = _image_metadata(image)
            report = analyze_image_errors(
                ground_truth,
                predictions[image.name],
                image_width=width,
                image_height=height,
                mean_luminance=luminance,
            )
            report["image_name"] = image.name
            image_reports.append(report)
        model_reports.append(
            {
                "role": role,
                "seed": seed,
                "experiment": entry["experiment"],
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": entry["checkpoint_sha256"],
                "validation_metrics_from_selection_lock": entry["validation_metrics"],
                "prediction_cache": str(prediction_path),
                "aggregate": aggregate_error_report(image_reports),
                "images": image_reports,
            }
        )
        _write_json(output_dir / f"{role}_seed_{seed}_diagnostic.json", model_reports[-1])

    assert canonical_images is not None
    validation_fingerprint = _validation_fingerprint(canonical_images)
    final = {
        "version": "1.0.0-real-val-localization-audit",
        "status": "valid",
        "selection_lock": str(args.selection_lock.resolve()),
        "selection_lock_sha256": file_sha256(args.selection_lock),
        "split": "val",
        "domain": "real_only",
        "image_count": len(canonical_images),
        "validation_fingerprint_sha256": validation_fingerprint,
        "test_consulted": False,
        "matching": {
            "method": "deterministic_greedy_descending_iou",
            "true_positive_threshold": 0.50,
            "high_localization_threshold": 0.75,
            "localization_miss_lower_bound": 0.10,
            "confidence_threshold": args.confidence,
            "nms_iou": args.nms_iou,
            "imgsz": args.imgsz,
        },
        "models": model_reports,
        "paired_differences_selected_minus_baseline": _paired_differences(model_reports),
    }
    _write_json(output_dir / "detection_diagnostic.json", final)
    _write_csv(output_dir / "detection_diagnostic_summary.csv", model_reports)
    (output_dir / "detection_diagnostic.md").write_text(
        _markdown(final), encoding="utf-8", newline="\n"
    )
    print(output_dir / "detection_diagnostic.json")


def _predict_checkpoint(
    checkpoint: Path,
    images: list[Path],
    output_path: Path,
    *,
    imgsz: int,
    confidence: float,
    nms_iou: float,
    device: str | None,
    resume: bool,
) -> dict[str, list[dict[str, Any]]]:
    existing = _read_prediction_cache(output_path) if resume else {}
    expected_names = {path.name for path in images}
    existing = {
        name: predictions
        for name, predictions in existing.items()
        if name in expected_names
    }
    if set(existing) == expected_names:
        return existing
    remaining = [path for path in images if path.name not in existing]
    if _available_ram_gb() < 4.0:
        raise RuntimeError("Less than 4 GB of physical RAM is available; inference was not started.")
    from ultralytics import YOLO

    model = YOLO(str(checkpoint))
    kwargs: dict[str, Any] = {
        "source": [str(path) for path in remaining],
        "stream": True,
        "imgsz": imgsz,
        "conf": confidence,
        "iou": nms_iou,
        "verbose": False,
        "save": False,
    }
    if device is not None:
        kwargs["device"] = device
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if existing else "w"
    with output_path.open(mode, encoding="utf-8", newline="\n") as handle:
        for result_index, result in enumerate(model.predict(**kwargs)):
            boxes = []
            if result.boxes is not None:
                xywhn = result.boxes.xywhn.detach().cpu().tolist()
                confidences = result.boxes.conf.detach().cpu().tolist()
                boxes = [
                    {
                        "box": [round(float(value), 10) for value in box],
                        "confidence": round(float(score), 10),
                    }
                    for box, score in zip(xywhn, confidences)
                ]
            # Ultralytics may report generic image0.jpg names when a list of
            # sources is streamed. Source order is preserved, so retain the
            # sealed validation member name explicitly.
            record = {
                "image_name": remaining[result_index].name,
                "predictions": boxes,
            }
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            existing[record["image_name"]] = boxes
    del model
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
    if set(existing) != expected_names:
        raise RuntimeError(f"Prediction cache is incomplete: {output_path}")
    return existing


def _resolve_val_images(data_yaml: Path) -> list[Path]:
    import yaml

    payload = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    root = Path(payload.get("path", data_yaml.parent))
    val = payload.get("val")
    if not isinstance(val, str) or "test" in val.lower():
        raise ValueError(f"Invalid or unsafe val entry in {data_yaml}")
    image_root = (root / val).resolve() if not Path(val).is_absolute() else Path(val).resolve()
    suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    return sorted(path for path in image_root.iterdir() if path.suffix.lower() in suffixes)


def _label_for_image(image: Path) -> Path:
    parts = list(image.parts)
    try:
        index = next(i for i, part in enumerate(parts) if part.lower() == "images")
    except StopIteration as error:
        raise ValueError(f"Image is outside a YOLO images tree: {image}") from error
    parts[index] = "labels"
    return Path(*parts).with_suffix(".txt")


def _read_yolo_labels(path: Path) -> list[tuple[float, float, float, float]]:
    boxes = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 5 or int(float(fields[0])) != 0:
            raise ValueError(f"Invalid single-class YOLO label: {path}")
        boxes.append(tuple(float(value) for value in fields[1:]))
    return boxes


def _image_metadata(path: Path) -> tuple[int, int, float]:
    from PIL import Image, ImageStat

    with Image.open(path) as source:
        width, height = source.size
        preview = source.convert("L")
        preview.thumbnail((64, 64))
        luminance = float(ImageStat.Stat(preview).mean[0])
    return int(width), int(height), luminance


def _read_prediction_cache(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    records = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["image_name"]] = record["predictions"]
    return records


def _available_ram_gb() -> float:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return status.ullAvailPhys / (1024**3)


def _validation_fingerprint(images: list[Path]) -> str:
    digest = hashlib.sha256()
    for image in images:
        label = _label_for_image(image)
        digest.update(image.name.encode("utf-8"))
        digest.update(file_sha256(image).encode("ascii"))
        digest.update(file_sha256(label).encode("ascii"))
    return digest.hexdigest()


def _paired_differences(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(item["role"], int(item["seed"])): item for item in models}
    rows = []
    for seed in sorted({int(item["seed"]) for item in models}):
        baseline = by_key[("baseline", seed)]["aggregate"]["outcome_counts"]
        selected = by_key[("selected_hybrid", seed)]["aggregate"]["outcome_counts"]
        keys = sorted(set(baseline) | set(selected))
        rows.append(
            {
                "seed": seed,
                "outcome_count_differences": {
                    key: int(selected.get(key, 0)) - int(baseline.get(key, 0))
                    for key in keys
                },
            }
        )
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_csv(path: Path, models: list[dict[str, Any]]) -> None:
    keys = sorted(
        set().union(*(item["aggregate"]["outcome_counts"] for item in models))
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["role", "seed", "experiment", *keys])
        writer.writeheader()
        for model in models:
            writer.writerow(
                {
                    "role": model["role"],
                    "seed": model["seed"],
                    "experiment": model["experiment"],
                    **model["aggregate"]["outcome_counts"],
                }
            )


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Diagnóstico multisemilla del detector en validación real",
        "",
        f"Se analizaron {report['image_count']} imágenes reales de `val`. `test` no fue consultado.",
        "",
        "| Modelo | Semilla | TP IoU≥0.75 | TP IoU 0.50–0.75 | Error loc. 0.10–0.50 | FN ausente | FP fondo |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in report["models"]:
        counts = model["aggregate"]["outcome_counts"]
        lines.append(
            f"| {model['role']} | {model['seed']} | "
            f"{counts.get('true_positive_iou_ge_075', 0)} | "
            f"{counts.get('localized_iou_050_075', 0)} | "
            f"{counts.get('localization_error_iou_010_050', 0)} | "
            f"{counts.get('false_negative_absent', 0)} | "
            f"{counts.get('false_positive_background', 0)} |"
        )
    lines.extend(
        [
            "",
            "Los conteos usan confianza 0.25 y emparejamiento IoU determinista. Son un diagnóstico operativo, no una reconstrucción de la curva AP completa.",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
