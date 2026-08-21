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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/domain_profile/real_train_profile.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="0")
    parser.add_argument("--skip-operational", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = read_profile(args.profile)
    runs = _discover_runs(args.project)
    if not runs:
        raise RuntimeError(f"No complete runs found under {args.project}")
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
        if all("operational" in run for run in selected):
            aggregate[scenario]["recall_at_precision_ge_098_mean"] = statistics.mean(run["operational"]["confidence_sweep"]["selected"]["recall"] for run in selected)
    paired = {}
    for scenario in scenarios:
        paired[scenario] = {}
        for baseline in ("V2-E0", "V2-E0R"):
            differences = []
            for run in [item for item in runs if item["scenario"] == scenario]:
                match = next((item for item in runs if item["scenario"] == baseline and item["seed"] == run["seed"]), None)
                if match:
                    differences.append(run["map5095"] - match["map5095"])
            paired[scenario][baseline] = {"mean_delta_map5095": statistics.mean(differences) if differences else None, "positive_seeds": sum(value > 0 for value in differences), "pair_count": len(differences), "differences": differences}
    ranking = sorted(scenarios, key=lambda scenario: (aggregate[scenario]["map5095"]["mean"], paired[scenario]["V2-E0R"]["positive_seeds"]), reverse=True)
    finalists = [code for code in ranking if code not in {"V2-E0", "V2-E0R"}][:3]
    return {"aggregate": aggregate, "paired": paired, "ranking": ranking, "recommended_confirmatory_scenarios": ["V2-E0", "V2-E0R", *finalists]}


def _read_simple_yaml(path: Path):
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _markdown(report):
    lines = ["# Screening Classical Augmentation v2", "", "Selección realizada exclusivamente sobre `val`; `test` no fue consultado.", "", "| Escenario | mAP50-95 media | Δ vs E0R | Signos positivos |", "|---|---:|---:|---:|"]
    for scenario in report["ranking"]:
        aggregate = report["aggregate"][scenario]["map5095"]["mean"]
        paired = report["paired"][scenario]["V2-E0R"]
        delta = paired["mean_delta_map5095"]
        lines.append(f"| {scenario} | {aggregate:.4f} | {delta if delta is not None else float('nan'):.4f} | {paired['positive_seeds']}/{paired['pair_count']} |")
    lines.extend(["", "Finalistas recomendados: " + ", ".join(report["recommended_confirmatory_scenarios"]), ""])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
