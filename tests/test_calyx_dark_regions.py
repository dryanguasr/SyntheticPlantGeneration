"""Sanity checks for darkness descriptors and color-independent core masks."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from quantify_calyx_dark_regions import darkness_metrics,central_mask


class DarkRegionTests(unittest.TestCase):
    def test_uniform_dark_is_not_lost_by_relative_threshold(self):
        mask=np.ones((20,20),bool);rgb=np.full((20,20,3),30,np.uint8)
        result=darkness_metrics(rgb,mask)
        self.assertEqual(result['absolute_dark_fraction']['35'],1)
        self.assertEqual(result['relative_contrast_dark_fraction'],0)

    def test_area_fraction_and_threshold_sensitivity(self):
        rgb=np.full((20,20,3),220,np.uint8);rgb[:10]=20
        result=darkness_metrics(rgb,np.ones((20,20),bool))
        self.assertEqual(result['absolute_dark_fraction']['35'],.5)
        self.assertLessEqual(result['absolute_dark_fraction']['25'],result['absolute_dark_fraction']['45'])

    def test_core_is_geometric_and_inside_box(self):
        m=central_mask((100,100,3),(10,20,60,60));ys,xs=np.nonzero(m)
        self.assertTrue(np.all((xs>=10)&(xs<70)&(ys>=20)&(ys<80)))
        self.assertTrue(m[50,40]);self.assertFalse(m[0,0])


if __name__=='__main__':unittest.main()
