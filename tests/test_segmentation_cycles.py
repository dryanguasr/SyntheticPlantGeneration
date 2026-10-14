import unittest
import json
from pathlib import Path
import tempfile
import cv2
import numpy as np
from uchuva_lsystem.segmentation_cycles import class_for_grade, group_seeds, assert_disjoint, mask_polygon, check_deadline


class SegmentationCycleTests(unittest.TestCase):
    def test_expired_run_cannot_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'run.json').write_text(json.dumps({'deadline_unix': 0}))
            with self.assertRaises(TimeoutError): check_deadline(root)

    def test_three_classes_and_invalid_grades(self):
        self.assertEqual([class_for_grade(i) for i in range(7)], [0,0,0,0,0,1,2])
        for value in (-1,7,True,2.0):
            with self.assertRaises(ValueError): class_for_grade(value)

    def test_group_leakage(self):
        assert_disjoint(group_seeds())
        with self.assertRaises(ValueError): assert_disjoint({'train':[1], 'val':[1]})

    def test_holes_and_components_are_not_silently_lost(self):
        mask = np.zeros((100,100), np.uint8)
        cv2.rectangle(mask, (10,10), (60,80), 1, -1)
        cv2.rectangle(mask, (20,20), (40,60), 0, -1)
        cv2.rectangle(mask, (65,30), (85,60), 1, -1)
        points, iou = mask_polygon(mask)
        rebuilt = np.zeros_like(mask)
        cv2.fillPoly(rebuilt, [(points*(100,100)).astype(np.int32)], 1)
        measured = np.count_nonzero((rebuilt>0)&(mask>0))/np.count_nonzero((rebuilt>0)|(mask>0))
        self.assertAlmostEqual(iou, measured)
        self.assertGreater(iou, .98)
        self.assertEqual(rebuilt[40,30], 0)

    def test_single_pixel(self):
        mask = np.zeros((10,10), np.uint8); mask[4,5] = 1
        points,iou = mask_polygon(mask)
        self.assertGreaterEqual(len(points),3); self.assertEqual(iou,1)


if __name__ == '__main__': unittest.main()
