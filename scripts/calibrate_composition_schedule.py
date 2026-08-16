"""Calibrate v2 camera scheduling from v1 yields and real-train statistics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.composition_calibration import (
    calibrate_camera_mixture,
    write_composition_calibration,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--reference-profile", type=Path, required=True)
    parser.add_argument("--reference-split", choices=("train", "overall"), default="train")
    parser.add_argument("--manifest-split", choices=("train", "val", "test", "all"), default="train")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = calibrate_camera_mixture(
        args.manifest,
        args.reference_profile,
        reference_split=args.reference_split,
        manifest_split="" if args.manifest_split == "all" else args.manifest_split,
    )
    path = write_composition_calibration(report, args.output)
    print(path)
    print(report["recommended_camera_profile_rates_pct"])
    print(report["predicted_mean_absolute_gap_pct_points"])


if __name__ == "__main__":
    main()
