from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_diffusion_texture import simulate,vein_graph,surface_plan
from uchuva_lsystem.calyx_mottling import surface_plan as old_plan


class DiffusionTextureTests(unittest.TestCase):
    def test_no_source_no_spontaneous_pigment(self):
        v=np.ones((20,20));r=simulate(v,(0,80),source_enabled=False)
        self.assertEqual(float(r[80].max()),0.)

    def test_proximal_and_vein_precedence_monotonic_irreversible_growth(self):
        v=np.zeros((40,40));v[:,19:22]=1
        r=simulate(v,(0,120,300,600))
        self.assertGreater(r[300][-4,20],r[300][4,20])
        self.assertGreater(r[300][-8,20],r[300][-8,4])
        self.assertTrue(np.all(r[600]>=r[300]));self.assertTrue(np.all(r[300]>=r[120]))
        self.assertGreaterEqual(float(r[600].min()),0);self.assertLessEqual(float(r[600].max()),1)

    def test_reproducible_graph_and_original_shape_grades(self):
        a,b,info=vein_graph(64,7);c,d,_=vein_graph(64,7)
        self.assertEqual(a,c);self.assertEqual(b,d);self.assertEqual(info['clipped_rows'],0)
        for j in range(6):
            p=surface_plan(2,j,7);q=old_plan(2,j,7)
            self.assertEqual((p.contraction,p.phenotype),(q.contraction,q.phenotype))

    def test_unstable_step_is_rejected(self):
        with self.assertRaises(ValueError):simulate(np.ones((10,10)),(0,1),dt=1)


if __name__=='__main__':unittest.main()
