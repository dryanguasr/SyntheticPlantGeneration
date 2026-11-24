"""Adversarial fixtures for the frozen-prediction audit, without model inference."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_cached_synthetic_bias import (count_exposure, native_stats, ordered_matches,
                                       selected_epoch, split_crossings, summarize_ap,
                                       truncate_predictions)


class CachedSyntheticBiasTests(unittest.TestCase):
    def test_absent_class_is_unknown_not_zero_or_changed_macro(self):
        row = dict(truth=[dict(class_id=2, bbox=[0, 0, 10, 10])], predictions=[])
        row["stats"] = native_stats(row)
        result = summarize_ap([row])
        self.assertIsNone(result["macro_ap50_95"])
        self.assertIsNone(result["per_class"]["0"])
        self.assertEqual(result["per_class"]["2"]["ap50_95"], 0)

    def test_duplicate_and_wrong_class_do_not_become_two_true_positives(self):
        row = dict(truth=[dict(class_id=2, bbox=[0, 0, 10, 10])], predictions=[
            dict(class_id=0, bbox=[0, 0, 10, 10], confidence=.9),
            dict(class_id=2, bbox=[0, 0, 10, 10], confidence=.8),
            dict(class_id=2, bbox=[0, 0, 10, 10], confidence=.7)])
        matches, fp, missing = ordered_matches(row, .1)
        self.assertEqual(matches[0]["prediction_index"], 1)
        self.assertEqual(fp, [0, 2])
        self.assertFalse(missing)
        geometric, _, _ = ordered_matches(row, .1, agnostic=True)
        self.assertEqual(geometric[0]["prediction_index"], 0)

    def test_selected_checkpoint_tie_is_not_resolved_using_test(self):
        text = "epoch,metrics/mAP50-95(B)\n" + "\n".join(f"{e},{.5 if e in (3, 4) else .2}" for e in range(1, 9))
        result = selected_epoch(text, .5)
        self.assertIsNone(result["epoch"])
        self.assertEqual(result["candidates"], [3, 4])

    def test_prefix_exposure_excludes_future_epochs(self):
        seq = [dict(actual_source_ids=["row_1", "view_1"]), dict(actual_source_ids=["view_1", "view_1"])]
        counts = {"row_1": {2: 1}, "view_1": {2: 100}}
        result = count_exposure(seq, counts, 1)
        self.assertEqual(result["images"], {"real": 1, "synthetic": 1})
        self.assertEqual(result["instances"]["synthetic"]["2"], 100)

    def test_exact_duplicate_leakage_detected_across_different_ids(self):
        rows = [dict(image_sha256="same", split="train"), dict(image_sha256="same", split="test")]
        self.assertEqual(split_crossings(rows, "image_sha256"), {"same": ["test", "train"]})

    def test_cap_follows_confidence_not_input_order_and_preserves_original(self):
        row = dict(truth=[dict(class_id=2, bbox=[0, 0, 10, 10])], predictions=[
            dict(class_id=2, bbox=[0, 0, 10, 10], confidence=.8),
            dict(class_id=0, bbox=[0, 0, 10, 10], confidence=.9)])
        row["stats"] = native_stats(row)
        self.assertTrue(row["stats"]["tp"][0][0])
        reduced = truncate_predictions(row, 1)
        self.assertFalse(reduced["stats"]["tp"][0][0])
        self.assertEqual(reduced["predictions"][0]["class_id"], 0)
        self.assertEqual(len(row["predictions"]), 2)

    def test_native_AP_and_operating_assignment_can_differ_in_crowded_boxes(self):
        row = dict(truth=[dict(class_id=2, bbox=[0, 0, 10, 10]),
                          dict(class_id=2, bbox=[2, 0, 12, 10])], predictions=[
            dict(class_id=2, bbox=[0, 0, 10, 10], confidence=.9),
            dict(class_id=2, bbox=[0, 0, 10, 10], confidence=.8)])
        self.assertEqual(sum(r[0] for r in native_stats(row)["tp"]), 1)
        matches, _, _ = ordered_matches(row, .1)
        self.assertEqual(len(matches), 2)


if __name__ == "__main__":
    unittest.main()
