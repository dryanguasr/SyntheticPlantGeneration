"""Frozen YOLO11n training harness with audit gates and resume detection."""

from __future__ import annotations

import csv
from contextlib import contextmanager
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class TrainingConfig:
    epochs: int
    imgsz: int = 640
    batch: int = 8
    workers: int = 4
    device: str = "0"
    optimizer: str = "AdamW"
    lr0: float = 0.001
    lrf: float = 0.01
    weight_decay: float = 0.0005
    amp: bool = False
    rect: bool = True
    deterministic: bool = True
    save_period: int = 5


def balanced_scenario_order(scenarios: Iterable[str], seed: int) -> list[str]:
    """Return one row of a deterministic balanced Latin-square schedule."""
    items = list(scenarios)
    count = len(items)
    if count < 2:
        return items
    first = []
    for index in range(count):
        position = index // 2 if index % 2 == 0 else count - 1 - index // 2
        first.append(items[position])
    rows = [[items[(items.index(value) + shift) % count] for value in first] for shift in range(count)]
    if count % 2:
        rows.extend([list(reversed(row)) for row in rows])
    return rows[(seed - 1) % len(rows)]


def run_training_matrix(
    datasets: dict[str, Path],
    project: Path,
    model_path: Path,
    *,
    seeds: Iterable[int],
    config: TrainingConfig,
    phase: str,
) -> list[dict[str, Any]]:
    project = project.resolve()
    project.mkdir(parents=True, exist_ok=True)
    with _exclusive_campaign_lock(project):
        model_path = model_path.resolve()
        if not model_path.is_file():
            raise FileNotFoundError(model_path)
        _validate_dataset_gates(datasets)
        seeds = list(seeds)
        scenario_codes = list(datasets)
        environment = _environment(model_path, datasets, seeds, config, phase)
        environment_text = json.dumps(
            environment, ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        (project / "execution_environment.json").write_text(
            environment_text, encoding="utf-8", newline="\n"
        )
        with (project / "execution_environment_history.jsonl").open(
            "a", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(json.dumps(environment, ensure_ascii=False, sort_keys=True) + "\n")
        results = []
        for seed in seeds:
            order = balanced_scenario_order(scenario_codes, seed)
            for run_order, scenario in enumerate(order, start=1):
                results.append(
                    run_training(
                        scenario,
                        datasets[scenario],
                        seed,
                        run_order,
                        project,
                        model_path,
                        config,
                        phase=phase,
                    )
                )
        return results


def run_training(
    scenario: str,
    dataset_dir: Path,
    seed: int,
    run_order: int,
    project: Path,
    model_path: Path,
    config: TrainingConfig,
    *,
    phase: str,
) -> dict[str, Any]:
    from ultralytics import YOLO

    safe_scenario = scenario.lower().replace("-", "_")
    name = f"{safe_scenario}_{phase}_yolo11n_e{config.epochs}_seed{seed:02d}"
    run_dir = project / name
    last = run_dir / "weights" / "last.pt"
    if _is_complete(run_dir, config.epochs):
        return _run_summary(run_dir, scenario, seed, run_order, "skipped_complete", phase)
    _validate_resumable_results(run_dir, config.epochs)
    action = "resume" if last.is_file() else "new"
    started = datetime.now(timezone.utc)
    monotonic_start = time.perf_counter()
    telemetry_start = _gpu_telemetry()
    _log_state(project, scenario, seed, run_order, name, action, "started", started)
    try:
        if action == "resume":
            YOLO(str(last)).train(resume=True)
        else:
            YOLO(str(model_path)).train(
                data=str((dataset_dir / "data.yaml").resolve()),
                epochs=config.epochs,
                imgsz=config.imgsz,
                batch=config.batch,
                device=config.device,
                workers=config.workers,
                rect=config.rect,
                cache=False,
                optimizer=config.optimizer,
                lr0=config.lr0,
                lrf=config.lrf,
                weight_decay=config.weight_decay,
                patience=config.epochs,
                seed=seed,
                deterministic=config.deterministic,
                amp=config.amp,
                val=True,
                plots=True,
                save=True,
                save_period=config.save_period,
                hsv_h=0.0,
                hsv_s=0.0,
                hsv_v=0.0,
                degrees=0.0,
                translate=0.0,
                scale=0.0,
                shear=0.0,
                perspective=0.0,
                flipud=0.0,
                fliplr=0.0,
                bgr=0.0,
                mosaic=0.0,
                mixup=0.0,
                cutmix=0.0,
                copy_paste=0.0,
                erasing=0.0,
                auto_augment=None,
                close_mosaic=0,
                project=str(project),
                name=name,
                exist_ok=False,
            )
        status, message = "complete", ""
    except BaseException as error:
        status, message = "failed", f"{type(error).__name__}: {error}"
        traceback.print_exc()
        raise
    finally:
        ended = datetime.now(timezone.utc)
        wall_time = time.perf_counter() - monotonic_start
        _log_state(project, scenario, seed, run_order, name, action, status, ended, wall_time, message, telemetry_start, _gpu_telemetry())
    return _run_summary(run_dir, scenario, seed, run_order, status, phase, wall_time)


def _validate_dataset_gates(datasets: dict[str, Path]) -> None:
    for scenario, dataset in datasets.items():
        audit_path = dataset / "audit_report.json"
        if not audit_path.is_file():
            raise RuntimeError(f"{scenario}: missing smoke/full audit gate: {audit_path}")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("status") != "valid":
            raise RuntimeError(f"{scenario}: dataset audit is not valid")


def _is_complete(run_dir: Path, epochs: int) -> bool:
    results = run_dir / "results.csv"
    if not results.is_file():
        return False
    return _epoch_sequence(results) == list(range(1, epochs + 1)) and (run_dir / "weights" / "best.pt").is_file()


def _validate_resumable_results(run_dir: Path, epochs: int) -> None:
    """Reject shared/corrupt run directories instead of silently resuming them."""
    results = run_dir / "results.csv"
    if not results.is_file():
        return
    sequence = _epoch_sequence(results)
    expected_prefix = list(range(1, len(sequence) + 1))
    if len(sequence) >= epochs or sequence != expected_prefix:
        raise RuntimeError(
            f"Non-resumable results history in {results}: expected a unique epoch prefix "
            f"1..N with N < {epochs}, observed {len(sequence)} rows ending in "
            f"{sequence[-5:] if sequence else []}. Quarantine the run and restart it cleanly."
        )


def _epoch_sequence(results: Path) -> list[int]:
    with results.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    try:
        return [int(float(row["epoch"])) for row in rows]
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"Invalid epoch column in {results}") from error


@contextmanager
def _exclusive_campaign_lock(project: Path):
    """Hold an OS-backed lock so suspensions or duplicate launchers cannot overlap."""
    lock_path = project / ".campaign.lock"
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+", encoding="utf-8") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                if lock_path.stat().st_size == 0:
                    handle.write("\n")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeError(
                f"Another campaign launcher already holds {lock_path}; refusing a duplicate instance"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "started_utc": datetime.now(timezone.utc).isoformat()}) + "\n")
        handle.flush()
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _run_summary(run_dir: Path, scenario: str, seed: int, run_order: int, status: str, phase: str, wall_time: float | None = None) -> dict[str, Any]:
    rows = []
    results = run_dir / "results.csv"
    if results.is_file():
        with results.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    best = max(rows, key=lambda row: float(row["metrics/mAP50-95(B)"])) if rows else None
    return {
        "scenario": scenario,
        "seed": seed,
        "run_order": run_order,
        "phase": phase,
        "completion_status": status,
        "epochs_completed": len(rows),
        "best_epoch": int(best["epoch"]) if best else None,
        "best_metric": float(best["metrics/mAP50-95(B)"]) if best else None,
        "wall_time_seconds_current_segment": wall_time,
        "run_dir": str(run_dir),
    }


def _log_state(project: Path, scenario: str, seed: int, run_order: int, run: str, action: str, status: str, timestamp: datetime, wall_time: float | None = None, message: str = "", telemetry_start=None, telemetry_end=None) -> None:
    path = project / "execution_state.jsonl"
    payload = {
        "timestamp_utc": timestamp.isoformat(), "scenario": scenario, "seed": seed, "run_order": run_order,
        "run": run, "action": action, "status": status, "wall_time_seconds": wall_time, "message": message,
        "gpu_telemetry_start": telemetry_start, "gpu_telemetry_end": telemetry_end,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _environment(model_path: Path, datasets: dict[str, Path], seeds: list[int], config: TrainingConfig, phase: str) -> dict[str, Any]:
    import cv2
    import numpy
    import torch
    import ultralytics

    return {
        "created_utc": datetime.now(timezone.utc).isoformat(), "phase": phase, "python": sys.version,
        "platform": platform.platform(), "torch": torch.__version__, "cuda": torch.version.cuda,
        "ultralytics": ultralytics.__version__, "opencv": cv2.__version__, "numpy": numpy.__version__,
        "gpus": [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())],
        "git_commit": _git_commit(), "model": str(model_path), "model_sha256": _sha256(model_path),
        "git_worktree_dirty": _git_worktree_dirty(),
        "training_module_sha256": _sha256(Path(__file__)),
        "datasets": {code: str(path.resolve()) for code, path in datasets.items()}, "seeds": seeds,
        "training_config": asdict(config),
        "offline_augmentation_only": True,
        "ultralytics_augmentation_overrides": {
            "mosaic": 0.0, "mixup": 0.0, "hsv_h": 0.0, "hsv_s": 0.0, "hsv_v": 0.0,
            "degrees": 0.0, "translate": 0.0, "scale": 0.0, "fliplr": 0.0, "flipud": 0.0,
            "erasing": 0.0, "auto_augment": None, "copy_paste": 0.0, "cutmix": 0.0,
        },
    }


def _gpu_telemetry():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu,power.draw,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        values = [value.strip() for value in result.stdout.strip().split(",")]
        return {"temperature_c": float(values[0]), "power_w": float(values[1]), "utilization_pct": float(values[2]), "vram_used_mb": float(values[3])}
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return {"status": "unavailable_non_blocking"}


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown_not_available"


def _git_worktree_dirty() -> bool | str:
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
        return bool(output.strip())
    except (OSError, subprocess.SubprocessError):
        return "unknown_not_available"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
