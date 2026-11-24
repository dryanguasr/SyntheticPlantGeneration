"""CPU checks for the public RGB proposal and native tile coordinates."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from field_roi_patch_pilot import vegetation_roi, tile_boxes


class FieldPatchTests(unittest.TestCase):
    def test_odd_roi_is_fully_covered(self):
        roi=[357,123,973,681]
        covered=np.zeros((720,1280),bool)
        for x,y,xx,yy in tile_boxes(roi,1280,720):
            self.assertTrue(0<=x<xx<=1280 and 0<=y<yy<=720)
            self.assertEqual((xx-x,yy-y),(384,384))
            covered[y:yy,x:xx]=True
        self.assertTrue(covered[123:681,357:973].all())

    def test_rgb_green_region_and_padding(self):
        rgb=np.full((720,1280,3),100,np.uint8)
        rgb[200:500,400:700]=(40,120,30)
        box,method=vegetation_roi(rgb)
        self.assertEqual(box,[352,152,748,548])
        self.assertEqual(method,'rgb_hsv_vegetation_union')

    def test_no_green_falls_back_without_truth(self):
        box,method=vegetation_roi(np.zeros((720,1280,3),np.uint8))
        self.assertEqual(box,[0,0,1280,720])
        self.assertIn('fallback',method)

    def test_crop_coordinate_round_trip(self):
        original=np.arange(720*1280,dtype=np.int32).reshape(720,1280)
        for x,y,xx,yy in tile_boxes([510,270,880,620],1280,720):
            crop=original[y:yy,x:xx].copy()
            for local_x,local_y in ((0,0),(123,217),(383,383)):
                self.assertEqual(crop[local_y,local_x],original[y+local_y,x+local_x])


if __name__=='__main__':unittest.main()
