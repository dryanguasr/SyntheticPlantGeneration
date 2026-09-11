"""Read local historical evidence without inference, training or source writes."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STUDY = "outputs/experiments/hybrid_fidelity_v2_leakage_repaired_20260811"
PILOT = "outputs/datasets/uchuva_virtual_fidelity_v2_pilot_seed_16000"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit(root: Path) -> dict:
    evidence = {}
    paths = [
        f"{STUDY}/final_test/final_test_summary.json",
        f"{STUDY}/phase_a_decision.json",
        f"{STUDY}/selection.lock.json",
        f"{STUDY}/repaired_source_audit.json",
        "outputs/experiments/checkpoint_interpolation_scale80_seed_1000_v1/checkpoint_interpolation_result.json",
        "outputs/audits/virtual_fidelity_v2_pilot_seed_16000/pilot_audit.json",
        "outputs/classical_augmentation_v2/metrics/confirmatory/confirmatory_summary.json",
    ]
    payloads = {}
    for name in paths:
        path = root / name
        evidence[name] = {"exists": path.is_file()}
        if path.is_file():
            payloads[name] = json.loads(path.read_text(encoding="utf-8-sig"))
            evidence[name].update(sha256=digest(path), bytes=path.stat().st_size)
    final = payloads.get(paths[0], {})
    rows = final.get("results", [])
    checkpoints = []
    for row in rows:
        path = Path(row["checkpoint"])
        if not path.is_absolute():
            path = root / path
        checkpoints.append({"seed": row["seed"], "role": row["role"],
                            "exists": path.is_file(),
                            "hash_matches": path.is_file() and digest(path) == row["checkpoint_sha256"]})
    by_seed = {}
    for row in rows:
        by_seed.setdefault(row["seed"], {})[row["role"]] = row["test_metrics"]
    deltas = [{"seed": seed, **{key: pair["selected"][key] - pair["baseline"][key]
                               for key in ("map50_95", "map75", "recall")}}
              for seed, pair in sorted(by_seed.items()) if set(pair) == {"baseline", "selected"}]
    manifest = root / PILOT / "manifest.jsonl"
    records = [json.loads(line) for line in manifest.read_text().splitlines()] if manifest.is_file() else []
    failures = []
    verified = 0
    for row in records:
        for field, key in (("image_path", "image_sha256"), ("label_path", "label_sha256"),
                           ("preview_path", "preview_sha256")):
            path = root / PILOT / row[field]
            if not path.is_file() or digest(path) != row["checksums"][key]:
                failures.append(row[field])
            else:
                verified += 1
    classes = Counter(d["class_name"] for r in records for d in r["detections"])
    states = Counter(d.get("calyx_state", "") for r in records for d in r["detections"])
    source_counts = {}
    # Read original label text only. No real test images or detector evaluation.
    for split in ("train", "val", "test"):
        folder = root / "Dataset Original" / "LABELS" / split
        labels = list(folder.glob("*.txt"))
        counts = Counter()
        for path in labels:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if line.strip():
                    counts[line.split()[0]] += 1
        images = [p for p in (root / "Dataset Original" / "IMAGENES" / split).glob("*")
                  if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        source_counts[split] = {
            "image_files": len(images), "label_files": len(labels), "class_id_counts": dict(counts),
            "images_without_label": sorted({p.stem for p in images} - {p.stem for p in labels}),
            "labels_without_image": sorted({p.stem for p in labels} - {p.stem for p in images}),
        }
    rejected_path = root / PILOT / "rejected_scenes.jsonl"
    return {"audit_version": "1.0", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "evidence_status": "recomputed_from_existing_artifacts_not_retrained",
            "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "historical_files": evidence, "checkpoints": checkpoints,
            "paired_deltas_recomputed": deltas,
            "mean_map_delta": statistics.mean(d["map50_95"] for d in deltas) if deltas else None,
            "pilot": {"images": len(records), "verified_files": verified, "hash_failures": failures,
                      "classes": dict(classes), "calyx_states": dict(states),
                      "plant_counts": dict(Counter(r["plant_count"] for r in records)),
                      "camera_profiles": dict(Counter(r["camera_profile"] for r in records)),
                      "lighting_by_state": {
                          state: dict(Counter(r["lighting_profile"] for r in records
                                              for d in r["detections"] if d.get("calyx_state") == state))
                          for state in sorted(states)
                      },
                      "states_by_split": {
                          split: dict(Counter(d.get("calyx_state", "") for r in records
                                              for d in r["detections"] if r["split"] == split))
                          for split in ("train", "val", "test")
                      },
                      "splits": dict(Counter(r["split"] for r in records)),
                      "rejected_candidates": len(rejected_path.read_text().splitlines()) if rejected_path.is_file() else None},
            "original_labels": source_counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "outputs").resolve()):
        parser.error("Write audit artifacts under outputs/; original data are read-only.")
    report = audit(ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
