from __future__ import annotations

import unittest

from uchuva_lsystem.blender_geometry import _leaf_centerline_point, _leaf_shape_profile
from uchuva_lsystem.grammar import generate_morphology_tree


class DenseStrictCalibrationTests(unittest.TestCase):
    def test_new_leaf_morphologies_have_bounded_nonplanar_variation(self) -> None:
        plant = generate_morphology_tree(29)
        leaves = []

        def collect(axis):
            leaves.extend(node.leaf for node in axis.nodes if node.leaf is not None)
            for child in axis.child_axes:
                collect(child)

        for root in plant.axes:
            collect(root)
        self.assertTrue(leaves)
        self.assertTrue(all(-0.10 <= leaf.curl <= 0.16 for leaf in leaves))
        self.assertTrue(all(-8.0 <= leaf.twist_deg <= 8.0 for leaf in leaves))
        self.assertTrue(any(abs(leaf.curl) > 1e-6 for leaf in leaves))
        self.assertTrue(any(abs(leaf.twist_deg) > 1e-6 for leaf in leaves))

    def test_leaf_height_is_quadratic_monotone_and_shared_by_both_edges(self) -> None:
        points = [_leaf_centerline_point(index / 20.0, 1.7, 0.16) for index in range(21)]
        heights = [point[2] for point in points]
        self.assertTrue(all(left >= right for left, right in zip(heights, heights[1:])))
        self.assertEqual(points[0], (0.0, 0.0, -0.0))
        self.assertAlmostEqual(points[-1][2], -0.16)
        for shape in ("ovate", "ovate_cordate", "deltoid_ovate"):
            profile, lobes = _leaf_shape_profile(shape, 0.5)
            self.assertGreater(profile, 0.0)
            self.assertGreaterEqual(lobes, 1.0)


if __name__ == "__main__":
    unittest.main()
