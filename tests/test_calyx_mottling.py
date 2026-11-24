from pathlib import Path
import sys,unittest,math
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_mottling import surface_plan,dark_weight
from uchuva_lsystem.calyx_darkening_review import surface_plan as old_plan


class MottlingTests(unittest.TestCase):
    def test_shape_stages_are_preserved_and_historical_surface_untouched(self):
        for j in range(6):
            plan=surface_plan(2,j,19);old=old_plan(2,j,19)
            self.assertEqual(plan.contraction,old.contraction)
            self.assertEqual(plan.phenotype,old.phenotype)
        self.assertEqual(surface_plan(2,0,19).patches,())

    def test_patch_field_varies_around_same_height(self):
        plan=surface_plan(2,3,19)
        values=[dark_weight((.5+.46*math.cos(a),.5+.46*math.sin(a),.6),plan)
                for a in [i*math.tau/60 for i in range(60)]]
        self.assertGreater(max(values)-min(values),.15)

    def test_expansion_is_progressive_for_same_seed(self):
        points=[(.5+.46*math.cos(a),.5+.46*math.sin(a),z/10)
                for a in [j*math.tau/24 for j in range(24)] for z in range(1,10)]
        totals=[sum(dark_weight(p,surface_plan(2,j,19)) for p in points) for j in range(1,5)]
        self.assertEqual(totals,sorted(totals))

    def test_windows_and_original_texture_are_never_fully_replaced(self):
        plan=surface_plan(2,4,19);p=plan.patches[0].center
        self.assertLess(dark_weight(p,plan,macro_noise=1,micro_noise=1),.9)
        self.assertLess(dark_weight(p,plan,macro_noise=0),dark_weight(p,plan,macro_noise=1))
        self.assertGreater(plan.transmitted_diffuse_mix,0)
        self.assertEqual(plan,surface_plan(2,4,19))


if __name__=='__main__':unittest.main()
