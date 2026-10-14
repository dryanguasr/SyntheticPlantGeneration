from __future__ import annotations

import json
import unittest
from copy import deepcopy

from uchuva_lsystem.blender_geometry import _mesh_intersection_classification
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.growth import (
    GrowthProposal,
    ProposalDecision,
    coordinate_synchronous_growth,
)
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.provenance import audit_parameter_provenance
from uchuva_lsystem.scene import CultivationScene, create_cultivation_scene
from uchuva_lsystem.spatial import (
    ContactPolicy,
    SpatialItem,
    SpatialOccupancy,
)


class SynchronousGrowthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = get_morphology_parameters("trained_trellis")

    def test_budgeted_tree_is_connected_deterministic_and_provenanced(self) -> None:
        first = generate_morphology_tree(7, params=self.params)
        second = generate_morphology_tree(7, params=self.params)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(
            first.metadata["parameter_provenance_audit"]["status"],
            "valid",
        )
        self.assertEqual(audit_parameter_provenance(self.params)["status"], "valid")
        for axis in _walk_axes(first.axes):
            self.assertLessEqual(
                sum(item.length_cm for item in axis.internodes),
                axis.growth_budget_length_cm + 0.01,
            )
            for child in axis.child_axes:
                self.assertEqual(child.order, axis.order + 1)
                self.assertIn(
                    child.parent_node_id,
                    {node.id for node in axis.nodes},
                )

    def test_legacy_seed_one_baseline_contract_is_preserved(self) -> None:
        from uchuva_lsystem.metrics import compute_morphology_metrics
        from uchuva_lsystem.parameters import get_initial_parameters

        scene = create_cultivation_scene(1, "dense_staked_crop", 20)
        params = get_initial_parameters()
        plants = {
            instance.plant_id: generate_morphology_tree(
                instance.seed,
                params=params,
                condition=instance.condition,
            )
            for instance in scene.plant_instances
        }
        metrics = compute_morphology_metrics(plants)
        self.assertEqual(metrics["axes_by_order"], {"0": 20, "1": 50, "2": 35})
        self.assertEqual(metrics["organ_counts"]["leaves"], 528)
        self.assertEqual(metrics["organ_counts"]["reproductive_units"], 168)

    def test_json_round_trip_preserves_additive_schema(self) -> None:
        plant = generate_morphology_tree(3, params=self.params)
        self.assertEqual(Plant.from_dict(plant.to_dict()).to_dict(), plant.to_dict())
        scene = _small_trellis_scene(3)
        self.assertEqual(
            CultivationScene.from_dict(scene.to_dict()).to_dict(),
            scene.to_dict(),
        )

    def test_contact_policy_separates_hard_visual_and_intentional(self) -> None:
        policy = ContactPolicy.default()
        occupancy = SpatialOccupancy(policy)
        occupancy.add(
            SpatialItem(
                id="stem_a",
                plant_id="plant_a",
                organ_type="stem",
                start=(0.0, 0.0, 0.0),
                end=(0.0, 0.0, 1.0),
                radius=0.02,
            )
        )
        hard = occupancy.query(
            SpatialItem(
                id="stem_b",
                plant_id="plant_b",
                organ_type="stem",
                start=(0.03, 0.0, 0.2),
                end=(0.03, 0.0, 0.8),
                radius=0.02,
            )
        )
        self.assertEqual(hard[0].classification, "proxy_conflict")
        self.assertEqual(hard[0].policy, "hard_occupancy")

        leaf_occupancy = SpatialOccupancy(policy)
        leaf_occupancy.add(
            SpatialItem(
                id="leaf_a",
                plant_id="plant_a",
                organ_type="leaf",
                start=(0.0, 0.0, 0.5),
                end=(0.5, 0.0, 0.5),
                radius=0.03,
            )
        )
        visual = leaf_occupancy.query(
            SpatialItem(
                id="leaf_b",
                plant_id="plant_b",
                organ_type="leaf",
                start=(0.0, 0.01, 0.5),
                end=(0.5, 0.01, 0.5),
                radius=0.03,
            )
        )
        self.assertEqual(visual[0].classification, "visual_occlusion")

        line_occupancy = SpatialOccupancy(policy)
        line_occupancy.add(
            SpatialItem(
                id="line",
                plant_id="support",
                organ_type="support_line",
                start=(-1.0, 0.0, 1.0),
                end=(1.0, 0.0, 1.0),
                radius=0.01,
                intentional_contact=True,
            )
        )
        contact = line_occupancy.query(
            SpatialItem(
                id="trained_stem",
                plant_id="plant_a",
                organ_type="stem",
                start=(0.0, 0.0, 0.8),
                end=(0.0, 0.0, 1.2),
                radius=0.01,
            )
        )
        self.assertEqual(contact[0].classification, "intentional_contact")

    def test_mesh_overlap_taxonomy_separates_contact_types(self) -> None:
        support_post = {
            "uchuva_plant_role": "support",
            "uchuva_plant_id": "support",
            "uchuva_organ_id": "row_post_0",
            "uchuva_semantic_class": "background",
        }
        support_line = {
            "uchuva_plant_role": "support",
            "uchuva_plant_id": "support",
            "uchuva_organ_id": "row_line_0",
            "uchuva_semantic_class": "background",
        }
        leaf = {
            "uchuva_plant_role": "foreground",
            "uchuva_plant_id": "plant_01",
            "uchuva_organ_id": "leaf_0",
            "uchuva_semantic_class": "leaf",
        }
        stem = {
            "uchuva_plant_role": "foreground",
            "uchuva_plant_id": "plant_01",
            "uchuva_organ_id": "axis_0",
            "uchuva_semantic_class": "stem",
        }
        foreign_stem = {
            **stem,
            "uchuva_plant_id": "plant_02",
            "uchuva_organ_id": "axis_1",
        }
        self.assertEqual(
            _mesh_intersection_classification(support_post, support_line),
            "intentional_support",
        )
        self.assertEqual(
            _mesh_intersection_classification(support_post, leaf),
            "soft_occupancy",
        )
        self.assertEqual(
            _mesh_intersection_classification(leaf, dict(leaf)),
            # Mesh overlap alone does not measure camera-dependent occlusion.
            "soft_occupancy",
        )
        self.assertEqual(
            _mesh_intersection_classification(stem, foreign_stem),
            "physical_collision",
        )

    def test_input_order_does_not_change_topology_or_decisions(self) -> None:
        scene = _small_trellis_scene(5)
        plants = _potential_plants(scene, self.params)
        forward_plants, forward_report = coordinate_synchronous_growth(
            scene,
            plants,
        )
        reversed_scene = deepcopy(scene)
        reversed_scene.plant_instances.reverse()
        reversed_plants = dict(reversed(list(plants.items())))
        reverse_output, reverse_report = coordinate_synchronous_growth(
            reversed_scene,
            reversed_plants,
        )
        self.assertEqual(
            json.dumps(
                {key: value.to_dict() for key, value in forward_plants.items()},
                sort_keys=True,
            ),
            json.dumps(
                {key: value.to_dict() for key, value in reverse_output.items()},
                sort_keys=True,
            ),
        )
        self.assertEqual(
            forward_report["decisions"],
            reverse_report["decisions"],
        )

    def test_support_ablation_changes_morphological_decisions(self) -> None:
        scene = _small_trellis_scene(1)
        plants = _potential_plants(scene, self.params)
        _, with_support = coordinate_synchronous_growth(
            scene,
            plants,
            support_enabled=True,
        )
        _, without_support = coordinate_synchronous_growth(
            scene,
            plants,
            support_enabled=False,
        )
        with_decisions = [
            (
                item["plant_id"],
                item["axis_id"],
                item["status"],
                item["angular_deviation_deg"],
            )
            for item in with_support["decisions"]
        ]
        without_decisions = [
            (
                item["plant_id"],
                item["axis_id"],
                item["status"],
                item["angular_deviation_deg"],
            )
            for item in without_support["decisions"]
        ]
        self.assertNotEqual(with_decisions, without_decisions)

    def test_proposal_contracts_round_trip(self) -> None:
        proposal = GrowthProposal(
            plant_id="plant_01",
            bud_id="bud",
            axis_id="axis",
            parent_axis_id="root",
            parent_node_id="node",
            order=1,
            origin=(0.0, 0.0, 1.0),
            parent_direction=(0.0, 0.0, 1.0),
            desired_direction=(1.0, 0.0, 0.2),
            desired_length=0.8,
            radius=0.01,
            vigor=0.9,
            age=3,
            target_region="mid_canopy",
        )
        self.assertEqual(
            GrowthProposal.from_dict(proposal.to_dict()).to_dict(),
            proposal.to_dict(),
        )
        decision = ProposalDecision(
            proposal_id="plant_01:axis",
            plant_id="plant_01",
            axis_id="axis",
            status="deviated",
            applied_direction=(0.9, 0.1, 0.2),
            applied_length=0.8,
            angular_deviation_deg=6.0,
            shortening_fraction=1.0,
            cost_terms={"support": 0.2},
            cause="support",
        )
        self.assertEqual(
            ProposalDecision.from_dict(decision.to_dict()).to_dict(),
            decision.to_dict(),
        )


def _small_trellis_scene(seed: int) -> CultivationScene:
    scene = create_cultivation_scene(
        seed,
        "dense_trellis_synchronous",
        plant_count=20,
    )
    scene.plant_instances = scene.plant_instances[:4]
    plant_ids = {item.plant_id for item in scene.plant_instances}
    assert scene.support_system is not None
    scene.support_system.ties = [
        item for item in scene.support_system.ties if item.plant_id in plant_ids
    ]
    return scene


def _potential_plants(
    scene: CultivationScene,
    params: dict,
) -> dict[str, Plant]:
    return {
        instance.plant_id: generate_morphology_tree(
            instance.seed,
            params=params,
            condition=instance.condition,
        )
        for instance in scene.plant_instances
    }


def _walk_axes(axes):
    for axis in axes:
        yield axis
        yield from _walk_axes(axis.child_axes)


if __name__ == "__main__":
    unittest.main()
