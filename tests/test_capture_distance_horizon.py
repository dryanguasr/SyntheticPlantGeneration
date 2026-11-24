from pathlib import Path
from array import array
from collections import Counter
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.continuous_capture_distance import sample_capture_distance
from uchuva_lsystem.horizon_matte import separate_panorama
from uchuva_lsystem.capture_skies import sky_condition_for_view


class DistanceHorizonTests(unittest.TestCase):
    def test_continuous_bounds_repeatability_and_mixture(self):
        counts=Counter();distances=set()
        for i in range(10000):
            sample=sample_capture_distance(.6,23+i//24,i%24)
            refs=sample['reference_distances_bu'];d=sample['distance_bu']
            self.assertLessEqual(refs['near'],d);self.assertLessEqual(d,refs['far'])
            if sample['segment']=='near_to_middle':self.assertLessEqual(d,refs['middle'])
            else:self.assertGreaterEqual(d,refs['middle'])
            counts[sample['segment']]+=1;distances.add(d)
        self.assertTrue(.685<counts['near_to_middle']/10000<.715)
        self.assertEqual(len(distances),10000)
        self.assertEqual(sample_capture_distance(.6,23,1),sample_capture_distance(.6,23,1))

    def test_bad_or_collapsed_camera_bounds_explicit(self):
        for bad in (0,-1,float('nan')):
            with self.assertRaises(ValueError):sample_capture_distance(bad,23,1)
        self.assertTrue(sample_capture_distance(100,23,1)['collapsed_segment'])

    def test_distance_mixture_is_not_tied_to_sky(self):
        counts=Counter();near=Counter()
        for i in range(10000):
            scene,view=23+i//24,i%24;sky=sky_condition_for_view(scene,view)['sky_type']
            counts[sky]+=1
            near[sky]+=sample_capture_distance(.6,scene,view)['segment']=='near_to_middle'
        for sky in counts:self.assertTrue(.67<near[sky]/counts[sky]<.73)

    def test_old_bright_sky_cannot_bleed_from_clean_landscape(self):
        w,h=32,32;pixels=array('f')
        for y in range(h):
            for x in range(w):
                rgb=(20.,20.,20.,1.) if y>16+(x%3) else (.04,.08,.03,1.)
                pixels.extend(rgb)
        clean,matte,metadata=separate_panorama(pixels,w,h)
        for y in range(h):
            for x in range(w):
                i=(y*w+x)*4
                self.assertLess(max(clean[i:i+3]),.1)
                if y<10:self.assertEqual(clean[i:i+4],pixels[i:i+4])
                if y>20:self.assertEqual(matte[i],1.)
        self.assertEqual(metadata['missing_columns'],[])
        self.assertTrue(any(0<matte[i]<1 for i in range(0,len(matte),4)))

    def test_missing_horizon_is_rejected(self):
        with self.assertRaises(ValueError):separate_panorama(array('f',[1.,1.,1.,1.])*1024,32,32)


if __name__=='__main__':unittest.main()
