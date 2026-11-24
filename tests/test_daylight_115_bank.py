from pathlib import Path
import sys,unittest,copy
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.daylight_115_bank import weather_slots,WEATHER_COUNTS,exact_mask_cache_gate,capture_condition


class Bank115Tests(unittest.TestCase):
    def test_exact_weather_quota_with_depth_coverage(self):
        rows=[dict(view_id=f'scene_023_view_{i:03d}',scene_id='scene_023',depth_stratum=('near','middle','far')[i%3]) for i in range(115)]
        a=weather_slots(rows);self.assertEqual(Counter(a.values()),Counter(WEATHER_COUNTS))
        self.assertEqual(a,weather_slots(list(reversed(rows))))
        for depth in ('near','middle','far'):self.assertEqual({a[r['view_id']] for r in rows if r['depth_stratum']==depth},set(WEATHER_COUNTS))
        for r in rows:
            c=capture_condition(r,a[r['view_id']]);self.assertIn(c['diagnostic_light'],('field','diffuse','shade'))

    def test_exact_cache_rejects_any_camera_geometry_visibility_or_intrinsic_change(self):
        row=dict(camera_matrix=[[1,0],[0,1]],bulk_geometry_sha256='abc',render_config=dict(width=960,height=720))
        args=[row,[[1,0],[0,1]],'abc','vis','vis',dict(lens=50),dict(lens=50)]
        self.assertTrue(exact_mask_cache_gate(*args))
        for index,bad in ((1,[[1,1e-12],[0,1]]),(2,'other'),(3,'different'),(5,dict(lens=49))):
            b=copy.deepcopy(args);b[index]=bad
            with self.assertRaises(ValueError):exact_mask_cache_gate(*b)


if __name__=='__main__':unittest.main()
