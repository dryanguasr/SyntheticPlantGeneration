"""Run smoke training or the frozen 3-seed/30-epoch v2 screening matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.config import default_campaign_config
from uchuva_classical_augmentation.v2.training import TrainingConfig, run_training_matrix


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=REPO_ROOT / "tmp/classical_campaign/yolo11n.pt")
    parser.add_argument("--phase", choices=("smoke", "screening"), default="screening")
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = [item.code for item in default_campaign_config().scenarios]
    datasets = _find_datasets(args.dataset_root, scenarios)
    smoke = args.phase == "smoke"
    config = TrainingConfig(epochs=8 if smoke else 30, device=args.device)
    results = run_training_matrix(datasets, args.project, args.model, seeds=[1] if smoke else [1, 2, 3], config=config, phase=args.phase)
    output = args.project / "training_matrix_summary.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(output.resolve())


def _find_datasets(root: Path, scenarios: list[str]) -> dict[str, Path]:
    result = {}
    for scenario in scenarios:
        matches = sorted(path for path in root.glob(f"{scenario}_seed_*_n*") if path.is_dir())
        if len(matches) != 1:
            raise RuntimeError(f"Expected exactly one dataset for {scenario} under {root}, found {len(matches)}")
        result[scenario] = matches[0]
    return result


if __name__ == "__main__":
    main()
