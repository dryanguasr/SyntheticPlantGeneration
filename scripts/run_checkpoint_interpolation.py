"""Select a natural/hybrid checkpoint interpolation using natural validation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from uchuva_lsystem.hybrid_training import TrainingConfig, run_checkpoint_interpolation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--natural-checkpoint", type=Path, required=True)
    parser.add_argument("--hybrid-checkpoint", type=Path, required=True)
    parser.add_argument("--natural-data", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--baseline-map50-95", type=float, required=True)
    parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=(0.15, 0.30, 0.45, 0.60, 0.75, 0.90),
        help="Hybrid weight fractions; all selection uses natural validation only.",
    )
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260731)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_checkpoint_interpolation(
        natural_checkpoint=args.natural_checkpoint,
        hybrid_checkpoint=args.hybrid_checkpoint,
        natural_data_yaml=args.natural_data,
        output_root=args.output_root,
        baseline_map50_95=args.baseline_map50_95,
        alphas=tuple(args.alphas),
        config=TrainingConfig(
            batch=args.batch,
            workers=args.workers,
            seed=args.seed,
        ),
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
