"""Safety and coordinate fixtures for the bounded real pilot."""
import json
from pathlib import Path
import sys
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_union_pilot import bbox, ROOT
from inspect_union_references import image_relative_xy, camera_displacement_to_user_cm, manual_references
from ultralytics.data.augment import RandomFlip, RandomHSV
from ultralytics.utils.instance import Instances
from evaluate_union_videos import marker_is_usable
from evaluate_union_detector import fixed_match


class UnionPilotTests(unittest.TestCase):
    def test_polygon_box_and_invalid_bounds(self):
        self.assertEqual(bbox([2, .1, .2, .3, .2, .3, .6]), [2, .2, .4, .19999999999999998, .39999999999999997])
        with self.assertRaises(ValueError):
            bbox([0, -.1, .2, .3, .2, .3, .6])

    def test_screen_axes_and_unknown_depth(self):
        self.assertEqual(image_relative_xy([12, 3], [10, 10]), [2, 7])
        self.assertEqual(image_relative_xy([8, 13], [10, 10]), [-2, -3])
        self.assertEqual(len(image_relative_xy([8, 13], [10, 10])), 2)

    def test_coordinate_units_and_missing_pose(self):
        self.assertEqual(camera_displacement_to_user_cm([.1, -.2, .3]), [10, 20, 30])
        self.assertIsNone(camera_displacement_to_user_cm(None))
        with self.assertRaises(ValueError):
            camera_displacement_to_user_cm([1, float('nan'), 2])

    def test_missing_manual_coordinates_are_not_zero(self):
        rows = manual_references({'N4':'7','P4':'x','Q4':'0','P5':'y','Q5':'No detecta','P6':'z'})
        self.assertEqual(rows[0]['coordinates_cm'], {'x':0., 'y':None, 'z':None})
        self.assertEqual(rows[0]['cells']['z'], 'Hoja 2!Q6')
        self.assertFalse(rows[0]['fruit_identity_verified'])

    def test_native_flip_keeps_boxes_and_class_aligned(self):
        image = np.zeros((20, 40, 3), dtype=np.uint8)
        image[:, :10] = 100
        labels = {'img':image.copy(),'cls':np.array([[2]],np.float32),
                  'instances':Instances(np.array([[.125,.5,.25,1]],np.float32),
                                        segments=np.zeros((0,1000,2),np.float32),bbox_format='xywh',normalized=True)}
        before = labels['instances'].bboxes.copy()
        RandomHSV(hgain=0,sgain=0,vgain=.1)(labels)
        np.testing.assert_array_equal(labels['instances'].bboxes, before)
        colored = labels['img'].copy()
        result = RandomFlip(p=1, direction='horizontal')(labels)
        np.testing.assert_array_equal(result['img'], colored[:, ::-1])
        np.testing.assert_allclose(result['instances'].bboxes, [[.875,.5,.25,1]])
        self.assertEqual(result['cls'][0,0],2)

    def test_prepared_split_and_quarantine(self):
        if not (ROOT/'manifest.json').exists():
            self.skipTest('Local dataset unavailable')
        records = json.loads((ROOT/'manifest.json').read_text())['records']
        included = [r for r in records if r['status']=='included']
        self.assertEqual(len(included),643)
        self.assertEqual(sum(r['status']=='quarantined_image' for r in records),22)
        for key in ['sha256','group_id']:
            groups = {}
            for r in included:
                groups.setdefault(r[key],set()).add(r['split'])
            self.assertTrue(all(len(s)==1 for s in groups.values()))
        for r in included:
            for line in (ROOT/r['label']).read_text().splitlines():
                cls,x,y,w,h=map(float,line.split())
                self.assertIn(cls,[0,1,2]); self.assertGreater(w,0); self.assertGreater(h,0)
                self.assertGreaterEqual(x-w/2,-1e-8); self.assertLessEqual(x+w/2,1+1e-8)

    def test_marker_geometry_rejects_slender_false_candidate(self):
        self.assertTrue(marker_is_usable({'corners_px':[[0,0],[100,0],[100,100],[0,100]]}))
        self.assertFalse(marker_is_usable({'corners_px':[[0,0],[3,0],[3,100],[0,100]]}))

    def test_detection_and_classification_are_separate(self):
        truth=[{'class_id':1,'bbox':[0,0,10,10]}]
        predictions=[{'class_id':0,'bbox':[0,0,10,10],'confidence':.9}]
        tp,fp,fn=fixed_match(truth,predictions)
        self.assertEqual((int(tp.sum()),int(fp.sum()),int(fn.sum())),(0,1,1))
        tp,fp,fn=fixed_match(truth,predictions,agnostic=True)
        self.assertEqual((int(tp.sum()),int(fp.sum()),int(fn.sum())),(1,0,0))
        tp,fp,fn=fixed_match(truth,predictions*2,agnostic=True)
        self.assertEqual((int(tp.sum()),int(fp.sum()),int(fn.sum())),(1,1,0))


if __name__=='__main__':
    unittest.main()
