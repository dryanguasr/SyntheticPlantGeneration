"""Memory-bounded mask evaluation must preserve every IoU exactly."""
import unittest
import numpy as np
from uchuva_gazebo.continuous_evaluation import mask_iou_matrix, packed_mask_iou_matrix


class PackedEvaluationTest(unittest.TestCase):
    def test_exact_with_padding_and_partial_batch(self):
        rng = np.random.default_rng(14)
        masks = rng.random((37, 17, 19)) > .7
        codes = rng.integers(0, 4, (17, 19))
        instances = [dict(code=i, bbox=[0, 0, 19, 17],
                          pixels=int((codes == i).sum())) for i in range(1, 4)]
        packed = np.packbits(masks.reshape(37, -1), axis=1)
        expected = mask_iou_matrix(masks, codes, instances)
        for batch in (1, 16, 37):
            np.testing.assert_array_equal(expected, packed_mask_iou_matrix(
                packed, (17, 19), codes, instances, batch))


if __name__ == '__main__':
    unittest.main()
