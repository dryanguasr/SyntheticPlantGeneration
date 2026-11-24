"""Weather variation must be reproducible and cover every depth."""
from collections import Counter,defaultdict
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.capture_skies import sky_condition_for_view


class SkyScheduleTests(unittest.TestCase):
    def test_balance_and_depth_coverage(self):
        for scene in range(15,35):
            by_depth=defaultdict(Counter);total=Counter()
            for view in range(24):
                c=sky_condition_for_view(scene,view);total[c['sky_type']]+=1
                by_depth[view%3][c['sky_type']]+=1
                self.assertTrue(-15<=c['elevation_offset_deg']<=23)
            self.assertEqual(set(total.values()),{8})
            for counts in by_depth.values():
                self.assertEqual(len(counts),3)
                self.assertLessEqual(max(counts.values())-min(counts.values()),1)

    def test_repeatable_independent_seed_and_coherent_light(self):
        mapping={'clear_blue':'field','hazy_clear':'diffuse','overcast':'shade'}
        for view in range(24):
            c=sky_condition_for_view(15,view)
            self.assertEqual(c,sky_condition_for_view(15,view))
            self.assertEqual(c['diagnostic_light'],mapping[c['sky_type']])
        self.assertNotEqual(sky_condition_for_view(15,1),sky_condition_for_view(15,1,seed=7))


if __name__=='__main__':unittest.main()
