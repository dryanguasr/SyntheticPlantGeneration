from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uchuva_lsystem.detection_diagnostics import (
    aggregate_error_report,
    analyze_image_errors,
    deterministic_iou_match,
    validate_real_val_only,
)


class DetectionDiagnosticsTests(unittest.TestCase):
    def test_matching_is_highest_iou_and_deterministic(self) -> None:
        ground_truth = [(0.3, 0.5, 0.2, 0.2), (0.7, 0.5, 0.2, 0.2)]
        predictions = [
            {"box": (0.31, 0.5, 0.2, 0.2), "confidence": 0.8},
            {"box": (0.69, 0.5, 0.2, 0.2), "confidence": 0.9},
        ]
        first = deterministic_iou_match(ground_truth, predictions)
        second = deterministic_iou_match(ground_truth, predictions)
        self.assertEqual(first, second)
        self.assertEqual(len(first["matches"]), 2)

    def test_absent_and_mislocalized_detections_are_distinguished(self) -> None:
        report = analyze_image_errors(
            [(0.3, 0.5, 0.2, 0.2), (0.8, 0.8, 0.1, 0.1)],
            [
                {"box": (0.38, 0.5, 0.2, 0.2), "confidence": 0.7},
                {"box": (0.05, 0.05, 0.05, 0.05), "confidence": 0.6},
            ],
            image_width=640,
            image_height=480,
            mean_luminance=120.0,
        )
        outcomes = {event["outcome"] for event in report["ground_truth_events"]}
        self.assertIn("localization_error_iou_010_050", outcomes)
        self.assertIn("false_negative_absent", outcomes)
        aggregate = aggregate_error_report([report])
        self.assertEqual(aggregate["ground_truth_count"], 2)

    def test_validation_guard_rejects_test_and_synthetic_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "images" / "val"
            root.mkdir(parents=True)
            valid = [root / f"real_val_{index:04d}.jpg" for index in range(133)]
            self.assertEqual(len(validate_real_val_only(valid)), 133)
            invalid = list(valid)
            invalid[0] = Path(temporary) / "images" / "test" / "real_val_0000.jpg"
            with self.assertRaises(ValueError):
                validate_real_val_only(invalid)


if __name__ == "__main__":
    unittest.main()
