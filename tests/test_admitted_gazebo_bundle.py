import copy
import unittest
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.nodal_repulsion import protected_anatomy
from uchuva_gazebo.admitted_plants import build_admitted_plant_bundle


class AdmittedGazeboBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plant=generate_morphology_tree(73)
        anatomy=protected_anatomy(cls.plant)
        cls.admission=dict(status='admitted',seed=73,anatomy_sha256=anatomy['sha256'],counts=anatomy['counts'],original_counts=anatomy['counts'])
        cls.audits=dict(mesh=dict(physical_collision_count=0,truncated=False),ground=dict(status='valid'),orientation=dict(status='valid'))

    def test_tree_identity_poses_and_units_are_preserved_without_runtime(self):
        before=copy.deepcopy(self.plant.to_dict())
        bundle=build_admitted_plant_bundle(self.plant,self.admission,self.audits,metres_per_scene_unit=.1)
        self.assertEqual(bundle['plant'],before);self.assertEqual(self.plant.to_dict(),before)
        self.assertEqual(bundle['gazebo_plan']['source_seed'],73)
        self.assertEqual(bundle['scene_units']['metres_per_scene_unit'],.1)
        self.assertIn('caller_supplied',bundle['static_evidence']['origin'])

    def test_mismatched_anatomy_or_hard_crossings_are_rejected(self):
        a=copy.deepcopy(self.admission);a['anatomy_sha256']='wrong'
        with self.assertRaises(ValueError):build_admitted_plant_bundle(self.plant,a,self.audits,metres_per_scene_unit=.1)
        audits=copy.deepcopy(self.audits);audits['mesh']['physical_collision_count']=1
        with self.assertRaises(ValueError):build_admitted_plant_bundle(self.plant,self.admission,audits,metres_per_scene_unit=.1)
        with self.assertRaises(ValueError):build_admitted_plant_bundle(self.plant,self.admission,self.audits,metres_per_scene_unit=0)
