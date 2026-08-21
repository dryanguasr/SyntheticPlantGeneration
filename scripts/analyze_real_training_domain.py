"""Profile the immutable real dataset using train-only image statistics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.profiles import analyze_real_training_domain, write_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/domain_profile")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = analyze_real_training_domain(args.dataset_root)
    output_path = args.output_dir.resolve() / "real_train_profile.json"
    write_profile(output_path, profile)
    summary = {
        "profile": str(output_path),
        "profile_sha256": profile["profile_sha256"],
        "splits": {name: {key: value for key, value in split.items() if key != "members"} for name, split in profile["splits"].items()},
        "bbox_area_bands": profile["geometry"]["bbox_area_bands"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
