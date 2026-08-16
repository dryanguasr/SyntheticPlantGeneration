"""Compare the immutable original dataset with a synthetic YOLO dataset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.domain_analysis import (
    analyze_yolo_domain,
    compare_domain_reports,
    write_domain_comparison,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare real and synthetic YOLO domains.")
    parser.add_argument("--real-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument(
        "--synthetic-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "datasets" / "uchuva_yolo_pilot_seed_0",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs" / "domain_analysis" / "real_vs_synthetic",
    )
    parser.add_argument("--skip-luminance", action="store_true")
    parser.add_argument(
        "--real-splits",
        nargs="+",
        choices=("train", "val", "test"),
        default=("train", "val"),
        help="Real splits used for calibration; test is excluded by default.",
    )
    parser.add_argument(
        "--synthetic-splits",
        nargs="+",
        choices=("train", "val", "test"),
        default=("train", "val", "test"),
        help="Synthetic splits to compare; use train for training-domain calibration.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    real = analyze_yolo_domain(
        "original_real",
        args.real_root / "IMAGENES",
        args.real_root / "LABELS",
        sample_luminance=not args.skip_luminance,
        splits=args.real_splits,
    )
    synthetic = analyze_yolo_domain(
        "synthetic_candidate",
        args.synthetic_root / "images",
        args.synthetic_root / "labels",
        sample_luminance=not args.skip_luminance,
        splits=args.synthetic_splits,
    )
    json_path, markdown_path = write_domain_comparison(
        compare_domain_reports(real, synthetic), args.output_dir
    )
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")


if __name__ == "__main__":
    main()
