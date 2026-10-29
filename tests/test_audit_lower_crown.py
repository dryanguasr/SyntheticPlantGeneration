"""Adult vegetative branches and reproductive eligibility are separate gates."""
from copy import deepcopy
import unittest

from uchuva_lsystem.blender_dataset import morphology_parameters_for_capture
from uchuva_lsystem.grammar import (
    _can_branch, _can_reproduce, generate_morphology_tree, reproductive_counts,
)
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import parameter_snapshot_sha256
from uchuva_lsystem.validation import validate_morphology_tree


PRESET = "trained_trellis_lower_crown_audit_v6"
PREVIOUS = "trained_trellis_broad_crown_audit_v5"


def grow(params, seed=2026102600):
    return generate_morphology_tree(seed,params=params,phenology_model="literature_cohort_v1")


def axes(items):
    for axis in items:
        yield axis
        yield from axes(axis.child_axes)


class AlwaysAllow:
    def random(self):
        return 0.0


class IndependentVegetativeActivation(unittest.TestCase):
    def test_previous_v5_snapshot_preserved(self):
        get_morphology_parameters(PRESET)
        self.assertEqual(parameter_snapshot_sha256(get_morphology_parameters(PREVIOUS)),
                         "bf1881966dfba4373732d42e2c9fbdbcaef7dc7dd203123a38c7854b3b7b749b")

    def test_four_v5_tree_hashes_preserve_reviewed_generation_exactly(self):
        # Preserved before the v6 intervention, including all organs and metadata.
        expected={
            2026102600:"8a5d1688193d1758392c0ece7f296b74b8ab5345cd8f8593bec7c46fcb438e09",
            2026102601:"4af9c363407a75039cf5492ae0841057af82d72fb1ec81c8693941836b51bdbc",
            2026102602:"a5c8b360c2afde65c3b0b28e796e668637d39bfb8c5bfb234d3fb0b830affa2d",
            2026102603:"8bb5c6999400c0c9cb7eccd49e18293f155637873550eba2c62f3103e3e3bb30",
        }
        for seed,digest in expected.items():
            self.assertEqual(parameter_snapshot_sha256(grow(get_morphology_parameters(PREVIOUS),seed).to_dict()),digest)

    def test_only_vegetative_gate_changes_not_dimensions_probabilities_or_budgets(self):
        old,new=[get_morphology_parameters(p) for p in (PREVIOUS,PRESET)]
        for key in ("axis","growth","leaf","internode","reproduction"):
            self.assertEqual(old[key],new[key])
        for key,value in old["branching"].items():
            self.assertEqual(value,new["branching"][key])

    def test_lower_vegetative_gate_does_not_advance_reproductive_gate(self):
        params=get_morphology_parameters(PRESET)
        params["reproduction"]["first_bifurcation_node"]={"value":10}
        self.assertFalse(_can_branch(params,0,1,20,AlwaysAllow()))
        self.assertTrue(_can_branch(params,0,2,20,AlwaysAllow()))
        self.assertFalse(_can_reproduce(params,0,2,AlwaysAllow()))
        self.assertFalse(_can_reproduce(params,0,8,AlwaysAllow()))
        self.assertTrue(_can_reproduce(params,0,9,AlwaysAllow()))
        params["branching"]["activation_policy"]["value"]="legacy_reproductive_gate"
        self.assertFalse(_can_branch(params,0,2,20,AlwaysAllow()))
        self.assertTrue(_can_branch(params,0,9,20,AlwaysAllow()))

    def test_branch_probability_is_still_stochastic_and_can_produce_no_laterals(self):
        params=get_morphology_parameters(PRESET)
        for value in params["growth"]["branch_probability_by_order"].values():
            value["value"]=0
        self.assertFalse(_can_branch(params,0,2,20,AlwaysAllow()))
        self.assertEqual(len(list(axes(grow(params).axes))),1)

    def test_four_seeds_keep_independent_thresholds_and_axillary_identity(self):
        for seed in range(2026102600,2026102604):
            old,new=[grow(get_morphology_parameters(p),seed) for p in (PREVIOUS,PRESET)]
            threshold=new.metadata["phenology_snapshot"]["first_bifurcation_node"]
            self.assertEqual(threshold,old.metadata["phenology_snapshot"]["first_bifurcation_node"])
            contract=new.metadata["vegetative_branching_contract"]
            self.assertEqual(contract["first_eligible_main_node"],3)
            self.assertEqual(contract["reproductive_landmark_node"],threshold)
            self.assertIsNone(contract["branch_count_target"])
            main=new.axes[0]
            nodes={n.id:n for n in main.nodes}
            starts=[]
            for child in main.child_axes:
                node=nodes[child.parent_node_id]
                starts.append(node.position_index+1)
                self.assertGreaterEqual(node.position_index+1,3)
                self.assertEqual(node.axillary_bud.branch_id,child.id)
                self.assertIsNone(node.reproductive_unit)
                origin=child.provenance["branch_origin"]
                self.assertEqual(origin,node.axillary_bud.provenance["branch_origin"])
                self.assertEqual(origin["parent_node_number"],node.position_index+1)
            self.assertLess(min(starts),threshold)
            for node in main.nodes:
                if node.reproductive_unit:
                    self.assertGreaterEqual(node.position_index+1,threshold)

    def test_invalid_gate_and_incompatible_modes_fail_before_generation(self):
        for value in (None,True,0,1,3.5,20,100):
            params=get_morphology_parameters(PRESET)
            params["branching"]["vegetative_first_main_node"]["value"]=value
            with self.assertRaisesRegex(ValueError,"vegetative first main node"):
                grow(params)
        params=get_morphology_parameters(PRESET)
        params["branching"]["activation_policy"]["value"]="fill_lower_image"
        with self.assertRaisesRegex(ValueError,"branch activation policy"):
            grow(params)
        for category,key,value in (("reproduction","load_policy","legacy_fruiting_range"),
                                   ("growth","mode","legacy_recursive")):
            params=get_morphology_parameters(PRESET)
            params[category][key]["value"]=value
            with self.assertRaisesRegex(ValueError,"Independent vegetative activation requires"):
                grow(params)

    def test_capture_targets_and_inactive_reproductive_quota_do_not_change_tree(self):
        params=morphology_parameters_for_capture({"density":1,"area":.8},preset_name=PRESET)
        other=morphology_parameters_for_capture({"density":1000,"area":.001},preset_name=PRESET)
        self.assertEqual(params,other)
        other["reproduction"]["target_reproductive_units_range"].update(min=4,max=4)
        left,right=grow(params),grow(other)
        self.assertEqual([a.to_dict() for a in left.axes],[a.to_dict() for a in right.axes])
        self.assertGreater(reproductive_counts(left)["fruits"],10)
        self.assertFalse(left.metadata["reproductive_normalization"]["applied"])

    def test_no_implicit_reproduction_or_leaf_duplication(self):
        params=get_morphology_parameters(PRESET)
        params["reproduction"]["reproductive_probability"]["value"]=0
        plant=grow(params)
        self.assertEqual(reproductive_counts(plant)["reproductive_units"],0)
        leaves=[n.leaf for a in axes(plant.axes) for n in a.nodes]
        self.assertTrue(all(leaves))
        self.assertEqual(len(leaves),plant.node_count())
        self.assertEqual(len({leaf.id for leaf in leaves}),len(leaves))

    def test_complete_snapshot_and_origin_survive_serialization(self):
        plant=grow(get_morphology_parameters(PRESET))
        self.assertEqual(Plant.from_dict(plant.to_dict()).to_dict(),plant.to_dict())
        params=plant.metadata["effective_parameters"]
        self.assertEqual(plant.metadata["effective_parameters_sha256"],parameter_snapshot_sha256(params))
        self.assertEqual(params["branching"]["activation_policy"]["value"],"vegetative_onset_independent_v1")
        self.assertEqual(params["reproduction"]["first_bifurcation_node"]["model_application"]["status"],"engineering_heuristic")

    def test_four_seed_validation_accepts_lower_vegetative_branches_only(self):
        for seed in range(2026102600,2026102604):
            report=validate_morphology_tree(grow(get_morphology_parameters(PRESET),seed))
            self.assertFalse(report["errors"])
            self.assertFalse([w for w in report["warnings"] if w["category"]!="morphology_proxy"])

    def test_branch_origin_and_contract_cannot_override_effective_snapshot(self):
        for target in ("metadata","branch","axilla","phenology"):
            plant=grow(get_morphology_parameters(PRESET))
            child=plant.axes[0].child_axes[0]
            node=next(n for n in plant.axes[0].nodes if n.id==child.parent_node_id)
            if target=="metadata":
                plant.metadata["vegetative_branching_contract"]["first_eligible_main_node"]=1
            elif target=="branch":
                child.provenance["branch_origin"]["parent_node_number"]=1
            elif target=="axilla":
                node.axillary_bud.provenance.pop("branch_origin")
            else:
                # Tamper metadata consistently; the effective snapshot remains authoritative.
                plant.metadata["phenology_snapshot"]["first_bifurcation_node"]=3
                plant.metadata["vegetative_branching_contract"]["reproductive_landmark_node"]=3
            self.assertTrue([e for e in validate_morphology_tree(plant)["errors"]
                             if e["category"]=="parameter_contract"],target)

    def test_vegetative_branching_never_admits_early_reproductive_units(self):
        plant=grow(get_morphology_parameters(PRESET))
        donor=next(n.reproductive_unit for axis in axes(plant.axes) for n in axis.nodes if n.reproductive_unit)
        plant.axes[0].nodes[1].reproductive_unit=deepcopy(donor)
        errors=validate_morphology_tree(plant)["errors"]
        self.assertTrue(any("precedes reproductive landmark" in e["message"] for e in errors))

    def test_unrecorded_reproductive_model_cannot_certify_independent_contract(self):
        plant=grow(get_morphology_parameters(PRESET))
        plant.metadata["phenology_model"]="legacy_independent"
        errors=validate_morphology_tree(plant)["errors"]
        self.assertTrue(any("recorded literature-cohort reproductive landmark" in e["message"] for e in errors))

    def test_legacy_v5_retains_the_original_shared_gate_warning(self):
        plant=grow(get_morphology_parameters(PREVIOUS))
        child=plant.axes[0].child_axes[0]
        child.parent_node_id=plant.axes[0].nodes[2].id
        warnings=validate_morphology_tree(plant)["warnings"]
        self.assertTrue(any("before literature threshold" in w["message"] for w in warnings))


if __name__=="__main__":
    unittest.main()
