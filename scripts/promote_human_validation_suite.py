"""Promote a completed human-validation suite without overwriting its manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.human_validation import (
    HumanValidationSuite,
    evaluate_human_review,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote an accepted human-validation suite to baseline."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--review-csv", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = _repo_path(args.manifest)
    _verify_manifest_sidecar(manifest_path)
    review_path = (
        _repo_path(args.review_csv)
        if args.review_csv is not None
        else manifest_path.parent / "human_review.csv"
    )
    output_path = (
        _repo_path(args.output)
        if args.output is not None
        else manifest_path.parent / "accepted_baseline_manifest.json"
    )
    if output_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite accepted baseline: {output_path}"
        )
    suite = HumanValidationSuite.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if suite.status != "complete_pending_human_review":
        raise ValueError(
            "Only a complete_pending_human_review suite can be promoted."
        )
    with review_path.open("r", encoding="utf-8-sig", newline="") as file:
        review_rows = list(csv.DictReader(file))
    required_problem_cases = (
        {
            problem_id: [
                case.case_id
                for case in suite.cases
                if problem_id in case.problem_ids
            ]
            for problem_id in suite.active_problem_ids
        }
        if not suite.bootstrap
        else None
    )
    evaluation = evaluate_human_review(
        review_rows,
        required_problem_cases=required_problem_cases,
    )
    if evaluation["status"] != "accepted":
        raise ValueError(
            "Human review does not meet acceptance rules: "
            f"{evaluation}"
        )
    suite.status = "accepted_baseline"
    suite.human_review = {
        **suite.human_review,
        **evaluation,
        "review_csv": str(review_path.resolve()),
        "accepted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_manifest": str(manifest_path.resolve()),
    }
    export_json(suite, output_path)
    print(f"Accepted baseline written without overwriting source: {output_path}")


def _repo_path(path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (REPO_ROOT / path).resolve()


def _verify_manifest_sidecar(manifest_path: Path) -> None:
    sidecar = manifest_path.with_suffix(manifest_path.suffix + ".sha256")
    if not sidecar.is_file():
        raise FileNotFoundError(
            f"Manifest SHA-256 sidecar is missing: {sidecar}"
        )
    expected = sidecar.read_text(encoding="ascii").split()[0].lower()
    digest = hashlib.sha256()
    with manifest_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(
            "Manifest SHA-256 mismatch; regenerate or restore the suite "
            "before promotion."
        )


if __name__ == "__main__":
    main()
