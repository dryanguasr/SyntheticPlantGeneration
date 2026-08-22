"""Summarize v2 validation metrics and compute Recall at Precision >= 0.98."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.labels import YoloBox, read_yolo_labels
from uchuva_classical_augmentation.v2.manifest import file_sha256
from uchuva_classical_augmentation.v2.metrics import Prediction, confidence_sweep, stratified_recall
from uchuva_classical_augmentation.v2.profiles import read_profile
from uchuva_classical_augmentation.v2.config import default_campaign_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/domain_profile/real_train_profile.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="0")
    parser.add_argument("--skip-operational", action="store_true")
    parser.add_argument("--expected-epochs", type=int, default=30)
    parser.add_argument("--expected-seeds", default="1,2,3")
    parser.add_argument(
        "--expected-scenarios",
        help="Comma-separated scenario codes; defaults to the full nine-scenario screening matrix",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = read_profile(args.profile)
    runs = _discover_runs(args.project)
    if not runs:
        raise RuntimeError(f"No complete runs found under {args.project}")
    configured_scenarios = [item.code for item in default_campaign_config().scenarios]
    expected_scenarios = (
        _parse_scenario_set(args.expected_scenarios, configured_scenarios)
        if args.expected_scenarios
        else configured_scenarios
    )
    expected_seeds = _parse_int_set(args.expected_seeds)
    _validate_complete_matrix(
        runs,
        expected_scenarios=expected_scenarios,
        expected_seeds=expected_seeds,
        expected_epochs=args.expected_epochs,
    )
    for run in runs:
        if not args.skip_operational:
            run["operational"] = _operational_metrics(run, profile, args.output_dir / "prediction_cache", args.device)
    report = _aggregate(runs)
    report["test_consulted"] = False
    report["selection_split"] = "val"
    report["runs"] = runs
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "screening_summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (args.output_dir / "screening_summary.md").write_text(_markdown(report), encoding="utf-8", newline="\n")
    print(args.output_dir.resolve() / "screening_summary.json")


def _discover_runs(project: Path):
    events = []
    state = project / "execution_state.jsonl"
    if state.is_file():
        events = [json.loads(line) for line in state.read_text(encoding="utf-8").splitlines() if line.strip()]
    latest = {}
    for event in events:
        if event["status"] == "complete":
            latest[event["run"]] = event
    runs = []
    for run_name, event in latest.items():
        run_dir = project / run_name
        results_path = run_dir / "results.csv"
        checkpoint = run_dir / "weights" / "best.pt"
        if not results_path.is_file() or not checkpoint.is_file():
            continue
        with results_path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        best = max(rows, key=lambda row: float(row["metrics/mAP50-95(B)"]))
        args_payload = _read_simple_yaml(run_dir / "args.yaml")
        runs.append({
            "scenario": event["scenario"], "seed": int(event["seed"]), "run_order": int(event["run_order"]),
            "run_dir": str(run_dir.resolve()), "checkpoint": str(checkpoint.resolve()), "checkpoint_sha256": file_sha256(checkpoint),
            "data_yaml": str(Path(args_payload["data"]).resolve()), "epochs_completed": len(rows), "best_epoch": int(best["epoch"]),
            "precision": float(best["metrics/precision(B)"]), "recall": float(best["metrics/recall(B)"]),
            "map50": float(best["metrics/mAP50(B)"]), "map5095": float(best["metrics/mAP50-95(B)"]),
            "wall_time_seconds": event.get("wall_time_seconds"),
        })
    return sorted(runs, key=lambda item: (item["scenario"], item["seed"]))


def _parse_int_set(value: str) -> list[int]:
    result = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not result or len(result) != len(set(result)) or min(result) < 0:
        raise ValueError("Expected seeds must be unique non-negative integers")
    return result


def _parse_scenario_set(value: str, allowed: list[str]) -> list[str]:
    result = [item.strip().upper() for item in value.split(",") if item.strip()]
    if not result or len(result) != len(set(result)):
        raise ValueError("Expected scenarios must be unique non-empty codes")
    unknown = sorted(set(result) - set(allowed))
    if unknown:
        raise ValueError(f"Unknown expected scenarios: {unknown}")
    return result


def _validate_complete_matrix(
    runs,
    *,
    expected_scenarios: list[str],
    expected_seeds: list[int],
    expected_epochs: int,
) -> None:
    if expected_epochs <= 0:
        raise ValueError("Expected epochs must be positive")
    expected = {
        (scenario, seed)
        for scenario in expected_scenarios
        for seed in expected_seeds
    }
    observed = {(run["scenario"], int(run["seed"])) for run in runs}
    duplicates = len(observed) != len(runs)
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    wrong_epochs = sorted(
        (run["scenario"], int(run["seed"]), int(run["epochs_completed"]))
        for run in runs
        if int(run["epochs_completed"]) != expected_epochs
    )
    if duplicates or missing or unexpected or wrong_epochs:
        details = {
            "duplicates": duplicates,
            "missing": missing,
            "unexpected": unexpected,
            "wrong_epochs": wrong_epochs,
            "expected_run_count": len(expected),
            "observed_run_count": len(runs),
        }
        raise RuntimeError(
            "Screening matrix is incomplete or inconsistent; refusing to rank: "
            + json.dumps(details, sort_keys=True)
        )


def _operational_metrics(run, profile, cache_root: Path, device: str):
    from ultralytics import YOLO

    data = _read_simple_yaml(Path(run["data_yaml"]))
    root = Path(data["path"])
    val_dir = root / data["val"]
    label_dir = root / "labels" / "val"
    images = sorted(path for path in val_dir.iterdir() if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
    ground_truth = {image.name: read_yolo_labels(label_dir / f"{image.stem}.txt") for image in images}
    cache_root.mkdir(parents=True, exist_ok=True)
    cache = cache_root / f"{run['scenario'].lower().replace('-', '_')}_seed{run['seed']:02d}.json"
    predictions = None
    if cache.is_file():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        if payload.get("checkpoint_sha256") == run["checkpoint_sha256"]:
            predictions = {name: [Prediction(YoloBox(**item["box"]), item["confidence"]) for item in values] for name, values in payload["predictions"].items()}
    if predictions is None:
        model = YOLO(run["checkpoint"])
        predictions = {}
        for image, result in zip(images, model.predict(source=[str(path) for path in images], stream=True, imgsz=640, conf=0.001, iou=0.70, device=device, verbose=False), strict=True):
            values = []
            if result.boxes is not None:
                for box, confidence in zip(result.boxes.xywhn.detach().cpu().tolist(), result.boxes.conf.detach().cpu().tolist(), strict=True):
                    values.append(Prediction(YoloBox(0, *[float(value) for value in box]), float(confidence)))
            predictions[image.name] = values
        payload = {"checkpoint_sha256": run["checkpoint_sha256"], "split": "val", "test_consulted": False, "predictions": {name: [{"box": vars(item.box), "confidence": item.confidence} for item in values] for name, values in predictions.items()}}
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    sweep = confidence_sweep(ground_truth, predictions)
    stratified = stratified_recall(ground_truth, predictions, profile, confidence=sweep["selected"]["confidence"])
    return {"confidence_sweep": sweep, "difficulty": stratified}


def _aggregate(runs):
    scenarios = sorted({run["scenario"] for run in runs})
    aggregate = {}
    for scenario in scenarios:
        selected = [run for run in runs if run["scenario"] == scenario]
        aggregate[scenario] = {metric: {"mean": statistics.mean(run[metric] for run in selected), "sd": statistics.stdev(run[metric] for run in selected) if len(selected) > 1 else 0.0} for metric in ("precision", "recall", "map50", "map5095")}
        wall_times = [float(run["wall_time_seconds"]) for run in selected if run.get("wall_time_seconds") is not None]
        aggregate[scenario]["wall_time_seconds"] = {
            "mean": statistics.mean(wall_times) if wall_times else None,
            "sd": statistics.stdev(wall_times) if len(wall_times) > 1 else 0.0,
        }
        if all("operational" in run for run in selected):
            aggregate[scenario]["recall_at_precision_ge_098_mean"] = statistics.mean(run["operational"]["confidence_sweep"]["selected"]["recall"] for run in selected)
            aggregate[scenario]["difficulty_recall_mean"] = {
                label: statistics.mean(
                    run["operational"]["difficulty"]["strata"][label]["recall"]
                    for run in selected
                )
                for label in sorted(selected[0]["operational"]["difficulty"]["strata"])
            }
    paired = {}
    for scenario in scenarios:
        paired[scenario] = {}
        for baseline in ("V2-E0", "V2-E0R"):
            differences = []
            for run in [item for item in runs if item["scenario"] == scenario]:
                match = next((item for item in runs if item["scenario"] == baseline and item["seed"] == run["seed"]), None)
                if match:
                    differences.append(run["map5095"] - match["map5095"])
            operational_differences = []
            size_differences = {f"size:{band}": [] for band in ("small", "medium", "large")}
            for run in [item for item in runs if item["scenario"] == scenario and "operational" in item]:
                match = next(
                    (
                        item
                        for item in runs
                        if item["scenario"] == baseline
                        and item["seed"] == run["seed"]
                        and "operational" in item
                    ),
                    None,
                )
                if match:
                    operational_differences.append(
                        run["operational"]["confidence_sweep"]["selected"]["recall"]
                        - match["operational"]["confidence_sweep"]["selected"]["recall"]
                    )
                    for label in size_differences:
                        size_differences[label].append(
                            run["operational"]["difficulty"]["strata"][label]["recall"]
                            - match["operational"]["difficulty"]["strata"][label]["recall"]
                        )
            paired[scenario][baseline] = {
                "mean_delta_map5095": statistics.mean(differences) if differences else None,
                "positive_seeds": sum(value > 0 for value in differences),
                "pair_count": len(differences),
                "differences": differences,
                "mean_delta_operational_recall": statistics.mean(operational_differences) if operational_differences else None,
                "operational_recall_differences": operational_differences,
                "mean_delta_size_recall": {
                    label: statistics.mean(values) if values else None
                    for label, values in size_differences.items()
                },
            }
    scorecard, ranking, finalists = _multi_criterion_selection(scenarios, aggregate, paired)
    return {
        "aggregate": aggregate,
        "paired": paired,
        "ranking": ranking,
        "selection_method": {
            "name": "unweighted_rank_sum_with_runtime_tiebreak",
            "status": "engineering_rule_fixed_before_screening_results",
            "descending_criteria": [
                "mean_map5095",
                "mean_delta_map5095_vs_e0r",
                "positive_seed_count_vs_e0r",
                "mean_delta_operational_recall_vs_e0r",
                "worst_mean_delta_size_recall_vs_e0r",
            ],
            "tiebreak": "lower_mean_wall_time_seconds_then_higher_mean_map5095",
            "maximum_recipe_finalists": 3,
        },
        "selection_scorecard": scorecard,
        "recommended_confirmatory_scenarios": ["V2-E0", "V2-E0R", *finalists] if finalists else [],
    }


def _multi_criterion_selection(scenarios, aggregate, paired):
    recipes = [scenario for scenario in scenarios if scenario not in {"V2-E0", "V2-E0R"}]
    scorecard = {}
    for scenario in recipes:
        comparison = paired[scenario]["V2-E0R"]
        size_deltas = [
            value
            for value in comparison["mean_delta_size_recall"].values()
            if value is not None
        ]
        scorecard[scenario] = {
            "mean_map5095": aggregate[scenario]["map5095"]["mean"],
            "mean_delta_map5095_vs_e0r": comparison["mean_delta_map5095"],
            "positive_seed_count_vs_e0r": comparison["positive_seeds"],
            "mean_delta_operational_recall_vs_e0r": comparison["mean_delta_operational_recall"],
            "worst_mean_delta_size_recall_vs_e0r": min(size_deltas) if size_deltas else None,
            "mean_wall_time_seconds": aggregate[scenario]["wall_time_seconds"]["mean"],
        }
    criteria = (
        "mean_map5095",
        "mean_delta_map5095_vs_e0r",
        "positive_seed_count_vs_e0r",
        "mean_delta_operational_recall_vs_e0r",
        "worst_mean_delta_size_recall_vs_e0r",
    )
    if not scorecard or any(scorecard[scenario][criterion] is None for scenario in scorecard for criterion in criteria):
        fallback = sorted(scenarios, key=lambda scenario: aggregate[scenario]["map5095"]["mean"], reverse=True)
        return scorecard, fallback, []
    for criterion in criteria:
        ordered_values = sorted({scorecard[scenario][criterion] for scenario in scorecard}, reverse=True)
        for scenario in scorecard:
            scorecard[scenario].setdefault("criterion_ranks", {})[criterion] = ordered_values.index(scorecard[scenario][criterion]) + 1
    for scenario in scorecard:
        scorecard[scenario]["rank_sum"] = sum(scorecard[scenario]["criterion_ranks"].values())
    recipe_ranking = sorted(
        recipes,
        key=lambda scenario: (
            scorecard[scenario]["rank_sum"],
            scorecard[scenario]["mean_wall_time_seconds"] if scorecard[scenario]["mean_wall_time_seconds"] is not None else float("inf"),
            -scorecard[scenario]["mean_map5095"],
            scenario,
        ),
    )
    controls = sorted((scenario for scenario in scenarios if scenario in {"V2-E0", "V2-E0R"}))
    return scorecard, [*recipe_ranking, *controls], recipe_ranking[:3]


def _read_simple_yaml(path: Path):
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _markdown(report):
    lines = [
        "# Screening Classical Augmentation v2",
        "",
        "Selección realizada exclusivamente sobre `val`; `test` no fue consultado.",
        "",
        "| Escenario | mAP50-95 media | Δ vs E0R | Signos + | Δ recall operacional | Peor Δ recall por tamaño | Tiempo medio (s) | Suma de rangos |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario in report["ranking"]:
        aggregate = report["aggregate"][scenario]["map5095"]["mean"]
        paired = report["paired"][scenario]["V2-E0R"]
        delta = paired["mean_delta_map5095"]
        size_values = [value for value in paired["mean_delta_size_recall"].values() if value is not None]
        worst_size = min(size_values) if size_values else float("nan")
        operational = paired["mean_delta_operational_recall"]
        wall_time = report["aggregate"][scenario]["wall_time_seconds"]["mean"]
        rank_sum = report["selection_scorecard"].get(scenario, {}).get("rank_sum")
        lines.append(
            f"| {scenario} | {aggregate:.4f} | {delta if delta is not None else float('nan'):.4f} "
            f"| {paired['positive_seeds']}/{paired['pair_count']} "
            f"| {operational if operational is not None else float('nan'):.4f} | {worst_size:.4f} "
            f"| {wall_time if wall_time is not None else float('nan'):.1f} "
            f"| {rank_sum if rank_sum is not None else 'n/a'} |"
        )
    finalists = report["recommended_confirmatory_scenarios"]
    recommendation = ", ".join(finalists) if finalists else "ninguna; faltan métricas operacionales completas"
    lines.extend(["", "Finalistas recomendados: " + recommendation, ""])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
