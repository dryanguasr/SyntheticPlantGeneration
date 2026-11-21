"""Post-contact engineering pose bounds do not replace generated morphology."""
from copy import deepcopy
import unittest

from uchuva_lsystem.blender_pose_repair_v2 import ADAPTED_ANGLE_LIMITS
from uchuva_lsystem.grammar import generate_morphology_tree,record_reproductive_counts
from uchuva_lsystem.validation import validate_morphology_tree


def axes(items):
    for axis in items:
        yield axis
        yield from axes(axis.child_axes)


class AdaptedPoseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=generate_morphology_tree(2026102600,preset_name="trained_trellis_lower_crown_audit_v6",
                                         phenology_model="literature_cohort_v1")

    def setUp(self):
        self.plant=deepcopy(self.base)
        self.leaf=self.plant.axes[0].nodes[0].leaf
        self.unit=next(n.reproductive_unit for a in axes(self.plant.axes) for n in a.nodes if n.reproductive_unit)
        record_reproductive_counts(self.plant,"adapted")

    def record(self,kind,angle):
        target=self.leaf if kind=="leaf" else self.unit.pedicel
        field="insertion_angle_deg" if kind=="leaf" else "angle_deg"
        record={"organ_id":self.leaf.id if kind=="leaf" else self.unit.id,"kind":kind,
                "node_id":target.node_id,"before_deg":[target.azimuth_deg,getattr(target,field)],
                "after_deg":[target.azimuth_deg,angle],"status":"engineering_heuristic",
                "dimensions_unchanged":True,
                "angular_limits_deg":{"azimuth":[0,360],"inclination":list(ADAPTED_ANGLE_LIMITS[kind])}}
        setattr(target,field,angle)
        target.provenance["mesh_feedback_pose_v2"]=record
        target.provenance["mesh_feedback_pose"]="bounded_angular_search_dimensions_preserved"
        target.provenance.setdefault("mesh_feedback_pose_history_v2",[]).append(deepcopy(record))
        target.provenance["mesh_feedback_pose_history_prefix_v2"]="complete_since_first_mesh_repair"
        return target

    def errors(self):
        return validate_morphology_tree(self.plant)["errors"]

    def test_valid_adapted_ranges_preserve_preferred_and_generated_snapshot(self):
        snapshot=deepcopy(self.plant.metadata["effective_parameters"])
        preferred=self.leaf.preferred_insertion_angle_deg
        self.record("leaf",130.)
        self.record("reproductive",70.)
        self.assertFalse(self.errors())
        self.assertEqual(preferred,self.leaf.preferred_insertion_angle_deg)
        self.assertEqual(snapshot,self.plant.metadata["effective_parameters"])
        errors=validate_morphology_tree(self.plant,stage="generated")["errors"]
        self.assertTrue(any("sampled range" in e["message"] for e in errors))

    def test_leaf175_and_pedicel999_or_nan_are_rejected(self):
        for kind,value in (("leaf",175.),("reproductive",999.),("reproductive",float("nan"))):
            self.setUp()
            self.record(kind,130. if kind=="leaf" else 70.)
            target=self.leaf if kind=="leaf" else self.unit.pedicel
            setattr(target,"insertion_angle_deg" if kind=="leaf" else "angle_deg",value)
            self.assertTrue(self.errors(),(kind,value))

    def test_after_deg_must_match_actual_pose(self):
        target=self.record("leaf",130.)
        target.insertion_angle_deg=120.
        self.assertTrue(any("after_deg differs" in e["message"] for e in self.errors()))

    def test_cumulative_history_cannot_have_a_hidden_gap(self):
        self.record("leaf",130.)
        target=self.record("leaf",100.)
        self.assertFalse(self.errors())
        target.provenance["mesh_feedback_pose_history_v2"][1]["before_deg"][1]=120.
        target.provenance["mesh_feedback_pose_v2"]=deepcopy(target.provenance["mesh_feedback_pose_history_v2"][-1])
        self.assertTrue(any("noncontiguous" in e["message"] for e in self.errors()))

    def test_fake_limits_or_different_organ_are_rejected(self):
        for key,value in (("angular_limits_deg",{"azimuth":[0,360],"inclination":[0,180]}),
                          ("organ_id","some_other_organ")):
            self.setUp();target=self.record("reproductive",70.)
            target.provenance["mesh_feedback_pose_v2"][key]=value
            target.provenance["mesh_feedback_pose_history_v2"][-1][key]=value
            self.assertTrue(self.errors())

    def test_legacy_last_record_is_checked_without_inventing_history(self):
        target=self.record("reproductive",70.)
        target.provenance.pop("mesh_feedback_pose_history_v2")
        target.provenance.pop("mesh_feedback_pose_history_prefix_v2")
        target.provenance["mesh_feedback_pose_v2"].pop("angular_limits_deg")
        report=validate_morphology_tree(self.plant)
        self.assertFalse(report["errors"])
        self.assertTrue(any(w["category"]=="provenance_limitation" for w in report["warnings"]))
        self.assertNotIn("mesh_feedback_pose_history_v2",target.provenance)
        target.angle_deg=73
        self.assertTrue(self.errors())

    def test_azimuth_and_missing_latest_record_are_checked(self):
        target=self.record("leaf",130.)
        target.azimuth_deg=float("nan")
        self.assertTrue(self.errors())
        self.setUp();target=self.record("leaf",130.)
        target.provenance.pop("mesh_feedback_pose_v2")
        self.assertTrue(self.errors())


if __name__=="__main__":
    unittest.main()
