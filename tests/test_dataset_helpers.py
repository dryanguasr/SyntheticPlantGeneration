from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from uchuva_lsystem.blender_annotations import (
    _nearest_palette_identifier,
    _remove_tiny_annotation_components,
)
from uchuva_lsystem.blender_dataset import (
    DatasetConfig,
    _annotation_visibility_summary,
    _composition_schedule,
    _detections_match_target,
    _image_level_area_rates,
    _morphology_params_for_target,
    _neighbor_count_for_target,
    _png_dimensions,
    _phenology_schedule,
    _split_scene_counts,
    _stored_record_matches_target,
    _reference_alignment,
)
from uchuva_lsystem.yolo_export import detections_from_mask_items


class DatasetHelperTests(unittest.TestCase):
    def test_real_matched_schedule_is_deterministic_and_hits_reference_mix(self) -> None:
        config = DatasetConfig(output_dir="unused")
        reference = {
            "overall": {
                "objects_per_image_band_rates_pct": {
                    "zero": 0.075,
                    "one_to_five": 89.006,
                    "six_to_ten": 10.015,
                    "more_than_ten": 0.904,
                },
                "orientation_rates_pct": {"portrait": 58.584, "landscape": 41.416},
                "box_area_band_rates_pct": {
                    "under_one_percent": 15.759,
                    "one_to_five_percent": 50.812,
                    "at_least_five_percent": 33.429,
                },
                "boundary_box_rate_pct": 10.366,
            }
        }
        first = _composition_schedule(config, reference)
        second = _composition_schedule(config, reference)
        self.assertEqual(first, second)
        self.assertEqual(sum(item["orientation"] == "portrait" for item in first), 59)
        self.assertEqual(sum(item["object_count_band"] == "one_to_five" for item in first), 89)
        self.assertEqual(sum(item["object_count_band"] == "six_to_ten" for item in first), 10)
        self.assertEqual(sum(item["object_count_band"] == "more_than_ten" for item in first), 1)
        self.assertEqual(sum(item["boundary_mode"] == "boundary" for item in first), 10)
        environments = [item["environment_mode"] for item in first]
        self.assertNotIn("isolated_neutral", environments)
        self.assertEqual(environments.count("canopy_close"), 50)
        self.assertEqual(environments.count("ground_tangle"), 35)
        self.assertEqual(environments.count("open_field_hybrid"), 15)
        self.assertEqual(
            sum(item["box_area_band"] == "under_one_percent" for item in first),
            5,
        )
        self.assertEqual(
            sum(item["box_area_band"] == "one_to_five_percent" for item in first),
            40,
        )
        self.assertEqual(
            sum(item["box_area_band"] == "at_least_five_percent" for item in first),
            55,
        )
        self.assertTrue(
            all(
                item["box_area_band"] == "one_to_five_percent"
                for item in first
                if item["object_count_band"] in {"six_to_ten", "more_than_ten"}
            )
        )

    def test_pilot_schedule_has_requested_profile_distribution(self) -> None:
        schedule = _phenology_schedule(50)
        self.assertEqual(schedule.count("mixed_early"), 17)
        self.assertEqual(schedule.count("mixed_balanced"), 17)
        self.assertEqual(schedule.count("mixed_late"), 16)

    def test_real_matched_morphology_uses_a_compact_dense_canopy(self) -> None:
        params = _morphology_params_for_target(
            {
                "object_count_band": "one_to_five",
                "box_area_band": "one_to_five_percent",
            }
        )
        self.assertGreaterEqual(
            params["axis"]["branch_node_count_range"]["min"],
            5,
        )
        self.assertGreaterEqual(
            params["branching"]["branch_probability"]["value"],
            0.48,
        )
        self.assertLessEqual(
            params["internode"]["length_cm_range"]["max"],
            3.2,
        )
        self.assertGreaterEqual(
            params["leaf"]["width_to_length_ratio_range"]["min"],
            0.64,
        )
        multi = _morphology_params_for_target(
            {
                "object_count_band": "six_to_ten",
                "box_area_band": "one_to_five_percent",
            }
        )
        self.assertGreaterEqual(
            multi["reproduction"]["target_reproductive_units_range"]["min"],
            10,
        )
        self.assertEqual(
            _neighbor_count_for_target(
                {
                    "object_count_band": "one_to_five",
                    "box_area_band": "one_to_five_percent",
                }
            ),
            1,
        )
        self.assertEqual(
            _neighbor_count_for_target(
                {
                    "object_count_band": "one_to_five",
                    "box_area_band": "at_least_five_percent",
                }
            ),
            0,
        )
        self.assertEqual(
            _neighbor_count_for_target(
                {
                    "object_count_band": "one_to_five",
                    "box_area_band": "under_one_percent",
                }
            ),
            0,
        )

    def test_box_rates_are_compensated_before_image_scheduling(self) -> None:
        rates = _image_level_area_rates(
            {
                "under_one_percent": 15.03,
                "one_to_five_percent": 50.719,
                "at_least_five_percent": 34.251,
            }
        )
        self.assertAlmostEqual(sum(rates.values()), 100.0)
        self.assertLess(rates["under_one_percent"], 6.0)
        self.assertGreater(rates["at_least_five_percent"], 55.0)

    def test_reference_alignment_uses_requested_train_split(self) -> None:
        profile = {
            "name": "reference",
            "overall": {
                "orientation_rates_pct": {"portrait": 0.0, "landscape": 100.0},
                "objects_per_image_band_rates_pct": {"one_to_five": 100.0},
                "box_area_band_rates_pct": {"at_least_five_percent": 100.0},
                "boundary_box_rate_pct": 100.0,
            },
            "splits": {
                "train": {
                    "orientation_rates_pct": {"portrait": 100.0, "landscape": 0.0},
                    "objects_per_image_band_rates_pct": {"one_to_five": 100.0},
                    "box_area_band_rates_pct": {"one_to_five_percent": 100.0},
                    "boundary_box_rate_pct": 0.0,
                }
            },
        }
        records = [
            {
                "frame": {"width": 640, "height": 960},
                "detections": [
                    {"yolo_xywh": [0.5, 0.5, 0.2, 0.2], "truncated": False}
                ],
            }
        ]
        alignment = _reference_alignment(records, profile, reference_split="train")
        self.assertEqual(alignment["reference_split"], "train")
        self.assertEqual(
            alignment["reference"]["orientation_rates_pct"]["portrait"],
            100.0,
        )
        self.assertEqual(
            alignment["reference"]["boundary_box_rate_pct"],
            0.0,
        )

    def test_pilot_split_is_scene_level_40_5_5(self) -> None:
        self.assertEqual(
            _split_scene_counts(50),
            {"train": 40, "val": 5, "test": 5},
        )

    def test_mid_area_target_accepts_a_majority_not_every_box(self) -> None:
        target = {
            "object_count_band": "one_to_five",
            "box_area_band": "one_to_five_percent",
            "boundary_mode": "interior",
            "schedule_index": 0,
        }
        detections = [
            SimpleNamespace(bbox_xywh=(0, 0, 20, 10), truncated=False),
            SimpleNamespace(bbox_xywh=(0, 0, 30, 10), truncated=False),
            SimpleNamespace(bbox_xywh=(0, 0, 80, 10), truncated=False),
        ]
        self.assertTrue(
            _detections_match_target(
                detections,
                target,
                width=100,
                height=100,
            )
        )
        self.assertFalse(
            _detections_match_target(
                [
                    detections[0],
                    SimpleNamespace(
                        bbox_xywh=(0, 0, 80, 10),
                        truncated=False,
                    ),
                    SimpleNamespace(
                        bbox_xywh=(0, 0, 5, 10),
                        truncated=False,
                    ),
                ],
                target,
                width=100,
                height=100,
            )
        )

    def test_close_area_target_accepts_one_large_or_half_large_boxes(self) -> None:
        target = {
            "object_count_band": "one_to_five",
            "box_area_band": "at_least_five_percent",
            "boundary_mode": "interior",
            "schedule_index": 2,
        }
        detections = [
            SimpleNamespace(bbox_xywh=(0, 0, 80, 10), truncated=False),
            SimpleNamespace(bbox_xywh=(0, 0, 40, 10), truncated=False),
        ]
        self.assertTrue(
            _detections_match_target(
                detections,
                target,
                width=100,
                height=100,
            )
        )
        self.assertTrue(
            _detections_match_target(
                detections[:1],
                target,
                width=100,
                height=100,
            )
        )
        self.assertFalse(
            _detections_match_target(
                [SimpleNamespace(bbox_xywh=(0, 0, 40, 10), truncated=False)],
                target,
                width=100,
                height=100,
            )
        )
        stored = {
            "composition_target": target,
            "detections": [
                {
                    "yolo_xywh": [0.5, 0.5, 0.30, 0.30],
                    "truncated": False,
                }
            ],
        }
        self.assertTrue(_stored_record_matches_target(stored))

    def test_tiny_mask_specks_are_removed_without_erasing_organs(self) -> None:
        identifiers = [0] * 25
        identifiers[0] = 4
        for index in (12, 13, 17, 18):
            identifiers[index] = 7
        _remove_tiny_annotation_components(identifiers, width=5, height=5)
        self.assertEqual(identifiers[0], 0)
        self.assertTrue(all(identifiers[index] == 7 for index in (12, 13, 17, 18)))

    def test_mask_snap_rejects_white_override_geometry(self) -> None:
        palette = [(0, (0, 0, 0)), (1, (107, 149, 189)), (5, (175, 185, 185))]
        self.assertEqual(_nearest_palette_identifier((255, 255, 255), palette), 0)
        self.assertEqual(_nearest_palette_identifier((107, 149, 189), palette), 1)
        self.assertEqual(_nearest_palette_identifier((181, 190, 187), palette), 5)

    def test_visibility_summary_distinguishes_threshold_filtering(self) -> None:
        items = {
            "1": {
                "name": "plant_01:unit_1",
                "semantic_class": "calyx",
                "calyx_state": "inflated_green",
                "visible_pixels": 120,
                "bbox_xywh": [10, 10, 20, 20],
            },
            "2": {
                "name": "plant_02:unit_2",
                "semantic_class": "flower",
                "visible_pixels": 10,
                "bbox_xywh": [40, 40, 4, 4],
            },
        }
        detections = detections_from_mask_items(items, width=100, height=100)
        summary = _annotation_visibility_summary(items, detections)
        self.assertEqual(summary["visible_reproductive_instance_count"], 2)
        self.assertEqual(summary["accepted_detection_count"], 1)
        self.assertEqual(summary["filtered_below_annotation_threshold_count"], 0)
        self.assertEqual(summary["unknown_visible_reproductive_instance_count"], 0)
        self.assertEqual(summary["ignored_flower_instance_count"], 1)

    def test_png_dimensions_are_read_from_ihdr(self) -> None:
        header = (
            b"\x89PNG\r\n\x1a\n"
            + (13).to_bytes(4, "big")
            + b"IHDR"
            + (1280).to_bytes(4, "big")
            + (960).to_bytes(4, "big")
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "header.png"
            path.write_bytes(header)
            self.assertEqual(_png_dimensions(path), (1280, 960))


if __name__ == "__main__":
    unittest.main()
