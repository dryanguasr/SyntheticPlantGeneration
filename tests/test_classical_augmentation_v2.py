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
from uchuva_classical_augmentation.v2.profiles import (
    analyze_real_training_domain,
    area_within_robust_train_range,
    write_profile,
)
from uchuva_classical_augmentation.v2.validation import audit_scenario_dataset
from uchuva_classical_augmentation.v2.training import _is_complete, balanced_scenario_order


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


class ClassicalAugmentationV2ProvenanceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
