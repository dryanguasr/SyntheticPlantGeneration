from copy import deepcopy
import math
import unittest

from uchuva_lsystem.grammar import generate_morphology_tree, reproductive_counts
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.reproductive_orientation import KEY, organ_direction, pedicel_direction
from uchuva_lsystem.validation import validate_morphology_tree


def units(axes):
    for axis in axes:
        for node in axis.nodes:
            if node.reproductive_unit:
                yield node.reproductive_unit
        yield from units(axis.child_axes)


class ReproductiveOrientation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = generate_morphology_tree(2026102600, preset_name="trained_trellis_lower_crown_audit_v6", phenology_model="literature_cohort_v1")
        cls.new = generate_morphology_tree(2026102600, preset_name="trained_trellis_pendulous_audit_v7", phenology_model="literature_cohort_v1")

    def test_architecture_organs_classes_and_sizes_unchanged(self):
        previous, current = self.old.to_dict()["axes"], deepcopy(self.new.to_dict()["axes"])
        def strip(axes):
            for axis in axes:
                for node in axis["nodes"]:
                    if node["reproductive_unit"]:
                        node["reproductive_unit"]["provenance"].pop(KEY)
                strip(axis["child_axes"])
        strip(current)
        self.assertEqual(previous, current)
        self.assertEqual(reproductive_counts(self.old), reproductive_counts(self.new))
        self.assertGreater(reproductive_counts(self.new)["fruits"], 10)

    def test_axes_down_and_independent_of_contact_pedicel_pose(self):
        for original in units(self.new.axes):
            unit = deepcopy(original)
            before = organ_direction(unit)
            self.assertLessEqual(math.degrees(math.acos(-before[2])), 25.00001)
            unit.pedicel.angle_deg = 5
            unit.pedicel.azimuth_deg = (unit.pedicel.azimuth_deg+179)%360
            self.assertEqual(before, organ_direction(unit))
            self.assertNotEqual(before, pedicel_direction(unit))

    def test_legacy_interpretation_and_snapshot_remain_explicit(self):
        for unit in units(self.old.axes):
            self.assertNotIn(KEY, unit.provenance)
            self.assertEqual(organ_direction(unit), pedicel_direction(unit))
        self.assertNotIn("organ_orientation", get_morphology_parameters("trained_trellis_lower_crown_audit_v6")["reproduction"])

    def test_serialization_and_validation(self):
        loaded = Plant.from_dict(self.new.to_dict())
        self.assertEqual(loaded.to_dict(), self.new.to_dict())
        self.assertFalse(validate_morphology_tree(loaded, stage="generated")["errors"])

    def test_missing_and_invalid_pose_are_rejected(self):
        for mutation in ("missing", "outside", "unknown", "nan"):
            plant = deepcopy(self.new)
            unit = next(units(plant.axes))
            if mutation == "missing":
                unit.provenance.pop(KEY)
            elif mutation == "outside":
                unit.provenance[KEY]["inclination_from_down_deg"] = 70
            elif mutation == "nan":
                unit.provenance[KEY]["inclination_from_down_deg"] = float("nan")
            else:
                unit.provenance[KEY]["policy"] = "unknown"
            self.assertTrue(validate_morphology_tree(plant, stage="adapted")["errors"], mutation)

    def test_sampling_reproducible_without_shared_rng(self):
        again = generate_morphology_tree(2026102600, preset_name="trained_trellis_pendulous_audit_v7", phenology_model="literature_cohort_v1")
        self.assertEqual(self.new.to_dict(), again.to_dict())


if __name__ == "__main__":
    unittest.main()
