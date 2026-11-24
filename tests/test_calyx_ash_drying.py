from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from uchuva_lsystem import calyx_ash_drying as ash
from uchuva_lsystem import calyx_dry_refinement as previous


class AshDryingTests(unittest.TestCase):
    def test_unchanged_pigment_source_solver_and_shape_states(self):
        self.assertIs(ash.simulate, previous.simulate)
        for index in range(6):
            a, b = ash.surface_plan(2, index, 9), previous.surface_plan(2, index, 9)
            self.assertEqual((a.contraction, a.snapshot_step, a.phenotype),
                             (b.contraction, b.snapshot_step, b.phenotype))

    def test_mature_and_unpigmented_tissue_are_unchanged(self):
        v=np.array([[1., 0.]]); o=np.array([[1, 0]]); p=np.zeros_like(v)
        c=np.full_like(v, .5); g=np.zeros_like(v)
        for cid in (1, 2):
            self.assertTrue(np.allclose(ash.color_surface(v,o,p,c,g,cid,severity=.88),
                                       previous.color_surface(v,o,p,c,g,cid,severity=.88)))

    def test_grey_reduces_postprofile_chroma_without_erasing_pigment_luminance(self):
        rgb=np.array([[[100.,75.,68.],[100.,75.,68.]]]); p=np.array([[0.,.95]])
        gain=np.array([1.28,1.04,.48]); c=np.full_like(p,.5)
        out=ash.grey_drying(rgb,p,.88,c,np.zeros_like(p),gain)
        def effective(x):
            x=x/255
            return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)*gain
        a,b=effective(rgb),effective(out)
        self.assertTrue(np.allclose(a[0,0],b[0,0]))
        self.assertLess(np.ptp(b[0,1]),np.ptp(a[0,1])*.4)
        self.assertTrue(np.allclose(a@np.array([.2126,.7152,.0722]),b@np.array([.2126,.7152,.0722])))


if __name__=='__main__': unittest.main()
