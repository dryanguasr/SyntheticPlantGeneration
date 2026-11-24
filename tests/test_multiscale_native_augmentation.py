"""CPU checks for native augmentation and exact raster synchronization."""

from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

import numpy as np
from ultralytics.data.augment import RandomFlip, RandomHSV

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from multiscale_native_augmentation import NativeAugmentationConfig, augment_raster_sample


def sample():
    raster = np.zeros((24, 32), np.uint16)
    raster[2:6, 3:7] = 257
    raster[10:14, 5:9] = 257  # disconnected visible components of the same object
    raster[5:20, 19:30] = 511
    raster[8:13, 22:27] = 0  # a real hole must not become a filled polygon
    image = np.zeros((24, 32, 3), np.uint8)
    image[raster == 257] = (20, 60, 130)
    image[raster == 511] = (90, 150, 30)
    ids = [257, 511]
    boxes = []
    for mask_id in ids:
        y, x = np.where(raster == mask_id)
        boxes.append([(x.min() + x.max() + 1) / 64, (y.min() + y.max() + 1) / 48,
                      (x.max() + 1 - x.min()) / 32, (y.max() + 1 - y.min()) / 24])
    return image, raster, np.array(boxes, np.float32), ids


class NativeRasterAugmentationTests(unittest.TestCase):
    def test_native_flip_preserves_components_holes_ids_and_boxes(self):
        image, raster, boxes, ids = sample()
        result = augment_raster_sample(image, raster, boxes, mask_ids=ids, training=True,
                                      config=NativeAugmentationConfig(hsv_v=0, fliplr=1))
        np.testing.assert_array_equal(result.image_bgr, image[:, ::-1])
        np.testing.assert_array_equal(result.instance_raster, raster[:, ::-1])
        expected = boxes.copy()
        expected[:, 0] = 1 - expected[:, 0]
        np.testing.assert_allclose(result.bboxes_xywh, expected)
        for mask_id in ids:
            self.assertEqual((raster == mask_id).sum(), (result.instance_raster == mask_id).sum())
        self.assertTrue(result.trace["horizontal_flip"])
        self.assertTrue(result.instance_raster.flags.c_contiguous)
        # Inputs remain unchanged, including when the native transform mutates labels.
        original_image, original_raster, original_boxes, _ = sample()
        np.testing.assert_array_equal(image, original_image)
        np.testing.assert_array_equal(raster, original_raster)
        np.testing.assert_array_equal(boxes, original_boxes)

    def test_installed_native_methods_really_execute(self):
        image, raster, boxes, ids = sample()
        hsv = RandomHSV.apply_image
        flip_image = RandomFlip.apply_image
        flip_instances = RandomFlip.apply_instances
        flip_mask = RandomFlip.apply_semantic
        with patch.object(RandomHSV, "apply_image", autospec=True, side_effect=hsv) as h, \
             patch.object(RandomFlip, "apply_image", autospec=True, side_effect=flip_image) as i, \
             patch.object(RandomFlip, "apply_instances", autospec=True, side_effect=flip_instances) as b, \
             patch.object(RandomFlip, "apply_semantic", autospec=True, side_effect=flip_mask) as m:
            result = augment_raster_sample(image, raster, boxes, mask_ids=ids, training=True)
        self.assertEqual([h.call_count, i.call_count, b.call_count, m.call_count], [1, 1, 1, 1])
        self.assertEqual(result.trace["native_calls"], ["RandomHSV", "RandomFlip"])

    def test_validation_is_identity_and_does_not_consume_randomness(self):
        image, raster, boxes, ids = sample()
        random.seed(53)
        np.random.seed(53)
        python_state, numpy_state = random.getstate(), np.random.get_state()
        with patch.object(RandomHSV, "__call__", side_effect=AssertionError("val augmented")), \
             patch.object(RandomFlip, "__call__", side_effect=AssertionError("val augmented")):
            result = augment_raster_sample(image, raster, boxes, mask_ids=ids, training=False)
        np.testing.assert_array_equal(result.image_bgr, image)
        np.testing.assert_array_equal(result.instance_raster, raster)
        np.testing.assert_array_equal(result.bboxes_xywh, boxes)
        self.assertEqual(random.getstate(), python_state)
        current_numpy_state = np.random.get_state()
        self.assertEqual(current_numpy_state[0], numpy_state[0])
        np.testing.assert_array_equal(current_numpy_state[1], numpy_state[1])
        self.assertEqual(current_numpy_state[2:], numpy_state[2:])

    def test_fixed_training_seed_replays_native_augmentation(self):
        image, raster, boxes, ids = sample()
        outputs = []
        for _ in range(2):
            random.seed(83)
            np.random.seed(83)
            outputs.append(augment_raster_sample(image, raster, boxes, mask_ids=ids, training=True))
        np.testing.assert_array_equal(outputs[0].image_bgr, outputs[1].image_bgr)
        np.testing.assert_array_equal(outputs[0].instance_raster, outputs[1].instance_raster)
        self.assertEqual(outputs[0].trace, outputs[1].trace)

    def test_empty_negative_retained_and_bad_identity_rejected(self):
        result = augment_raster_sample(np.zeros((8, 8, 3), np.uint8),
                                      np.zeros((8, 8), np.uint16), np.empty((0, 4), np.float32),
                                      mask_ids=[], training=True)
        self.assertEqual(result.bboxes_xywh.shape, (0, 4))
        image, raster, boxes, _ = sample()
        with self.assertRaisesRegex(ValueError, "disagree"):
            augment_raster_sample(image, raster, boxes, mask_ids=[257, 255], training=True)

    def test_unsupported_class_color_and_composite_augmentations_fail_closed(self):
        for kwargs in ({"hsv_h": .015}, {"hsv_s": .7}, {"mosaic": .5}, {"copy_paste": .1},
                       {"scale": .2}, {"bgr": .1}, {"hsv_v": .4}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                NativeAugmentationConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
