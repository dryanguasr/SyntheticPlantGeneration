from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from uchuva_lsystem.yolo_export import (
    YOLO_CLASSES,
    bbox_xywh_to_yolo,
    clip_bbox_xywh,
    detections_from_mask_items,
    global_reproductive_id,
    write_yolo_file,
)


class YoloExportTests(unittest.TestCase):
    def test_global_reproductive_id_namespaces_local_ids(self) -> None:
        local_id = "axis_0_0_node_1_reproductive_unit"
        self.assertNotEqual(
            global_reproductive_id("plant_01", local_id),
            global_reproductive_id("plant_02", local_id),
        )

    def test_bbox_conversion_uses_top_left_xywh(self) -> None:
        self.assertEqual(
            bbox_xywh_to_yolo((10, 20, 40, 20), 100, 100),
            (0.3, 0.3, 0.4, 0.2),
        )

    def test_clip_reports_border_touching_boxes(self) -> None:
        clipped, truncated = clip_bbox_xywh((-5, 10, 20, 30), 100, 80)
        self.assertEqual(clipped, (0, 10, 15, 30))
        self.assertTrue(truncated)

    def test_mask_items_map_calyx_states_to_classes_and_filter_tiny_items(self) -> None:
        items = {
            "0": {"name": "background", "visible_pixels": 1000},
            "1": {
                "name": "plant_01:unit_1",
                "local_reproductive_id": "unit_1",
                "plant_id": "plant_01",
                "plant_role": "foreground",
                "semantic_class": "calyx",
                "calyx_state": "inflated_green",
                "maturity": "young",
                "reproductive_stage": "young_fruit_with_calyx",
                "visible_pixels": 120,
                "bbox_xywh": [10, 20, 30, 40],
            },
            "2": {
                "name": "plant_02:unit_1",
                "local_reproductive_id": "unit_1",
                "plant_id": "plant_02",
                "plant_role": "neighbor",
                "semantic_class": "flower",
                "visible_pixels": 12,
                "bbox_xywh": [50, 50, 8, 8],
            },
        }
        detections = detections_from_mask_items(items, width=100, height=100)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].class_id, YOLO_CLASSES["calyx"])
        self.assertEqual(detections[0].class_name, "calyx")
        self.assertEqual(detections[0].instance_id, "plant_01:unit_1")
        self.assertEqual(
            detections[0].reproductive_stage, "young_fruit_with_calyx"
        )

    def test_writer_creates_make_sense_yolo_rows(self) -> None:
        items = {
            "1": {
                "name": "plant_01:unit_1",
                "local_reproductive_id": "unit_1",
                "plant_id": "plant_01",
                "plant_role": "foreground",
                "semantic_class": "calyx",
                "calyx_state": "straw_yellow",
                "maturity": "mature",
                "visible_pixels": 500,
                "bbox_xywh": [10, 20, 30, 40],
            }
        }
        detection = detections_from_mask_items(items, width=100, height=100)
        with tempfile.TemporaryDirectory() as temporary:
            path = write_yolo_file(Path(temporary) / "sample.txt", detection)
            fields = path.read_text(encoding="utf-8").strip().split()
        self.assertEqual(len(fields), 5)
        self.assertEqual(int(fields[0]), YOLO_CLASSES["calyx"])
        self.assertTrue(all(0.0 <= float(value) <= 1.0 for value in fields[1:]))

    def test_all_calyx_states_share_class_zero_and_flowers_are_ignored(self) -> None:
        items = {
            str(index): {
                "name": f"plant_01:unit_{index}",
                "semantic_class": semantic_class,
                "calyx_state": state,
                "maturity": maturity,
                "visible_pixels": 500,
                "bbox_xywh": [10 + index * 5, 20, 20, 30],
            }
            for index, (semantic_class, state, maturity) in enumerate(
                (
                    ("calyx", "inflated_green", "young"),
                    ("calyx", "straw_yellow", "mature"),
                    ("calyx", "dry_deteriorated", "overripe"),
                    ("flower", "", "flower"),
                ),
                start=1,
            )
        }
        detections = detections_from_mask_items(items, width=100, height=100)
        self.assertEqual(len(detections), 3)
        self.assertEqual({item.class_id for item in detections}, {0})
        self.assertEqual(
            {item.calyx_state for item in detections},
            {"inflated_green", "straw_yellow", "dry_deteriorated"},
        )


if __name__ == "__main__":
    unittest.main()
