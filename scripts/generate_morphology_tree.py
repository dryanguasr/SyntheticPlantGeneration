"""Generate one morphology tree JSON without requiring Blender."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.exporters import export_json, export_morphology_tree
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.validation import validate_morphology_tree


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a JSON-serializable uchuva morphology tree."
    )
    parser.add_argument("--seed", type=int, default=0, help="Reproducible seed.")
    parser.add_argument(
        "--condition",
        choices=("healthy", "drying"),
        default="healthy",
        help="Whole-plant stem/health condition.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for morphology JSON.",
    )
    parser.add_argument(
        "--validation-output",
        type=Path,
        default=None,
        help="Output path for validation report JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plant = generate_morphology_tree(seed=args.seed, condition=args.condition)
    output_path = args.output or (
        REPO_ROOT / "outputs" / "specs" / f"morphology_tree_seed_{args.seed}.json"
    )
    validation_path = args.validation_output or (
        REPO_ROOT / "outputs" / "specs" / f"validation_report_seed_{args.seed}.json"
    )

    export_morphology_tree(plant, output_path)
    export_json(validate_morphology_tree(plant), validation_path)

    print(f"Wrote morphology tree: {output_path}")
    print(f"Wrote validation report: {validation_path}")


if __name__ == "__main__":
    main()
