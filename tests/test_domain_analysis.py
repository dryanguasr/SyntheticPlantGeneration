from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from uchuva_lsystem.domain_analysis import analyze_yolo_domain, compare_domain_reports


class DomainAnalysisTests(unittest.TestCase):
    def test_reports_missing_label_and_box_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for kind in ("images", "labels"):
                for split in ("train", "val", "test"):
                    (root / kind / split).mkdir(parents=True)
            Image.new("RGB", (100, 200), (120, 120, 120)).save(root / "images/train/0117.jpg")
            Image.new("RGB", (200, 100), (80, 80, 80)).save(root / "images/val/1064.jpg")
            Image.new("RGB", (200, 100), (90, 90, 90)).save(root / "images/test/1064.jpg")
            (root / "labels/val/1064.txt").write_text("0 0.5 0.5 0.2 0.4\n", encoding="utf-8")
            (root / "labels/test/1064.txt").write_text(
                "0 0.05000001 0.5 0.1 0.4\n", encoding="utf-8"
            )

            report = analyze_yolo_domain(
                "fixture", root / "images", root / "labels", sample_luminance=True
            )

        self.assertEqual(report["overall"]["image_count"], 3)
        self.assertEqual(report["overall"]["object_count"], 2)
        self.assertIn("0117", report["splits"]["train"]["missing_label_ids"])
        self.assertEqual(report["overall"]["orientation_counts"]["portrait"], 1)
        self.assertEqual(report["overall"]["boundary_box_count"], 1)
        context = report["overall"]["non_calyx_scene_context"]
        self.assertEqual(context["sample_count"], 3)
        self.assertIsNotNone(context["edge_energy"]["p50"])
        self.assertIsNotNone(context["luminance_spread"]["p50"])
        self.assertIn(
            "val_test_capture_correlation_risk",
            {item["code"] for item in report["warnings"]},
        )

    def test_comparison_distance_is_zero_for_same_report(self) -> None:
        payload = {
            "name": "same",
            "overall": {
                "orientation_rates_pct": {"portrait": 50.0, "landscape": 50.0},
                "objects_per_image_band_rates_pct": {"one_to_five": 100.0},
                "box_area_band_rates_pct": {"one_to_five_percent": 100.0},
                "boundary_box_rate_pct": 10.0,
                "mean_luminance_quantiles": {"p50": 110.0},
            },
        }
        comparison = compare_domain_reports(payload, payload)
        self.assertEqual(
            comparison["distance"]["composition_mean_absolute_gap_pct_points"], 0.0
        )
        self.assertEqual(comparison["distance"]["mean_luminance_median_gap"], 0.0)

    def test_selected_splits_can_exclude_the_held_out_test_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for kind in ("images", "labels"):
                for split in ("train", "val", "test"):
                    (root / kind / split).mkdir(parents=True)
            for split in ("train", "val", "test"):
                Image.new("RGB", (40, 40), (80, 100, 70)).save(
                    root / f"images/{split}/{split}.jpg"
                )
                (root / f"labels/{split}/{split}.txt").write_text(
                    "0 0.5 0.5 0.2 0.2\n",
                    encoding="utf-8",
                )
            report = analyze_yolo_domain(
                "calibration_only",
                root / "images",
                root / "labels",
                sample_luminance=False,
                splits=("train", "val"),
            )

        self.assertEqual(report["selected_splits"], ["train", "val"])
        self.assertEqual(report["overall"]["image_count"], 2)
        self.assertNotIn("test", report["splits"])


if __name__ == "__main__":
    unittest.main()
