"""Run the single final test phase authorized by a v2 selection lock."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.final_test import evaluate_locked_final_test


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection-lock",
        type=Path,
        default=REPO_ROOT / "outputs/classical_augmentation_v2/selection.lock.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "outputs/classical_augmentation_v2/metrics/final_test",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPO_ROOT
        / "outputs/classical_augmentation_v2/domain_profile/real_train_profile.json",
    )
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = evaluate_locked_final_test(
        lock_path=args.selection_lock,
        output_dir=args.output_dir,
        profile_path=args.profile,
        device=args.device,
    )
    print(
        json.dumps(
            {
                "status": summary["status"],
                "test_consulted": summary["test_consulted"],
                "summary": str((args.output_dir / "final_test_summary.json").resolve()),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
