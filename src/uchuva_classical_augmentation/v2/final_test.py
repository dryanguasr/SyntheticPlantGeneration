"""One sealed final-test phase for validation-locked v2 checkpoints."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .labels import YoloBox, read_yolo_labels
from .manifest import file_sha256
from .metrics import Prediction, detection_metrics_at_confidence, stratified_recall
from .profiles import read_profile
from .selection import SELECTION_PROTOCOL_VERSION, paired_interval, verify_selection_lock


def evaluate_locked_final_test(
    *,
    lock_path: str | Path,
    output_dir: str | Path,
    profile_path: str | Path,
    device: str = "0",
) -> dict[str, Any]:
    """Evaluate only lock-authorized checkpoints, without threshold selection."""
    lock_path = Path(lock_path).resolve()
    output_dir = Path(output_dir).resolve()
    summary_path = output_dir / "final_test_summary.json"
    if summary_path.is_file():
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        if existing.get("selection_lock_sha256") != file_sha256(lock_path):
            raise RuntimeError("Final-test summary belongs to a different selection lock.")
        return existing
    lock = verify_selection_lock(lock_path)
    if not lock["selected_scenarios"]:
        summary = {
            "protocol_version": SELECTION_PROTOCOL_VERSION,
            "status": "skipped_no_validation_selected_candidate",
            "selection_lock": str(lock_path),
            "selection_lock_sha256": file_sha256(lock_path),
            "test_consulted": False,
            "historical_test_caveat": lock["historical_test_caveat"],
        }
        _write_json(summary_path, summary)
        return summary

    profile = read_profile(Path(profile_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    start_marker = output_dir / "final_test_access_started.json"
    if not start_marker.exists():
        _write_json(
            start_marker,
            {
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "selection_lock": str(lock_path),
                "selection_lock_sha256": file_sha256(lock_path),
                "authorized_scenarios": ["V2-E0", "V2-E0R", *lock["selected_scenarios"]],
                "purpose": "single_final_standard_and_fixed_threshold_operational_evaluation",
            },
        )
    else:
        marker = json.loads(start_marker.read_text(encoding="utf-8"))
        if marker.get("selection_lock_sha256") != file_sha256(lock_path):
            raise RuntimeError("Final-test output belongs to a different selection lock.")

    results = []
    training_config = lock["training_environment"]["training_config"]
    verified_datasets: set[str] = set()
    for run in lock["locked_runs"]:
        result_path = output_dir / run["scenario"] / f"seed_{run['seed']:02d}.json"
        if result_path.is_file():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        verify_selection_lock(lock_path)
        dataset_key = str(Path(run["data_yaml"]).resolve())
        if dataset_key not in verified_datasets:
            _verify_frozen_test_split(run, profile)
            verified_datasets.add(dataset_key)
        _append_jsonl(
            output_dir / "test_access_log.jsonl",
            {
                "started_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "started",
                "scenario": run["scenario"],
                "seed": run["seed"],
                "checkpoint_sha256": run["checkpoint_sha256"],
            },
        )
        result = _evaluate_one(run, output_dir, profile, device, training_config)
        _write_json(result_path, result)
        _append_jsonl(
            output_dir / "test_access_log.jsonl",
            {
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "complete",
                "scenario": run["scenario"],
                "seed": run["seed"],
                "checkpoint_sha256": run["checkpoint_sha256"],
                "validation_selected_confidence": run["validation_selected_confidence"],
            },
        )
        results.append(result)
    summary = _summarize(results, lock, lock_path)
    _write_json(summary_path, summary)
    return summary


def _evaluate_one(
    run: dict[str, Any],
    output_dir: Path,
    profile: dict[str, Any],
    device: str,
    training_config: dict[str, Any],
) -> dict[str, Any]:
    from ultralytics import YOLO

    import yaml

    checkpoint = Path(run["checkpoint"])
    data_yaml = Path(run["data_yaml"])
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    dataset_root = Path(data["path"])
    if not dataset_root.is_absolute():
        dataset_root = (data_yaml.parent / dataset_root).resolve()
    test_dir = (dataset_root / data["test"]).resolve()
    label_dir = dataset_root / "labels" / "test"
    images = sorted(
        path
        for path in test_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )
    ground_truth = {
        image.name: read_yolo_labels(label_dir / f"{image.stem}.txt") for image in images
    }
    model = YOLO(str(checkpoint))
    standard = model.val(
        data=str(data_yaml),
        split="test",
        imgsz=int(training_config["imgsz"]),
        batch=int(training_config["batch"]),
        device=device,
        workers=int(training_config["workers"]),
        project=str(output_dir / "ultralytics"),
        name=f"{run['scenario'].lower().replace('-', '_')}_seed{run['seed']:02d}",
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    predictions: dict[str, list[Prediction]] = {}
    sources = [str(path) for path in images]
    for image, prediction_result in zip(
        images,
        model.predict(
            source=sources,
            stream=True,
            imgsz=int(training_config["imgsz"]),
            conf=0.001,
            iou=0.70,
            device=device,
            verbose=False,
        ),
        strict=True,
    ):
        values = []
        if prediction_result.boxes is not None:
            boxes = prediction_result.boxes.xywhn.detach().cpu().tolist()
            confidences = prediction_result.boxes.conf.detach().cpu().tolist()
            for box, confidence in zip(boxes, confidences, strict=True):
                values.append(
                    Prediction(
                        YoloBox(0, *[float(value) for value in box]), float(confidence)
                    )
                )
        predictions[image.name] = values
    threshold = float(run["validation_selected_confidence"])
    operational = detection_metrics_at_confidence(
        ground_truth, predictions, confidence=threshold
    )
    difficulty = stratified_recall(
        ground_truth, predictions, profile, confidence=threshold
    )
    return {
        "protocol_version": SELECTION_PROTOCOL_VERSION,
        "evaluation_split": "test",
        "scenario": run["scenario"],
        "role": run["role"],
        "seed": int(run["seed"]),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": file_sha256(checkpoint),
        "checkpoint_rule": run["checkpoint_rule"],
        "confidence_threshold_rule": run["confidence_threshold_rule"],
        "validation_selected_confidence": threshold,
        "standard_metrics": _extract_standard_metrics(standard),
        "fixed_threshold_operational_metrics": operational,
        "difficulty": difficulty,
        "threshold_reselected_on_test": False,
    }


def _verify_frozen_test_split(run: dict[str, Any], profile: dict[str, Any]) -> None:
    """Re-hash the sealed test split against the original domain profile."""
    import yaml

    data_yaml = Path(run["data_yaml"])
    data = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    dataset_root = Path(data["path"])
    if not dataset_root.is_absolute():
        dataset_root = (data_yaml.parent / dataset_root).resolve()
    build_config = json.loads(Path(run["dataset_build_config"]).read_text(encoding="utf-8"))
    if build_config.get("profile_sha256") != profile.get("profile_sha256"):
        raise ValueError("Final-test profile does not match the locked dataset profile.")
    expected = profile["splits"]["test"]["members"]
    expected_names = {item["image"] for item in expected}
    test_dir = (dataset_root / data["test"]).resolve()
    actual_names = {
        path.name
        for path in test_dir.iterdir()
        if path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
    if actual_names != expected_names:
        raise ValueError("Locked test image membership changed.")
    label_dir = dataset_root / "labels" / "test"
    for member in expected:
        image = test_dir / member["image"]
        label = label_dir / member["label"]
        if file_sha256(image) != member["image_sha256"]:
            raise ValueError(f"Locked test image changed: {image}")
        expected_label_hash = member["label_sha256"]
        if expected_label_hash is not None and file_sha256(label) != expected_label_hash:
            raise ValueError(f"Locked test label changed: {label}")


def _extract_standard_metrics(metrics: Any) -> dict[str, float]:
    box = getattr(metrics, "box", None)
    if box is None:
        raise ValueError("Ultralytics result does not expose box metrics.")
    return {
        "precision": float(box.mp),
        "recall": float(box.mr),
        "map50": float(box.map50),
        "map75": float(box.map75),
        "map50_95": float(box.map),
    }


def _summarize(
    results: list[dict[str, Any]], lock: dict[str, Any], lock_path: Path
) -> dict[str, Any]:
    scenarios = sorted({item["scenario"] for item in results})
    aggregates = {}
    for scenario in scenarios:
        selected = [item for item in results if item["scenario"] == scenario]
        aggregates[scenario] = {
            metric: paired_interval(
                [float(item["standard_metrics"][metric]) for item in selected]
            )
            for metric in ("precision", "recall", "map50", "map50_95")
        }
        aggregates[scenario]["fixed_threshold_operational_recall"] = paired_interval(
            [
                float(item["fixed_threshold_operational_metrics"]["recall"])
                for item in selected
            ]
        )
    paired = {}
    by_key = {(item["scenario"], item["seed"]): item for item in results}
    for candidate in lock["selected_scenarios"]:
        paired[candidate] = {}
        for control in ("V2-E0", "V2-E0R"):
            map_deltas = []
            operational_deltas = []
            candidate_seeds = sorted(
                item["seed"] for item in results if item["scenario"] == candidate
            )
            for seed in candidate_seeds:
                candidate_run = by_key[(candidate, seed)]
                control_run = by_key[(control, seed)]
                map_deltas.append(
                    candidate_run["standard_metrics"]["map50_95"]
                    - control_run["standard_metrics"]["map50_95"]
                )
                operational_deltas.append(
                    candidate_run["fixed_threshold_operational_metrics"]["recall"]
                    - control_run["fixed_threshold_operational_metrics"]["recall"]
                )
            paired[candidate][control] = {
                "map50_95_delta": paired_interval(map_deltas),
                "fixed_threshold_operational_recall_delta": paired_interval(
                    operational_deltas
                ),
                "map50_95_positive_seed_count": sum(value > 0 for value in map_deltas),
            }
    return {
        "protocol_version": SELECTION_PROTOCOL_VERSION,
        "status": "complete",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_lock": str(lock_path),
        "selection_lock_sha256": file_sha256(lock_path),
        "test_consulted": True,
        "threshold_reselected_on_test": False,
        "historical_test_caveat": lock["historical_test_caveat"],
        "selected_scenarios": lock["selected_scenarios"],
        "aggregates": aggregates,
        "paired": paired,
        "results": results,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
