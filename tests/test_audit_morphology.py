"""Contracts separating plant development from camera targets, without Blender."""
from copy import deepcopy
import json
import random
import unittest

from uchuva_lsystem.blender_dataset import (
    _morphology_params_for_target,
    morphology_parameters_for_capture,
)
from uchuva_lsystem.cultivation import generate_cultivation_morphologies
from uchuva_lsystem.grammar import (
    _apply_literature_cohorts,
    enforce_parent_radius_continuity,
    generate_morphology_tree,
    record_reproductive_counts,
    reproductive_counts,
)
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import (
    audit_parameter_provenance,
    normalise_parameter_provenance,
    override_parameter,
    parameter_snapshot_sha256,
    provenance_for_status,
)
from uchuva_lsystem.scene import create_cultivation_scene


def axes(plant):
    def visit(axis):
        yield axis
        for child in axis.child_axes:
            yield from visit(child)
    for root in plant.axes:
        yield from visit(root)


class AuditMorphologyTests(unittest.TestCase):
    def params(self):
        return get_morphology_parameters("trained_trellis_audit_v2")

    def test_camera_bands_cannot_change_plant_parameters_or_tree(self):
        params = [morphology_parameters_for_capture(target) for target in (
            {"object_count_band": "one_to_five", "box_area_band": "at_least_five_percent"},
            {"object_count_band": "more_than_ten", "box_area_band": "under_one_percent",
             "camera": "wide", "lighting": "dark", "materials": "candidate"},
        )]
        self.assertEqual(params[0], params[1])
        trees = [generate_morphology_tree(17, params=p, phenology_model="literature_cohort_v1")
                 for p in params]
        self.assertEqual(trees[0].to_dict(), trees[1].to_dict())

    def test_independent_route_rejects_legacy_preset(self):
        with self.assertRaisesRegex(ValueError, "architecture_driven"):
            morphology_parameters_for_capture({}, preset_name="trained_trellis")

    def test_more_than_ten_fruits_is_not_a_quota_violation(self):
        params = self.params()
        # A deliberately reproductive one-axis fixture tests semantics, not
        # the biological frequency of such a plant in the target cultivation.
        params["axis"]["main_node_count"]["value"] = 30
        params["axis"]["max_branch_order"]["value"] = 0
        params["growth"]["max_internodes_by_order"]["0"]["value"] = 30
        params["growth"]["length_budget_cm_by_order"]["0"].update(min=250, max=250)
        params["reproduction"]["reproductive_probability"]["value"] = 1.0
        plant = generate_morphology_tree(2, params=params, phenology_profile="mixed_late",
                                         phenology_model="literature_cohort_v1")
        counts = reproductive_counts(plant)
        self.assertGreater(counts["fruits"], 10)
        self.assertFalse(plant.metadata["reproductive_normalization"]["applied"])
        self.assertEqual(counts, plant.metadata["reproductive_counts_by_stage"]["generated"])

    def test_adult_preset_allows_load_above_ten_without_fixture_overrides(self):
        plant = generate_morphology_tree(6, preset_name="trained_trellis_audit_v2",
                                         phenology_model="literature_cohort_v1")
        self.assertGreater(reproductive_counts(plant)["fruits"], 10)
        original = get_morphology_parameters("trained_trellis")
        new = self.params()
        self.assertEqual(new["leaf"]["length_cm_range"]["min"], original["leaf"]["length_cm_range"]["min"])
        self.assertEqual(new["leaf"]["length_cm_range"]["max"], original["leaf"]["length_cm_range"]["max"])

    def test_zero_reproductive_sites_stay_zero_after_cohorts(self):
        params = self.params()
        params["reproduction"]["reproductive_probability"]["value"] = 0.0
        plant = generate_morphology_tree(8, params=params, phenology_model="literature_cohort_v1")
        self.assertEqual(reproductive_counts(plant)["reproductive_units"], 0)
        self.assertEqual(plant.metadata["reproductive_cohorts"]["unit_count"], 0)

    def test_one_existing_unit_stays_one_after_cohorts(self):
        params = self.params()
        plant = generate_morphology_tree(1, params=params, phenology_model="literature_cohort_v1")
        retained = False
        for axis in axes(plant):
            for node in axis.nodes:
                if node.reproductive_unit is not None:
                    if retained:
                        node.reproductive_unit = None
                    else:
                        retained = True
        before = {node.id for axis in axes(plant) for node in axis.nodes if node.reproductive_unit}
        self.assertEqual(len(before), 1)
        _apply_literature_cohorts(plant.axes[0], random.Random(0), params)
        after = {node.id for axis in axes(plant) for node in axis.nodes if node.reproductive_unit}
        self.assertEqual(before, after)

    def test_snapshot_is_canonical_and_round_trips(self):
        plant = generate_morphology_tree(7, params=self.params(), phenology_model="literature_cohort_v1")
        data = json.loads(json.dumps(plant.to_dict()))
        restored = Plant.from_dict(data)
        self.assertEqual(plant.to_dict(), restored.to_dict())
        snapshot = plant.metadata["effective_parameters"]
        self.assertEqual(parameter_snapshot_sha256(snapshot), plant.metadata["effective_parameters_sha256"])
        reordered = dict(reversed(list(snapshot.items())))
        self.assertEqual(parameter_snapshot_sha256(snapshot), parameter_snapshot_sha256(reordered))
        self.assertEqual(audit_parameter_provenance(snapshot)["status"], "valid")

    def test_counts_can_be_refreshed_after_adaptation(self):
        plant = generate_morphology_tree(0, params=self.params(), phenology_model="literature_cohort_v1")
        original = deepcopy(plant.metadata["reproductive_counts_by_stage"]["generated"])
        for axis in axes(plant):
            for node in axis.nodes:
                node.reproductive_unit = None
        record_reproductive_counts(plant, "adapted")
        self.assertEqual(plant.metadata["reproductive_counts_by_stage"]["generated"], original)
        self.assertEqual(plant.metadata["reproductive_counts_by_stage"]["adapted"]["reproductive_units"], 0)

    def test_cultivation_records_its_actual_final_stage(self):
        scene = create_cultivation_scene(3, "single_plant_study", 1)
        _, plants, _ = generate_cultivation_morphologies(
            scene, params=self.params(), model_variant="B_morphology_calibrated")
        plant = next(iter(plants.values()))
        self.assertEqual(plant.metadata["model_stage"], "adapted")
        self.assertEqual(plant.metadata["reproductive_counts_by_stage"]["adapted"], reproductive_counts(plant))

    def test_radius_order_three_uses_declared_decreasing_rule(self):
        params = self.params()
        table = params["internode"]["radius_cm_by_order"]
        for key in ("min", "max"):
            self.assertAlmostEqual(table["3"][key], table["2"][key] ** 2 / table["1"][key])
        self.assertEqual(table["3"]["status"], "engineering_heuristic")
        params["internode"]["radius_cm_by_order"].pop("3")
        with self.assertRaisesRegex(ValueError, "Missing radius"):
            generate_morphology_tree(0, params=params)

    def test_enabled_new_order_without_radius_fails_before_generation(self):
        params = self.params()
        params["axis"]["max_branch_order"]["value"] = 4
        with self.assertRaisesRegex(ValueError, "\\[4\\]"):
            generate_morphology_tree(0, params=params)

    def test_invalid_radius_bounds_fail_before_generation(self):
        for bounds in ({"min": 0, "max": 1}, {"min": 2, "max": 1},
                       {"min": .1, "max": float("nan")}):
            params = self.params()
            params["internode"]["radius_cm_by_order"]["3"].update(bounds)
            with self.assertRaisesRegex(ValueError, "Invalid radius"):
                generate_morphology_tree(0, params=params)

    def test_sampling_records_taper_before_axis_budget_truncation(self):
        plant = generate_morphology_tree(0, params=self.params())
        for axis in axes(plant):
            for index, part in enumerate(axis.internodes):
                sampling = part.provenance["radius_sampling"]
                expected = max(.52, 1 - .34 * index / max(sampling["axis_node_count_at_sampling"] - 1, 1))
                self.assertAlmostEqual(sampling["taper_factor"], expected)

    def test_continuity_compares_actual_insertion_and_records_scaling(self):
        plant = generate_morphology_tree(7, params=self.params())
        parent = next(a for a in axes(plant) if a.child_axes)
        child = parent.child_axes[0]
        limit = next(i.radius_cm for n, i in zip(parent.nodes, parent.internodes)
                     if n.id == child.parent_node_id)
        child.internodes[0].radius_cm = limit * 2
        changes = enforce_parent_radius_continuity(plant, stage="adapted")
        self.assertTrue(changes)
        self.assertLessEqual(max(i.radius_cm for i in child.internodes), limit)
        self.assertEqual(child.internodes[0].provenance["radius_continuity"]["parent_node_id"], child.parent_node_id)

    def test_override_replaces_claim_and_keeps_antecedent(self):
        record = normalise_parameter_provenance({"min": 2., "max": 5.2,
                                                "status": "literature_reported"})
        override_parameter(record, min=3.5, max=5.8, status="manual_initial_guess",
                           method="local_profile_override")
        self.assertEqual(record["provenance"]["status"], "manual_initial_guess")
        self.assertEqual(record["override_history"][0]["provenance"]["status"], "literature_reported")
        self.assertEqual(audit_parameter_provenance(record)["status"], "valid")

    def test_legacy_dataset_petiole_override_does_not_keep_literature_claim(self):
        record = _morphology_params_for_target({"object_count_band": "one_to_five"})["leaf"]["petiole_length_cm_range"]
        self.assertEqual((record["min"], record["max"]), (3.5, 5.8))
        self.assertEqual(record["provenance"]["status"], "manual_initial_guess")
        self.assertIn("literature", record["override_history"][0]["status"])

    def test_measured_local_alias_does_not_certify_evidence(self):
        record = provenance_for_status("measured_local").to_dict()
        self.assertEqual(record["status"], "real_dataset_measured")
        self.assertEqual(record["legacy_status"], "measured_local")
        self.assertTrue(record["pending_validation"])
        self.assertEqual(record["source_ids"], [])

    def test_malformed_old_provenance_is_preserved_when_normalized(self):
        old = {"value": 9, "status": "literature_reported",
               "provenance": {"source": "reference", "uncertainty": "unverified"}}
        normalized = normalise_parameter_provenance(old)
        self.assertEqual(normalized["provenance"]["legacy_provenance"], old["provenance"])
        self.assertEqual(audit_parameter_provenance(normalized)["status"], "valid")


if __name__ == "__main__":
    unittest.main()
