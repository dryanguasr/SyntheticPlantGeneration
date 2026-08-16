from __future__ import annotations

import unittest

from uchuva_lsystem.blender_environment import (
    _effective_terrain_size,
    _terrain_height_at,
)


class EnvironmentSizingTests(unittest.TestCase):
    def test_ground_extent_keeps_context_camera_inside_patch(self) -> None:
        size = _effective_terrain_size(12.0, 1.25)
        self.assertGreaterEqual(size, 260.0)
        self.assertGreater(size * 0.5, 120.0)

    def test_large_requested_or_scene_extent_is_preserved(self) -> None:
        self.assertEqual(_effective_terrain_size(300.0, 1.0), 300.0)
        self.assertEqual(_effective_terrain_size(12.0, 5.0), 260.0)

    def test_terrain_height_is_deterministic_and_seeded(self) -> None:
        first = _terrain_height_at(0.25, -0.4, 650)
        self.assertAlmostEqual(first, _terrain_height_at(0.25, -0.4, 650))
        self.assertNotAlmostEqual(first, _terrain_height_at(0.25, -0.4, 651))

    def test_terrain_height_stays_within_constructive_amplitude(self) -> None:
        heights = [
            _terrain_height_at(x / 5.0, y / 5.0, 650)
            for x in range(-10, 11)
            for y in range(-10, 11)
        ]
        self.assertGreaterEqual(min(heights), -0.1471)
        self.assertLessEqual(max(heights), 0.0371)


if __name__ == "__main__":
    unittest.main()
