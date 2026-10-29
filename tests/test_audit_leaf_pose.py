"""Leaf posture opt-in changes angles, not organs, architecture or RNG usage."""
from copy import deepcopy
import math
import unittest

from uchuva_lsystem.grammar import generate_morphology_tree, reproductive_counts
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.organ_frames import orthogonal_leaf_direction
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import parameter_snapshot_sha256
from uchuva_lsystem.validation import validate_morphology_tree


OLD = "trained_trellis_bush_audit_v3"
NEW = "trained_trellis_bush_pose_audit_v4"


def axes(items):
    for axis in items:
        yield axis
        yield from axes(axis.child_axes)


def generate(seed, name):
    return generate_morphology_tree(seed,preset_name=name,phenology_model="literature_cohort_v1")


def without_leaf_pose(plant):
    values = deepcopy(plant.to_dict()["axes"])
    def visit(items):
        for axis in items:
            for node in axis["nodes"]:
                leaf = node.get("leaf")
                if leaf:
                    leaf.pop("insertion_angle_deg")
                    leaf.pop("preferred_insertion_angle_deg")
                    leaf["provenance"].pop("insertion_frame",None)
                    leaf["provenance"].pop("pose_sampling",None)
            visit(axis["child_axes"])
    visit(values)
    return values


class LeafPoseOptInTests(unittest.TestCase):
    def test_v3_parameter_snapshot_is_unchanged(self):
        get_morphology_parameters(NEW)
        self.assertEqual(parameter_snapshot_sha256(get_morphology_parameters(OLD)),
                         "629a15fc31a5761461b28be50cecba22443458499dcf1c0b0a55392c460e828c")

    def test_same_seed_retains_every_organ_dimension_id_and_nodal_decision(self):
        for seed in range(2026102600,2026102604):
            old,new = generate(seed,OLD),generate(seed,NEW)
            self.assertEqual(without_leaf_pose(old),without_leaf_pose(new))
            self.assertEqual(reproductive_counts(old),reproductive_counts(new))

    def test_single_draw_reuses_identical_random_quantile(self):
        old,new = generate(2026102600,OLD),generate(2026102600,NEW)
        old_leaves = [n.leaf for a in axes(old.axes) for n in a.nodes]
        new_leaves = [n.leaf for a in axes(new.axes) for n in a.nodes]
        for a,b in zip(old_leaves,new_leaves):
            self.assertAlmostEqual((a.insertion_angle_deg-55)/31,(b.insertion_angle_deg-30)/50,delta=.0003)
            self.assertEqual(b.insertion_angle_deg,b.preferred_insertion_angle_deg)
            self.assertNotIn("insertion_frame",a.provenance)
            self.assertEqual(b.provenance["insertion_frame"],"orthogonal_local_v1")
            self.assertEqual(b.provenance["pose_sampling"]["range_min_deg"],30)
            self.assertEqual(b.provenance["pose_sampling"]["range_max_deg"],80)
            self.assertEqual(b.provenance["pose_sampling"]["camera_dependency"],"none")

    def test_insertion_means_local_axis_angle_for_oblique_and_horizontal_stems(self):
        for axis in ((0,0,1),(1,0,0),(.8,.2,.4)):
            norm=math.sqrt(sum(x*x for x in axis))
            unit=tuple(x/norm for x in axis)
            for azimuth in (0,45,90,230):
                for angle in (30,55,80):
                    direction=orthogonal_leaf_direction(axis,azimuth,angle)
                    self.assertAlmostEqual(sum(x*y for x,y in zip(direction,unit)),math.cos(math.radians(angle)),places=10)

    def test_invalid_effective_pose_range_or_frame_rejected(self):
        for bounds in ((-1,80),(80,30),(30,181),(30,float('nan'))):
            params=get_morphology_parameters(NEW)
            params['leaf']['insertion_angle_deg_range'].update(min=bounds[0],max=bounds[1])
            with self.assertRaisesRegex(ValueError,"insertion angle"):
                generate_morphology_tree(1,params=params)
        params=get_morphology_parameters(NEW)
        params['leaf']['insertion_frame']['value']='camera_facing'
        with self.assertRaisesRegex(ValueError,"insertion frame"):
            generate_morphology_tree(1,params=params)

    def test_effective_snapshot_stage_serialization_and_validation(self):
        for seed in range(2026102600,2026102604):
            plant=generate(seed,NEW)
            self.assertEqual(plant.to_dict(),Plant.from_dict(plant.to_dict()).to_dict())
            self.assertEqual(plant.metadata['effective_parameters_sha256'],
                             parameter_snapshot_sha256(plant.metadata['effective_parameters']))
            result=validate_morphology_tree(plant,stage='generated')
            self.assertEqual(result['errors'],[])
            self.assertTrue(all(w['category']=='morphology_proxy' for w in result['warnings']))


if __name__ == '__main__':
    unittest.main()
