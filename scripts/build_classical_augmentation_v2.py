"""Build one or all Classical Augmentation v2 datasets (smoke by default)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.builder import build_scenario_dataset
from uchuva_classical_augmentation.v2.config import default_campaign_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/domain_profile/real_train_profile.json")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/datasets/smoke")
    parser.add_argument("--scenario", action="append", help="Scenario code; repeat or omit for all")
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--derived-count", type=int, default=25, help="Smoke count; use 532 only after smoke audit passes")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = default_campaign_config()
    selected = set(args.scenario or [scenario.code for scenario in config.scenarios])
    unknown = selected - {scenario.code for scenario in config.scenarios}
    if unknown:
        raise SystemExit(f"Unknown scenarios: {sorted(unknown)}")
    summaries = []
    for scenario in config.scenarios:
        if scenario.code not in selected:
            continue
        count = 0 if scenario.code == "V2-E0" else args.derived_count
        summaries.append(
            build_scenario_dataset(
                args.dataset_root,
                args.output_root,
                args.profile,
                scenario,
                seed=args.seed,
                derived_count=count,
                overwrite=args.overwrite,
            )
        )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
