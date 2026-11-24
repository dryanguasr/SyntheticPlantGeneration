"""Pure continuity, provenance and attachment guards for the visual pilot."""
import unittest,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_deterioration import deterioration_state,deform_calyx_point


class DeteriorationTests(unittest.TestCase):
    def test_identity_and_determinism(self):
        self.assertEqual(deterioration_state(3,.6),deterioration_state(3,.6))
        self.assertEqual(deform_calyx_point((.8,.5,-.2),length=4,radius=1,state=deterioration_state(3,0)),(.8,.5,-.2))

    def test_attachment_is_fixed_and_body_compresses(self):
        for d in (.2,.5,.9):
            s=deterioration_state(5,d)
            self.assertEqual(deform_calyx_point((0,0,2),length=4,radius=1,state=s),(0,0,2))
            x,y,z=deform_calyx_point((0,1,0),length=4,radius=1,state=s)
            self.assertLess(math.hypot(x,y),1);self.assertGreater(z,0)

    def test_invalid_severity_and_claims(self):
        for value in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):deterioration_state(0,value)
        self.assertEqual(deterioration_state(1,1).physiological_resorption,'unverified_not_simulated')

    def test_deterioration_is_not_always_black(self):
        dark=deterioration_state(5,.9,'dark_proximal');dry=deterioration_state(5,.9,'bleached_dry')
        self.assertLess(dry.proximal_darkening,dark.proximal_darkening)
        self.assertGreater(dry.bleaching,dark.bleaching)


if __name__=='__main__':unittest.main()
