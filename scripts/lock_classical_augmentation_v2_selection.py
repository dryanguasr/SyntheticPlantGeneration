"""Freeze the validation-selected v2 candidates before final-test access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.selection import create_selection_lock


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmatory-summary", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument(
        "--campaign-config",
        type=Path,
        default=REPO_ROOT / "configs/classical_augmentation_v2/campaign_v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "outputs/classical_augmentation_v2/selection.lock.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    lock = create_selection_lock(
        confirmatory_summary_path=args.confirmatory_summary,
        project=args.project,
        campaign_config_path=args.campaign_config,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "selection_lock": str(args.output.resolve()),
                "lock_content_sha256": lock["lock_content_sha256"],
                "selected_scenarios": lock["selected_scenarios"],
                "test_consulted": lock["test_consulted"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
