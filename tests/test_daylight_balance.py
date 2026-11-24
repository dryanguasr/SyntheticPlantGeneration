from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.daylight_balance import radiance_balance,balance_for_condition,LUMA


class DaylightBalanceTests(unittest.TestCase):
    def test_chroma_reduction_preserves_luminance_and_directional_variation(self):
        for rgb in ((.1,.4,1.2),(3.,1.,.5),(.2,.2,.2)):
            r=radiance_balance(rgb,.85)
            self.assertAlmostEqual(sum(a*b for a,b in zip(rgb,LUMA)),sum(a*b for a,b in zip(r,LUMA)))
            self.assertAlmostEqual(max(r)-min(r),.15*(max(rgb)-min(rgb)))
        self.assertNotEqual(radiance_balance((.1,.4,1.2),.85),radiance_balance((1.,2.,3.),.85))

    def test_identity_neutral_limit_and_distinct_weather_plans(self):
        self.assertEqual(radiance_balance((.2,.5,1.),0),(.2,.5,1.))
        self.assertEqual(len(set(radiance_balance((.2,.5,1.),1))),1)
        self.assertNotEqual(balance_for_condition({'sky_type':'clear_blue'}),balance_for_condition({'sky_type':'hazy_clear'}))

    def test_invalid_radiance_fails_closed(self):
        for rgb,m in (((1,2,-1),.5),((1,2,3),1.1),((1,2,float('nan')),.5)):
            with self.assertRaises(ValueError):radiance_balance(rgb,m)


if __name__=='__main__':unittest.main()
