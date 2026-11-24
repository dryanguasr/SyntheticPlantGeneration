from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_lsystem.calyx_dry_refinement import simulate,color_surface,dry_fibres,surface_plan
from uchuva_lsystem.calyx_diffusion_texture import simulate as old_simulate,surface_plan as old_plan


class DryRefinementTests(unittest.TestCase):
    def test_mature_primary_veins_retain_high_contrast_and_light_tissue(self):
        v=np.array([[1.,0.]]);order=np.array([[1,0]]);p=np.zeros_like(v);noise=np.ones_like(v)*.5
        rgb=color_surface(v,order,p,noise,np.zeros_like(v),1)
        lum=rgb@np.array([.2126,.7152,.0722])
        self.assertGreater(lum[0,1]-lum[0,0],100)
        self.assertGreater(lum[0,1],150)

    def test_late_reticulation_softens_as_pigment_enters_intervenal_tissue(self):
        v=np.array([[.5,0.]]);order=np.array([[3,0]]);noise=np.ones_like(v)*.5
        def contrast(p):
            c=color_surface(v,order,np.ones_like(v)*p,noise,np.zeros_like(v),2)
            return abs(float((c[0,0]-c[0,1])@np.array([.2126,.7152,.0722])))
        self.assertLess(contrast(.85),contrast(.1))

    def test_more_intervenal_pigment_without_remote_seeding_or_reversal(self):
        v=np.zeros((40,40));v[:,19:22]=1
        r=simulate(v,(0,200,600));old=old_simulate(v,(0,600))
        self.assertGreater(r[600][-5,16],old[600][-5,16])
        self.assertTrue(np.all(r[600]>=r[200]))
        self.assertEqual(float(simulate(v,(0,50),source_enabled=False)[50].max()),0)

    def test_reproducible_dry_relief_and_preserved_shape_grades(self):
        a=dry_fibres(64,8);b=dry_fibres(64,8)
        self.assertEqual(a,b);self.assertGreater(max(a),0)
        for j in range(6):
            p=surface_plan(2,j,8);q=old_plan(2,j,8)
            self.assertEqual((p.contraction,p.phenotype,p.snapshot_step),(q.contraction,q.phenotype,q.snapshot_step))


if __name__=='__main__':unittest.main()
