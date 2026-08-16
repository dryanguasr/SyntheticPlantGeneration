from __future__ import annotations

import unittest

from uchuva_classical_augmentation import student_yolo11n_conditions
from uchuva_classical_augmentation.protocol import RECIPE_STATUS_PRECOMPUTED_ONLY


class ClassicalAugmentationProtocolTests(unittest.TestCase):
    def test_student_protocol_preserves_documented_conditions(self) -> None:
        conditions = student_yolo11n_conditions()
        self.assertEqual([condition.code for condition in conditions], ["E0", "E1", "E2"])
        self.assertEqual(conditions[0].expected_split_counts, (1062, 109, 109))
        self.assertEqual(conditions[1].expected_split_counts, (2124, 109, 109))

    def test_undelivered_recipes_remain_explicitly_unavailable(self) -> None:
        conditions = {condition.code: condition for condition in student_yolo11n_conditions()}
        self.assertEqual(conditions["E1"].recipe_status, RECIPE_STATUS_PRECOMPUTED_ONLY)
        self.assertEqual(conditions["E2"].recipe_status, RECIPE_STATUS_PRECOMPUTED_ONLY)
        self.assertEqual(conditions["E0"].recipe_status, "natural_only")


if __name__ == "__main__":
    unittest.main()
