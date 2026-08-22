from __future__ import annotations

import json
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np

from uchuva_classical_augmentation.v2.builder import build_scenario_dataset
from uchuva_classical_augmentation.v2.config import default_campaign_config
from uchuva_classical_augmentation.v2.copy_paste import apply_cluster_copy_paste
from uchuva_classical_augmentation.v2.labels import YoloBox, bbox_from_binary_mask
from uchuva_classical_augmentation.v2.manifest import (
    DerivedSampleRecord,
    file_sha256,
    read_jsonl,
    verify_record_hashes,
    write_jsonl,
)
from uchuva_classical_augmentation.v2.occlusion import GrabCutMaskError, estimate_object_mask
from uchuva_classical_augmentation.v2.metrics import (
    Prediction,
    detection_metrics_at_confidence,
    match_predictions,
)
from uchuva_classical_augmentation.v2.profiles import (
    analyze_real_training_domain,
    area_within_robust_train_range,
    write_profile,
)
from uchuva_classical_augmentation.v2.validation import audit_scenario_dataset
from uchuva_classical_augmentation.v2.training import _is_complete, balanced_scenario_order
from uchuva_classical_augmentation.v2.final_test import evaluate_locked_final_test
from uchuva_classical_augmentation.v2.selection import (
    _canonical_hash,
    confirmation_decisions,
    paired_interval,
    verify_selection_lock,
)
from scripts.summarize_classical_augmentation_v2 import (
    _aggregate,
    _discover_runs,
    _parse_int_set,
    _parse_scenario_set,
    _validate_complete_matrix,
)


class ClassicalAugmentationV2GeometryTests(unittest.TestCase):
    def test_horizontal_flip_labels(self) -> None:
        box = YoloBox(0, 0.2, 0.4, 0.1, 0.2)
        flipped = box.horizontal_flip()
        self.assertAlmostEqual(flipped.x_center, 0.8)
        self.assertEqual((flipped.width, flipped.height), (box.width, box.height))

    def test_crop_label_transformation_and_clipping(self) -> None:
        box = YoloBox(0, 0.30, 0.50, 0.40, 0.40)
        cropped = box.crop((0.20, 0.20, 0.80, 0.80), min_visible=0.2)
        self.assertIsNotNone(cropped)
        assert cropped is not None
        cropped.validate()
        self.assertAlmostEqual(cropped.x_center, 0.25, places=6)
        self.assertAlmostEqual(cropped.width, 0.50, places=6)

    def test_crop_removes_box_outside_window(self) -> None:
        box = YoloBox(0, 0.1, 0.1, 0.08, 0.08)
        self.assertIsNone(box.crop((0.4, 0.4, 0.9, 0.9)))

    def test_size_preservation_filter_uses_profile_range(self) -> None:
        profile = {"geometry": {"bbox_area_robust_range": [0.01, 0.10]}}
        self.assertTrue(area_within_robust_train_range(0.04, profile))
        self.assertFalse(area_within_robust_train_range(0.20, profile))

    def test_occlusion_bbox_recomputation(self) -> None:
        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[20:60, 30:70] = 1
        mask[:, 50:] = 0
        box = bbox_from_binary_mask(mask, class_id=0, image_width=100, image_height=100)
        self.assertIsNotNone(box)
        assert box is not None
        self.assertAlmostEqual(box.x_center, 0.40)
        self.assertAlmostEqual(box.width, 0.20)

    def test_grabcut_failure_handling_for_tiny_box(self) -> None:
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        with self.assertRaises(GrabCutMaskError):
            estimate_object_mask(image, YoloBox(0, 0.5, 0.5, 0.02, 0.02))

    def test_copy_paste_adds_new_label(self) -> None:
        image = np.full((120, 120, 3), (30, 120, 40), dtype=np.uint8)
        boxes = [YoloBox(0, 0.5, 0.5, 0.20, 0.20)]
        profile = {"geometry": {"bbox_area_robust_range": [0.001, 0.25]}}

        def fake_mask(_image, box):
            mask = np.zeros(_image.shape[:2], dtype=np.uint8)
            x1, y1, x2, y2 = box.to_xyxy_pixels(_image.shape[1], _image.shape[0])
            mask[y1:y2, x1:x2] = 1
            return mask

        with patch("uchuva_classical_augmentation.v2.copy_paste.estimate_object_mask", side_effect=fake_mask):
            result = apply_cluster_copy_paste(image, boxes, image, boxes, random.Random(7), profile)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result[1]), 2)

    def test_operational_matching_prioritizes_detection_confidence(self) -> None:
        truths = [YoloBox(0, 0.3, 0.5, 0.1, 0.1), YoloBox(0, 0.4, 0.5, 0.1, 0.1)]
        predictions = [
            Prediction(YoloBox(0, 0.1, 0.5, 0.1, 0.1), 0.9),
            Prediction(YoloBox(0, 0.2, 0.5, 0.1, 0.1), 0.5),
        ]
        overlaps = {
            (0.1, 0.3): 0.60,
            (0.1, 0.4): 0.55,
            (0.2, 0.3): 0.90,
            (0.2, 0.4): 0.40,
        }
        with patch(
            "uchuva_classical_augmentation.v2.metrics.pairwise_iou",
            side_effect=lambda prediction, truth: overlaps[(prediction.x_center, truth.x_center)],
        ):
            matches, unmatched = match_predictions(truths, predictions)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["prediction_index"], 0)
        self.assertEqual(matches[0]["truth_index"], 0)
        self.assertEqual(len(unmatched), 1)

    def test_fixed_confidence_metrics_do_not_reselect_threshold(self) -> None:
        truth = {"image.jpg": [YoloBox(0, 0.5, 0.5, 0.2, 0.2)]}
        predictions = {
            "image.jpg": [
                Prediction(YoloBox(0, 0.5, 0.5, 0.2, 0.2), 0.75),
                Prediction(YoloBox(0, 0.1, 0.1, 0.1, 0.1), 0.60),
            ]
        }
        high = detection_metrics_at_confidence(truth, predictions, confidence=0.70)
        low = detection_metrics_at_confidence(truth, predictions, confidence=0.50)
        self.assertEqual((high["tp"], high["fp"], high["fn"]), (1, 0, 0))
        self.assertEqual((low["tp"], low["fp"], low["fn"]), (1, 1, 0))
        self.assertEqual(high["confidence"], 0.70)


class ClassicalAugmentationV2ProvenanceTests(unittest.TestCase):
    def test_audit_detects_content_hash_split_leakage(self) -> None:
        import cv2

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            shared = np.full((80, 100, 3), 90, dtype=np.uint8)
            for split in ("train", "val", "test"):
                (source / "IMAGENES" / split).mkdir(parents=True)
                (source / "LABELS" / split).mkdir(parents=True)
                image = shared if split != "test" else np.full((80, 100, 3), 180, dtype=np.uint8)
                self.assertTrue(cv2.imwrite(str(source / "IMAGENES" / split / f"{split}.jpg"), image))
                (source / "LABELS" / split / f"{split}.txt").write_text(
                    "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
                )
            profile = analyze_real_training_domain(source)
            profile_path = root / "profile.json"
            write_profile(profile_path, profile)
            scenario = next(
                item
                for item in default_campaign_config().scenarios
                if item.code == "V2-E0R"
            )
            built = build_scenario_dataset(
                source, root / "generated", profile_path, scenario, seed=5, derived_count=1
            )
            audit = audit_scenario_dataset(
                Path(built["dataset_dir"]),
                source,
                profile_path,
                expected_derived_count=1,
            )
            self.assertEqual(audit["status"], "invalid")
            self.assertIn("split_leakage", {issue["code"] for issue in audit["issues"]})

    def test_confirmatory_decision_requires_repeated_paired_improvement(self) -> None:
        runs = [
            {"scenario": scenario, "seed": seed, "epochs_completed": 50}
            for scenario in ("V2-E0", "V2-E0R", "V2-E6")
            for seed in range(1, 6)
        ]
        paired = {
            "V2-E6": {
                "V2-E0": {
                    "mean_delta_map5095": 0.01,
                    "positive_seeds": 4,
                    "differences": [0.01, 0.02, 0.01, 0.01, -0.001],
                    "operational_recall_differences": [0.01] * 5,
                    "mean_delta_difficulty_recall": {
                        "size:small": 0.01,
                        "clustered:True": 0.01,
                        "border_contact:True": 0.0,
                    },
                },
                "V2-E0R": {
                    "mean_delta_map5095": 0.01,
                    "positive_seeds": 4,
                    "differences": [0.01, 0.02, 0.01, 0.01, -0.001],
                    "operational_recall_differences": [0.01] * 5,
                    "mean_delta_difficulty_recall": {
                        "size:small": 0.01,
                        "clustered:True": 0.01,
                        "border_contact:True": 0.0,
                    },
                },
            }
        }
        decision = confirmation_decisions(
            {
                "test_consulted": False,
                "selection_split": "val",
                "runs": runs,
                "paired": paired,
            }
        )
        recipe = decision["decisions"]["V2-E6"]
        self.assertTrue(recipe["case_a_global_improvement"])
        self.assertTrue(recipe["extend_to_ten_seeds"])
        self.assertEqual(recipe["paired_map5095_vs_e0r"]["n"], 5)
        self.assertIsNotNone(recipe["paired_map5095_vs_e0r"]["ci95"])

    def test_confirmatory_decision_rejects_single_seed_win(self) -> None:
        runs = [
            {"scenario": scenario, "seed": seed, "epochs_completed": 50}
            for scenario in ("V2-E0", "V2-E0R", "V2-E5")
            for seed in range(1, 6)
        ]
        comparison = {
            "mean_delta_map5095": -0.006,
            "positive_seeds": 1,
            "differences": [0.02, -0.01, -0.01, -0.01, -0.02],
            "operational_recall_differences": [-0.03] * 5,
            "mean_delta_difficulty_recall": {
                "size:small": -0.03,
                "clustered:True": -0.03,
                "border_contact:True": -0.03,
            },
        }
        decision = confirmation_decisions(
            {
                "test_consulted": False,
                "selection_split": "val",
                "runs": runs,
                "paired": {"V2-E5": {"V2-E0": comparison, "V2-E0R": comparison}},
            }
        )
        recipe = decision["decisions"]["V2-E5"]
        self.assertFalse(recipe["strong_candidate"])
        self.assertFalse(recipe["extend_to_ten_seeds"])

    def test_paired_interval_refuses_to_imply_precision_from_one_seed(self) -> None:
        self.assertIsNone(paired_interval([0.01])["ci95"])

    def test_final_test_requires_intact_lock_and_skips_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "confirmatory.json"
            config = root / "campaign.json"
            evidence.write_text("{}\n", encoding="utf-8")
            config.write_text("{}\n", encoding="utf-8")
            payload = {
                "protocol_version": "classical_augmentation_v2_selection_v1.0.0",
                "status": "locked",
                "selection_split": "val",
                "test_consulted": False,
                "historical_test_caveat": "historically consulted",
                "confirmatory_summary": str(evidence),
                "confirmatory_summary_sha256": file_sha256(evidence),
                "campaign_config": str(config),
                "campaign_config_sha256": file_sha256(config),
                "selected_scenarios": [],
                "training_environment": {"training_config": {}},
                "locked_runs": [],
            }
            payload["lock_content_sha256"] = _canonical_hash(payload)
            lock_path = root / "selection.lock.json"
            lock_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            self.assertEqual(verify_selection_lock(lock_path)["status"], "locked")
            result = evaluate_locked_final_test(
                lock_path=lock_path,
                output_dir=root / "final",
                profile_path=root / "profile_not_needed.json",
            )
            self.assertFalse(result["test_consulted"])
            self.assertEqual(result["status"], "skipped_no_validation_selected_candidate")
            tampered = dict(payload)
            tampered["selection_split"] = "test"
            lock_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                verify_selection_lock(lock_path)

    def test_manifest_round_trip_and_hash_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source.jpg", root / "output.jpg"
            source.write_bytes(b"source")
            output.write_bytes(b"output")
            record = DerivedSampleRecord(
                derived_image_id=output.name,
                source_image_id=source.name,
                source_sha256=file_sha256(source),
                recipe_id="test",
                recipe_version="1",
                augmentation_seed=3,
                transform_sequence=("identity",),
                transform_parameters=({},),
                source_labels=(),
                output_labels=(),
                bbox_visibility_changes=(),
                source_domain_if_known=None,
                output_sha256=file_sha256(output),
            )
            manifest = root / "manifest.jsonl"
            write_jsonl(manifest, [record])
            loaded = read_jsonl(manifest)
            self.assertEqual(loaded, [record])
            verify_record_hashes(loaded[0], source_path=source, output_path=output)
            with self.assertRaises(ValueError):
                verify_record_hashes(replace(record, source_split="val"), source_path=source, output_path=output)

    def test_seed_reproducibility_dataset_counts_and_resume_detection(self) -> None:
        import cv2

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            for split, count in (("train", 2), ("val", 1), ("test", 1)):
                (source / "IMAGENES" / split).mkdir(parents=True)
                (source / "LABELS" / split).mkdir(parents=True)
                for index in range(count):
                    image = np.full((80, 100, 3), 30 + index * 50 + {"train": 0, "val": 5, "test": 10}[split], dtype=np.uint8)
                    name = f"{split}_{index}.jpg"
                    self.assertTrue(cv2.imwrite(str(source / "IMAGENES" / split / name), image))
                    (source / "LABELS" / split / f"{Path(name).stem}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            profile = analyze_real_training_domain(source)
            profile_path = root / "profile.json"
            write_profile(profile_path, profile)
            scenario = next(item for item in default_campaign_config().scenarios if item.code == "V2-E0R")
            first = build_scenario_dataset(source, root / "out1", profile_path, scenario, seed=11, derived_count=1)
            resumed = build_scenario_dataset(source, root / "out1", profile_path, scenario, seed=11, derived_count=1)
            second = build_scenario_dataset(source, root / "out2", profile_path, scenario, seed=11, derived_count=1)
            self.assertEqual(first, resumed)
            first_record = read_jsonl(Path(first["dataset_dir"]) / "manifests/derived_samples.jsonl")[0]
            second_record = read_jsonl(Path(second["dataset_dir"]) / "manifests/derived_samples.jsonl")[0]
            self.assertEqual(first_record.output_sha256, second_record.output_sha256)
            self.assertEqual(first_record.output_sha256, first_record.source_sha256)
            audit = audit_scenario_dataset(Path(first["dataset_dir"]), source, profile_path, expected_derived_count=1)
            self.assertEqual(audit["status"], "valid", audit["issues"])
            self.assertEqual(audit["split_counts"]["train"]["images"], 3)

    def test_training_order_and_resume_detection(self) -> None:
        scenarios = ["V2-E0", "V2-E0R", "V2-E2", "V2-E3"]
        first = balanced_scenario_order(scenarios, 1)
        second = balanced_scenario_order(scenarios, 2)
        self.assertEqual(set(first), set(scenarios))
        self.assertEqual(set(second), set(scenarios))
        self.assertNotEqual(first, second)
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "weights").mkdir()
            (run / "results.csv").write_text(
                "epoch,metrics/mAP50-95(B)\n1,0.1\n2,0.2\n", encoding="utf-8"
            )
            self.assertFalse(_is_complete(run, 2))
            (run / "weights/best.pt").write_bytes(b"checkpoint")
            self.assertTrue(_is_complete(run, 2))

    def test_screening_summary_refuses_incomplete_matrix(self) -> None:
        runs = [
            {"scenario": "V2-E0", "seed": 1, "epochs_completed": 30},
            {"scenario": "V2-E0R", "seed": 1, "epochs_completed": 29},
        ]
        with self.assertRaisesRegex(RuntimeError, "refusing to rank"):
            _validate_complete_matrix(
                runs,
                expected_scenarios=["V2-E0", "V2-E0R"],
                expected_seeds=[1],
                expected_epochs=30,
            )

    def test_screening_summary_accepts_exact_complete_matrix(self) -> None:
        runs = [
            {"scenario": scenario, "seed": seed, "epochs_completed": 30}
            for scenario in ("V2-E0", "V2-E0R")
            for seed in (1, 2, 3)
        ]
        _validate_complete_matrix(
            runs,
            expected_scenarios=["V2-E0", "V2-E0R"],
            expected_seeds=_parse_int_set("1,2,3"),
            expected_epochs=30,
        )

    def test_confirmatory_summary_accepts_selected_scenario_cohort(self) -> None:
        allowed = ["V2-E0", "V2-E0R", "V2-E6", "V2-E7"]
        selected = _parse_scenario_set("V2-E0,V2-E0R,V2-E6", allowed)
        self.assertEqual(selected, ["V2-E0", "V2-E0R", "V2-E6"])
        with self.assertRaisesRegex(ValueError, "Unknown expected scenarios"):
            _parse_scenario_set("V2-E0,V2-E99", allowed)

    def test_multicriterion_ranking_uses_operational_size_and_runtime_evidence(self) -> None:
        def run(scenario, seed, map5095, operational, size, wall_time):
            return {
                "scenario": scenario,
                "seed": seed,
                "precision": 0.9,
                "recall": 0.8,
                "map50": 0.85,
                "map5095": map5095,
                "wall_time_seconds": wall_time,
                "ultralytics_active_time_seconds": wall_time - 5,
                "timing_status": "wall_time_observed",
                "operational": {
                    "confidence_sweep": {"selected": {"recall": operational}},
                    "difficulty": {
                        "strata": {
                            **{
                                f"size:{band}": {"recall": value}
                                for band, value in zip(("small", "medium", "large"), size, strict=True)
                            },
                            "clustered:True": {"recall": size[0]},
                            "border_contact:True": {"recall": size[1]},
                            "object_count:high": {"recall": size[2]},
                        }
                    },
                },
            }

        runs = []
        for seed in (1, 2, 3):
            runs.extend(
                [
                    run("V2-E0", seed, 0.58, 0.30, (0.25, 0.35, 0.40), 100),
                    run("V2-E0R", seed, 0.60, 0.32, (0.27, 0.37, 0.42), 150),
                    run("V2-E5", seed, 0.61, 0.31, (0.24, 0.38, 0.43), 140),
                    run("V2-E6", seed, 0.62, 0.36, (0.31, 0.41, 0.45), 170),
                ]
            )
        report = _aggregate(runs)
        self.assertEqual(report["recommended_confirmatory_scenarios"][:2], ["V2-E0", "V2-E0R"])
        self.assertEqual(report["recommended_confirmatory_scenarios"][2], "V2-E6")
        self.assertIn("worst_mean_delta_size_recall_vs_e0r", report["selection_scorecard"]["V2-E6"])
        self.assertIn(
            "clustered:True",
            report["paired"]["V2-E6"]["V2-E0R"]["mean_delta_difficulty_recall"],
        )
        self.assertEqual(report["selection_scorecard"]["V2-E6"]["mean_active_time_seconds"], 165)
        self.assertEqual(report["selection_method"]["status"], "engineering_rule_fixed_before_screening_results")

    def test_summary_censors_wall_time_after_external_pause(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_name = "v2_e0_screening_yolo11n_e30_seed01"
            run = project / run_name
            (run / "weights").mkdir(parents=True)
            (run / "weights/best.pt").write_bytes(b"checkpoint")
            (run / "args.yaml").write_text("data: dataset/data.yaml\n", encoding="utf-8")
            (run / "results.csv").write_text(
                "epoch,time,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n"
                "30,900,0.9,0.8,0.85,0.6\n",
                encoding="utf-8",
            )
            (project / "execution_state.jsonl").write_text(
                json.dumps(
                    {
                        "run": run_name,
                        "status": "complete",
                        "scenario": "V2-E0",
                        "seed": 1,
                        "run_order": 1,
                        "wall_time_seconds": 72000,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            discovered = _discover_runs(project)
            self.assertEqual(discovered[0]["ultralytics_active_time_seconds"], 900)
            self.assertEqual(discovered[0]["timing_status"], "wall_time_censored_external_pause")


if __name__ == "__main__":
    unittest.main()
