"""Audit a frozen pilot using saved predictions only; never loads a model.

The output is a new directory. Inputs, historical metrics, labels and weights
are read-only. Uses the NumPy/Pillow/Ultralytics installation already present.
Run with --help; no generation, inference, training or network is performed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import platform
import re
import statistics
import time
from types import SimpleNamespace

import numpy as np

VERSION = "cached-synthetic-bias/1.1"
PRESET = "reviewed115_frozen_evaluation"
CLASSES = (0, 1, 2)
BANDS = ("<16", "16-32", "32-64", ">=64")
METRIC_ORDER = ("macro", "Pintona", "Madura", "Sobremadura", "collapsed")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Inputs:
    """Record hashes and verify that every observed input stays unchanged."""

    def __init__(self):
        self.hashes = {}

    def digest(self, path, expected=None):
        path = Path(path).resolve()
        value = sha(path)
        if expected is not None:
            require(value == expected, "Hash mismatch: " + str(path))
        if str(path) in self.hashes:
            require(self.hashes[str(path)] == value, "Input changed: " + str(path))
        self.hashes[str(path)] = value
        return value

    def text(self, path):
        self.digest(path)
        return Path(path).read_text(encoding="utf-8-sig")

    def read(self, path):
        return json.loads(self.text(path))

    def verify(self):
        for path, expected in self.hashes.items():
            require(sha(path) == expected, "Input changed during audit: " + path)


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def size_band(value):
    return BANDS[0 if value < 16 else 1 if value < 32 else 2 if value < 64 else 3]


def split_crossings(rows, key):
    observed = defaultdict(set)
    for row in rows:
        observed[row[key]].add(row["split"])
    return {str(k): sorted(v) for k, v in observed.items() if len(v) > 1}


def selected_epoch(csv_text, best_fitness):
    """Infer only a unique best val epoch; CSV is rounded, not checkpoint metadata."""
    rows = [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(csv_text))]
    scores = [float(r["metrics/mAP50-95(B)"]) for r in rows]
    candidates = [int(float(r["epoch"])) for r, score in zip(rows, scores) if score == max(scores)]
    require(abs(max(scores) - best_fitness) <= 0.00001, "CSV best differs from completion fitness")
    require([int(float(r["epoch"])) for r in rows] == list(range(1, 9)), "Expected eight complete epochs")
    return dict(epoch=candidates[0] if len(candidates) == 1 else None,
                candidates=candidates, updates=500*candidates[0] if len(candidates) == 1 else None,
                evidence="unique maximum of rounded validation CSV, checked against completion fitness",
                last_validation_ap=scores[-1], best_validation_ap=best_fitness)


def summarize_ap(records, key="stats"):
    """Absent classes remain null; never silently change the three-class macro."""
    from ultralytics.utils.metrics import ap_per_class
    tp = np.concatenate([np.asarray(r[key]["tp"], bool).reshape(-1, 10) for r in records])
    conf = np.concatenate([np.asarray(r[key]["conf"], float) for r in records])
    pc = np.concatenate([np.asarray(r[key]["pred_cls"], int) for r in records])
    gc = np.concatenate([np.asarray(r[key]["target_cls"], int) for r in records])
    target = Counter(map(int, gc))
    if len(gc):
        native = ap_per_class(tp, conf, pc, gc)
        values = {int(c): native[5][i] for i, c in enumerate(native[6])}
    else:
        values = {}
    per_class = {str(c): (dict(ap50_95=float(values[c].mean()), ap50=float(values[c][0]),
                             ap75=float(values[c][5]), truth=target[c]) if c in values else None)
                 for c in (CLASSES if key == "stats" else (0,))}
    expected = set(CLASSES if key == "stats" else (0,))
    return dict(macro_ap50_95=float(np.mean([v.mean() for v in values.values()]))
                if set(values) == expected else None,
                per_class=per_class, predictions=len(conf), truth=len(gc))


def native_stats(row, collapsed=False):
    """Recompute matching from saved boxes, independently of saved TP flags."""
    import torch
    from ultralytics.engine.validator import BaseValidator
    from ultralytics.utils.metrics import box_iou
    truth, predictions = row["truth"], row["predictions"]
    g = torch.tensor([r["bbox"] for r in truth], dtype=torch.float32).reshape(-1, 4)
    p = torch.tensor([r["bbox"] for r in predictions], dtype=torch.float32).reshape(-1, 4)
    gc = torch.tensor([0 if collapsed else r["class_id"] for r in truth])
    pc = torch.tensor([0 if collapsed else r["class_id"] for r in predictions])
    correct = BaseValidator.match_predictions(
        SimpleNamespace(iouv=torch.linspace(.5, .95, 10)), pc, gc, box_iou(g, p))
    return dict(tp=correct.tolist(), conf=[r["confidence"] for r in predictions],
                pred_cls=pc.tolist(), target_cls=gc.tolist())


def verify_truth(inputs, rows, real_manifest):
    """Compare cached truth to the independently frozen real labels and images."""
    from PIL import Image
    sources = {r["source_row"]: r for r in real_manifest["records"] if r["split"] == "test"}
    require({r["source_row"] for r in rows} == set(sources), "Evaluation is not the complete frozen test")
    for row in rows:
        source = sources[row["source_row"]]
        require(row["group"] == source["group_id"], "Cached acquisition group changed")
        inputs.digest(row["image"], source["image_sha256"])
        inputs.digest(source["label"], source["label_sha256"])
        labels = [list(map(float, line.split())) for line in inputs.text(source["label"]).splitlines() if line.strip()]
        with Image.open(row["image"]) as im:
            w, h = im.size
        require(len(labels) == len(row["truth"]), "Cached truth count changed")
        for (cid, x, y, bw, bh), cached in zip(labels, row["truth"]):
            box = [(x-bw/2)*w, (y-bh/2)*h, (x+bw/2)*w, (y+bh/2)*h]
            require(cid == cached["class_id"], "Cached truth class changed")
            require(np.allclose(box, cached["bbox"], rtol=0, atol=1e-6), "Cached truth box differs from labels")
            require(abs(min(bw*w, bh*h)*960/max(w, h)-cached["size"]) < 1e-6, "Cached resize size differs")


def ordered_matches(row, threshold, agnostic=False):
    """Confidence-ordered one-to-one matches for operational diagnostics."""
    from ultralytics.utils.metrics import box_iou
    import torch
    truth = row["truth"]
    predictions = [(i, p) for i, p in enumerate(row["predictions"]) if p["confidence"] >= threshold]
    g = torch.tensor([r["bbox"] for r in truth], dtype=torch.float32).reshape(-1, 4)
    p = torch.tensor([r["bbox"] for _, r in predictions], dtype=torch.float32).reshape(-1, 4)
    overlaps = box_iou(g, p).numpy()
    remaining, matches, false_positives = set(range(len(truth))), {}, []
    for j in sorted(range(len(predictions)), key=lambda j: -predictions[j][1]["confidence"]):
        index, prediction = predictions[j]
        candidates = ((float(overlaps[i, j]), i) for i in remaining
                      if agnostic or prediction["class_id"] == truth[i]["class_id"])
        overlap, i = max(candidates, default=(0, None))
        if overlap >= .5:
            matches[i] = dict(prediction_index=index, iou=overlap)
            remaining.remove(i)
        else:
            false_positives.append(index)
    return matches, false_positives, remaining


def operational_summary(rows, threshold):
    tp, fp, fn = Counter(), Counter(), Counter()
    strata = defaultdict(Counter)
    for row in rows:
        matches, fps, missing = ordered_matches(row, threshold)
        tp.update(row["truth"][i]["class_id"] for i in matches)
        fp.update(row["predictions"][i]["class_id"] for i in fps)
        fn.update(row["truth"][i]["class_id"] for i in missing)
        geometric, _, _ = ordered_matches(row, threshold, agnostic=True)
        for i, truth in enumerate(row["truth"]):
            band = size_band(truth["size"])
            for key in ("all", "class:" + str(truth["class_id"]), "size:" + band,
                        "class_size:" + str(truth["class_id"]) + ":" + band):
                strata[key]["truth"] += 1
                strata[key]["class_aware_tp"] += i in matches
                strata[key]["geometrically_localized"] += i in geometric
                strata[key]["correct_class_given_geometric_match"] += (i in geometric and
                    row["predictions"][geometric[i]["prediction_index"]]["class_id"] == truth["class_id"])
    return dict(threshold=threshold, tp=[tp[c] for c in CLASSES], fp=[fp[c] for c in CLASSES],
                fn=[fn[c] for c in CLASSES], strata={k: dict(v) for k, v in strata.items()})


def count_exposure(sequences, per_source, epochs):
    images, instances = Counter(), defaultdict(Counter)
    for epoch in sequences[:epochs]:
        for source in epoch["actual_source_ids"]:
            domain = "real" if source.startswith("row_") else "synthetic"
            images[domain] += 1
            instances[domain].update(per_source[source])
    return dict(images=dict(images), instances={k: {str(c): v[c] for c in CLASSES}
                                               for k, v in instances.items()})


def truncate_predictions(row, cap):
    """Changing the candidate set requires new matches, not sliced TP flags."""
    selected = dict(row, predictions=sorted(row["predictions"], key=lambda p: -p["confidence"])[:cap])
    selected["stats"] = native_stats(selected)
    selected["collapsed_stats"] = native_stats(selected, True)
    return selected


def cap_sensitivity(predictions, seeds, threshold):
    caps, saturation = {}, {}
    for name, rows in predictions.items():
        capped = [r for r in rows if len(r["predictions"]) == 300]
        saturation[name] = dict(images=len(capped), source_rows=[r["source_row"] for r in capped],
                                last_scores=[r["predictions"][-1]["confidence"] for r in capped],
                                capped_at_operating_threshold=sum(r["predictions"][-1]["confidence"] >= threshold for r in capped))
    for cap in (100, 200):
        reduced = {name: [truncate_predictions(r, cap) for r in rows] for name, rows in predictions.items()}
        caps[str(cap)] = paired_delta(reduced, seeds, lambda rows: rows)
    caps["300"] = paired_delta(predictions, seeds, lambda rows: rows)
    return dict(caps=caps, saturation=saturation,
                interpretation="Post hoc evaluation truncation only; candidates above 300 or below confidence .001 are unavailable. No new limit is selected.")


def exposure_audit(inputs, manifest, plan, root):
    from PIL import Image
    from ultralytics.utils.instance import Instances
    from ultralytics.data.augment import RandomPerspective
    per_source, sizes = {}, defaultdict(list)
    counts = defaultdict(Counter)
    for row in manifest["entries"]:
        if row["split"] != "train":
            continue
        data = np.asarray([list(map(float, line.split())) for line in inputs.text(row["label"]).splitlines()
                           if line.strip()], dtype=np.float32).reshape(-1, 5)
        with Image.open(row["image"]) as im:
            w, h = im.size
        scale = 960 / max(w, h)
        rw, rh = min(math.ceil(w*scale), 960), min(math.ceil(h*scale), 960)
        boxes = Instances(data[:, 1:].copy(), np.zeros((0, 1000, 2), np.float32),
                          bbox_format="xywh", normalized=True)
        boxes.convert_bbox("xyxy")
        boxes.denormalize(rw, rh)
        boxes.add_padding(round((960-rw)/2-.1), round((960-rh)/2-.1))
        keep = RandomPerspective.box_candidates(boxes.bboxes.T, boxes.bboxes.T)
        per_source[row["source_id"]] = Counter(map(int, data[keep, 0]))
        for stage, subset in (("raw", data), ("native_kept", data[keep])):
            for cid, _, _, bw, bh in subset:
                key = (row["domain"], stage, int(cid))
                size = float(min(bw*w, bh*h)*scale)
                sizes[key].append(size)
                counts[key][size_band(size)] += 1
    distribution = [dict(domain=k[0], stage=k[1], class_id=k[2], instances=len(v),
                         min_side_960_median=float(np.median(v)), bands=dict(counts[k]))
                    for k, v in sorted(sizes.items())]
    runs, sequences, curves = {}, {}, {}
    for config in plan["configs"]:
        name = config["name"]
        folder = root / "training" / name
        completion = inputs.read(folder / "completion.json")
        sequence = inputs.read(folder / "sampling_sequences.json")
        sequences[name] = sequence
        require([e["epoch"] for e in sequence] == list(range(8)), "Nonsequential epochs")
        require(all(len(e["actual_source_ids"]) == 1000 for e in sequence), "Incomplete exposure sequence")
        csv_text = inputs.text(folder / "results.csv")
        best = selected_epoch(csv_text, completion["best_validation_ap"])
        curves[name] = [float(r["metrics/mAP50-95(B)"]) for r in csv.DictReader(io.StringIO(csv_text))]
        full = count_exposure(sequence, per_source, 8)
        require(full["images"] == completion["exposure"], "Image exposure mismatch")
        require({k: sum(v.values()) for k, v in full["instances"].items()} == completion["instance_exposure"],
                "Native instance exposure mismatch")
        for filename, key in (("weights/best.pt", "best_sha256"), ("weights/last.pt", "last_sha256"),
                              ("sampling_sequences.json", "sequence_sha256"),
                              ("augmentation_decisions.json", "augmentation_sha256"),
                              ("learning_rates.json", "learning_rates_sha256")):
            inputs.digest(folder / filename, completion[key])
        runs[name] = dict(selected_checkpoint=best, full_training=full,
                          selected_prefix=count_exposure(sequence, per_source, best["epoch"])
                          if best["epoch"] is not None else None)
    pairs = []
    for seed in sorted({c["seed"] for c in plan["configs"]}):
        a, b = (f"final_{arm}_{seed}" for arm in ("real_classical", "synthetic115_classical"))
        x, y = sequences[a], sequences[b]
        require([e["planned_source_ids"] for e in x] == [e["planned_source_ids"] for e in y], "Unpaired slots")
        require(all(actual_a == actual_b for ea, eb in zip(x, y)
                    for planned, actual_a, actual_b in zip(ea["planned_source_ids"], ea["actual_source_ids"], eb["actual_source_ids"])
                    if planned.startswith("row_")), "Real slots changed")
        require(all(s.startswith("row_") for e in x for s in e["actual_source_ids"]), "Control saw synthetic data")
        require(all(e["planned_source_ids"] == e["actual_source_ids"] for e in y), "Mixture resampling changed")
        for filename in ("learning_rates.json", "augmentation_decisions.json"):
            require(inputs.digest(root / "training" / a / filename) == inputs.digest(root / "training" / b / filename),
                    "Paired training settings changed")
        pairs.append(dict(seed=seed, slots_real_positions_LR_augmentation_equal=True,
                          selected_updates=[runs[a]["selected_checkpoint"]["updates"], runs[b]["selected_checkpoint"]["updates"]]))
    val_fixed_steps = []
    for epoch in range(8):
        deltas = [curves[f"final_synthetic115_classical_{p['seed']}"][epoch]
                  - curves[f"final_real_classical_{p['seed']}"][epoch] for p in pairs]
        val_fixed_steps.append(dict(updates=(epoch+1)*500, paired_deltas=deltas, mean_delta=statistics.mean(deltas)))
    return dict(distributions=distribution, runs=runs, pairs=pairs,
                validation_at_fixed_steps=val_fixed_steps,
                interpretation="Instance appearances, not independent organs or gradient weights. Prefix depends on inferred selected epoch.")


def composition(manifest):
    rows = manifest["entries"]
    real = [r for r in rows if r["domain"] == "real"]
    synth = [r for r in rows if r["domain"] == "synthetic"]
    names = []
    for r in real:
        match = re.match(r"(.+)_f\d+\.[^.]+$", r["file"])
        if match:
            names.append(dict(sequence=match[1], split=r["split"]))
    organs = defaultdict(set)
    repeats = Counter()
    for row in synth:
        for item in row["instances"]:
            organs[item["instance_id"]].add(item["class_id"])
            repeats[item["instance_id"]] += 1
    return dict(real_images_by_split=dict(Counter(r["split"] for r in real)),
                cross_split_image_hashes=split_crossings(real, "image_sha256"),
                cross_split_groups=split_crossings(real, "group_id"),
                cross_split_filename_prefixes=split_crossings(names, "sequence"),
                synthetic_images=len(synth), synthetic_splits=sorted({r["split"] for r in synth}),
                synthetic_scenes=dict(Counter(r["scene_id"] for r in synth)),
                synthetic_plant_ids=sorted({p for r in synth for p in r["plant_ids"]}),
                synthetic_unique_instance_ids=len(organs),
                synthetic_instances_repeated_across_views=sum(n > 1 for n in repeats.values()),
                synthetic_instance_view_count_median=statistics.median(repeats.values()),
                synthetic_instance_ids_with_multiple_classes={k: sorted(v) for k, v in organs.items() if len(v) > 1},
                limits="Hash/filename components are not verified acquisition-session identities; exact-image isolation does not remove historical test reuse.")


def metric_vector(rows):
    result = summarize_ap(rows)
    return [result["macro_ap50_95"], *[result["per_class"][str(c)]["ap50_95"]
            if result["per_class"][str(c)] is not None else None for c in CLASSES],
            summarize_ap(rows, "collapsed_stats")["macro_ap50_95"]]


def paired_delta(predictions, seeds, select):
    deltas = []
    for seed in seeds:
        values = [metric_vector(select(predictions[f"final_{arm}_{seed}"]))
                  for arm in ("real_classical", "synthetic115_classical")]
        deltas.append([b-a if a is not None and b is not None else None for a, b in zip(*values)])
    return dict(by_seed=deltas, mean=[statistics.mean(v) if all(x is not None for x in v) else None for v in zip(*deltas)])


def run(root, output):
    started = time.monotonic()
    root, output = root.resolve(), output.resolve()
    require(not output.exists(), "Output must be a new directory; preserve previous audit")
    require(root not in output.parents and output != root, "Write outside the frozen pilot")
    output.mkdir(parents=True)
    inputs = Inputs()
    plan = inputs.read(root / "plan.json")
    lock = inputs.read(root / "training_source_lock.json")
    for path, expected in lock["files"].items():
        inputs.digest(path, expected)
    versions = {p: importlib.metadata.version(p) for p in lock["packages"]}
    require(versions == lock["packages"], "Installed package versions differ from frozen training")
    print("Verified", len(lock["files"]), "locked inputs", flush=True)
    manifest = inputs.read(root / "datasets/paired_slots115/manifest.json")
    real_manifest = inputs.read(root / "real_manifest.json")
    summary = inputs.read(root / "evaluation/summary.json")
    evaluation_lock = inputs.read(root / "evaluation_lock.json")
    threshold = inputs.read(root / "evaluation_threshold.json")
    require(threshold["test_used"] is False and threshold["split"] == "val", "Threshold must be fixed from val")
    require(threshold["evaluation_lock_sha256"] == inputs.digest(root / "evaluation_lock.json"), "Threshold lock mismatch")
    require(evaluation_lock["plan_sha256"] == inputs.digest(root / "plan.json"), "Plan lock mismatch")
    require(evaluation_lock["source_lock_sha256"] == inputs.digest(root / "training_source_lock.json"), "Training lock mismatch")
    seeds = sorted({r["seed"] for r in plan["configs"]})
    predictions, metrics, recomputation = {}, {}, []
    import torch
    import inspect
    from ultralytics.engine.validator import BaseValidator
    from ultralytics.utils.metrics import ap_per_class
    from ultralytics.data.augment import RandomPerspective
    for native in (BaseValidator, ap_per_class, RandomPerspective):
        inputs.digest(inspect.getfile(native))
    torch.set_num_threads(2)
    common = None
    for config in plan["configs"]:
        name = config["name"]
        path = root / "evaluation" / name / "predictions.json"
        inputs.digest(path, summary[name]["predictions_sha256"])
        inputs.digest(root / "training" / name / "weights/best.pt", evaluation_lock["weights"][name])
        require(summary[name]["inputs"] == dict(weight_sha256=evaluation_lock["weights"][name],
                    evaluation_lock_sha256=inputs.digest(root / "evaluation_lock.json"),
                    threshold_sha256=inputs.digest(root / "evaluation_threshold.json"),
                    real_manifest_sha256=inputs.digest(root / "real_manifest.json")), "Evaluation provenance changed")
        rows = inputs.read(path)
        identity = [(r["source_row"], r["group"], r["truth"]) for r in rows]
        require(len({r["source_row"] for r in rows}) == len(rows), "Duplicate source row in evaluation")
        require(common is None or common == identity, "Unpaired truth/group/order")
        if common is None:
            verify_truth(inputs, rows, real_manifest)
        common = identity
        for row in rows:
            require(row["stats"] == native_stats(row), "Native TP flags differ from stored boxes")
            require(row["collapsed_stats"] == native_stats(row, True), "Collapsed TP flags differ")
        ap, collapsed = summarize_ap(rows), summarize_ap(rows, "collapsed_stats")
        require(abs(ap["macro_ap50_95"]-summary[name]["ap"]["map50_95"]) < 1e-12, "AP reproduction failed")
        for expected in summary[name]["ap"]["per_class"]:
            actual = ap["per_class"][str(expected["class_id"])]
            require(abs(actual["ap50_95"]-expected["map50_95"]) < 1e-12 and
                    abs(actual["ap50"]-expected["map50"]) < 1e-12, "Per-class AP reproduction failed")
        require(abs(statistics.mean(v["ap75"] for v in ap["per_class"].values())
                    - summary[name]["ap"]["map75"]) < 1e-12, "AP75 reproduction failed")
        require(abs(collapsed["macro_ap50_95"]-summary[name]["collapsed_ap"]["map50_95"]) < 1e-12, "Collapsed AP reproduction failed")
        fixed = operational_summary(rows, threshold["value"])
        require(all(fixed[k] == summary[name]["fixed"]["class_aware"][k] for k in ("tp", "fp", "fn")), "Fixed matches differ")
        native_tp50 = sum(sum(r["stats"]["tp"][j][0] for j, p in enumerate(r["predictions"])
                             if p["confidence"] >= threshold["value"]) for r in rows)
        metrics[name] = dict(ap=ap, collapsed_ap=collapsed, fixed=fixed,
                             cached_native_tp50_above_operational_threshold=native_tp50,
                             prediction_count_min_max=[min(len(r["predictions"]) for r in rows), max(len(r["predictions"]) for r in rows)],
                             images_at_max_det300=sum(len(r["predictions"]) >= 300 for r in rows))
        predictions[name] = rows
        recomputation.append(dict(run=name, images=len(rows), native_and_collapsed_flags_exact=True, AP_and_fixed_counts_exact=True))
        print("Reproduced", name, flush=True)
    exposure = exposure_audit(inputs, manifest, plan, root)
    print("Reconstructed full and selected-checkpoint exposure", flush=True)
    cap_check = cap_sensitivity(predictions, seeds, threshold["value"])
    write_new(output / "candidate_cap_sensitivity.json", dict(schema=VERSION,
              parameter_preset=PRESET, paired_seeds=seeds, metric_order=METRIC_ORDER, **cap_check))
    print("Recomputed matching at candidate caps100/200; original cap300 preserved", flush=True)
    first = next(iter(predictions.values()))
    groups = sorted({r["group"] for r in first})
    support = {g: dict(images=sum(r["group"] == g for r in first),
                       classes=dict(Counter(t["class_id"] for r in first if r["group"] == g for t in r["truth"]))) for g in groups}
    loo = [dict(excluded_group=g, **paired_delta(predictions, seeds, lambda rows, g=g: [r for r in rows if r["group"] != g])) for g in groups]
    group_results = {g: paired_delta(predictions, seeds, lambda rows, g=g: [r for r in rows if r["group"] == g]) for g in groups}
    design = inputs.read(root / "evaluation/bootstrap_design.json")
    samples = []
    for draw in design["draws"]:
        samples.append(paired_delta(predictions, seeds, lambda rows, draw=draw:
                                   [r for g in draw for r in rows if r["group"] == g])["mean"])
    intervals = np.percentile(np.asarray(samples), [2.5, 97.5], axis=0).T.tolist()
    historical = inputs.read(root / "evaluation/comparison.json")
    diagnosis = inputs.read(root / "diagnostics/sobremadura_20261031/diagnosis.json")
    require(np.allclose(intervals[0], historical["paired_group_bootstrap"]["percentile_95"], atol=1e-12, rtol=0), "Original macro interval differs")
    require(np.allclose(intervals[3], diagnosis["bootstrap_same_original_draws"]["percentile_95"], atol=1e-12, rtol=0), "Original class interval differs")
    write_new(output / "resampling.json", dict(schema=VERSION, parameter_preset=PRESET,
               paired_seeds=seeds, metric_order=METRIC_ORDER,
               original_draws=design, mean_paired_deltas=samples, percentile95=intervals,
               leave_one_group_out=loo, groups_separately=group_results, group_support=support,
               interpretation="Post hoc sensitivity with fixed trained seeds and few unverified groups; not training ablations or external confirmation."))
    pause = root.parent / "spatial_dataset_completion_20261030/pause_requested.json"
    require(inputs.read(pause)["active"] is True, "Generation pause flag is not active")
    inputs.verify()
    result = dict(schema=VERSION, parameter_preset=PRESET, completed_utc=datetime.now(timezone.utc).isoformat(),
                  no_new_training_inference_or_rendering=True, immutable_inputs_verified=True,
                  source_lock_entries=len(lock["files"]), packages=versions, paired_seeds=seeds,
                  python=platform.python_version(),
                  composition=composition(manifest), recomputation=recomputation, metrics=metrics,
                  exposure=exposure, overall_delta=paired_delta(predictions, seeds, lambda rows: rows),
                  resampling_artifact="resampling.json", generation_pause_flag_active=True,
                  audit_seconds=time.monotonic()-started)
    write_new(output / "audit.json", result)
    inputs.digest(__file__)
    write_new(output / "provenance.json", dict(schema=VERSION, source_root=str(root), inputs=inputs.hashes,
                                              script_version=VERSION, parameter_preset=PRESET, seeds=seeds,
                                              outputs={p.name: sha(p) for p in output.glob("*.json")}))
    print("Saved", output, "in", round(time.monotonic()-started, 2), "seconds", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.root, args.out)
