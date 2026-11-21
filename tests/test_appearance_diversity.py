"""Diversity must be reproducible and independent of labels, camera and bank."""
import copy
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.appearance_diversity import plant_appearance,appearance_assignments,leaf_appearance
from uchuva_lsystem.blender_bank_repair import anatomy_signature
from uchuva_lsystem.grammar import generate_morphology_tree
from render_appearance_bank import scene_physically_admitted


class AppearanceDiversityTests(unittest.TestCase):
    def test_24_distinct_streams_and_balanced_foliage_strata(self):
        profiles=[plant_appearance(26,f'p{s}_{i}',s,i,[80,12,8]) for s in range(12) for i in range(2)]
        self.assertEqual(len({p['seed'] for p in profiles}),24)
        self.assertEqual([sum(p['foliage']==k for p in profiles) for k in ('green','mixed','yellowing')],[8]*3)
        self.assertTrue(all(abs(sum(p['class_probabilities'])-1)<1e-12 for p in profiles))
        self.assertTrue(all(0<p['senescent_leaf_fraction']<1 for p in profiles))

    def test_class_mixture_does_not_follow_foliage_stratum(self):
        a=plant_appearance(26,'same',0,0,[80,12,8]);b=plant_appearance(26,'same',1,0,[80,12,8])
        self.assertNotEqual(a['foliage'],b['foliage'])
        self.assertEqual(a['class_probabilities'],b['class_probabilities'])

    def test_class_coverage_reassigns_existing_units_without_inventing_organs(self):
        ids=[f'u{i}' for i in range(300)]
        a=appearance_assignments(26,'p',ids,[.7,.2,.1])
        self.assertEqual(set(a),set(ids));self.assertEqual(set(a.values()),{0,1,2})
        self.assertEqual(a,appearance_assignments(26,'p',list(reversed(ids)),[.7,.2,.1]))
        self.assertEqual(appearance_assignments(26,'p',[],[.7,.2,.1]),{})
        self.assertEqual(len(appearance_assignments(26,'p',['u'],[.7,.2,.1])),1)

    def test_leaf_decisions_are_fixed_without_a_bank_or_camera_input(self):
        p=plant_appearance(26,'p',0,0,[80,12,8]);before=copy.deepcopy(p)
        a=[leaf_appearance(26,'p',f'leaf{i}',p) for i in range(500)]
        self.assertEqual(a,[leaf_appearance(26,'p',f'leaf{i}',p) for i in range(500)])
        self.assertGreater(a.count('leaf_senescent'),0);self.assertLess(a.count('leaf_senescent'),100)
        self.assertEqual(p,before)

    def test_new_geometry_policy_reports_positive_gaps_but_blocks_intersections(self):
        policy='mesh_intersections_block_positive_gaps_descriptive/1'
        mesh=dict(status='invalid',tolerate_only_leaf_leaf=True,physical_collision_count=0,clearance_violation_count=3)
        ground=dict(status='valid',physical_collision_count=0)
        self.assertFalse(scene_physically_admitted(mesh,ground))
        self.assertTrue(scene_physically_admitted(mesh,ground,policy))
        self.assertFalse(scene_physically_admitted(dict(mesh,physical_collision_count=1),ground,policy))
        self.assertFalse(scene_physically_admitted(mesh,dict(ground,status='invalid'),policy))
        with self.assertRaises(ValueError):scene_physically_admitted(mesh,ground,'unknown')

    def test_joint_pose_invariant_protects_dimensions_and_organ_counts(self):
        plant=generate_morphology_tree(1)
        before=anatomy_signature(plant)
        plant.axes[0].azimuth_deg+=1
        self.assertEqual(anatomy_signature(plant),before)
        plant.axes[0].internodes[0].length_cm*=1.1
        self.assertNotEqual(anatomy_signature(plant),before)


if __name__=='__main__':unittest.main()
