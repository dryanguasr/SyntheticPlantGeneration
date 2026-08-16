"""Create a label-preserving photometrically calibrated synthetic dataset."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from uchuva_lsystem.photometric_calibration import derive_photometrically_calibrated_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--synthetic-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = derive_photometrically_calibrated_dataset(
        real_root=args.real_root,
        synthetic_root=args.synthetic_root,
        output_root=args.output_root,
        real_splits=("train", "val"),
    )
    print(json.dumps({key: report[key] for key in ("version", "output_root", "transform", "image_count")}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
