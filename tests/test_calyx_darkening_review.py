from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_darkening_review import surface_plan,dark_weight


class DarkeningReviewTests(unittest.TestCase):
    def test_extent_is_independent_from_class_and_historical_unchanged(self):
        self.assertEqual(dark_weight(1,.5,surface_plan(2,0,4)),0)
        self.assertGreater(dark_weight(1,.5,surface_plan(0,1,4)),0)
        self.assertGreater(dark_weight(1,.5,surface_plan(1,2,4)),0)

    def test_nearly_total_reaches_distal_body_but_local_patch_does_not(self):
        self.assertEqual(dark_weight(.2,.5,surface_plan(2,1,4)),0)
        self.assertGreater(dark_weight(.2,.5,surface_plan(2,4,4)),.9)
        self.assertEqual(surface_plan(2,3,4),surface_plan(2,3,4))

    def test_invalid_class(self):
        with self.assertRaises(ValueError):surface_plan(5,1,4)


if __name__=='__main__':unittest.main()
