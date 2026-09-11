import unittest

from uchuva_lsystem.annotation_contract import instance_observation, mask_visibility_metrics


class AnnotationContractTests(unittest.TestCase):
    def test_round_unoccluded_mask_has_occupancy_below_one_but_zero_occlusion(self):
        metrics = mask_visibility_metrics(78, 100, isolated_pixels=78)
        self.assertEqual(metrics["mask_fill_ratio"], 0.78)
        self.assertEqual(metrics["occluded_fraction_in_frame"], 0.0)

    def test_unknown_occlusion_is_not_inferred_from_bbox(self):
        self.assertIsNone(mask_visibility_metrics(40, 100)["occluded_fraction_in_frame"])
        self.assertEqual(mask_visibility_metrics(40, 100, isolated_pixels=80)["occluded_fraction_in_frame"], 0.5)

    def test_invalid_counts_rejected(self):
        for visible, area, isolated in ((101, 100, None), (-1, 100, None), (5, 10, 4), (0, 0, 0)):
            with self.assertRaises(ValueError):
                mask_visibility_metrics(visible, area, isolated_pixels=isolated)

    def test_real_metadata_does_not_become_maturity_ground_truth(self):
        record = instance_observation({"instance_id": "real:1", "bbox_xywh": [1, 2, 10, 10],
                                       "calyx_state": "straw_yellow", "maturity": "mature"}, source_domain="real")
        for key in ("agronomic_maturity", "observed_calyx_appearance", "training_class_id", "synthetic_appearance_candidate"):
            self.assertIsNone(record[key])

    def test_synthetic_state_remains_candidate_pending_visual_review(self):
        record = instance_observation({"instance_id": "plant1:unit1", "bbox_xywh": [0, 0, 10, 10],
                                       "visible_pixels": 50, "calyx_state": "inflated_green"}, source_domain="synthetic")
        self.assertEqual(record["synthetic_appearance_candidate"], "inflated_green")
        self.assertEqual(record["review_status"], "pending")
        self.assertIsNone(record["training_class_id"])

    def test_unmapped_state_is_an_error(self):
        with self.assertRaises(ValueError):
            instance_observation({"instance_id": "a", "bbox_xywh": [0, 0, 10, 10], "calyx_state": "unknown"}, source_domain="synthetic")


if __name__ == "__main__":
    unittest.main()
