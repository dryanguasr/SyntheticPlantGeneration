"""Pure evidence that appearance controls cannot silently change paired inputs."""
from copy import deepcopy
from types import SimpleNamespace as Obj
import unittest

from uchuva_lsystem.appearance_profiles import (
    calibration_schedule, initial_profiles, resolved_profile, component_seed,
)
from uchuva_lsystem.blender_appearance import geometry_digest


class AppearanceProfileTests(unittest.TestCase):
    def test_resolving_or_editing_light_does_not_edit_profile_or_materials(self):
        profiles=initial_profiles();original=deepcopy(profiles)
        a=resolved_profile(profiles,'B');b=resolved_profile(profiles,'L')
        self.assertEqual(a['materials'],b['materials'])
        b['lighting']['exposure_ev']=9
        self.assertEqual(profiles,original)
        self.assertNotEqual(a['material_mode'],resolved_profile(profiles,'T')['material_mode'])

    def test_focal_and_context_have_complete_pairing(self):
        rows=calibration_schedule()
        self.assertEqual(len({r['view_id'] for r in rows}),50)
        for cl in range(3):
            for light in ('diffuse','field','shade'):
                group=[r for r in rows if r['kind']=='focal' and r['class_id']==cl and r['light']==light]
                self.assertEqual({r['bank'] for r in group},{'B','T'})
        for plant in range(4):
            for view in range(2):
                group=[r for r in rows if r['kind']=='context' and r['plant_index']==plant and r['view']==view]
                self.assertEqual({r['bank'] for r in group},{'B','L','T','LT'})

    def test_seed_streams_are_reproducible_and_separate(self):
        seeds=[component_seed(20261026,k,12) for k in ('plant','camera','light','material','context')]
        self.assertEqual(len(set(seeds)),5)
        self.assertEqual(seeds[0],component_seed(20261026,'plant',12))

    def test_geometry_hash_detects_curve_deformation_and_ignores_camera_light(self):
        point=Obj(co=(0,0,0,1),radius=1)
        data=Obj(bevel_depth=.1,bevel_resolution=2,resolution_u=8,
                 splines=[Obj(type='POLY',use_cyclic_u=False,points=[point],bezier_points=[])])
        curve=Obj(type='CURVE',name='stem',matrix_world=((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,0,1)),data=data)
        scene=Obj(objects=[curve]);baseline=geometry_digest(scene)
        scene.objects.append(Obj(type='LIGHT',name='sun'))
        scene.objects.append(Obj(type='CAMERA',name='camera'))
        self.assertEqual(baseline,geometry_digest(scene))
        point.co=(0,0,1,1)
        self.assertNotEqual(baseline,geometry_digest(scene))


if __name__=='__main__':unittest.main()
