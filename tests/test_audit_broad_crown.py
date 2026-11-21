"""Adult lateral modules and explicit blade-size policy remain botanical data."""
from copy import deepcopy
import unittest

from uchuva_lsystem.blender_dataset import morphology_parameters_for_capture
from uchuva_lsystem.grammar import generate_morphology_tree, reproductive_counts
from uchuva_lsystem.parameters import get_morphology_parameters, leaf_length_factor
from uchuva_lsystem.provenance import parameter_snapshot_sha256
from uchuva_lsystem.morphology import Plant


PRESET = "trained_trellis_broad_crown_audit_v5"


def axes(items):
    for axis in items:
        yield axis
        yield from axes(axis.child_axes)


def grow(params, seed=2026102600):
    return generate_morphology_tree(seed,params=params,phenology_model="literature_cohort_v1")


class BroadCrownContracts(unittest.TestCase):
    def test_previous_parameter_snapshots_preserved(self):
        expected = {
            "trained_trellis_audit_v2":"b2059054441fdab904ea2679aa25267c20f0f9cd61c2eeb6b9effc28b5738922",
            "trained_trellis_bush_audit_v3":"629a15fc31a5761461b28be50cecba22443458499dcf1c0b0a55392c460e828c",
            "trained_trellis_bush_pose_audit_v4":"b0d674c6a76ca45bb08ea597ab7e9f4a0469aa0563da7fef56157ac04150c49b",
        }
        get_morphology_parameters(PRESET)
        for name,value in expected.items():
            self.assertEqual(parameter_snapshot_sha256(get_morphology_parameters(name)),value)

    def test_main_axis_base_blade_and_reproductive_dimensions_unchanged(self):
        old,new = [get_morphology_parameters(p) for p in ("trained_trellis_bush_pose_audit_v4",PRESET)]
        self.assertEqual(old["axis"]["main_node_count"],new["axis"]["main_node_count"])
        self.assertEqual(old["growth"]["length_budget_cm_by_order"]["0"],new["growth"]["length_budget_cm_by_order"]["0"])
        self.assertEqual(old["leaf"]["length_cm_range"],new["leaf"]["length_cm_range"])
        self.assertEqual(old["leaf"]["width_to_length_ratio_range"],new["leaf"]["width_to_length_ratio_range"])
        self.assertEqual(old["reproduction"],new["reproduction"])
        self.assertEqual(old["internode"],new["internode"])

    def test_adult_blade_scaling_is_separate_from_axis_resource_vigor(self):
        params = get_morphology_parameters(PRESET)
        for order, factor in enumerate((1,.98,.95,.90)):
            self.assertEqual(leaf_length_factor(params,order,.4),factor)
            self.assertEqual(leaf_length_factor(params,order,.95),factor)
        old = get_morphology_parameters("trained_trellis_bush_pose_audit_v4")
        self.assertEqual(leaf_length_factor(old,2,.6),.82*.72)
        self.assertEqual(leaf_length_factor(old,2,.95),.82*.95)

    def test_no_leaf_duplicate_and_every_blade_uses_declared_adult_range(self):
        params = get_morphology_parameters(PRESET)
        plant = grow(params)
        ids = []
        for axis in axes(plant.axes):
            factor = leaf_length_factor(params,axis.order,axis.vigor)
            for node in axis.nodes:
                leaf = node.leaf
                self.assertEqual(leaf.node_id,node.id)
                ids.append(leaf.id)
                self.assertGreaterEqual(leaf.length_cm,4.6*factor-.002)
                self.assertLessEqual(leaf.length_cm,9.2*factor+.002)
                self.assertFalse(leaf.provenance["adult_blade_scaling"]["axis_vigor_used_for_blade_length"])
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(ids),plant.node_count())

    def test_branch_frame_is_activated_in_actual_axes_and_sampling_is_by_order(self):
        params = get_morphology_parameters(PRESET)
        plant = grow(params)
        for axis in axes(plant.axes):
            if not axis.order:
                continue
            self.assertTrue(axis.provenance["branch_frame_v140"])
            self.assertEqual(axis.provenance["branch_direction_frame"],"local_cone_v1")
            record = axis.provenance["branch_angle_sampling"]
            self.assertEqual(record["child_order"],axis.order)
            self.assertLessEqual(record["range_min_deg"],axis.branch_angle_deg)
            self.assertGreaterEqual(record["range_max_deg"],axis.branch_angle_deg)
        self.assertTrue(all(n.leaf.provenance["insertion_frame"]=="local_cone_v2"
                            for a in axes(plant.axes) for n in a.nodes))

    def test_missing_branch_order_and_unknown_policies_fail_closed(self):
        params = get_morphology_parameters(PRESET)
        params["branching"]["branch_angle_deg_by_order"].pop("3")
        with self.assertRaisesRegex(ValueError,"child order 3"):
            grow(params)
        params = get_morphology_parameters(PRESET)
        params["branching"]["frame"]["value"]="camera_facing"
        with self.assertRaisesRegex(ValueError,"branch frame"):
            grow(params)
        params = get_morphology_parameters(PRESET)
        params["growth"]["leaf_vigor_scaling"]["value"]="visible_leaf_quota"
        with self.assertRaisesRegex(ValueError,"vigor scaling"):
            grow(params)

    def test_blade_maturation_does_not_change_random_stream_or_other_organs(self):
        adult = get_morphology_parameters(PRESET)
        legacy = deepcopy(adult)
        legacy["growth"]["leaf_vigor_scaling"]["value"]="legacy_axis_vigor"
        a,b = grow(adult),grow(legacy)
        left,right = a.to_dict()["axes"],b.to_dict()["axes"]
        def strip_blade_size(items):
            for axis in items:
                for node in axis["nodes"]:
                    leaf=node["leaf"]
                    leaf.pop("length_cm");leaf.pop("width_cm")
                    leaf["provenance"].pop("adult_blade_scaling",None)
                strip_blade_size(axis["child_axes"])
        strip_blade_size(left);strip_blade_size(right)
        self.assertEqual(left,right)

    def test_framing_and_inactive_quota_have_no_effect(self):
        a=morphology_parameters_for_capture({"size":"close","density":1},preset_name=PRESET)
        b=morphology_parameters_for_capture({"size":"wide","density":1000},preset_name=PRESET)
        self.assertEqual(a,b)
        b["reproduction"]["target_reproductive_units_range"].update(min=10000,max=10000)
        left,right=grow(a),grow(b)
        self.assertEqual([x.to_dict() for x in left.axes],[x.to_dict() for x in right.axes])
        self.assertGreater(reproductive_counts(left)["fruits"],10)
        self.assertFalse(left.metadata["reproductive_normalization"]["applied"])

    def test_zero_reproductive_probability_never_gets_filled(self):
        params=get_morphology_parameters(PRESET)
        params["reproduction"]["reproductive_probability"]["value"]=0
        self.assertEqual(reproductive_counts(grow(params))["reproductive_units"],0)

    def test_snapshot_and_serialization_capture_the_complete_contract(self):
        plant=grow(get_morphology_parameters(PRESET))
        self.assertEqual(Plant.from_dict(plant.to_dict()).to_dict(),plant.to_dict())
        self.assertEqual(plant.metadata["effective_parameters_sha256"],
                         parameter_snapshot_sha256(plant.metadata["effective_parameters"]))


if __name__=="__main__":
    unittest.main()
