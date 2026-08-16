"""Leakage-safe multi-seed real/synthetic training study orchestration."""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .hybrid_experiments import (
    HybridExperimentSpec,
    build_hybrid_experiment_matrix,
    discover_paired_samples,
)
from .hybrid_training import TrainingConfig, extract_detection_metrics


STUDY_PROTOCOL_VERSION = "0.3.0-leakage-repaired-real-validation-sealed"
STUDY_SEEDS = (20260811, 20260812, 20260813)
PHASE_A_SYNTHETIC_COUNTS = (56, 118, 265, 512)
PHASE_B_REAL_COUNTS = (64, 128, 256, 384, 512, 768, 1061)
BASELINE_NAME = "natural_full"
PHASE_A_NAMES = {
    56: "phase_a_synthetic_005",
    118: "phase_a_synthetic_010",
    265: "phase_a_synthetic_020",
    512: "phase_a_synthetic_0325",
}
PHASE_B_NAMES = {
    count: f"phase_b_real_{count:04d}_synthetic_0512"
    for count in PHASE_B_REAL_COUNTS
}


def phase_a_specs() -> tuple[HybridExperimentSpec, ...]:
    specs = [HybridExperimentSpec(BASELINE_NAME, "natural_full", 1.0)]
    specs.extend(
        HybridExperimentSpec(
            PHASE_A_NAMES[count],
            "additive_capped",
            1.0,
            synthetic_count=count,
            selection_group="phase_a_nested_synthetic",
        )
        for count in PHASE_A_SYNTHETIC_COUNTS
    )
    return tuple(specs)


def phase_b_specs() -> tuple[HybridExperimentSpec, ...]:
    return tuple(
        HybridExperimentSpec(
            PHASE_B_NAMES[count],
            "fixed_synthetic_variable_real",
            1.0,
            synthetic_count=512,
            selection_group="phase_b_nested_real",
            real_count=count,
        )
        for count in PHASE_B_REAL_COUNTS
    )


def audit_study_sources(
    *,
    real_root: str | Path,
    synthetic_root: str | Path,
    perceptual_hamming_threshold: int = 2,
    expected_missing_train_ids: Iterable[str] = ("0117",),
) -> dict[str, Any]:
    """Audit real split isolation, labels, and near-duplicate candidates."""
    real_root = Path(real_root).resolve()
    synthetic_root = Path(synthetic_root).resolve()
    real_samples = {
        split: discover_paired_samples(
            real_root / "IMAGENES" / split,
            real_root / "LABELS" / split,
            source_domain="real",
            source_split=split,
        )
        for split in ("train", "val", "test")
    }
    synthetic_train = discover_paired_samples(
        synthetic_root / "images" / "train",
        synthetic_root / "labels" / "train",
        source_domain="synthetic",
        source_split="train",
    )
    errors: list[str] = []
    warnings: list[str] = []
    label_errors: list[dict[str, Any]] = []
    all_samples = [
        sample
        for samples in (*real_samples.values(), synthetic_train)
        for sample in samples
    ]
    for sample in all_samples:
        label_errors.extend(_validate_yolo_label(sample.label_path))
    if label_errors:
        errors.append(f"Found {len(label_errors)} invalid YOLO label rows.")

    real_hashes = {
        split: {_sha256(sample.image_path): sample.sample_id for sample in samples}
        for split, samples in real_samples.items()
    }
    exact_overlaps: list[dict[str, str]] = []
    for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
        for digest in sorted(set(real_hashes[left]) & set(real_hashes[right])):
            exact_overlaps.append(
                {
                    "left_split": left,
                    "left_id": real_hashes[left][digest],
                    "right_split": right,
                    "right_id": real_hashes[right][digest],
                    "sha256": digest,
                }
            )
    if exact_overlaps:
        errors.append(f"Found {len(exact_overlaps)} exact image overlaps across real splits.")

    perceptual_candidates: list[dict[str, Any]] = []
    perceptual_error = ""
    try:
        fingerprints = {
            split: {
                sample.sample_id: _perceptual_fingerprint(sample.image_path)
                for sample in samples
            }
            for split, samples in real_samples.items()
        }
        for left, right in (("train", "val"), ("train", "test"), ("val", "test")):
            for left_id, left_value in fingerprints[left].items():
                for right_id, right_value in fingerprints[right].items():
                    if abs(left_value[1] - right_value[1]) > 0.02:
                        continue
                    distance = (left_value[0] ^ right_value[0]).bit_count()
                    if distance <= perceptual_hamming_threshold:
                        perceptual_candidates.append(
                            {
                                "left_split": left,
                                "left_id": left_id,
                                "right_split": right,
                                "right_id": right_id,
                                "dhash_hamming": distance,
                            }
                        )
    except (ImportError, OSError, ValueError) as error:
        perceptual_error = str(error)
        warnings.append(f"Perceptual duplicate audit was unavailable: {error}")
    if perceptual_candidates:
        warnings.append(
            f"Found {len(perceptual_candidates)} perceptual candidates requiring review."
        )

    expected_counts = {
        "real_train": 1061,
        "real_val": 133,
        "real_test": 133,
        "synthetic_train": 512,
    }
    actual_counts = {
        "real_train": len(real_samples["train"]),
        "real_val": len(real_samples["val"]),
        "real_test": len(real_samples["test"]),
        "synthetic_train": len(synthetic_train),
    }
    for name, expected in expected_counts.items():
        if actual_counts[name] != expected:
            errors.append(f"Expected {expected} paired {name} samples, found {actual_counts[name]}.")
    missing_real_labels = {
        split: sorted(
            {
                path.stem
                for path in (real_root / "IMAGENES" / split).glob("*")
                if path.is_file()
            }
            - {
                path.stem
                for path in (real_root / "LABELS" / split).glob("*.txt")
                if path.is_file()
            }
        )
        for split in ("train", "val", "test")
    }
    expected_missing_train = sorted(str(item) for item in expected_missing_train_ids)
    if missing_real_labels["train"] != expected_missing_train:
        warnings.append(
            "The unpaired real-train images differ from the documented expectation: "
            f"expected {expected_missing_train}, found {missing_real_labels['train']}."
        )
    return {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
        "real_root": str(real_root),
        "synthetic_root": str(synthetic_root),
        "paired_counts": actual_counts,
        "expected_counts": expected_counts,
        "missing_real_label_ids": missing_real_labels,
        "exact_cross_split_overlaps": exact_overlaps,
        "perceptual_hamming_threshold": perceptual_hamming_threshold,
        "perceptual_candidates": perceptual_candidates,
        "perceptual_audit_error": perceptual_error,
        "invalid_label_rows": label_errors[:100],
        "policy": {
            "training_real_split": "train",
            "training_synthetic_split": "train",
            "validation_domain": "real_only",
            "test_domain": "real_only_sealed_until_selection",
            "synthetic_val_or_test_used": False,
        },
    }


def materialize_repaired_real_partition(
    *,
    real_root: str | Path,
    output_root: str | Path,
    source_audit: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    """Materialize a reviewed, group-safe real partition without editing originals."""
    real_root = Path(real_root).resolve()
    output_root = Path(output_root).resolve()
    manifest_path = output_root / "partition_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        validate_perceptual_review(source_audit, review)
        if manifest.get("review_sha256") != _json_sha256(review):
            raise ValueError("Existing repaired partition was made from a different review.")
        return manifest
    if output_root.exists():
        raise FileExistsError(
            f"Incomplete repaired partition already exists: {output_root}"
        )

    validate_perceptual_review(source_audit, review)
    samples = {
        (split, sample.sample_id): sample
        for split in ("train", "val", "test")
        for sample in discover_paired_samples(
            real_root / "IMAGENES" / split,
            real_root / "LABELS" / split,
            source_domain="real",
            source_split=split,
        )
    }
    assignments = {key: key[0] for key in samples}
    for item in review["split_overrides"]:
        key = (str(item["source_split"]), str(item["sample_id"]))
        if key not in samples:
            raise ValueError(f"Unknown split override sample: {key}.")
        destination = str(item["destination_split"])
        if destination not in {"train", "val", "test"}:
            raise ValueError(f"Invalid destination split for {key}: {destination}.")
        assignments[key] = destination

    confirmed_pairs = _confirmed_review_pairs(review)
    for left, right in confirmed_pairs:
        if assignments[left] != assignments[right]:
            raise ValueError(
                "Confirmed near-duplicate pair remains split across cohorts: "
                f"{left} -> {assignments[left]}, {right} -> {assignments[right]}."
            )
    counts = {
        split: sum(destination == split for destination in assignments.values())
        for split in ("train", "val", "test")
    }
    expected_counts = review.get(
        "expected_partition_counts", {"train": 1061, "val": 133, "test": 133}
    )
    if counts != expected_counts:
        raise ValueError(
            f"Repaired partition counts differ: expected {expected_counts}, found {counts}."
        )

    records = []
    for key in sorted(samples):
        sample = samples[key]
        destination_split = assignments[key]
        destination_stem = f"{sample.source_split}_{sample.sample_id}"
        image_destination = (
            output_root
            / "IMAGENES"
            / destination_split
            / f"{destination_stem}{sample.image_path.suffix.lower()}"
        )
        label_destination = (
            output_root / "LABELS" / destination_split / f"{destination_stem}.txt"
        )
        image_destination.parent.mkdir(parents=True, exist_ok=True)
        label_destination.parent.mkdir(parents=True, exist_ok=True)
        _hardlink_or_copy(sample.image_path, image_destination)
        _hardlink_or_copy(sample.label_path, label_destination)
        records.append(
            {
                "source_split": sample.source_split,
                "source_sample_id": sample.sample_id,
                "destination_split": destination_split,
                "destination_stem": destination_stem,
                "moved": sample.source_split != destination_split,
                "source_image": str(sample.image_path),
                "source_label": str(sample.label_path),
            }
        )
    manifest = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "status": "materialized",
        "source_real_root": str(real_root),
        "output_root": str(output_root),
        "review_sha256": _json_sha256(review),
        "counts": counts,
        "moved_count": sum(item["moved"] for item in records),
        "excluded_unpaired_ids": ["0117"],
        "records": records,
    }
    _write_json(manifest_path, manifest)
    return manifest


def validate_perceptual_review(
    source_audit: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    """Require an explicit verdict for every perceptual candidate in the audit."""
    audit_pairs = {
        _normalized_pair(item) for item in source_audit.get("perceptual_candidates", [])
    }
    reviewed_items = review.get("candidate_reviews", [])
    reviewed_pairs = {_normalized_pair(item) for item in reviewed_items}
    if reviewed_pairs != audit_pairs:
        missing = sorted(audit_pairs - reviewed_pairs)
        unexpected = sorted(reviewed_pairs - audit_pairs)
        raise ValueError(
            f"Perceptual review does not cover the audit exactly; "
            f"missing={missing}, unexpected={unexpected}."
        )
    allowed = {"confirmed_near_duplicate", "different_scene"}
    invalid = [
        item for item in reviewed_items if item.get("verdict") not in allowed
    ]
    if invalid:
        raise ValueError(f"Invalid perceptual review verdicts: {invalid}.")
    if not review.get("reviewer") or not review.get("reviewed_at_utc"):
        raise ValueError("Perceptual review must record reviewer and review timestamp.")
    return {
        "status": "valid",
        "reviewed_candidate_count": len(reviewed_items),
        "confirmed_near_duplicate_count": sum(
            item["verdict"] == "confirmed_near_duplicate" for item in reviewed_items
        ),
    }


def prepare_study_matrices(
    *,
    real_root: str | Path,
    synthetic_root: str | Path,
    study_root: str | Path,
    seeds: Iterable[int] = STUDY_SEEDS,
) -> dict[str, Any]:
    """Prepare phase A and phase B matrices for every independent seed."""
    study_root = Path(study_root).resolve()
    matrices: dict[str, dict[str, str]] = {}
    for seed in seeds:
        seed_key = str(int(seed))
        matrices[seed_key] = {}
        for phase, specs in (("phase_a", phase_a_specs()), ("phase_b", phase_b_specs())):
            matrix_root = study_root / "matrices" / f"seed_{seed}" / phase
            matrix_path = matrix_root / "matrix.json"
            if matrix_path.is_file():
                matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
                expected_names = [spec.name for spec in specs]
                actual_names = [item["spec"]["name"] for item in matrix["experiments"]]
                if actual_names != expected_names:
                    raise ValueError(f"Existing matrix does not match {phase} specs: {matrix_root}")
            else:
                build_hybrid_experiment_matrix(
                    real_root=real_root,
                    synthetic_root=synthetic_root,
                    output_root=matrix_root,
                    seed=int(seed),
                    experiment_specs=specs,
                )
            matrices[seed_key][phase] = str(matrix_root)
    report = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "seeds": [int(seed) for seed in seeds],
        "matrices": matrices,
    }
    _write_json(study_root / "matrices.json", report)
    return report


def audit_prepared_matrices(study_root: str | Path) -> dict[str, Any]:
    """Verify materialized matrices preserve the intended real-only held-outs."""
    study_root = Path(study_root).resolve()
    index = json.loads((study_root / "matrices.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    summaries: list[dict[str, Any]] = []
    for seed, phases in index["matrices"].items():
        for phase, matrix_root_text in phases.items():
            matrix_root = Path(matrix_root_text)
            matrix = json.loads((matrix_root / "matrix.json").read_text(encoding="utf-8"))
            for experiment in matrix["experiments"]:
                manifest_path = Path(experiment["dataset_root"]) / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                records = manifest["records"]
                held_out = [
                    item for item in records if item["destination_split"] in {"val", "test"}
                ]
                if not held_out or any(item["source_domain"] != "real" for item in held_out):
                    errors.append(f"Non-real held-out data in {manifest_path}.")
                if any(
                    item["source_split"] != item["destination_split"] for item in held_out
                ):
                    errors.append(f"Held-out split remapping in {manifest_path}.")
                train_sources = {
                    (item["source_domain"], item["source_split"], item["source_sample_id"])
                    for item in records
                    if item["destination_split"] == "train"
                }
                held_out_sources = {
                    (item["source_domain"], item["source_split"], item["source_sample_id"])
                    for item in held_out
                }
                if train_sources & held_out_sources:
                    errors.append(f"Source overlap in {manifest_path}.")
                summaries.append(
                    {
                        "seed": int(seed),
                        "phase": phase,
                        "experiment": experiment["spec"]["name"],
                        "counts": experiment["counts"],
                    }
                )
    return {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "experiments": summaries,
    }


def run_validation_experiment(
    *,
    matrix_root: str | Path,
    experiment_name: str,
    output_root: str | Path,
    config: TrainingConfig,
    minimum_available_ram_gb: float = 4.0,
) -> dict[str, Any]:
    """Train or resume one condition and evaluate its best checkpoint on real val."""
    matrix_root = Path(matrix_root).resolve()
    output_root = Path(output_root).resolve()
    result_path = output_root / experiment_name / "validation_result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    available = available_ram_gb()
    if available < minimum_available_ram_gb:
        raise RuntimeError(
            f"Only {available:.2f} GB RAM available; {minimum_available_ram_gb:.2f} GB required."
        )
    matrix = json.loads((matrix_root / "matrix.json").read_text(encoding="utf-8"))
    experiment = next(
        (item for item in matrix["experiments"] if item["spec"]["name"] == experiment_name),
        None,
    )
    if experiment is None:
        raise ValueError(f"Unknown experiment {experiment_name!r} in {matrix_root}.")
    dataset_root = Path(experiment["dataset_root"]).resolve()
    data_yaml = dataset_root / "data.yaml"
    run_dir = output_root / experiment_name
    weights_dir = run_dir / "weights"
    last_checkpoint = weights_dir / "last.pt"
    YOLO = _load_yolo()
    if last_checkpoint.is_file() and _completed_epoch(run_dir / "results.csv") < config.epochs:
        YOLO(str(last_checkpoint)).train(
            resume=True,
            device=config.device,
            workers=config.workers,
        )
    elif not (weights_dir / "best.pt").is_file():
        YOLO(config.model).train(
            data=str(data_yaml),
            epochs=config.epochs,
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            patience=config.patience,
            seed=config.seed,
            deterministic=True,
            project=str(output_root),
            name=experiment_name,
            exist_ok=True,
            plots=True,
            verbose=True,
        )
    best_checkpoint = weights_dir / "best.pt"
    if not best_checkpoint.is_file():
        raise FileNotFoundError(f"Best checkpoint missing for {experiment_name}.")
    validation = YOLO(str(best_checkpoint)).val(
        data=str(data_yaml),
        split="val",
        imgsz=config.image_size,
        batch=config.batch,
        device=config.device,
        workers=config.workers,
        project=str(output_root / "validation_evaluations"),
        name=experiment_name,
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    metrics = _with_f1(extract_detection_metrics(validation))
    result = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "evaluation_split": "val",
        "evaluation_domain": "real_only",
        "experiment": experiment_name,
        "dataset_counts": experiment["counts"],
        "achieved_train_fraction": experiment["achieved_train_fraction"],
        "config": asdict(config),
        "data_yaml": str(data_yaml),
        "best_checkpoint": str(best_checkpoint.resolve()),
        "best_checkpoint_sha256": _sha256(best_checkpoint),
        "validation_metrics": metrics,
        "training_curve": _training_curve_summary(run_dir / "results.csv"),
        "environment": _environment_report(),
    }
    _write_json(result_path, result)
    return result


def aggregate_validation_results(
    results: Iterable[dict[str, Any]],
    *,
    baseline_results: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate validation metrics and paired seed deltas."""
    result_list = list(results)
    if not result_list:
        raise ValueError("At least one validation result is required.")
    by_experiment: dict[str, list[dict[str, Any]]] = {}
    for result in result_list:
        by_experiment.setdefault(result["experiment"], []).append(result)
    baseline_by_seed = {
        int(item["config"]["seed"]): item
        for item in (baseline_results or [])
    }
    aggregates: dict[str, Any] = {}
    for name, items in sorted(by_experiment.items()):
        items = sorted(items, key=lambda item: int(item["config"]["seed"]))
        metric_names = tuple(items[0]["validation_metrics"])
        metrics = {
            metric: _summary_stats(
                [float(item["validation_metrics"][metric]) for item in items]
            )
            for metric in metric_names
        }
        paired = []
        for item in items:
            seed = int(item["config"]["seed"])
            if seed in baseline_by_seed:
                baseline = baseline_by_seed[seed]
                paired.append(
                    {
                        "seed": seed,
                        "map50_95_delta": float(item["validation_metrics"]["map50_95"])
                        - float(baseline["validation_metrics"]["map50_95"]),
                        "recall_delta": float(item["validation_metrics"]["recall"])
                        - float(baseline["validation_metrics"]["recall"]),
                    }
                )
        aggregates[name] = {
            "experiment": name,
            "seed_count": len(items),
            "seeds": [int(item["config"]["seed"]) for item in items],
            "dataset_counts": items[0]["dataset_counts"],
            "metrics": metrics,
            "paired_deltas": paired,
            "paired_map50_95_delta": _summary_stats(
                [item["map50_95_delta"] for item in paired]
            )
            if paired
            else None,
            "paired_recall_delta": _summary_stats(
                [item["recall_delta"] for item in paired]
            )
            if paired
            else None,
            "positive_map50_95_seed_count": sum(
                item["map50_95_delta"] > 0.0 for item in paired
            ),
            "within_noninferiority_seed_count": sum(
                item["map50_95_delta"] >= -0.005 for item in paired
            ),
            "results": items,
        }
    return {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "evaluation_split": "val",
        "experiments": aggregates,
    }


def decide_phase_a(aggregate: dict[str, Any]) -> dict[str, Any]:
    """Select the smallest practically useful additive dose using real val only."""
    candidates = []
    for count in PHASE_A_SYNTHETIC_COUNTS:
        name = PHASE_A_NAMES[count]
        item = aggregate["experiments"][name]
        map_delta = item["paired_map50_95_delta"]["mean"]
        recall_delta = item["paired_recall_delta"]["mean"]
        practical = (
            map_delta >= 0.005
            and item["positive_map50_95_seed_count"] >= 2
            and recall_delta >= -0.01
        )
        candidates.append(
            {
                "experiment": name,
                "synthetic_count": count,
                "map50_95_mean": item["metrics"]["map50_95"]["mean"],
                "map50_95_delta_mean": map_delta,
                "recall_delta_mean": recall_delta,
                "positive_seed_count": item["positive_map50_95_seed_count"],
                "practical_improvement": practical,
            }
        )
    eligible = [item for item in candidates if item["practical_improvement"]]
    selected = None
    if eligible:
        best_score = max(item["map50_95_mean"] for item in eligible)
        selected = min(
            (item for item in eligible if item["map50_95_mean"] >= best_score - 0.002),
            key=lambda item: item["synthetic_count"],
        )
    return {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "phase": "phase_a",
        "criteria": {
            "minimum_map50_95_delta": 0.005,
            "minimum_positive_seed_count": 2,
            "minimum_recall_delta": -0.01,
            "tie_tolerance": 0.002,
            "tie_break": "lowest_synthetic_count",
        },
        "candidates": candidates,
        "success": selected is not None,
        "selected": selected,
        "next_phase": "final_test" if selected else "phase_b",
    }


def decide_phase_b_cohort(
    aggregate_item: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate one ascending-real cohort against the fixed full-real baseline."""
    map_delta = aggregate_item["paired_map50_95_delta"]["mean"]
    recall_delta = aggregate_item["paired_recall_delta"]["mean"]
    success = (
        map_delta >= -0.005
        and aggregate_item["within_noninferiority_seed_count"] >= 2
        and recall_delta >= -0.01
    )
    worsening = (
        not success
        and map_delta <= -0.005
        and sum(item["map50_95_delta"] < 0.0 for item in aggregate_item["paired_deltas"])
        >= 2
    )
    return {
        "experiment": aggregate_item["experiment"],
        "real_count": aggregate_item["dataset_counts"]["train_real"],
        "synthetic_count": aggregate_item["dataset_counts"]["train_synthetic"],
        "map50_95_delta_mean": map_delta,
        "recall_delta_mean": recall_delta,
        "within_noninferiority_seed_count": aggregate_item[
            "within_noninferiority_seed_count"
        ],
        "success": success,
        "worsening": worsening,
    }


def should_stop_phase_b(cohort_decisions: Iterable[dict[str, Any]]) -> bool:
    """Stop after two worsening cohorts, whether consecutive or not."""
    return sum(bool(item.get("worsening")) for item in cohort_decisions) >= 2


def create_selection_lock(
    *,
    study_root: str | Path,
    phase: str,
    selected_results: Iterable[dict[str, Any]],
    baseline_results: Iterable[dict[str, Any]],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Freeze the validation-selected checkpoints before any test evaluation."""
    study_root = Path(study_root).resolve()
    lock_path = study_root / "selection.lock.json"
    if lock_path.exists():
        return json.loads(lock_path.read_text(encoding="utf-8"))
    selected = sorted(selected_results, key=lambda item: int(item["config"]["seed"]))
    baselines = sorted(baseline_results, key=lambda item: int(item["config"]["seed"]))
    payload = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "status": "locked",
        "locked_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_phase": phase,
        "selection_split": "val",
        "selection_domain": "real_only",
        "test_policy": "baseline_and_locked_winner_only",
        "historical_test_caveat": (
            "Real test images were never used for training, but were evaluated in "
            "historical experiments before this sealed study."
        ),
        "decision": decision,
        "baseline": [_locked_checkpoint(item) for item in baselines],
        "selected": [_locked_checkpoint(item) for item in selected],
    }
    if {item["seed"] for item in payload["baseline"]} != {
        item["seed"] for item in payload["selected"]
    }:
        raise ValueError("Baseline and selected checkpoints do not cover the same seeds.")
    _write_json(lock_path, payload)
    return payload


def evaluate_selection_lock_on_test(
    *,
    lock_path: str | Path,
    output_root: str | Path,
    config_template: TrainingConfig,
    minimum_available_ram_gb: float = 4.0,
) -> dict[str, Any]:
    """Evaluate only the locked baseline and winner on the real test split."""
    lock_path = Path(lock_path).resolve()
    output_root = Path(output_root).resolve()
    summary_path = output_root / "final_test_summary.json"
    if summary_path.is_file():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("status") != "locked":
        raise ValueError("Selection lock is not sealed.")
    allowed = {
        (role, int(item["seed"]), item["checkpoint_sha256"])
        for role in ("baseline", "selected")
        for item in lock[role]
    }
    YOLO = _load_yolo()
    results: list[dict[str, Any]] = []
    for role in ("baseline", "selected"):
        for item in lock[role]:
            result_path = output_root / role / f"seed_{item['seed']}" / "test_result.json"
            if result_path.is_file():
                results.append(json.loads(result_path.read_text(encoding="utf-8")))
                continue
            if available_ram_gb() < minimum_available_ram_gb:
                raise RuntimeError("Insufficient available RAM for sealed test evaluation.")
            checkpoint = Path(item["checkpoint"])
            digest = _sha256(checkpoint)
            key = (role, int(item["seed"]), digest)
            if key not in allowed:
                raise ValueError("Attempted test evaluation outside the selection lock.")
            config = TrainingConfig(**{**asdict(config_template), "seed": int(item["seed"])})
            metrics = YOLO(str(checkpoint)).val(
                data=item["data_yaml"],
                split="test",
                imgsz=config.image_size,
                batch=config.batch,
                device=config.device,
                workers=config.workers,
                project=str(output_root / "evaluations"),
                name=f"{role}_seed_{item['seed']}",
                exist_ok=True,
                plots=True,
                verbose=True,
            )
            result = {
                "protocol_version": STUDY_PROTOCOL_VERSION,
                "role": role,
                "experiment": item["experiment"],
                "seed": int(item["seed"]),
                "evaluation_split": "test",
                "evaluation_domain": "real_only",
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": digest,
                "test_metrics": _with_f1(extract_detection_metrics(metrics)),
            }
            _write_json(result_path, result)
            _append_jsonl(
                output_root / "test_access_log.jsonl",
                {
                    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "role": role,
                    "experiment": item["experiment"],
                    "seed": int(item["seed"]),
                    "checkpoint_sha256": digest,
                },
            )
            results.append(result)
    grouped = {
        role: [item for item in results if item["role"] == role]
        for role in ("baseline", "selected")
    }
    aggregates = {
        role: {
            metric: _summary_stats(
                [float(item["test_metrics"][metric]) for item in grouped[role]]
            )
            for metric in grouped[role][0]["test_metrics"]
        }
        for role in grouped
    }
    paired_deltas = []
    baseline_by_seed = {item["seed"]: item for item in grouped["baseline"]}
    for item in grouped["selected"]:
        baseline = baseline_by_seed[item["seed"]]
        paired_deltas.append(
            {
                "seed": item["seed"],
                "map50_95_delta": item["test_metrics"]["map50_95"]
                - baseline["test_metrics"]["map50_95"],
                "recall_delta": item["test_metrics"]["recall"]
                - baseline["test_metrics"]["recall"],
            }
        )
    summary = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "selection_lock": str(lock_path),
        "historical_test_caveat": lock["historical_test_caveat"],
        "aggregates": aggregates,
        "paired_deltas": paired_deltas,
        "paired_map50_95_delta": _summary_stats(
            [item["map50_95_delta"] for item in paired_deltas]
        ),
        "paired_recall_delta": _summary_stats(
            [item["recall_delta"] for item in paired_deltas]
        ),
        "results": results,
    }
    _write_json(summary_path, summary)
    return summary


def available_ram_gb() -> float:
    """Return physical RAM currently available without third-party dependencies."""
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("GlobalMemoryStatusEx failed.")
        return status.available_physical / (1024**3)
    page_size = os.sysconf("SC_PAGE_SIZE")
    available_pages = os.sysconf("SC_AVPHYS_PAGES")
    return page_size * available_pages / (1024**3)


def _validate_yolo_label(path: Path) -> list[dict[str, Any]]:
    errors = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split()
        reason = ""
        if len(parts) != 5:
            reason = "token_count"
        else:
            try:
                class_id = int(parts[0])
                values = [float(value) for value in parts[1:]]
                if (
                    class_id != 0
                    or not all(0.0 <= value <= 1.0 for value in values)
                    or values[2] <= 0.0
                    or values[3] <= 0.0
                ):
                    reason = "range_or_class"
            except ValueError:
                reason = "parse"
        if reason:
            errors.append(
                {"path": str(path), "line": line_number, "reason": reason, "value": line}
            )
    return errors


def _perceptual_fingerprint(path: Path) -> tuple[int, float]:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise ImportError("Pillow is required for perceptual duplicate auditing.") from error
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        aspect = width / max(height, 1)
        gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
        pixels = list(gray.getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            left = pixels[row * 9 + column]
            right = pixels[row * 9 + column + 1]
            value = (value << 1) | int(left > right)
    return value, aspect


def _load_yolo() -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError("Ultralytics is required for hybrid training.") from error
    return YOLO


def _with_f1(metrics: dict[str, float]) -> dict[str, float]:
    precision = metrics["precision"]
    recall = metrics["recall"]
    denominator = precision + recall
    return {**metrics, "f1": 2.0 * precision * recall / denominator if denominator else 0.0}


def _summary_stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("Cannot summarize an empty sequence.")
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def _training_curve_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"results_csv": str(path), "epoch_count": 0}
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [
            {key.strip(): value.strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    metric_key = next(
        (key for key in rows[0] if "mAP50-95" in key),
        None,
    ) if rows else None
    best_row = max(rows, key=lambda row: float(row.get(metric_key, "-inf"))) if metric_key else None
    time_values = [float(row["time"]) for row in rows if row.get("time")]
    return {
        "results_csv": str(path),
        "epoch_count": len(rows),
        "best_epoch": int(float(best_row["epoch"])) if best_row and best_row.get("epoch") else None,
        "best_validation_map50_95_during_training": float(best_row[metric_key])
        if best_row and metric_key
        else None,
        "duration_seconds": max(time_values) if time_values else None,
    }


def _completed_epoch(results_csv: Path) -> int:
    summary = _training_curve_summary(results_csv)
    return int(summary.get("epoch_count", 0))


def _locked_checkpoint(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment": result["experiment"],
        "seed": int(result["config"]["seed"]),
        "checkpoint": result["best_checkpoint"],
        "checkpoint_sha256": result["best_checkpoint_sha256"],
        "data_yaml": result["data_yaml"],
        "validation_metrics": result["validation_metrics"],
    }


def _environment_report() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "ultralytics": _package_version("ultralytics"),
        "torch": _package_version("torch"),
    }


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_pair(item: dict[str, Any]) -> tuple[tuple[str, str], tuple[str, str]]:
    left = (str(item["left_split"]), str(item["left_id"]))
    right = (str(item["right_split"]), str(item["right_id"]))
    ordered = sorted((left, right))
    return ordered[0], ordered[1]


def _confirmed_review_pairs(
    review: dict[str, Any],
) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    return [
        _normalized_pair(item)
        for item in review.get("candidate_reviews", [])
        if item.get("verdict") == "confirmed_near_duplicate"
    ]


def _hardlink_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
