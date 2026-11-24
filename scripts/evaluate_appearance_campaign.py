"""Locked development evaluation and paired factorial contrasts for appearance v1."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import contextlib
import csv
from pathlib import Path
import statistics
import time

import numpy as np
import torch
from ultralytics import YOLO
from ultralytics.utils.metrics import box_iou

from appearance_campaign import (BANKS, SEEDS, NAMES, arm_id, charged_job, checked_labels, digest,
    process_identity, read, real_rows, remaining_budget, require, sha, verify_real, verify_review, verify_sources, write)
from evaluate_augmentation_campaign import stats, ap_summary
from evaluate_union_detector import fixed_match
from run_appearance_campaign import audit_confirmation, verify_pair


def mean_sd(values):
    return dict(mean=float(statistics.mean(values)), sd=float(statistics.stdev(values)) if len(values) > 1 else 0.)


def checked_groups(records, replicates=200, seed=20261022):
    """Common draws retain the same three-class denominator; rejections persist."""
    groups = sorted({row["group"] for row in records})
    presence = {group: set() for group in groups}
    for row in records:
        presence[row["group"]].update(row["stats"]["target_cls"])
    require(set().union(*presence.values()) == {0, 1, 2}, "Development truth lacks a class")
    rng = np.random.default_rng(seed)
    accepted, rejected = [], []
    attempts = 0
    while len(accepted) < replicates:
        sampled = rng.choice(groups, len(groups), replace=True).tolist()
        classes = set().union(*(presence[g] for g in sampled))
        if classes == {0, 1, 2}:
            accepted.append(sampled)
        else:
            rejected.append(dict(draw_index=attempts, groups=sampled, missing_classes=sorted({0, 1, 2} - classes)))
        attempts += 1
        require(attempts <= 100000, "Unable to obtain class-complete group draws")
    return dict(seed=seed, replicates=replicates, groups=groups, draws=accepted, rejected=rejected,
                attempts=attempts, group_image_counts=dict(Counter(r["group"] for r in records)),
                conditioning="All three truth classes; fixed trained seeds; common paired group draws",
                limitation="Few unequal groups, repeated development test, selected candidates; no independent-session or confirmatory significance claim")


def three_class_ap(records):
    result = ap_summary(records)
    require({r["class_id"] for r in result["per_class"]} == {0, 1, 2}, "Macro denominator must remain three classes")
    return result


def evaluate_run(root, name, threshold, lock):
    root = Path(root)
    folder = root / "evaluation" / name
    summary_path = folder / "summary.json"
    prediction_path = folder / "predictions.json"
    provenance = dict(weight_sha256=lock["weights"][name], evaluation_lock_sha256=sha(root / "evaluation_lock.json"),
                      threshold_sha256=sha(root / "evaluation_threshold.json"), real_manifest_sha256=sha(root / "real_manifest.json"))
    if summary_path.exists():
        summary = read(summary_path)
        require(summary["inputs"] == provenance, "Cached evaluation inputs changed")
        require(summary["predictions_sha256"] == sha(prediction_path), "Cached predictions changed")
        return summary
    model = YOLO(root / "training" / name / "weights/best.pt")
    records = []
    confusion = np.zeros((4, 4), int)
    strata = defaultdict(Counter)
    for row in real_rows(root):
        if row["split"] != "test":
            continue
        if remaining_budget(root, "evaluation") <= 0:
            raise TimeoutError("Active evaluation budget exhausted")
        result = model.predict(row["image"], imgsz=960, conf=.001, iou=.7, max_det=300, device=0, verbose=False)[0]
        height, width = result.orig_shape
        truth = [dict(class_id=int(c), bbox=[(x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height],
                      size=min(w*width, h*height) * 960 / max(width, height)) for c, x, y, w, h in checked_labels(row["label"])]
        predictions = [dict(class_id=int(c), confidence=float(score), bbox=box.tolist()) for box, c, score in
                       zip(result.boxes.xyxy.cpu().numpy(), result.boxes.cls.cpu().numpy(), result.boxes.conf.cpu().numpy())]
        predictions.sort(key=lambda p: -p["confidence"])
        fixed = [p for p in predictions if p["confidence"] >= threshold]
        counts = {}
        for key, collapsed in (("class_aware", False), ("collapsed", True)):
            tp, fp, fn = fixed_match(truth, fixed, collapsed)
            counts[key] = dict(tp=tp.tolist(), fp=fp.tolist(), fn=fn.tolist())
        g = torch.tensor([r["bbox"] for r in truth], dtype=torch.float32).reshape(-1, 4)
        p = torch.tensor([r["bbox"] for r in fixed], dtype=torch.float32).reshape(-1, 4)
        ious = box_iou(g, p).numpy()
        remaining, matched = set(range(len(truth))), {}
        for j, prediction in enumerate(fixed):
            value, i = max(((ious[i, j], i) for i in remaining), default=(0, None))
            if value >= .5:
                matched[i] = prediction
                remaining.remove(i)
                confusion[truth[i]["class_id"], prediction["class_id"]] += 1
            else:
                confusion[3, prediction["class_id"]] += 1
        for i in remaining:
            confusion[truth[i]["class_id"], 3] += 1
        for i, item in enumerate(truth):
            size = item["size"]
            band = "<16" if size < 16 else "16-32" if size < 32 else "32-64" if size < 64 else ">=64"
            density = "1-7" if len(truth) <= 7 else "8-22" if len(truth) <= 22 else ">22"
            for key in ("size:" + band, "density:" + density):
                strata[key]["truth"] += 1
                strata[key]["localized"] += i in matched
                strata[key]["correct_class"] += i in matched and matched[i]["class_id"] == item["class_id"]
        records.append(dict(source_row=row["source_row"], group=row["group_id"], image=row["image"],
                            truth=truth, predictions=predictions, stats=stats(truth, predictions),
                            collapsed_stats=stats(truth, predictions, True), fixed=counts))
    summary = dict(ap=three_class_ap(records), collapsed_ap=ap_summary(records, "collapsed_stats"),
                   threshold=threshold, confusion_rows_truth_columns_pred_background_last=confusion.tolist(),
                   strata=dict(strata), fixed={}, inputs=provenance)
    for key in ("class_aware", "collapsed"):
        totals = {k: np.sum([r["fixed"][key][k] for r in records], axis=0) for k in ("tp", "fp", "fn")}
        tp, fp, fn = totals["tp"], totals["fp"], totals["fn"]
        summary["fixed"][key] = dict(**{k: v.tolist() for k, v in totals.items()},
                                        precision=float(tp.sum() / max(1, (tp+fp).sum())),
                                        recall=float(tp.sum() / max(1, (tp+fn).sum())))
    write(prediction_path, records)
    summary["predictions_sha256"] = sha(prediction_path)
    write(summary_path, summary)
    return summary


def audit_lock(root):
    root = Path(root)
    verify_review(root)
    verify_sources(root)
    verify_real(root)
    lock, runs = audit_confirmation(root)
    for c, winner in lock["winners"].items():
        dose, classic = winner["dose"], bool(int(c))
        for seed in SEEDS:
            base = f"final_{arm_id('B', dose, classic)}_{seed}"
            for bank in ("L", "T", "LT"):
                verify_pair(root, base, f"final_{arm_id(bank, dose, classic)}_{seed}")
            original = f"final_{arm_id(winner['bank'], dose, classic)}_{seed}"
            verify_pair(root, original, "repeat_" + original, repeat=True)
    return lock, runs


def calculate_contrasts(root, lock, runs, summaries):
    root = Path(root)
    predictions = {name: read(root / "evaluation" / name / "predictions.json") for name in lock["runs"]}
    common = next(iter(predictions.values()))
    expected = [(r["source_row"], r["group"], r["truth"]) for r in common]
    require(all([(r["source_row"], r["group"], r["truth"]) for r in rows] == expected for rows in predictions.values()),
            "Evaluation truth differs across paired runs")
    design = checked_groups(common)
    write(root / "evaluation/bootstrap_design.json", design)
    caches = {}
    for name in lock["runs"]:
        path = root / "evaluation/bootstrap_cache" / (name + ".json")
        inputs = dict(predictions_sha256=sha(root / "evaluation" / name / "predictions.json"), design=digest(design))
        if path.exists():
            stored = read(path)
            require(stored["inputs"] == inputs, "Bootstrap cache changed")
            values = stored["values"]
            require(len(values) == design["replicates"] and all(np.isfinite(x) and 0 <= x <= 1 for x in values),
                    "Incomplete or invalid bootstrap cache")
        else:
            by_group = {g: [r for r in predictions[name] if r["group"] == g] for g in design["groups"]}
            values = []
            for sampled in design["draws"]:
                if remaining_budget(root, "evaluation") <= 0:
                    raise TimeoutError("Active budget exhausted during group bootstrap")
                values.append(three_class_ap([r for g in sampled for r in by_group[g]])["map50_95"])
            write(path, dict(inputs=inputs, values=values))
        caches[name] = np.asarray(values)
        print("Bootstrap", name, flush=True)
    contrasts = []
    factorial = []
    for key, winner in lock["winners"].items():
        classic, dose = bool(int(key)), winner["dose"]
        chosen = arm_id(winner["bank"], dose, classic)
        comparator_arms = [arm_id("B", dose, classic), arm_id("real", 0, classic), "repeat_" + chosen]
        for comparator in comparator_arms:
            rows, samples = [], []
            for seed in SEEDS:
                a = f"final_{chosen}_{seed}"
                b = f"repeat_final_{chosen}_{seed}" if comparator.startswith("repeat_") else f"final_{comparator}_{seed}"
                delta = summaries[a]["ap"]["map50_95"] - summaries[b]["ap"]["map50_95"]
                sampled = caches[a] - caches[b]
                samples.append(sampled)
                rows.append(dict(seed=seed, candidate_run=a, comparator_run=b, delta=delta,
                                 group_bootstrap_95=np.quantile(sampled, [.025, .975]).tolist(),
                                 class_deltas={str(c): next(x["map50_95"] for x in summaries[a]["ap"]["per_class"] if x["class_id"] == c)
                                  - next(x["map50_95"] for x in summaries[b]["ap"]["per_class"] if x["class_id"] == c) for c in range(3)}))
            contrasts.append(dict(classical=classic, candidate=chosen, comparator=comparator, seeds=rows,
                                  paired_delta=mean_sd([r["delta"] for r in rows]),
                                  group_bootstrap_mean_delta_95=np.quantile(np.mean(samples, axis=0), [.025, .975]).tolist(),
                                  positive_all_three_seeds=all(r["delta"] > 0 for r in rows)))
        coefficients = {"light_L_minus_B": {"L": 1, "B": -1}, "materials_T_minus_B": {"T": 1, "B": -1},
                        "interaction_LT_minus_L_minus_T_plus_B": {"LT": 1, "L": -1, "T": -1, "B": 1}}
        for effect, coeffs in coefficients.items():
            rows, samples = [], []
            for seed in SEEDS:
                names = {bank: f"final_{arm_id(bank, dose, classic)}_{seed}" for bank in BANKS}
                value = sum(coef * summaries[names[bank]]["ap"]["map50_95"] for bank, coef in coeffs.items())
                sample = sum(coef * caches[names[bank]] for bank, coef in coeffs.items())
                rows.append(dict(seed=seed, effect=value))
                samples.append(sample)
            factorial.append(dict(classical=classic, dose=dose, effect=effect, seeds=rows,
                                  estimate=mean_sd([r["effect"] for r in rows]),
                                  group_bootstrap_mean_95=np.quantile(np.mean(samples, axis=0), [.025, .975]).tolist()))
    arms = defaultdict(list)
    for name, run in runs.items():
        arm = ("repeat_" if run["config"]["repeat_control"] else "") + run["config"]["arm"]
        value = summaries[name]
        arms[arm].append(dict(run=name, seed=run["config"]["seed"], validation_ap=run["best_validation_ap"],
             test_ap=value["ap"]["map50_95"], per_class=value["ap"]["per_class"],
             collapsed_ap=value["collapsed_ap"]["map50_95"], precision=value["fixed"]["class_aware"]["precision"],
             recall=value["fixed"]["class_aware"]["recall"], exposure=run["exposure"],
             instance_exposure=run["instance_exposure"], best_sha256=run["best_sha256"]))
    payload = dict(test_status="development_previously_consulted", winners=lock["winners"],
                   arms={arm: dict(runs=sorted(rows, key=lambda r: r["seed"]), test_ap=mean_sd([r["test_ap"] for r in rows])) for arm, rows in arms.items()},
                   contrasts=contrasts, factorial=factorial, bootstrap_limitation=design["limitation"],
                   pending_runs=lock["pending_runs"], selection_used_test=False)
    write(root / "evaluation/paired_comparisons.json", payload)
    return payload, predictions


def report(root, payload, summaries, predictions):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from PIL import Image
    root = Path(root)
    output = root / "evaluation"
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for axis, classic in zip(axes, (True, False)):
        for bank in BANKS:
            points = []
            for path in (root / "training").glob("screen_*/completion.json"):
                row = read(path)
                if row["config"]["bank"] == bank and row["config"]["classical"] == classic:
                    points.append((row["config"]["synthetic_images"] / 461, 100 * row["best_validation_ap"]))
            points.sort()
            if points:
                axis.plot(*zip(*points), marker="o", label=bank)
        axis.set(title=f"Screening: clásica {'sí' if classic else 'no'}", xlabel="Sintéticas / reales", ylabel="AP macro validación (%)")
        axis.grid(alpha=.2)
        axis.legend()
    fig.tight_layout(); fig.savefig(output / "screening_curves.png", dpi=150); plt.close(fig)
    fig, axis = plt.subplots(figsize=(10, 5))
    for arm, data in payload["arms"].items():
        axis.errorbar(arm, data["test_ap"]["mean"] * 100, yerr=data["test_ap"]["sd"] * 100, fmt="o", capsize=4)
    axis.set(ylabel="AP macro desarrollo (%), media ± DE", title="Tres semillas; no evaluación externa")
    axis.tick_params(axis="x", labelrotation=65); axis.grid(axis="y", alpha=.2)
    fig.tight_layout(); fig.savefig(output / "confirmation_ap.png", dpi=150); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 8))
    for axis, classic in zip(axes, (True, False)):
        for name in sorted(predictions):
            if bool(read(root / "training" / name / "completion.json")["config"]["classical"]) != classic:
                continue
            path = root / "training" / name / "results.csv"
            if not path.exists():
                continue
            with path.open() as stream:
                rows = [{k.strip(): v for k, v in row.items()} for row in csv.DictReader(stream)]
            axis.plot([int(float(r["epoch"])) * 500 for r in rows],
                      [100 * float(r["metrics/mAP50-95(B)"]) for r in rows], alpha=.7, label=name)
        axis.set(title=f"Curvas de validación, clásica={classic}", xlabel="Actualizaciones", ylabel="AP macro (%)")
        axis.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(output / "validation_curves.png", dpi=150); plt.close(fig)
    # Persisted predictions only; deterministic sample panels do not select models.
    first_winner = next(iter(payload["winners"].values()))
    arm = arm_id(first_winner["bank"], first_winner["dose"], first_winner["classical"])
    selected = f"final_{arm}_{SEEDS[0]}"
    rows = predictions[selected]
    chosen = sorted(rows, key=lambda r: r["source_row"])[:4]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    colors = ("lime", "orange", "magenta")
    for axis, row in zip(axes.flat, chosen):
        axis.imshow(Image.open(row["image"]))
        for truth in row["truth"]:
            x1, y1, x2, y2 = truth["bbox"]
            axis.add_patch(Rectangle((x1, y1), x2-x1, y2-y1, fill=False, edgecolor="white", linewidth=.8, linestyle="--"))
        for prediction in row["predictions"]:
            if prediction["confidence"] < summaries[selected]["threshold"]:
                continue
            x1, y1, x2, y2 = prediction["bbox"]
            axis.add_patch(Rectangle((x1, y1), x2-x1, y2-y1, fill=False, edgecolor=colors[prediction["class_id"]], linewidth=.8))
        axis.set_title(f"Fila {row['source_row']}; blanco=anotación"); axis.axis("off")
    fig.tight_layout(); fig.savefig(output / "prediction_samples.png", dpi=150); plt.close(fig)
    lines = ["# Piloto factorial de apariencia", "", "Evaluación de desarrollo históricamente consultada; no validación externa.", "",
             "La selección de dosis, variantes y checkpoints usó exclusivamente validación. Las diferencias son exploratorias.", "",
             "## Contrastes emparejados", "", "| Clásica | Candidato | Comparador | Δ AP medio (pp) | DE (pp) | Tres semillas positivas |",
             "|---|---|---|---:|---:|---|"]
    for row in payload["contrasts"]:
        lines.append(f"| {row['classical']} | {row['candidate']} | {row['comparator']} | {100*row['paired_delta']['mean']:.3f} | {100*row['paired_delta']['sd']:.3f} | {row['positive_all_three_seeds']} |")
    lines += ["", "## Resultados por semilla", "", "| Ejecución | AP macro | Pintona | Madura | Sobremadura | AP colapsado | Precisión | Recall |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm, data in payload["arms"].items():
        for row in data["runs"]:
            values = {r["class_id"]: r["map50_95"] for r in row["per_class"]}
            numbers = [row["test_ap"], *[values[c] for c in range(3)], row["collapsed_ap"], row["precision"], row["recall"]]
            lines.append("| " + row["run"] + " | " + " | ".join(f"{100*v:.2f}" for v in numbers) + " |")
    lines += ["", "## Matriz de screening", "", "| Ejecución | Reales | Sintéticas | AP validación | Pasos |", "|---|---:|---:|---:|---:|"]
    for path in sorted((root / "training").glob("screen_*/completion.json")):
        row = read(path)
        lines.append(f"| {row['config']['name']} | 461 | {row['config']['synthetic_images']} | {100*row['best_validation_ap']:.2f} | {row['steps']} |")
    lines += ["", "## Límites e interpretación", "", payload["bootstrap_limitation"], "",
              "Una ganancia macro con caída de Madura constituye un intercambio de desempeño. Los contrastes de materiales incluyen conjuntamente textura y apariencia de clase; no separan cada parámetro del shader.", "",
              "La nueva carga por planta, composición y diversidad son comunes a B/L/T/LT; este factorial no estima sus efectos individuales. Tamaño y densidad se describen, sin admisión geométrica retrospectiva.", "",
              "Pendientes: " + str(payload["pending_runs"]), "",
              "![Screening](screening_curves.png)", "![Confirmación](confirmation_ap.png)",
              "![Validación](validation_curves.png)", "![Muestras](prediction_samples.png)", "",
              "Resultados completos, confusiones y estratos en summary.json; contrastes e interacción en paired_comparisons.json. Exposición y hashes por corrida en training/. Se requiere revisión final de estas evidencias antes de cerrar."]
    destination = output / "report.md"
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write(output / "report_manifest.json", dict(report=str(destination), sha256=sha(destination),
                                              status="pending_human_and_agent_final_review"))


def evaluate(root):
    root = Path(root).resolve()
    torch.set_num_threads(4)
    lock, runs = audit_lock(root)
    threshold_path = root / "evaluation_threshold.json"
    if not threshold_path.exists():
        classic = True if "1" in lock["winners"] else False
        baseline = f"final_{arm_id('real', 0, classic)}_{SEEDS[0]}"
        result = YOLO(root / "training" / baseline / "weights/best.pt").val(
            data=runs[baseline]["config"]["dataset"], split="val", imgsz=960, batch=2, device=0, workers=0,
            conf=.001, iou=.7, max_det=300, plots=False, project=str(root / "evaluation"), name="threshold_validation")
        curve = np.asarray(result.box.f1_curve)
        threshold = float(result.box.px[np.argmax(curve.mean(0))])
        write(threshold_path, dict(value=threshold, source=baseline, split="val", test_used=False,
                                  weight_sha256=lock["weights"][baseline], evaluation_lock_sha256=sha(root / "evaluation_lock.json")))
    threshold_record = read(threshold_path)
    require(threshold_record["test_used"] is False and threshold_record["evaluation_lock_sha256"] == sha(root / "evaluation_lock.json"), "Invalid operating threshold lock")
    summaries = {name: evaluate_run(root, name, threshold_record["value"], lock) for name in lock["runs"]}
    write(root / "evaluation/summary.json", summaries)
    payload, predictions = calculate_contrasts(root, lock, runs, summaries)
    report(root, payload, summaries, predictions)
    write(root / "evaluation/completion.json", dict(completed=True, runs=len(runs), finished_utc=time.time(),
          paired_comparisons_sha256=sha(root / "evaluation/paired_comparisons.json"), selection_used_test=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--accounting-job", default=None)
    args = parser.parse_args()
    if args.accounting_job:
        job = read(args.root / "execution_jobs" / (args.accounting_job + ".json"))
        require(job["state"] == "active" and job["phase"] == "evaluation"
                and process_identity(job["identity"]["pid"]) == job["identity"], "Accounting owner is not alive")
        context = contextlib.nullcontext()
    else:
        context = charged_job(args.root, "evaluation", "development_evaluation")
    with context:
        evaluate(args.root)
