"""Audit generated v2 datasets, frozen splits, labels, hashes and provenance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_classical_augmentation.v2.validation import audit_scenario_dataset, write_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, action="append", required=True)
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT / "Dataset Original")
    parser.add_argument("--profile", type=Path, default=REPO_ROOT / "outputs/classical_augmentation_v2/domain_profile/real_train_profile.json")
    parser.add_argument("--derived-count", type=int, help="Override expected count; otherwise read build_summary.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reports = []
    for dataset_dir in args.dataset_dir:
        expected = args.derived_count
        if expected is None:
            summary = json.loads((dataset_dir / "build_summary.json").read_text(encoding="utf-8"))
            expected = int(summary["derived_count"])
        report = audit_scenario_dataset(dataset_dir, args.source_root, args.profile, expected_derived_count=expected)
        write_audit(dataset_dir / "audit_report.json", report)
        reports.append(report)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    if any(report["status"] != "valid" for report in reports):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
