"""Prepare deterministic real/synthetic YOLO experiment datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.hybrid_experiments import (
    HybridExperimentSpec,
    build_hybrid_experiment_matrix,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare leakage-safe real/synthetic YOLO training matrices."
    )
    parser.add_argument("--real-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--synthetic-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260731)
    parser.add_argument("--fixed-budget", type=int, default=None)
    parser.add_argument(
        "--preset",
        choices=("default", "additive_only", "capped"),
        default="default",
        help="Use additive_only for all synthetic train images or capped for a deterministic subset.",
    )
    parser.add_argument(
        "--synthetic-count",
        type=int,
        default=40,
        help="Synthetic training count used by the capped preset.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.preset == "additive_only":
        experiment_specs = (
            HybridExperimentSpec("natural_full", "natural_full", 1.0),
            HybridExperimentSpec("hybrid_additive_all", "additive", 1.0),
        )
    elif args.preset == "capped":
        experiment_specs = (
            HybridExperimentSpec("natural_full", "natural_full", 1.0),
            HybridExperimentSpec(
                f"hybrid_additive_{args.synthetic_count}",
                "additive_capped",
                1.0,
                args.synthetic_count,
                "spatial_calibration_dose",
            ),
        )
    else:
        experiment_specs = None
    kwargs = {"experiment_specs": experiment_specs} if experiment_specs is not None else {}
    report = build_hybrid_experiment_matrix(
        real_root=_repo_path(args.real_root),
        synthetic_root=_repo_path(args.synthetic_root),
        output_root=_repo_path(args.output_root),
        seed=args.seed,
        fixed_budget=args.fixed_budget,
        **kwargs,
    )
    print(f"Matrix: {_repo_path(args.output_root) / 'matrix.json'}")
    for experiment in report["experiments"]:
        counts = experiment["counts"]
        print(
            f"{experiment['spec']['name']}: "
            f"real={counts['train_real']} synthetic={counts['train_synthetic']}"
        )


def _repo_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


if __name__ == "__main__":
    main()
