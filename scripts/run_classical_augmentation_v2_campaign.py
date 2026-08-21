"""Run a frozen confirmatory v2 matrix for selected scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.training import TrainingConfig, run_training_matrix
from run_classical_augmentation_v2_screening import _find_datasets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", required=True)
    parser.add_argument("--seeds", default="1-5")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--model", type=Path, default=REPO_ROOT / "tmp/classical_campaign/yolo11n.pt")
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    seeds = _parse_seeds(args.seeds)
    datasets = _find_datasets(args.dataset_root, args.scenarios)
    results = run_training_matrix(datasets, args.project, args.model, seeds=seeds, config=TrainingConfig(epochs=args.epochs, device=args.device), phase="confirmatory")
    output = args.project / "training_matrix_summary.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(output.resolve())


def _parse_seeds(value: str) -> list[int]:
    result = []
    for part in value.split(","):
        if "-" in part:
            first, last = (int(item) for item in part.split("-", 1))
            result.extend(range(first, last + 1))
        else:
            result.append(int(part))
    if not result or min(result) < 0 or len(result) != len(set(result)):
        raise ValueError("Seeds must be unique non-negative integers")
    return result


if __name__ == "__main__":
    main()
