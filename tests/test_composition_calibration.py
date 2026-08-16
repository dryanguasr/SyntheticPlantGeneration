from __future__ import annotations

import unittest

from uchuva_lsystem.composition_calibration import (
    camera_yield_matrix,
    optimize_camera_mixture,
)


class CompositionCalibrationTests(unittest.TestCase):
    def test_yield_matrix_uses_actual_boxes_and_requested_split(self) -> None:
        records = [
            {
                "split": "train",
                "camera_profile": "real_context",
                "detections": [{"yolo_xywh": [0.5, 0.5, 0.05, 0.05]}],
            },
            {
                "split": "train",
                "camera_profile": "real_mid",
                "detections": [{"yolo_xywh": [0.5, 0.5, 0.15, 0.10]}],
            },
            {
                "split": "train",
                "camera_profile": "real_close",
                "detections": [{"yolo_xywh": [0.5, 0.5, 0.30, 0.20]}],
            },
            {
                "split": "val",
                "camera_profile": "real_context",
                "detections": [{"yolo_xywh": [0.5, 0.5, 0.80, 0.80]}],
            },
        ]
        matrix = camera_yield_matrix(records, split="train")
        self.assertEqual(matrix["real_context"]["actual_box_counts"]["under_one_percent"], 1)
        self.assertEqual(matrix["real_mid"]["actual_box_counts"]["one_to_five_percent"], 1)
        self.assertEqual(matrix["real_close"]["actual_box_counts"]["at_least_five_percent"], 1)

    def test_grid_search_recovers_target_camera_mix(self) -> None:
        matrix = {
            "real_context": {
                "boxes_per_capture_by_band": {
                    "under_one_percent": 1.0,
                    "one_to_five_percent": 0.0,
                    "at_least_five_percent": 0.0,
                }
            },
            "real_mid": {
                "boxes_per_capture_by_band": {
                    "under_one_percent": 0.0,
                    "one_to_five_percent": 1.0,
                    "at_least_five_percent": 0.0,
                }
            },
            "real_close": {
                "boxes_per_capture_by_band": {
                    "under_one_percent": 0.0,
                    "one_to_five_percent": 0.0,
                    "at_least_five_percent": 1.0,
                }
            },
        }
        target = {
            "under_one_percent": 14.0,
            "one_to_five_percent": 51.0,
            "at_least_five_percent": 35.0,
        }
        mixture, predicted, gap = optimize_camera_mixture(matrix, target)
        self.assertEqual(mixture, {
            "real_context": 14.0,
            "real_mid": 51.0,
            "real_close": 35.0,
        })
        self.assertEqual(predicted, target)
        self.assertEqual(gap, 0.0)


if __name__ == "__main__":
    unittest.main()
