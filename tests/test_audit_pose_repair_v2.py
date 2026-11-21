from copy import deepcopy
import unittest

from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.blender_pose_repair_v2 import (
    angular_candidates, fine_angular_candidates, pose_invariant_manifest, _rectangular_height_field, _ground_not_worse)


class SizePreservingPoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = generate_morphology_tree(6, preset_name="trained_trellis_audit_v2")

    def test_angle_candidates_deterministic_bounded_and_unique(self):
        for kind, bounds in (("reproductive",(5,72)),("leaf",(15,165))):
            values = angular_candidates(354,51,kind=kind,limit=56)
            self.assertEqual(values,angular_candidates(354,51,kind=kind,limit=56))
            self.assertEqual(len(values),len(set(values)))
            self.assertLessEqual(len(values),56)
            self.assertNotIn((354,51),values)
            self.assertTrue(all(0 <= a < 360 and bounds[0] <= b <= bounds[1] for a,b in values))

    def test_invalid_candidates_rejected(self):
        for kwargs in ({"kind":"camera"},{"kind":"leaf","limit":0}):
            with self.assertRaises(ValueError):
                angular_candidates(0,45,**kwargs)
        with self.assertRaises(ValueError):
            angular_candidates(float("nan"),45,kind="leaf")

    def test_pose_is_only_allowed_anatomical_change(self):
        plant=deepcopy(self.original)
        before=pose_invariant_manifest(plant)
        leaf=plant.axes[0].nodes[0].leaf
        leaf.azimuth_deg+=30
        leaf.insertion_angle_deg+=15
        leaf.provenance["mesh_feedback_pose_v2"]={"before_deg":[0,0]}
        self.assertEqual(before,pose_invariant_manifest(plant))
        for field in ("length_cm","width_cm","petiole_length_cm","curl","twist_deg","clearance_lift_cm"):
            value=getattr(leaf,field)
            setattr(leaf,field,value+.01)
            self.assertNotEqual(before,pose_invariant_manifest(plant),field)
            setattr(leaf,field,value)

    def test_load_identity_and_parameter_changes_detected(self):
        plant=deepcopy(self.original)
        before=pose_invariant_manifest(plant)
        plant.axes[0].nodes[0].leaf=None
        self.assertNotEqual(before,pose_invariant_manifest(plant))
        plant=deepcopy(self.original)
        plant.metadata["effective_parameters_sha256"]="unexpected"
        self.assertNotEqual(before,pose_invariant_manifest(plant))

    def test_fruit_and_pedicel_sizes_protected(self):
        plant=deepcopy(self.original)
        def units(axes):
            for axis in axes:
                yield from (n.reproductive_unit for n in axis.nodes if n.reproductive_unit and n.reproductive_unit.fruit)
                yield from units(axis.child_axes)
        unit=next(units(plant.axes))
        before=pose_invariant_manifest(plant)
        unit.pedicel.azimuth_deg+=50
        unit.pedicel.angle_deg+=10
        self.assertEqual(before,pose_invariant_manifest(plant))
        unit.pedicel.length_cm*=1.25
        self.assertNotEqual(before,pose_invariant_manifest(plant))

    def test_ground_fast_path_requires_complete_rectangle_without_holes(self):
        vertices=[(0,0,0),(1,0,.3),(1,1,.2),(0,1,.1)]
        self.assertTrue(_rectangular_height_field(vertices,[(0,1,2),(0,2,3)]))
        self.assertFalse(_rectangular_height_field(vertices,[(0,1,2)]))
        self.assertFalse(_rectangular_height_field(vertices,[(0,1,2),(0,1,2)]))
        self.assertFalse(_rectangular_height_field(vertices,[(0,1,2),(1,2,3)]))
        self.assertFalse(_rectangular_height_field(vertices+[(0,0,.5)],[(0,1,2),(0,2,3)]))

    def test_ground_component_cannot_worsen_to_improve_another_metric(self):
        self.assertTrue(_ground_not_worse((0,0,0),(1,1,1)))
        self.assertFalse(_ground_not_worse((0,1,0),(1,0,0)))
        self.assertFalse(_ground_not_worse((0,0,1),(0,0,0)))

    def test_fine_candidates_are_local_deterministic_bounded_and_unique(self):
        result=fine_angular_candidates(358,35,kind="reproductive",step_deg=5)
        self.assertEqual(result,fine_angular_candidates(358,35,kind="reproductive",step_deg=5))
        self.assertEqual(len(result),8)
        self.assertEqual(result[0],(3,35))
        self.assertEqual(len(result),len(set(result)))
        for a,b in fine_angular_candidates(0,5,kind="reproductive",step_deg=2):
            self.assertTrue(0<=a<360 and 5<=b<=72)
        self.assertEqual(len(fine_angular_candidates(0,35,kind="leaf",limit=3)),3)
        self.assertEqual(fine_angular_candidates(0,35,kind="leaf",limit=0),[])
        for bad in (0,15,float("nan"),-2):
            with self.assertRaises(ValueError):
                fine_angular_candidates(0,35,kind="leaf",step_deg=bad)

    def test_history_only_is_omitted_from_protected_anatomy(self):
        plant=deepcopy(self.original)
        before=pose_invariant_manifest(plant)
        leaf=plant.axes[0].nodes[0].leaf
        leaf.provenance["mesh_feedback_pose_history_v2"]=[{"after_deg":[1,20]}]
        leaf.provenance["mesh_feedback_pose_history_prefix_v2"]="only_last_legacy_record_available"
        self.assertEqual(before,pose_invariant_manifest(plant))
        leaf.provenance["not_pose_repair"]="must remain protected"
        self.assertNotEqual(before,pose_invariant_manifest(plant))


if __name__ == "__main__":
    unittest.main()
