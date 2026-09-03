"""Export a byte-preserving review snapshot; never train or evaluate a model.

Only structured campaign evidence and explicitly requested preview sheets are
copied. Original datasets, weights and unrelated workstreams stay local.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/classical_augmentation_v2"
TEXT_SUFFIXES = {".json", ".jsonl", ".csv", ".yaml", ".yml", ".md"}
SECRET = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{30,}"
    r"|\bAKIA[A-Z0-9]{16}"
    r"|https?://[^\s/:]+:[^\s/@]+@"
)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def category(path: Path) -> str:
    name = path.name.lower()
    if name.startswith(("preview", "contact_sheet")):
        return "preview"
    if "prediction_cache" in path.parts:
        return "predictions"
    if "manifests" in path.parts:
        return "manifest"
    if path.suffix in {".yaml", ".yml"}:
        return "yaml"
    if name == "results.csv":
        return "results"
    if "environment" in name:
        return "environment"
    if name.startswith("execution_state"):
        return "execution_state"
    if "lock" in name:
        return "selection_lock"
    return "metadata_or_report"


def selected_files() -> list[Path]:
    files = []
    for path in SOURCE.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(SOURCE)
        if any(part in {"images", "labels", "weights", "__pycache__"} for part in relative.parts):
            continue
        preview = path.name.startswith(("preview", "contact_sheet")) and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        if path.suffix.lower() not in TEXT_SUFFIXES and not preview:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError(f"Source escapes campaign directory: {path}")
        files.append(path)
    files.extend((ROOT / "configs/classical_augmentation_v2").glob("*.json"))
    files.extend((ROOT / "docs/reports").glob("aumento_clasico_v2*.md"))
    files.append(ROOT / "docs/workstreams/classical_augmentation.md")
    return sorted(set(files))


def check_text(path: Path) -> None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return
    value = path.read_text(encoding="utf-8-sig")
    if SECRET.search(value):
        raise ValueError(f"Potential credential detected; manual review required: {path}")
    if path.suffix == ".json":
        json.loads(value)
    elif path.suffix == ".jsonl":
        for line in value.splitlines():
            if line.strip():
                json.loads(line)


def build(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite snapshot: {output}")
    if not output.is_relative_to(ROOT / "artifacts/classical_augmentation_v2_review"):
        raise ValueError("Snapshot must stay inside artifacts/classical_augmentation_v2_review")
    sources = selected_files()
    # Validate everything before creating the snapshot. Do not expose matches.
    for source in sources:
        if source.stat().st_size >= 50 * 1024**2:
            raise ValueError(f"File exceeds review-size budget: {source}")
        check_text(source)
    output.mkdir(parents=True)
    entries = []
    for source in sources:
        relative = source.relative_to(ROOT)
        target = output / "snapshot" / relative
        original_hash = sha256(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256(target) != original_hash or sha256(source) != original_hash:
            raise RuntimeError(f"Source changed during export: {source}")
        entries.append({
            "path": target.relative_to(output).as_posix(),
            "source": relative.as_posix(), "kind": "byte_identical_copy",
            "category": category(source), "sha256": original_hash,
            "bytes": target.stat().st_size,
            "source_mtime_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
        })

    membership = {}
    for phase in ("screening", "confirmatory"):
        source = f"snapshot/outputs/classical_augmentation_v2/metrics/{phase}/{phase}_summary.json"
        summary = json.loads((output / source).read_text(encoding="utf-8"))
        if summary["test_consulted"] is not False:
            raise ValueError("Unexpected test access in selection evidence")
        for run in summary["runs"]:
            membership[Path(run["run_dir"]).relative_to(ROOT).as_posix()] = phase
        for label, key in (("thresholds", "confidence_sweep"), ("difficulty", "difficulty")):
            payload = {
                "kind": "extracted_without_recalculation", "source": source,
                "source_sha256": sha256(output / source), "selection_split": "val",
                "test_consulted": False,
                "runs": [{"scenario": run["scenario"], "seed": run["seed"],
                          "run_dir": run["run_dir"], key: run["operational"][key]}
                         for run in summary["runs"]],
            }
            write_json(output / "extracted" / f"{label}_{phase}.json", payload)

    catalog = []
    for source in sources:
        if source.name != "results.csv":
            continue
        with source.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        epochs = [float(row["epoch"]) for row in rows]
        run_path = source.parent.relative_to(ROOT).as_posix()
        catalog.append({
            "source": source.relative_to(ROOT).as_posix(),
            "rows": len(rows), "unique_epoch_prefix": epochs == list(range(1, len(rows) + 1)),
            "included_in_summary": membership.get(run_path),
            "interpretation": "included" if run_path in membership else "diagnostic_or_excluded_attempt",
            "best_pt_present_at_export_not_distributed": (source.parent / "weights/best.pt").is_file(),
        })
    write_json(output / "extracted/run_catalog.json", catalog)
    lock_source = "snapshot/outputs/classical_augmentation_v2/selection.lock.json"
    lock = json.loads((output / lock_source).read_text(encoding="utf-8"))
    write_json(output / "extracted/selected_scenarios.json", {
        "kind": "extracted_without_recalculation", "source": lock_source,
        "source_sha256": sha256(output / lock_source),
        "selected_scenarios": lock["selected_scenarios"], "decision": lock["decision"],
        "test_consulted": lock["test_consulted"],
    })
    for path in sorted((output / "extracted").glob("*.json")):
        entries.append({"path": path.relative_to(output).as_posix(),
                        "kind": "extracted_without_recalculation",
                        "sha256": sha256(path), "bytes": path.stat().st_size})
    write_json(output / "inventory.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "historical_environment": "snapshot/outputs/classical_augmentation_v2/runs/*/execution_environment*.json*",
        "historical_pip_freeze": "not_found; do not substitute current packages for the training environment",
        "source_base": "C:/dev/SyntheticPlantGeneration",
        "files": entries,
    })
    verify(output)


def verify(output: Path) -> None:
    inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    for entry in inventory["files"]:
        path = (output / entry["path"]).resolve()
        if not path.is_relative_to(output) or not path.is_file():
            raise ValueError(f"Invalid inventory path: {entry['path']}")
        if path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {entry['path']}")
    print(json.dumps({"verified_files": len(inventory["files"]),
                      "bytes": sum(e["bytes"] for e in inventory["files"]),
                      "output": str(output)}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify:
        verify(output)
    else:
        build(output)


if __name__ == "__main__":
    main()
