import copy
import unittest
from uchuva_lsystem.cultivation_floor import CultivationFloorConfig,plan_cultivation_floor


class CultivationFloorTests(unittest.TestCase):
    def test_reproducible_irregular_context_preserves_inputs_and_root_clearance(self):
        centres=[(-3.,0.,0.),(3.,0.,0.)];original=copy.deepcopy(centres)
        cfg=CultivationFloorConfig(litter_count=100,twig_count=20,vegetation_clusters=8)
        plan=plan_cultivation_floor(1,centres,(-10,10,-10,10),cfg)
        self.assertEqual(plan,plan_cultivation_floor(1,centres,(-10,10,-10,10),cfg))
        self.assertNotEqual(plan,plan_cultivation_floor(2,centres,(-10,10,-10,10),cfg))
        self.assertEqual(centres,original);self.assertEqual(len(plan['litter']),100)
        for p in plan['litter']+plan['twigs']:
            self.assertTrue(all((p['x']-cx)**2+(p['y']-cy)**2>cfg.root_clearance_bu**2 for cx,cy,_ in centres))
        self.assertEqual(plan['config']['parameter_status'],'engineering_heuristic')

    def test_invalid_budget_or_bounds_fail_instead_of_silently_degrading(self):
        with self.assertRaises(ValueError):plan_cultivation_floor(1,[],(0,0,0,1))
        with self.assertRaises(ValueError):plan_cultivation_floor(1,[],(0,1,0,1),CultivationFloorConfig(litter_count=-1))
