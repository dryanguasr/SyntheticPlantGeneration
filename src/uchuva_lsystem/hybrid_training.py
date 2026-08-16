"""Run fair Ultralytics experiments over a prepared real/synthetic matrix.

Ultralytics is imported only when training starts.  The repository's pure
generation and validation modules therefore remain usable without ML packages.
"""

from __future__ import annotations

import copy
import importlib.metadata
import json
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .hybrid_experiments import MATRIX_MANIFEST_FILENAME


TRAINING_PROTOCOL_VERSION = "0.1.0-natural-test-fixed"


@dataclass(frozen=True)
class TrainingConfig:
    model: str = "yolo26n.pt"
    epochs: int = 40
    image_size: int = 640
    batch: int = 16
    device: str = "0"
    workers: int = 4
    patience: int = 10
    seed: int = 20260731


def run_hybrid_training_matrix(
    matrix_root: str | Path,
    output_root: str | Path,
    *,
    config: TrainingConfig = TrainingConfig(),
) -> dict[str, Any]:
    """Train every matrix entry and evaluate its best checkpoint on real test."""
    matrix_root = Path(matrix_root).resolve()
    output_root = Path(output_root).resolve()
    matrix = json.loads(
        (matrix_root / MATRIX_MANIFEST_FILENAME).read_text(encoding="utf-8")
    )
    output_root.mkdir(parents=True, exist_ok=True)

    YOLO = _load_yolo()
    experiment_results: list[dict[str, Any]] = []
    for experiment in matrix["experiments"]:
        name = experiment["spec"]["name"]
        dataset_root = Path(experiment["dataset_root"])
        if not dataset_root.is_absolute():
            dataset_root = (matrix_root / dataset_root).resolve()
        data_yaml = dataset_root / "data.yaml"
        run_dir = output_root / name
        result_path = run_dir / "experiment_result.json"
        if result_path.is_file():
            experiment_results.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue

        weights_dir = run_dir / "weights"
        last_checkpoint = weights_dir / "last.pt"
        if last_checkpoint.is_file():
            model = YOLO(str(last_checkpoint))
            train_metrics = model.train(
                resume=True,
                device=config.device,
                workers=config.workers,
            )
        else:
            model = YOLO(config.model)
            train_metrics = model.train(
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
                name=name,
                exist_ok=True,
                plots=True,
                verbose=True,
            )

        best_checkpoint = weights_dir / "best.pt"
        if not best_checkpoint.is_file():
            candidate = Path(getattr(train_metrics, "save_dir", run_dir)) / "weights" / "best.pt"
            if candidate.is_file():
                best_checkpoint = candidate
        if not best_checkpoint.is_file():
            raise FileNotFoundError(f"Best checkpoint was not produced for {name}: {best_checkpoint}")

        evaluator = YOLO(str(best_checkpoint))
        test_metrics = evaluator.val(
            data=str(data_yaml),
            split="test",
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            project=str(output_root / "test_evaluations"),
            name=name,
            exist_ok=True,
            plots=True,
            verbose=True,
        )
        result = {
            "protocol_version": TRAINING_PROTOCOL_VERSION,
            "experiment": name,
            "dataset_counts": experiment["counts"],
            "config": asdict(config),
            "best_checkpoint": str(best_checkpoint.resolve()),
            "test_metrics": extract_detection_metrics(test_metrics),
        }
        _write_json(result_path, result)
        experiment_results.append(result)

    summary = build_training_summary(
        matrix_root=matrix_root,
        output_root=output_root,
        config=config,
        results=experiment_results,
    )
    _write_json(output_root / "training_summary.json", summary)
    return summary


def run_synthetic_pretrain_natural_finetune(
    *,
    synthetic_data_yaml: str | Path,
    natural_data_yaml: str | Path,
    output_root: str | Path,
    baseline_map50_95: float,
    config: TrainingConfig = TrainingConfig(workers=2),
    synthetic_epochs: int = 12,
) -> dict[str, Any]:
    """Learn synthetic organ shape first, then train exclusively on natural data."""
    synthetic_data_yaml = Path(synthetic_data_yaml).resolve()
    natural_data_yaml = Path(natural_data_yaml).resolve()
    output_root = Path(output_root).resolve()
    result_path = output_root / "curriculum_result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    output_root.mkdir(parents=True, exist_ok=True)
    synthetic_data_yaml = _absolute_dataset_yaml(
        synthetic_data_yaml,
        output_root / "synthetic_data.absolute.yaml",
    )
    natural_data_yaml = _absolute_dataset_yaml(
        natural_data_yaml,
        output_root / "natural_data.absolute.yaml",
    )
    YOLO = _load_yolo()

    synthetic_run = output_root / "stage_1_synthetic_pretrain"
    synthetic_last = synthetic_run / "weights" / "last.pt"
    if synthetic_last.is_file() and _completed_epoch(synthetic_run / "results.csv") < synthetic_epochs:
        YOLO(str(synthetic_last)).train(
            resume=True,
            device=config.device,
            workers=config.workers,
        )
    elif not synthetic_last.is_file():
        YOLO(config.model).train(
            data=str(synthetic_data_yaml),
            epochs=synthetic_epochs,
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            patience=synthetic_epochs,
            seed=config.seed,
            deterministic=True,
            project=str(output_root),
            name="stage_1_synthetic_pretrain",
            exist_ok=True,
            plots=True,
            verbose=True,
        )
    if not synthetic_last.is_file():
        raise FileNotFoundError(f"Synthetic pretraining checkpoint missing: {synthetic_last}")

    natural_run = output_root / "stage_2_natural_finetune"
    natural_last = natural_run / "weights" / "last.pt"
    if natural_last.is_file() and _completed_epoch(natural_run / "results.csv") < config.epochs:
        YOLO(str(natural_last)).train(
            resume=True,
            device=config.device,
            workers=config.workers,
        )
    elif not (natural_run / "weights" / "best.pt").is_file():
        YOLO(str(synthetic_last)).train(
            data=str(natural_data_yaml),
            epochs=config.epochs,
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            patience=config.patience,
            seed=config.seed,
            deterministic=True,
            project=str(output_root),
            name="stage_2_natural_finetune",
            exist_ok=True,
            plots=True,
            verbose=True,
        )
    natural_best = natural_run / "weights" / "best.pt"
    if not natural_best.is_file():
        raise FileNotFoundError(f"Natural fine-tuning checkpoint missing: {natural_best}")

    test_metrics = YOLO(str(natural_best)).val(
        data=str(natural_data_yaml),
        split="test",
        imgsz=config.image_size,
        batch=config.batch,
        device=config.device,
        workers=config.workers,
        project=str(output_root),
        name="stage_3_natural_test",
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    metrics = extract_detection_metrics(test_metrics)
    report = {
        "protocol_version": TRAINING_PROTOCOL_VERSION,
        "strategy": "synthetic_pretrain_then_natural_finetune",
        "synthetic_data_yaml": str(synthetic_data_yaml),
        "natural_data_yaml": str(natural_data_yaml),
        "synthetic_epochs": synthetic_epochs,
        "natural_epochs": config.epochs,
        "config": asdict(config),
        "synthetic_checkpoint": str(synthetic_last),
        "best_checkpoint": str(natural_best),
        "test_metrics": metrics,
        "baseline_map50_95": float(baseline_map50_95),
        "delta_vs_natural": metrics["map50_95"] - float(baseline_map50_95),
        "target_achieved": metrics["map50_95"] >= float(baseline_map50_95),
        "environment": {
            "python": platform.python_version(),
            "ultralytics": _package_version("ultralytics"),
            "torch": _package_version("torch"),
        },
    }
    _write_json(result_path, report)
    return report


def run_natural_refinement_from_hybrid(
    *,
    starting_checkpoint: str | Path,
    natural_data_yaml: str | Path,
    output_root: str | Path,
    baseline_map50_95: float,
    mixed_epochs_before_refinement: int,
    config: TrainingConfig = TrainingConfig(epochs=10, workers=2),
    learning_rate: float = 0.001,
) -> dict[str, Any]:
    """Finish a mixed-domain checkpoint with a short natural-only refinement."""
    starting_checkpoint = Path(starting_checkpoint).resolve()
    natural_data_yaml = Path(natural_data_yaml).resolve()
    output_root = Path(output_root).resolve()
    result_path = output_root / "refinement_result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    if not starting_checkpoint.is_file():
        raise FileNotFoundError(f"Starting hybrid checkpoint missing: {starting_checkpoint}")
    if mixed_epochs_before_refinement < 1:
        raise ValueError("mixed_epochs_before_refinement must be positive.")
    if config.epochs < 1:
        raise ValueError("Natural refinement epochs must be positive.")
    output_root.mkdir(parents=True, exist_ok=True)
    natural_data_yaml = _absolute_dataset_yaml(
        natural_data_yaml,
        output_root / "natural_data.absolute.yaml",
    )
    YOLO = _load_yolo()

    refinement_run = output_root / "stage_2_natural_refinement"
    refinement_last = refinement_run / "weights" / "last.pt"
    refinement_best = refinement_run / "weights" / "best.pt"
    if refinement_last.is_file() and _completed_epoch(refinement_run / "results.csv") < config.epochs:
        YOLO(str(refinement_last)).train(
            resume=True,
            device=config.device,
            workers=config.workers,
        )
    elif not refinement_best.is_file():
        YOLO(str(starting_checkpoint)).train(
            data=str(natural_data_yaml),
            epochs=config.epochs,
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            patience=config.epochs,
            seed=config.seed,
            deterministic=True,
            optimizer="AdamW",
            lr0=learning_rate,
            lrf=0.10,
            warmup_epochs=1.0,
            project=str(output_root),
            name="stage_2_natural_refinement",
            exist_ok=True,
            plots=True,
            verbose=True,
        )
    if not refinement_best.is_file():
        raise FileNotFoundError(f"Natural refinement checkpoint missing: {refinement_best}")

    test_metrics = YOLO(str(refinement_best)).val(
        data=str(natural_data_yaml),
        split="test",
        imgsz=config.image_size,
        batch=config.batch,
        device=config.device,
        workers=config.workers,
        project=str(output_root),
        name="stage_3_natural_test",
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    metrics = extract_detection_metrics(test_metrics)
    report = {
        "protocol_version": TRAINING_PROTOCOL_VERSION,
        "strategy": "mixed_training_then_natural_refinement",
        "starting_checkpoint": str(starting_checkpoint),
        "natural_data_yaml": str(natural_data_yaml),
        "mixed_epochs_before_refinement": mixed_epochs_before_refinement,
        "natural_refinement_epochs": config.epochs,
        "approximate_total_epochs": mixed_epochs_before_refinement + config.epochs,
        "learning_rate": learning_rate,
        "config": asdict(config),
        "best_checkpoint": str(refinement_best),
        "test_metrics": metrics,
        "baseline_map50_95": float(baseline_map50_95),
        "delta_vs_natural": metrics["map50_95"] - float(baseline_map50_95),
        "target_achieved": metrics["map50_95"] >= float(baseline_map50_95),
        "environment": {
            "python": platform.python_version(),
            "ultralytics": _package_version("ultralytics"),
            "torch": _package_version("torch"),
        },
    }
    _write_json(result_path, report)
    return report


def run_checkpoint_interpolation(
    *,
    natural_checkpoint: str | Path,
    hybrid_checkpoint: str | Path,
    natural_data_yaml: str | Path,
    output_root: str | Path,
    baseline_map50_95: float,
    alphas: tuple[float, ...] = (0.15, 0.30, 0.45, 0.60, 0.75, 0.90),
    config: TrainingConfig = TrainingConfig(workers=2),
) -> dict[str, Any]:
    """Select a natural/hybrid weight interpolation on natural validation only."""
    natural_checkpoint = Path(natural_checkpoint).resolve()
    hybrid_checkpoint = Path(hybrid_checkpoint).resolve()
    natural_data_yaml = Path(natural_data_yaml).resolve()
    output_root = Path(output_root).resolve()
    result_path = output_root / "checkpoint_interpolation_result.json"
    if result_path.is_file():
        return json.loads(result_path.read_text(encoding="utf-8"))
    if not natural_checkpoint.is_file() or not hybrid_checkpoint.is_file():
        raise FileNotFoundError("Both natural and hybrid checkpoints are required.")
    if not alphas or any(not 0.0 < alpha < 1.0 for alpha in alphas):
        raise ValueError("Interpolation alphas must be strictly between zero and one.")
    output_root.mkdir(parents=True, exist_ok=True)
    natural_data_yaml = _absolute_dataset_yaml(
        natural_data_yaml,
        output_root / "natural_data.absolute.yaml",
    )

    try:
        import torch
    except ImportError as error:
        raise RuntimeError("PyTorch is required for checkpoint interpolation.") from error
    natural_payload = torch.load(natural_checkpoint, map_location="cpu", weights_only=False)
    hybrid_payload = torch.load(hybrid_checkpoint, map_location="cpu", weights_only=False)
    natural_model = natural_payload.get("model")
    hybrid_model = hybrid_payload.get("model")
    if natural_model is None or hybrid_model is None:
        raise ValueError("Both checkpoints must contain a serialized model.")
    natural_state = natural_model.float().state_dict()
    hybrid_state = hybrid_model.float().state_dict()
    if natural_state.keys() != hybrid_state.keys():
        raise ValueError("Natural and hybrid checkpoint architectures differ.")

    YOLO = _load_yolo()
    candidates: list[dict[str, Any]] = []
    checkpoint_dir = output_root / "interpolated_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for alpha in sorted(set(float(value) for value in alphas)):
        alpha_code = f"{round(alpha * 100):03d}"
        checkpoint_path = checkpoint_dir / f"natural_hybrid_alpha_{alpha_code}.pt"
        if not checkpoint_path.is_file():
            merged_model = copy.deepcopy(natural_model).float()
            merged_state: dict[str, Any] = {}
            for key, natural_tensor in natural_state.items():
                hybrid_tensor = hybrid_state[key]
                if natural_tensor.is_floating_point():
                    merged_state[key] = natural_tensor.lerp(hybrid_tensor, alpha)
                else:
                    merged_state[key] = natural_tensor if alpha < 0.5 else hybrid_tensor
            merged_model.load_state_dict(merged_state, strict=True)
            merged_payload = copy.deepcopy(natural_payload)
            merged_payload["model"] = merged_model.half()
            merged_payload["ema"] = None
            merged_payload["optimizer"] = None
            merged_payload["epoch"] = -1
            merged_payload["train_args"] = dict(merged_payload.get("train_args") or {})
            merged_payload["train_args"]["checkpoint_interpolation_alpha"] = alpha
            torch.save(merged_payload, checkpoint_path)

        validation_metrics = YOLO(str(checkpoint_path)).val(
            data=str(natural_data_yaml),
            split="val",
            imgsz=config.image_size,
            batch=config.batch,
            device=config.device,
            workers=config.workers,
            project=str(output_root / "validation"),
            name=f"alpha_{alpha_code}",
            exist_ok=True,
            plots=False,
            verbose=False,
        )
        candidates.append(
            {
                "alpha_hybrid": alpha,
                "alpha_natural": 1.0 - alpha,
                "checkpoint": str(checkpoint_path),
                "validation_metrics": extract_detection_metrics(validation_metrics),
            }
        )

    selected = max(
        candidates,
        key=lambda item: (
            item["validation_metrics"]["map50_95"],
            -item["alpha_hybrid"],
        ),
    )
    test_metrics = YOLO(selected["checkpoint"]).val(
        data=str(natural_data_yaml),
        split="test",
        imgsz=config.image_size,
        batch=config.batch,
        device=config.device,
        workers=config.workers,
        project=str(output_root),
        name="selected_natural_test",
        exist_ok=True,
        plots=True,
        verbose=True,
    )
    metrics = extract_detection_metrics(test_metrics)
    report = {
        "protocol_version": TRAINING_PROTOCOL_VERSION,
        "strategy": "validation_selected_natural_hybrid_checkpoint_interpolation",
        "selection_policy": "maximum natural validation mAP50-95; natural-biased tie break",
        "natural_checkpoint": str(natural_checkpoint),
        "hybrid_checkpoint": str(hybrid_checkpoint),
        "natural_data_yaml": str(natural_data_yaml),
        "candidates": candidates,
        "selected": selected,
        "test_metrics": metrics,
        "baseline_map50_95": float(baseline_map50_95),
        "delta_vs_natural": metrics["map50_95"] - float(baseline_map50_95),
        "target_achieved": metrics["map50_95"] >= float(baseline_map50_95),
        "config": asdict(config),
        "environment": {
            "python": platform.python_version(),
            "ultralytics": _package_version("ultralytics"),
            "torch": _package_version("torch"),
        },
    }
    _write_json(result_path, report)
    return report


def extract_detection_metrics(metrics: Any) -> dict[str, float]:
    """Extract stable detection metrics from an Ultralytics result object."""
    box = getattr(metrics, "box", None)
    if box is None:
        raise ValueError("Ultralytics result does not expose detection box metrics.")
    values = {
        "map50_95": getattr(box, "map", None),
        "map50": getattr(box, "map50", None),
        "map75": getattr(box, "map75", None),
        "precision": getattr(box, "mp", None),
        "recall": getattr(box, "mr", None),
    }
    missing = [name for name, value in values.items() if value is None]
    if missing:
        raise ValueError(f"Ultralytics result is missing metrics: {', '.join(missing)}")
    return {name: float(value) for name, value in values.items()}


def build_training_summary(
    *,
    matrix_root: Path,
    output_root: Path,
    config: TrainingConfig,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare every candidate against the natural-only mAP50-95 baseline."""
    baseline = next(
        (item for item in results if item["experiment"] == "natural_full"),
        None,
    )
    if baseline is None:
        raise ValueError("The experiment matrix must include natural_full.")
    baseline_score = float(baseline["test_metrics"]["map50_95"])
    ranking = sorted(
        (
            {
                "experiment": item["experiment"],
                "map50_95": float(item["test_metrics"]["map50_95"]),
                "delta_vs_natural": float(item["test_metrics"]["map50_95"])
                - baseline_score,
                "meets_target": float(item["test_metrics"]["map50_95"])
                >= baseline_score,
            }
            for item in results
        ),
        key=lambda item: (-item["map50_95"], item["experiment"]),
    )
    return {
        "protocol_version": TRAINING_PROTOCOL_VERSION,
        "matrix_root": str(matrix_root),
        "output_root": str(output_root),
        "config": asdict(config),
        "environment": {
            "python": platform.python_version(),
            "ultralytics": _package_version("ultralytics"),
            "torch": _package_version("torch"),
        },
        "baseline_map50_95": baseline_score,
        "ranking": ranking,
        "target_achieved": any(
            item["experiment"] != "natural_full" and item["meets_target"]
            for item in ranking
        ),
        "results": results,
    }


def _load_yolo() -> Any:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise RuntimeError(
            "Ultralytics is required only for training. Install the approved ML "
            "environment before running this experiment."
        ) from error
    return YOLO


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def _completed_epoch(results_csv: Path) -> int:
    if not results_csv.is_file():
        return 0
    rows = [line for line in results_csv.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < 2:
        return 0
    try:
        return int(rows[-1].split(",", 1)[0].strip())
    except ValueError:
        return 0


def _absolute_dataset_yaml(source: Path, destination: Path) -> Path:
    """Make a YOLO YAML's dataset root explicit for cwd-independent runs."""
    lines = source.read_text(encoding="utf-8").splitlines()
    rewritten: list[str] = []
    found_path = False
    for line in lines:
        if line.strip().startswith("path:"):
            raw_value = line.split(":", 1)[1].strip().strip('"').strip("'")
            root = source.parent if raw_value in {"", "."} else Path(raw_value)
            if not root.is_absolute():
                root = (source.parent / root).resolve()
            rewritten.append(f'path: "{root.as_posix()}"')
            found_path = True
        else:
            rewritten.append(line)
    if not found_path:
        rewritten.insert(0, f'path: "{source.parent.as_posix()}"')
    destination.write_text("\n".join(rewritten) + "\n", encoding="utf-8", newline="\n")
    return destination


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
