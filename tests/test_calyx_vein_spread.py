from pathlib import Path
import math,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_vein_spread import arrival_field,surface_plan,pigment_weights
from uchuva_lsystem.calyx_mottling import surface_plan as prior_plan


class VeinSpreadTests(unittest.TestCase):
    def test_proximal_veins_start_before_distal_and_adjacent_tissue(self):
        w=h=31;signal=[float(x==15) for y in range(h) for x in range(w)]
        times=arrival_field(signal,w,h)
        self.assertLess(times[27*w+15],times[3*w+15])
        self.assertLess(times[20*w+15],times[20*w+19])

    def test_uv_seam_wraps_but_proximal_distal_axis_does_not(self):
        w=h=21;signal=[float(x==0) for y in range(h) for x in range(w)]
        times=arrival_field(signal,w,h)
        self.assertLess(times[10*w+1],times[10*w+w//2])
        self.assertLess(times[10*w+w-1],times[10*w+w//2])
        self.assertLess(times[18*w],times[2*w])

    def test_no_seeds_fails_instead_of_generating_unrelated_patches(self):
        with self.assertRaises(ValueError):arrival_field([0.]*64,8,8)

    def test_progress_preserves_drying_geometry_and_never_reverses_spread(self):
        for j in range(6):
            p=surface_plan(2,j,7);old=prior_plan(2,j,7)
            self.assertEqual((p.contraction,p.phenotype),(old.contraction,old.phenotype))
        values=[pigment_weights(.27,.8,.4,surface_plan(2,j,7)) for j in range(1,5)]
        self.assertEqual(values,sorted(values))
        core,halo=pigment_weights(.01,1,0,surface_plan(2,4,7))
        self.assertLess(max(core,halo),1)
        self.assertEqual(pigment_weights(.01,1,0,surface_plan(2,0,7)),(0.,0.))

    def test_vein_pigment_precedes_surrounding_tissue_at_same_distal_position(self):
        core,halo=pigment_weights(.40,1,.8,surface_plan(2,2,7))
        self.assertGreater(core,.5)
        self.assertEqual(halo,0)


if __name__=='__main__':unittest.main()
