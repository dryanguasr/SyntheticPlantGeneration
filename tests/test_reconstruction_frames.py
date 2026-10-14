"""Check that the frame selector responds to image motion, not just time."""
from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_reconstruction.frames import motion_between


class ReconstructionMotionTests(unittest.TestCase):
    def test_translation_and_identical_view(self):
        random = np.random.default_rng(123)
        a = np.zeros((270, 480), dtype=np.uint8)
        for x, y in random.integers([20, 20], [450, 240], size=(150, 2)):
            cv2.circle(a, (int(x), int(y)), 3, 230, -1)
        b = cv2.warpAffine(a, np.float32([[1, 0, 9], [0, 1, 0]]), (480, 270))
        flow, count = motion_between(a, b)
        self.assertGreater(count, 20)
        self.assertAlmostEqual(flow, 9, delta=.2)
        unchanged, _ = motion_between(a, a)
        self.assertLess(unchanged, .01)

    def test_textureless_view_is_uncertain(self):
        image = np.zeros((270, 480), dtype=np.uint8)
        self.assertEqual(motion_between(image, image), (None, 0))


if __name__ == "__main__":
    unittest.main()
