from __future__ import annotations

import unittest

from uchuva_lsystem.grammar import generate_morphology_tree


class RealMatchedMorphologyTests(unittest.TestCase):
    def test_new_variation_fields_are_deterministic_and_serializable(self) -> None:
        first = generate_morphology_tree(23)
        second = generate_morphology_tree(23)
        self.assertEqual(first.to_dict(), second.to_dict())
        internode = first.axes[0].internodes[0]
        leaf = first.axes[0].nodes[0].leaf
        self.assertGreaterEqual(internode.bend_angle_deg, 0.0)
        self.assertIsNotNone(leaf)
        self.assertIn(leaf.shape, {"ovate_cordate", "ovate", "deltoid_ovate"})
        self.assertGreaterEqual(leaf.pubescence, 0.0)

    def test_all_generated_fruit_stays_hidden_inside_closed_calyxes(self) -> None:
        plant = generate_morphology_tree(31, phenology_profile="mixed_late")
        units = []

        def collect(axis) -> None:
            units.extend(
                node.reproductive_unit
                for node in axis.nodes
                if node.reproductive_unit is not None and node.reproductive_unit.fruit is not None
            )
            for child in axis.child_axes:
                collect(child)

        collect(plant.axes[0])
        self.assertTrue(units)
        for unit in units:
            self.assertEqual(unit.fruit.visibility, "hidden")
            self.assertEqual(unit.calyx.openness, 0.0)
            self.assertEqual(unit.calyx.profile, "lantern_squash")
            aspect = unit.calyx.length_cm / (unit.calyx.radius_cm * 2.0)
            self.assertGreaterEqual(aspect, 1.15)
            self.assertLessEqual(aspect, 1.55)
            self.assertIn(unit.calyx.texture_variant, {
                "calyx_green_v0", "calyx_green_v1", "calyx_green_v2", "calyx_green_v3",
                "calyx_transition_v0", "calyx_transition_v1",
                "calyx_straw_v0", "calyx_straw_v1", "calyx_straw_v2",
                "calyx_dry_v0", "calyx_dry_v1", "calyx_dry_v2",
            })


if __name__ == "__main__":
    unittest.main()
