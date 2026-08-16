"""Prepare leakage-safe real/synthetic training matrices without ML dependencies."""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MATRIX_VERSION = "0.1.0-real-test-held-out"
MATRIX_MANIFEST_FILENAME = "matrix.json"


@dataclass(frozen=True)
class PairedSample:
    source_domain: str
    source_split: str
    sample_id: str
    image_path: Path
    label_path: Path


@dataclass(frozen=True)
class HybridExperimentSpec:
    name: str
    mode: str
    real_fraction: float
    synthetic_count: int | None = None
    selection_group: str | None = None
    real_count: int | None = None


DEFAULT_EXPERIMENT_SPECS = (
    HybridExperimentSpec("natural_full", "natural_full", 1.00),
    HybridExperimentSpec("hybrid_additive_all", "additive", 1.00),
    HybridExperimentSpec("hybrid_75_real_25_synthetic", "fixed_budget", 0.75),
    HybridExperimentSpec("hybrid_50_real_50_synthetic", "fixed_budget", 0.50),
    HybridExperimentSpec("hybrid_25_real_75_synthetic", "fixed_budget", 0.25),
)


def discover_paired_samples(
    images_dir: str | Path,
    labels_dir: str | Path,
    *,
    source_domain: str,
    source_split: str,
) -> list[PairedSample]:
    """Return only image/label pairs; unmatched originals remain untouched."""
    image_root = Path(images_dir)
    label_root = Path(labels_dir)
    images = {
        path.stem: path
        for path in sorted(image_root.glob("*"))
        if path.suffix.lower() in IMAGE_SUFFIXES
    }
    labels = {path.stem: path for path in sorted(label_root.glob("*.txt"))}
    return [
        PairedSample(
            source_domain=source_domain,
            source_split=source_split,
            sample_id=sample_id,
            image_path=images[sample_id].resolve(),
            label_path=labels[sample_id].resolve(),
        )
        for sample_id in sorted(set(images) & set(labels))
    ]


def build_hybrid_experiment_matrix(
    *,
    real_root: str | Path,
    synthetic_root: str | Path,
    output_root: str | Path,
    seed: int = 20260731,
    fixed_budget: int | None = None,
    experiment_specs: Iterable[HybridExperimentSpec] = DEFAULT_EXPERIMENT_SPECS,
) -> dict[str, Any]:
    """Create hard-linked datasets with real-only validation and test splits."""
    real_root = Path(real_root).resolve()
    synthetic_root = Path(synthetic_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError(
            f"Experiment output already exists: {output_root}. Use a new directory."
        )

    real = {
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
    if not real["train"] or not real["val"] or not real["test"]:
        raise ValueError("Real train, val, and test must each contain paired samples.")
    if not synthetic_train:
        raise ValueError("Synthetic train must contain paired samples.")
    budget = int(fixed_budget or len(real["train"]))
    if budget < 1 or budget > len(real["train"]):
        raise ValueError("fixed_budget must remain within 1..real_train_count.")

    specs = tuple(experiment_specs)
    output_root.mkdir(parents=True)
    reports = []
    for spec in specs:
        reports.append(
            _build_one_experiment(
                spec=spec,
                real=real,
                synthetic_train=synthetic_train,
                output_root=output_root,
                seed=seed,
                budget=budget,
            )
        )
    matrix = {
        "matrix_version": MATRIX_VERSION,
        "seed": seed,
        "real_root": str(real_root),
        "synthetic_root": str(synthetic_root),
        "fixed_training_budget": budget,
        "policy": {
            "original_dataset_writes": False,
            "validation_domain": "real_only",
            "test_domain": "real_only_held_out",
            "synthetic_test_used_for_model_selection": False,
            "duplicate_policy": "deterministic_repetition_when_ratio_exceeds_unique_synthetic_train",
        },
        "experiments": reports,
    }
    _write_json(output_root / MATRIX_MANIFEST_FILENAME, matrix)
    return matrix


def _build_one_experiment(
    *,
    spec: HybridExperimentSpec,
    real: dict[str, list[PairedSample]],
    synthetic_train: list[PairedSample],
    output_root: Path,
    seed: int,
    budget: int,
) -> dict[str, Any]:
    if not 0.0 <= spec.real_fraction <= 1.0:
        raise ValueError(f"Invalid real_fraction for {spec.name}: {spec.real_fraction}")
    experiment_root = output_root / spec.name
    rng = random.Random(_stable_seed(seed, spec.selection_group or spec.name))
    if spec.mode == "natural_full":
        selected_real = [(sample, 0) for sample in real["train"]]
        selected_synthetic: list[tuple[PairedSample, int]] = []
    elif spec.mode == "additive":
        selected_real = [(sample, 0) for sample in real["train"]]
        selected_synthetic = [(sample, 0) for sample in synthetic_train]
    elif spec.mode == "additive_capped":
        if spec.synthetic_count is None or spec.synthetic_count < 1:
            raise ValueError(
                f"additive_capped requires a positive synthetic_count: {spec.name}"
            )
        selected_real = [(sample, 0) for sample in real["train"]]
        selected_synthetic = _select_samples(
            synthetic_train,
            spec.synthetic_count,
            rng,
        )
    elif spec.mode == "fixed_synthetic_variable_real":
        if spec.real_count is None or spec.real_count < 1:
            raise ValueError(
                f"fixed_synthetic_variable_real requires a positive real_count: {spec.name}"
            )
        if spec.synthetic_count is None or spec.synthetic_count < 1:
            raise ValueError(
                "fixed_synthetic_variable_real requires a positive "
                f"synthetic_count: {spec.name}"
            )
        selected_real = _select_samples(real["train"], spec.real_count, rng)
        selected_synthetic = _select_samples(
            synthetic_train,
            spec.synthetic_count,
            rng,
        )
    elif spec.mode == "fixed_budget":
        real_count = int(round(budget * spec.real_fraction))
        synthetic_count = budget - real_count
        selected_real = _select_samples(real["train"], real_count, rng)
        selected_synthetic = _select_samples(
            synthetic_train,
            synthetic_count,
            rng,
            allow_repetition=True,
        )
    else:
        raise ValueError(f"Unknown hybrid experiment mode: {spec.mode}")

    records: list[dict[str, Any]] = []
    records.extend(
        _materialize_split(
            experiment_root,
            "train",
            selected_real + selected_synthetic,
        )
    )
    for split in ("val", "test"):
        records.extend(
            _materialize_split(
                experiment_root,
                split,
                [(sample, 0) for sample in real[split]],
            )
        )
    _write_data_yaml(experiment_root)
    train_real = sum(
        item["source_domain"] == "real" and item["destination_split"] == "train"
        for item in records
    )
    train_synthetic = sum(
        item["source_domain"] == "synthetic"
        and item["destination_split"] == "train"
        for item in records
    )
    total_train = train_real + train_synthetic
    report = {
        "spec": asdict(spec),
        "dataset_root": str(experiment_root),
        "data_yaml": str(experiment_root / "data.yaml"),
        "counts": {
            "train_total": total_train,
            "train_real": train_real,
            "train_synthetic": train_synthetic,
            "val_real": len(real["val"]),
            "test_real": len(real["test"]),
        },
        "achieved_train_fraction": {
            "real": round(train_real / total_train, 6),
            "synthetic": round(train_synthetic / total_train, 6),
        },
        "synthetic_repeat_count": sum(
            item["source_domain"] == "synthetic" and item["repeat_index"] > 0
            for item in records
            if item["destination_split"] == "train"
        ),
    }
    _write_json(experiment_root / "manifest.json", {**report, "records": records})
    return report


def _select_samples(
    samples: list[PairedSample],
    count: int,
    rng: random.Random,
    *,
    allow_repetition: bool = False,
) -> list[tuple[PairedSample, int]]:
    if count <= 0:
        return []
    if count > len(samples) and not allow_repetition:
        raise ValueError("Requested more unique samples than available.")
    result: list[tuple[PairedSample, int]] = []
    repeat_index = 0
    while len(result) < count:
        cycle = samples[:]
        rng.shuffle(cycle)
        for sample in cycle:
            if len(result) >= count:
                break
            result.append((sample, repeat_index))
        repeat_index += 1
    return result


def _materialize_split(
    experiment_root: Path,
    destination_split: str,
    samples: list[tuple[PairedSample, int]],
) -> list[dict[str, Any]]:
    images_dir = experiment_root / "images" / destination_split
    labels_dir = experiment_root / "labels" / destination_split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for ordinal, (sample, repeat_index) in enumerate(samples):
        stem = (
            f"{sample.source_domain}_{sample.source_split}_{sample.sample_id}"
            f"_r{repeat_index:03d}_n{ordinal:05d}"
        )
        image_destination = images_dir / f"{stem}{sample.image_path.suffix.lower()}"
        label_destination = labels_dir / f"{stem}.txt"
        _hardlink_or_copy(sample.image_path, image_destination)
        _hardlink_or_copy(sample.label_path, label_destination)
        records.append(
            {
                "destination_split": destination_split,
                "destination_stem": stem,
                "source_domain": sample.source_domain,
                "source_split": sample.source_split,
                "source_sample_id": sample.sample_id,
                "source_image": str(sample.image_path),
                "source_label": str(sample.label_path),
                "repeat_index": repeat_index,
            }
        )
    return records


def _hardlink_or_copy(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _write_data_yaml(root: Path) -> None:
    text = (
        f'path: "{root.as_posix()}"\n'
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        "  0: calyx\n"
    )
    (root / "data.yaml").write_text(text, encoding="utf-8", newline="\n")


def _stable_seed(seed: int, name: str) -> int:
    digest = hashlib.sha256(f"{seed}:{name}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
