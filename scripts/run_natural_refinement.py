"""Refine a mixed-domain checkpoint on natural images and evaluate natural test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from uchuva_lsystem.hybrid_training import TrainingConfig, run_natural_refinement_from_hybrid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--starting-checkpoint", type=Path, required=True)
    parser.add_argument("--natural-data", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--baseline-map50-95", type=float, required=True)
    parser.add_argument("--mixed-epochs", type=int, required=True)
    parser.add_argument("--natural-epochs", type=int, default=10)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260731)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_natural_refinement_from_hybrid(
        starting_checkpoint=args.starting_checkpoint,
        natural_data_yaml=args.natural_data,
        output_root=args.output_root,
        baseline_map50_95=args.baseline_map50_95,
        mixed_epochs_before_refinement=args.mixed_epochs,
        learning_rate=args.learning_rate,
        config=TrainingConfig(
            epochs=args.natural_epochs,
            batch=args.batch,
            workers=args.workers,
            seed=args.seed,
        ),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
