"""Run the sealed multi-seed fidelity-v1 real/synthetic training study."""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import secrets
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from uchuva_lsystem.hybrid_study import (
    BASELINE_NAME,
    PHASE_A_NAMES,
    PHASE_A_SYNTHETIC_COUNTS,
    PHASE_B_NAMES,
    PHASE_B_REAL_COUNTS,
    STUDY_PROTOCOL_VERSION,
    STUDY_SEEDS,
    aggregate_validation_results,
    audit_prepared_matrices,
    audit_study_sources,
    create_selection_lock,
    decide_phase_a,
    decide_phase_b_cohort,
    evaluate_selection_lock_on_test,
    materialize_repaired_real_partition,
    prepare_study_matrices,
    run_validation_experiment,
    should_stop_phase_b,
    validate_perceptual_review,
)
from uchuva_lsystem.hybrid_training import TrainingConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--action",
        choices=("prepare", "smoke", "phase-a", "phase-b", "final-test", "report", "all"),
        default="all",
    )
    parser.add_argument(
        "--real-root", type=Path, default=REPO_ROOT / "Dataset Original"
    )
    parser.add_argument(
        "--synthetic-root",
        type=Path,
        default=REPO_ROOT
        / "outputs"
        / "datasets"
        / "uchuva_synthetic_fidelity_v1_seed_5000",
    )
    parser.add_argument(
        "--study-root",
        type=Path,
        default=REPO_ROOT
        / "outputs"
        / "experiments"
        / "hybrid_fidelity_v2_leakage_repaired_20260811",
    )
    parser.add_argument(
        "--perceptual-review",
        type=Path,
        default=REPO_ROOT
        / "docs"
        / "governance"
        / "real_split_perceptual_review_20260811.json",
    )
    parser.add_argument(
        "--model", default=str(REPO_ROOT / "outputs" / "models" / "yolo26n.pt")
    )
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--minimum-available-ram-gb", type=float, default=4.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    real_root = _repo_path(args.real_root)
    synthetic_root = _repo_path(args.synthetic_root)
    study_root = _repo_path(args.study_root)
    perceptual_review = _repo_path(args.perceptual_review)
    study_root.mkdir(parents=True, exist_ok=True)
    actions = (
        ("prepare", "smoke", "phase-a", "phase-b", "final-test", "report")
        if args.action == "all"
        else (args.action,)
    )
    base_config = TrainingConfig(
        model=str(_repo_path(Path(args.model))),
        epochs=args.epochs,
        image_size=args.image_size,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        seed=STUDY_SEEDS[0],
    )
    with _study_run_lock(study_root, args.action):
        for action in actions:
            if action == "prepare":
                prepare(real_root, synthetic_root, study_root, perceptual_review)
            elif action == "smoke":
                _require_preflight(study_root)
                smoke(study_root, base_config, args.minimum_available_ram_gb)
            elif action == "phase-a":
                _require_preflight(study_root)
                run_phase_a(study_root, base_config, args.minimum_available_ram_gb)
            elif action == "phase-b":
                _require_preflight(study_root)
                run_phase_b(study_root, base_config, args.minimum_available_ram_gb)
            elif action == "final-test":
                _require_preflight(study_root)
                run_final_test(study_root, base_config, args.minimum_available_ram_gb)
            elif action == "report":
                _require_preflight(study_root)
                render_report(study_root)


def prepare(
    real_root: Path,
    synthetic_root: Path,
    study_root: Path,
    perceptual_review_path: Path,
) -> None:
    audit_path = study_root / "source_audit.json"
    if audit_path.is_file():
        audit = _read_json(audit_path)
    else:
        audit = audit_study_sources(
            real_root=real_root,
            synthetic_root=synthetic_root,
        )
        _write_json(audit_path, audit)
    if audit["status"] != "valid":
        raise RuntimeError(f"Source audit failed: {audit['errors']}")
    review = _read_json(perceptual_review_path)
    review_validation = validate_perceptual_review(audit, review)
    _write_json(study_root / "perceptual_review.json", review)
    _write_json(study_root / "perceptual_review_validation.json", review_validation)
    repaired_root = study_root / "repaired_real_partition"
    materialize_repaired_real_partition(
        real_root=real_root,
        output_root=repaired_root,
        source_audit=audit,
        review=review,
    )
    repaired_audit_path = study_root / "repaired_source_audit.json"
    if repaired_audit_path.is_file():
        repaired_audit = _read_json(repaired_audit_path)
    else:
        repaired_audit = audit_study_sources(
            real_root=repaired_root,
            synthetic_root=synthetic_root,
            expected_missing_train_ids=(),
        )
        _write_json(repaired_audit_path, repaired_audit)
    if repaired_audit["status"] != "valid":
        raise RuntimeError(f"Repaired source audit failed: {repaired_audit['errors']}")
    if repaired_audit["perceptual_candidates"]:
        raise RuntimeError(
            "Repaired partition still has cross-cohort perceptual candidates: "
            f"{repaired_audit['perceptual_candidates']}"
        )
    prepare_study_matrices(
        real_root=repaired_root,
        synthetic_root=synthetic_root,
        study_root=study_root,
        seeds=STUDY_SEEDS,
    )
    matrix_audit = audit_prepared_matrices(study_root)
    _write_json(study_root / "matrix_audit.json", matrix_audit)
    if matrix_audit["status"] != "valid":
        raise RuntimeError(f"Matrix audit failed: {matrix_audit['errors']}")
    print(
        "Preparation valid. "
        f"Reviewed candidates: {review_validation['reviewed_candidate_count']}; "
        "remaining cross-cohort candidates: 0."
    )


def _require_preflight(study_root: Path) -> None:
    required = {
        "source audit": study_root / "source_audit.json",
        "perceptual review": study_root / "perceptual_review.json",
        "review validation": study_root / "perceptual_review_validation.json",
        "repaired source audit": study_root / "repaired_source_audit.json",
        "matrix audit": study_root / "matrix_audit.json",
        "matrix index": study_root / "matrices.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Study preparation is incomplete; missing {missing}.")
    if _read_json(required["source audit"])["status"] != "valid":
        raise RuntimeError("Source audit is invalid.")
    if _read_json(required["review validation"])["status"] != "valid":
        raise RuntimeError("Perceptual review is incomplete.")
    repaired = _read_json(required["repaired source audit"])
    if repaired["status"] != "valid" or repaired["perceptual_candidates"]:
        raise RuntimeError("Repaired real partition is not leakage-safe.")
    if _read_json(required["matrix audit"])["status"] != "valid":
        raise RuntimeError("Prepared training matrices are invalid.")


@contextlib.contextmanager
def _study_run_lock(study_root: Path, action: str):
    """Prevent two independent study orchestrators from running concurrently."""
    lock_path = study_root / "study_run.lock.json"
    token = secrets.token_hex(16)
    payload = {
        "pid": os.getpid(),
        "action": action,
        "token": token,
    }
    for attempt in range(2):
        try:
            descriptor = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
            break
        except FileExistsError:
            existing = _read_json(lock_path)
            if _pid_is_running(int(existing.get("pid", -1))):
                raise RuntimeError(
                    "Another hybrid-study orchestrator is already active: "
                    f"pid={existing.get('pid')} action={existing.get('action')}."
                )
            if attempt:
                raise RuntimeError(f"Could not recover stale study lock: {lock_path}")
            lock_path.unlink()
    else:
        raise RuntimeError(f"Could not acquire study lock: {lock_path}")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        yield
    finally:
        if lock_path.is_file():
            existing = _read_json(lock_path)
            if existing.get("token") == token:
                lock_path.unlink()


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def smoke(study_root: Path, config: TrainingConfig, minimum_ram: float) -> None:
    marker = study_root / "smoke" / "smoke_result.json"
    if marker.is_file():
        print(f"Smoke test already complete: {marker}")
        return
    matrix_root = _matrix_root(study_root, STUDY_SEEDS[0], "phase_a")
    smoke_config = TrainingConfig(
        **{
            **asdict(config),
            "epochs": 1,
            "patience": 1,
            "seed": STUDY_SEEDS[0],
        }
    )
    result = run_validation_experiment(
        matrix_root=matrix_root,
        experiment_name=BASELINE_NAME,
        output_root=study_root / "smoke" / "runs",
        config=smoke_config,
        minimum_available_ram_gb=minimum_ram,
    )
    _write_json(marker, result)
    print(f"Smoke test valid: {marker}")


def run_phase_a(study_root: Path, config: TrainingConfig, minimum_ram: float) -> None:
    decision_path = study_root / "phase_a_decision.json"
    if decision_path.is_file():
        print(f"Phase A already decided: {decision_path}")
        return
    names = (BASELINE_NAME, *(PHASE_A_NAMES[count] for count in PHASE_A_SYNTHETIC_COUNTS))
    all_results: list[dict[str, Any]] = []
    for name in names:
        for seed in STUDY_SEEDS:
            seed_config = TrainingConfig(**{**asdict(config), "seed": seed})
            result = run_validation_experiment(
                matrix_root=_matrix_root(study_root, seed, "phase_a"),
                experiment_name=name,
                output_root=study_root / "runs" / f"seed_{seed}" / "phase_a",
                config=seed_config,
                minimum_available_ram_gb=minimum_ram,
            )
            all_results.append(result)
            print(
                f"Phase A {name} seed={seed}: "
                f"val mAP50-95={result['validation_metrics']['map50_95']:.6f}"
            )
    baselines = [item for item in all_results if item["experiment"] == BASELINE_NAME]
    aggregate = aggregate_validation_results(all_results, baseline_results=baselines)
    decision = decide_phase_a(aggregate)
    _write_json(study_root / "phase_a_summary.json", aggregate)
    _write_json(decision_path, decision)
    _write_aggregate_csv(study_root / "phase_a_summary.csv", aggregate)
    if decision["success"]:
        selected_name = decision["selected"]["experiment"]
        create_selection_lock(
            study_root=study_root,
            phase="phase_a",
            selected_results=[
                item for item in all_results if item["experiment"] == selected_name
            ],
            baseline_results=baselines,
            decision=decision,
        )
    print(json.dumps(decision, indent=2, ensure_ascii=False))


def run_phase_b(study_root: Path, config: TrainingConfig, minimum_ram: float) -> None:
    phase_a_decision = _read_json(study_root / "phase_a_decision.json")
    if phase_a_decision["success"]:
        print("Phase A succeeded; Phase B is not applicable.")
        return
    summary_path = study_root / "phase_b_summary.json"
    if summary_path.is_file():
        summary = _read_json(summary_path)
        if summary.get("status") in {"success", "stopped_after_two_worsenings"}:
            print(f"Phase B already concluded: {summary_path}")
            return
    baseline_results = _load_phase_results(study_root, "phase_a", BASELINE_NAME)
    cohort_decisions: list[dict[str, Any]] = []
    worsening_count = 0
    status = "in_progress"
    selected_name = None
    for real_count in PHASE_B_REAL_COUNTS:
        name = PHASE_B_NAMES[real_count]
        cohort_results = []
        for seed in STUDY_SEEDS:
            seed_config = TrainingConfig(**{**asdict(config), "seed": seed})
            result = run_validation_experiment(
                matrix_root=_matrix_root(study_root, seed, "phase_b"),
                experiment_name=name,
                output_root=study_root / "runs" / f"seed_{seed}" / "phase_b",
                config=seed_config,
                minimum_available_ram_gb=minimum_ram,
            )
            cohort_results.append(result)
            print(
                f"Phase B {name} seed={seed}: "
                f"val mAP50-95={result['validation_metrics']['map50_95']:.6f}"
            )
        aggregate = aggregate_validation_results(
            cohort_results,
            baseline_results=baseline_results,
        )
        _write_json(study_root / "phase_b" / f"{name}_summary.json", aggregate)
        decision = decide_phase_b_cohort(aggregate["experiments"][name])
        cohort_decisions.append(decision)
        if decision["success"]:
            status = "success"
            selected_name = name
            create_selection_lock(
                study_root=study_root,
                phase="phase_b",
                selected_results=cohort_results,
                baseline_results=baseline_results,
                decision={
                    "protocol_version": STUDY_PROTOCOL_VERSION,
                    "phase": "phase_b",
                    "status": status,
                    "cohort_decisions": cohort_decisions,
                    "selected": decision,
                },
            )
            break
        if decision["worsening"]:
            worsening_count += 1
        if should_stop_phase_b(cohort_decisions):
            status = "stopped_after_two_worsenings"
            break
    summary = {
        "protocol_version": STUDY_PROTOCOL_VERSION,
        "comparison_baseline": "1061_real_images",
        "status": status,
        "worsening_count": worsening_count,
        "selected_experiment": selected_name,
        "cohort_decisions": cohort_decisions,
        "causal_caveat": (
            "Underperformance means the hybrid did not match the full-real baseline; "
            "it does not isolate a causal synthetic-data effect."
        ),
    }
    _write_json(summary_path, summary)
    _write_phase_b_csv(study_root / "phase_b_summary.csv", cohort_decisions)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def run_final_test(study_root: Path, config: TrainingConfig, minimum_ram: float) -> None:
    lock_path = study_root / "selection.lock.json"
    if not lock_path.is_file():
        print("No validation-selected winner exists; sealed test remains untouched.")
        return
    summary = evaluate_selection_lock_on_test(
        lock_path=lock_path,
        output_root=study_root / "final_test",
        config_template=config,
        minimum_available_ram_gb=minimum_ram,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def render_report(study_root: Path) -> None:
    _write_per_seed_validation_csv(
        study_root / "validation_metrics_per_seed.csv", study_root
    )
    phase_a = _read_json(study_root / "phase_a_summary.json")
    phase_a_decision = _read_json(study_root / "phase_a_decision.json")
    phase_b_path = study_root / "phase_b_summary.json"
    final_test_path = study_root / "final_test" / "final_test_summary.json"
    phase_b = _read_json(phase_b_path) if phase_b_path.is_file() else None
    final_test = _read_json(final_test_path) if final_test_path.is_file() else None
    if final_test:
        _write_final_test_csv(study_root / "final_test_metrics_per_seed.csv", final_test)
    lines = [
        "# Estudio híbrido real–sintético sellado",
        "",
        f"Protocolo: `{STUDY_PROTOCOL_VERSION}`.",
        "",
        "La selección usa exclusivamente `val` real. El test real nunca entra al "
        "entrenamiento y solo se consulta si existe un ganador bloqueado. El test "
        "fue evaluado en experimentos históricos, por lo que no es un test externo virgen.",
        "",
        "## Fase A",
        "",
        "| Experimento | Real | Sintético | mAP50–95 media | Δ vs real | Recall medio |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, item in phase_a["experiments"].items():
        delta = item.get("paired_map50_95_delta")
        lines.append(
            f"| {name} | {item['dataset_counts']['train_real']} | "
            f"{item['dataset_counts']['train_synthetic']} | "
            f"{item['metrics']['map50_95']['mean']:.4f} | "
            f"{delta['mean'] if delta else 0.0:+.4f} | "
            f"{item['metrics']['recall']['mean']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"Resultado de Fase A: **{'éxito' if phase_a_decision['success'] else 'sin mejora práctica'}**.",
            "",
        ]
    )
    if phase_b:
        lines.extend(
            [
                "## Fase B",
                "",
                f"Estado: **{phase_b['status']}**.",
                "",
                "| Cohorte | Real | Sintético | Δ mAP50–95 | Δ recall | Resultado |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for item in phase_b["cohort_decisions"]:
            result = "iguala baseline" if item["success"] else (
                "empeora" if item["worsening"] else "inconclusa"
            )
            lines.append(
                f"| {item['experiment']} | {item['real_count']} | "
                f"{item['synthetic_count']} | {item['map50_95_delta_mean']:+.4f} | "
                f"{item['recall_delta_mean']:+.4f} | {result} |"
            )
        lines.extend(
            [
                "",
                "La comparación usa como referencia fija las 1061 imágenes reales; "
                "por ello una caída no demuestra causalmente que los sintéticos dañen el modelo.",
                "",
            ]
        )
    if final_test:
        lines.extend(
            [
                "## Test real sellado",
                "",
                f"Δ mAP50–95 medio ganador–baseline: "
                f"**{final_test['paired_map50_95_delta']['mean']:+.4f}**.",
                f"Δ recall medio: **{final_test['paired_recall_delta']['mean']:+.4f}**.",
                "",
            ]
        )
    elif phase_b and phase_b["status"] == "stopped_after_two_worsenings":
        lines.extend(
            [
                "## Conclusión",
                "",
                "La búsqueda se detuvo tras dos cohortes por debajo del baseline completo. "
                "No se consultó el test para escoger una alternativa.",
                "",
                "El siguiente diagnóstico debe priorizar la escala aparente de los capachos, "
                "la luminancia, la textura/pubescencia, la densidad del dosel y la complejidad "
                "del fondo antes de generar otro lote grande.",
                "",
            ]
        )
    report_path = study_root / "study_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Report: {report_path}")


def _load_phase_results(study_root: Path, phase: str, experiment: str) -> list[dict[str, Any]]:
    return [
        _read_json(
            study_root
            / "runs"
            / f"seed_{seed}"
            / phase
            / experiment
            / "validation_result.json"
        )
        for seed in STUDY_SEEDS
    ]


def _matrix_root(study_root: Path, seed: int, phase: str) -> Path:
    return study_root / "matrices" / f"seed_{seed}" / phase


def _write_aggregate_csv(path: Path, aggregate: dict[str, Any]) -> None:
    rows = []
    for name, item in aggregate["experiments"].items():
        rows.append(
            {
                "experiment": name,
                "train_real": item["dataset_counts"]["train_real"],
                "train_synthetic": item["dataset_counts"]["train_synthetic"],
                "map50_95_mean": item["metrics"]["map50_95"]["mean"],
                "map50_95_stdev": item["metrics"]["map50_95"]["stdev"],
                "map50_mean": item["metrics"]["map50"]["mean"],
                "map50_stdev": item["metrics"]["map50"]["stdev"],
                "map75_mean": item["metrics"]["map75"]["mean"],
                "map75_stdev": item["metrics"]["map75"]["stdev"],
                "map50_95_delta_mean": (
                    item["paired_map50_95_delta"]["mean"]
                    if item["paired_map50_95_delta"]
                    else 0.0
                ),
                "precision_mean": item["metrics"]["precision"]["mean"],
                "precision_stdev": item["metrics"]["precision"]["stdev"],
                "recall_mean": item["metrics"]["recall"]["mean"],
                "recall_stdev": item["metrics"]["recall"]["stdev"],
                "f1_mean": item["metrics"]["f1"]["mean"],
                "f1_stdev": item["metrics"]["f1"]["stdev"],
            }
        )
    _write_csv(path, rows)


def _write_phase_b_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_csv(path, rows)


def _write_per_seed_validation_csv(path: Path, study_root: Path) -> None:
    rows = []
    for result_path in sorted(
        study_root.glob("runs/seed_*/phase_*/*/validation_result.json")
    ):
        item = _read_json(result_path)
        metrics = item["validation_metrics"]
        curve = item["training_curve"]
        phase = result_path.parents[1].name
        rows.append(
            {
                "phase": phase,
                "experiment": item["experiment"],
                "seed": item["config"]["seed"],
                "train_real": item["dataset_counts"]["train_real"],
                "train_synthetic": item["dataset_counts"]["train_synthetic"],
                "map50_95": metrics["map50_95"],
                "map50": metrics["map50"],
                "map75": metrics["map75"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "best_epoch": curve.get("best_epoch"),
                "epoch_count": curve.get("epoch_count"),
                "duration_seconds": curve.get("duration_seconds"),
                "best_checkpoint": item["best_checkpoint"],
                "best_checkpoint_sha256": item["best_checkpoint_sha256"],
            }
        )
    _write_csv(path, rows)


def _write_final_test_csv(path: Path, summary: dict[str, Any]) -> None:
    rows = []
    for item in sorted(summary["results"], key=lambda row: (row["role"], row["seed"])):
        rows.append(
            {
                "role": item["role"],
                "experiment": item["experiment"],
                "seed": item["seed"],
                **item["test_metrics"],
                "checkpoint": item["checkpoint"],
                "checkpoint_sha256": item["checkpoint_sha256"],
            }
        )
    _write_csv(path, rows)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _repo_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


if __name__ == "__main__":
    os.environ.setdefault(
        "YOLO_CONFIG_DIR", str(REPO_ROOT / "outputs" / "experiments" / "ultralytics_config")
    )
    os.environ.setdefault(
        "MPLCONFIGDIR", str(REPO_ROOT / "outputs" / "experiments" / "matplotlib_config")
    )
    main()
