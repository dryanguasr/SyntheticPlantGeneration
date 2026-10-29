"""Independent adult development, with no camera or reproductive quotas."""
from copy import deepcopy
import unittest

from uchuva_lsystem.blender_dataset import morphology_parameters_for_capture
from uchuva_lsystem.grammar import generate_morphology_tree, reproductive_counts
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import audit_parameter_provenance, parameter_snapshot_sha256
from uchuva_lsystem.validation import validate_morphology_tree


PRESET = "trained_trellis_bush_audit_v3"
SEEDS = tuple(range(2026102600, 2026102604))


def axes(items):
    for axis in items:
        yield axis
        yield from axes(axis.child_axes)


def grow(seed, preset=PRESET, params=None):
    return generate_morphology_tree(seed, params=params, preset_name=preset if params is None else None,
                                    phenology_model="literature_cohort_v1")


class AdultBushContracts(unittest.TestCase):
    def test_previous_preset_is_unchanged(self):
        before = get_morphology_parameters("trained_trellis_audit_v2")
        get_morphology_parameters(PRESET)
        self.assertEqual(before, get_morphology_parameters("trained_trellis_audit_v2"))
        self.assertEqual(parameter_snapshot_sha256(before),
                         "b2059054441fdab904ea2679aa25267c20f0f9cd61c2eeb6b9effc28b5738922")

    def test_individual_organs_probabilities_and_radius_policy_not_enlarged(self):
        before, after = [get_morphology_parameters(p) for p in ("trained_trellis_audit_v2", PRESET)]
        for key in ("leaf", "internode", "reproduction", "fruit", "calyx", "branching", "phyllotaxis"):
            if key in before:
                self.assertEqual(before[key], after[key], key)
        for key in ("vigor_decay_by_order", "apical_dominance", "branch_probability_by_order",
                    "internode_length_scale_by_order", "leaf_length_scale_by_order"):
            self.assertEqual(before["growth"][key], after["growth"][key], key)

    def test_development_overrides_are_traceable_hypotheses(self):
        params = get_morphology_parameters(PRESET)
        records = [params["axis"]["main_node_count"], params["axis"]["branch_node_count_range"]]
        records += list(params["growth"]["length_budget_cm_by_order"].values())
        records += list(params["growth"]["max_internodes_by_order"].values())
        for record in records:
            self.assertEqual(record["status"], "engineering_heuristic")
            self.assertEqual(record["provenance"]["status"], "engineering_heuristic")
            self.assertTrue(record["override_history"])
            self.assertIn("human_rejection", record["provenance"]["method"])
        self.assertEqual(audit_parameter_provenance(params)["status"], "valid")

    def test_framing_targets_cannot_change_the_tree(self):
        close = morphology_parameters_for_capture({"object_count_band":"one_to_five", "size":"large"},preset_name=PRESET)
        wide = morphology_parameters_for_capture({"object_count_band":"many", "size":"tiny"},preset_name=PRESET)
        self.assertEqual(close,wide)
        self.assertEqual(grow(SEEDS[0],params=close).to_dict(),grow(SEEDS[0],params=wide).to_dict())

    def test_inactive_historical_quota_does_not_add_or_remove_organs(self):
        params = get_morphology_parameters(PRESET)
        changed = deepcopy(params)
        changed["reproduction"]["target_reproductive_units_range"].update(min=999,max=999)
        left, right = grow(SEEDS[0],params=params), grow(SEEDS[0],params=changed)
        self.assertEqual([a.to_dict() for a in left.axes], [a.to_dict() for a in right.axes])
        self.assertFalse(right.metadata["reproductive_normalization"]["applied"])

    def test_no_implicit_flower_creation_without_reproductive_sites(self):
        params = get_morphology_parameters(PRESET)
        params["reproduction"]["reproductive_probability"]["value"] = 0
        plant = grow(SEEDS[0],params=params)
        self.assertEqual(reproductive_counts(plant), dict(reproductive_units=0,flowers=0,fruits=0,fruits_with_calyx=0))

    def test_same_review_seeds_have_richer_nodal_architecture_without_fixed_load(self):
        fruit_counts = []
        for seed in SEEDS:
            old, new = grow(seed,"trained_trellis_audit_v2"), grow(seed)
            old_axes, new_axes = list(axes(old.axes)), list(axes(new.axes))
            self.assertGreater(len(new_axes),len(old_axes))
            self.assertGreater(sum(len(a.nodes) for a in new_axes),sum(len(a.nodes) for a in old_axes))
            self.assertEqual(old.metadata["phenology_snapshot"]["first_bifurcation_node"],
                             new.metadata["phenology_snapshot"]["first_bifurcation_node"])
            fruit_counts.append(reproductive_counts(new)["fruits"])
        self.assertEqual(len(set(fruit_counts)),len(SEEDS))
        self.assertTrue(any(count>10 for count in fruit_counts))

    def test_integrity_snapshot_stage_counts_and_serialization(self):
        for seed in SEEDS:
            plant = grow(seed)
            restored = Plant.from_dict(plant.to_dict())
            self.assertEqual(restored.to_dict(),plant.to_dict())
            self.assertEqual(plant.metadata["model_stage"],"generated")
            self.assertEqual(plant.metadata["reproductive_counts_by_stage"]["generated"],reproductive_counts(plant))
            self.assertEqual(plant.metadata["effective_parameters_sha256"],
                             parameter_snapshot_sha256(plant.metadata["effective_parameters"]))
            validation = validate_morphology_tree(plant,stage="generated")
            self.assertEqual(validation["errors"],[])
            self.assertTrue(all(w["category"]=="morphology_proxy" for w in validation["warnings"]))

    def test_laterals_remain_axillary_with_parent_radius_continuity(self):
        for seed in SEEDS:
            plant = grow(seed)
            for parent in axes(plant.axes):
                limits = {node.id:part.radius_cm for node,part in zip(parent.nodes,parent.internodes)}
                for child in parent.child_axes:
                    self.assertIn(child.parent_node_id,limits)
                    self.assertEqual(child.order,parent.order+1)
                    self.assertLessEqual(max(part.radius_cm for part in child.internodes),limits[child.parent_node_id]+1e-9)


if __name__ == "__main__":
    unittest.main()
