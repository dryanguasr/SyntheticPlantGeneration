from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from uchuva_lsystem.hybrid_study import (
    BASELINE_NAME,
    PHASE_A_NAMES,
    PHASE_A_SYNTHETIC_COUNTS,
    PHASE_B_REAL_COUNTS,
    available_ram_gb,
    create_selection_lock,
    decide_phase_a,
    decide_phase_b_cohort,
    materialize_repaired_real_partition,
    phase_a_specs,
    phase_b_specs,
    run_validation_experiment,
    should_stop_phase_b,
    validate_perceptual_review,
)
from uchuva_lsystem.hybrid_training import TrainingConfig


class HybridStudyTests(unittest.TestCase):
    def test_phase_specs_encode_expected_nested_counts(self) -> None:
        phase_a = phase_a_specs()
        self.assertEqual(phase_a[0].name, BASELINE_NAME)
        self.assertEqual(
            [item.synthetic_count for item in phase_a[1:]],
            list(PHASE_A_SYNTHETIC_COUNTS),
        )
        phase_b = phase_b_specs()
        self.assertEqual([item.real_count for item in phase_b], list(PHASE_B_REAL_COUNTS))
        self.assertTrue(all(item.synthetic_count == 512 for item in phase_b))

    def test_phase_a_selects_lower_dose_within_tie_tolerance(self) -> None:
        experiments = {}
        for count in PHASE_A_SYNTHETIC_COUNTS:
            name = PHASE_A_NAMES[count]
            score = 0.706 if count == 118 else 0.707 if count == 265 else 0.690
            delta = score - 0.700
            experiments[name] = _aggregate_item(
                name=name,
                map_mean=score,
                map_delta=delta,
                recall_delta=0.0,
                positive_count=3 if delta > 0 else 0,
                within_count=3,
                train_real=1061,
                train_synthetic=count,
            )
        decision = decide_phase_a({"experiments": experiments})
        self.assertTrue(decision["success"])
        self.assertEqual(decision["selected"]["synthetic_count"], 118)

    def test_phase_b_success_precedes_boundary_worsening(self) -> None:
        item = _aggregate_item(
            name="phase_b",
            map_mean=0.68,
            map_delta=-0.005,
            recall_delta=-0.005,
            positive_count=0,
            within_count=2,
            train_real=128,
            train_synthetic=512,
        )
        decision = decide_phase_b_cohort(item)
        self.assertTrue(decision["success"])
        self.assertFalse(decision["worsening"])

    def test_phase_b_marks_clear_underperformance(self) -> None:
        item = _aggregate_item(
            name="phase_b",
            map_mean=0.65,
            map_delta=-0.02,
            recall_delta=-0.03,
            positive_count=0,
            within_count=0,
            train_real=64,
            train_synthetic=512,
        )
        decision = decide_phase_b_cohort(item)
        self.assertFalse(decision["success"])
        self.assertTrue(decision["worsening"])

    def test_phase_b_stops_after_two_nonconsecutive_worsenings(self) -> None:
        decisions = [
            {"worsening": True},
            {"worsening": False},
            {"worsening": True},
        ]
        self.assertTrue(should_stop_phase_b(decisions))
        self.assertFalse(should_stop_phase_b(decisions[:2]))

    def test_selection_lock_contains_only_baseline_and_selected_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = []
            selected = []
            for seed in (1, 2, 3):
                checkpoint = root / f"checkpoint_{seed}.pt"
                checkpoint.write_bytes(f"checkpoint-{seed}".encode())
                common = {
                    "config": {"seed": seed},
                    "best_checkpoint": str(checkpoint),
                    "best_checkpoint_sha256": _sha256(checkpoint),
                    "data_yaml": str(root / "data.yaml"),
                    "validation_metrics": {"map50_95": 0.7},
                }
                baseline.append({**common, "experiment": BASELINE_NAME})
                selected.append({**common, "experiment": "winner"})
            lock = create_selection_lock(
                study_root=root,
                phase="phase_a",
                selected_results=selected,
                baseline_results=baseline,
                decision={"success": True},
            )
            self.assertEqual(lock["status"], "locked")
            self.assertEqual({item["seed"] for item in lock["baseline"]}, {1, 2, 3})
            self.assertEqual({item["seed"] for item in lock["selected"]}, {1, 2, 3})
            stored = json.loads((root / "selection.lock.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["test_policy"], "baseline_and_locked_winner_only")

    def test_available_ram_is_positive(self) -> None:
        self.assertGreater(available_ram_gb(), 0.0)

    def test_perceptual_review_must_cover_every_candidate(self) -> None:
        audit = {"perceptual_candidates": [_candidate("train", "a", "val", "b")]}
        with self.assertRaises(ValueError):
            validate_perceptual_review(
                audit,
                {
                    "reviewer": "tester",
                    "reviewed_at_utc": "2026-08-11T00:00:00Z",
                    "candidate_reviews": [],
                },
            )

    def test_repaired_partition_colocates_confirmed_near_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            for split, sample_ids in {
                "train": ("a", "t"),
                "val": ("b", "v"),
                "test": ("e",),
            }.items():
                for sample_id in sample_ids:
                    image = source / "IMAGENES" / split / f"{sample_id}.jpg"
                    label = source / "LABELS" / split / f"{sample_id}.txt"
                    image.parent.mkdir(parents=True, exist_ok=True)
                    label.parent.mkdir(parents=True, exist_ok=True)
                    image.write_bytes(f"image-{split}-{sample_id}".encode())
                    label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            candidate = _candidate("train", "a", "val", "b")
            review = {
                "reviewer": "tester",
                "reviewed_at_utc": "2026-08-11T00:00:00Z",
                "candidate_reviews": [
                    {**candidate, "verdict": "confirmed_near_duplicate"}
                ],
                "split_overrides": [
                    {
                        "source_split": "train",
                        "sample_id": "a",
                        "destination_split": "val",
                    },
                    {
                        "source_split": "val",
                        "sample_id": "v",
                        "destination_split": "train",
                    },
                ],
                "expected_partition_counts": {"train": 2, "val": 2, "test": 1},
            }
            manifest = materialize_repaired_real_partition(
                real_root=source,
                output_root=root / "repaired",
                source_audit={"perceptual_candidates": [candidate]},
                review=review,
            )
            self.assertEqual(manifest["counts"], {"train": 2, "val": 2, "test": 1})
            assignments = {
                (item["source_split"], item["source_sample_id"]): item[
                    "destination_split"
                ]
                for item in manifest["records"]
            }
            self.assertEqual(assignments[("train", "a")], "val")
            self.assertEqual(assignments[("val", "b")], "val")

    def test_validation_experiment_resumes_from_last_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix_root = root / "matrix"
            dataset_root = root / "dataset"
            output_root = root / "runs"
            run_dir = output_root / "resume_me"
            (run_dir / "weights").mkdir(parents=True)
            matrix_root.mkdir()
            dataset_root.mkdir()
            (dataset_root / "data.yaml").write_text("names: {0: calyx}\n")
            (run_dir / "weights" / "last.pt").write_bytes(b"last")
            (run_dir / "weights" / "best.pt").write_bytes(b"best")
            (run_dir / "results.csv").write_text(
                "epoch,time,metrics/mAP50-95(B)\n0,1.0,0.2\n",
                encoding="utf-8",
            )
            (matrix_root / "matrix.json").write_text(
                json.dumps(
                    {
                        "experiments": [
                            {
                                "spec": {"name": "resume_me"},
                                "dataset_root": str(dataset_root),
                                "counts": {
                                    "train_total": 1,
                                    "train_real": 1,
                                    "train_synthetic": 0,
                                    "val_real": 1,
                                    "test_real": 1,
                                },
                                "achieved_train_fraction": {
                                    "real": 1.0,
                                    "synthetic": 0.0,
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            class DummyModel:
                def __init__(self, checkpoint: str) -> None:
                    self.checkpoint = checkpoint

                def train(self, **kwargs):
                    calls.append(("train", self.checkpoint, kwargs))

                def val(self, **kwargs):
                    calls.append(("val", self.checkpoint, kwargs))
                    return SimpleNamespace(
                        box=SimpleNamespace(
                            map=0.5, map50=0.7, map75=0.55, mp=0.6, mr=0.65
                        )
                    )

            with patch(
                "uchuva_lsystem.hybrid_study._load_yolo",
                return_value=lambda checkpoint: DummyModel(checkpoint),
            ):
                result = run_validation_experiment(
                    matrix_root=matrix_root,
                    experiment_name="resume_me",
                    output_root=output_root,
                    config=TrainingConfig(epochs=40, seed=7),
                    minimum_available_ram_gb=0.0,
                )
            self.assertTrue(calls[0][2]["resume"])
            self.assertEqual(calls[1][2]["split"], "val")
            self.assertEqual(result["evaluation_split"], "val")


def _candidate(left_split: str, left_id: str, right_split: str, right_id: str) -> dict:
    return {
        "left_split": left_split,
        "left_id": left_id,
        "right_split": right_split,
        "right_id": right_id,
        "dhash_hamming": 0,
    }


def _aggregate_item(
    *,
    name: str,
    map_mean: float,
    map_delta: float,
    recall_delta: float,
    positive_count: int,
    within_count: int,
    train_real: int,
    train_synthetic: int,
) -> dict:
    deltas = [map_delta, map_delta, map_delta]
    return {
        "experiment": name,
        "dataset_counts": {
            "train_real": train_real,
            "train_synthetic": train_synthetic,
        },
        "metrics": {"map50_95": {"mean": map_mean}},
        "paired_map50_95_delta": {"mean": map_delta},
        "paired_recall_delta": {"mean": recall_delta},
        "paired_deltas": [
            {"seed": seed, "map50_95_delta": value, "recall_delta": recall_delta}
            for seed, value in enumerate(deltas, start=1)
        ],
        "positive_map50_95_seed_count": positive_count,
        "within_noninferiority_seed_count": within_count,
    }


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
