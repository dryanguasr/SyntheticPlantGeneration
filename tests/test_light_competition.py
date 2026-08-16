from __future__ import annotations

import unittest

from uchuva_lsystem.blender_environment import (
    _ground_vegetation_plan,
    _terrain_surface_profile,
)
from uchuva_lsystem.collisions import _leaf_direction_with_clearance_lift
from uchuva_lsystem.cultivation import generate_cultivation_morphologies
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.light_competition import StratifiedLightField
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.scene import create_cultivation_scene
from uchuva_lsystem.validation import validate_morphology_tree


class StratifiedLightCompetitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.params = get_morphology_parameters("trained_trellis")
        self.light_options = self.params["light_competition"]

    def test_field_distinguishes_open_self_and_neighbour_claims(self) -> None:
        field = StratifiedLightField.from_parameters(self.light_options)
        candidate = {
            "start": (0.0, 0.0, 1.15),
            "end": (0.62, 0.18, 1.28),
            "width": 0.34,
        }
        open_evaluation = field.evaluate_leaf(
            plant_id="plant_01",
            **candidate,
        )
        self.assertEqual(open_evaluation.stratum, "middle")
        self.assertGreater(open_evaluation.new_coverage_fraction, 0.0)
        field.register_leaf(
            plant_id="plant_01",
            leaf_id="leaf_01",
            evaluation=open_evaluation,
        )

        self_overlap = field.evaluate_leaf(
            plant_id="plant_01",
            **candidate,
        )
        neighbour_overlap = field.evaluate_leaf(
            plant_id="plant_02",
            **candidate,
        )
        self.assertGreater(self_overlap.same_plant_overlap_fraction, 0.0)
        self.assertGreater(neighbour_overlap.other_plant_overlap_fraction, 0.0)
        self.assertLess(
            neighbour_overlap.daily_light_interception_proxy,
            open_evaluation.daily_light_interception_proxy,
        )

    def test_growth_records_strata_training_and_light_proxies(self) -> None:
        scene = create_cultivation_scene(
            4,
            "dense_trellis_synchronous",
            plant_count=20,
        )
        scene.plant_instances = scene.plant_instances[:2]
        plant_ids = {item.plant_id for item in scene.plant_instances}
        assert scene.support_system is not None
        scene.support_system.ties = [
            item
            for item in scene.support_system.ties
            if item.plant_id in plant_ids
        ]
        potentials = {
            instance.plant_id: generate_morphology_tree(
                instance.seed,
                params=self.params,
                condition=instance.condition,
            )
            for instance in scene.plant_instances
        }
        _scene, plants, report = generate_cultivation_morphologies(
            scene,
            self.params,
            potential_plants=potentials,
        )

        self.assertTrue(report["light_competition_enabled"])
        field_report = report["stratified_light_field"]
        self.assertEqual(
            field_report["registered_leaf_count"],
            report["leaf_posture_decision_count"],
        )
        self.assertTrue(
            all(
                "trellis_training" in item["cost_terms"]
                for item in report["decisions"]
            )
        )
        self.assertTrue(
            {
                item["training_phase"]
                for item in report["decisions"]
            }
            <= {"stratum_expansion", "apical_lift_to_trellis"}
        )

        assigned = []
        for plant in plants.values():
            for axis in _walk_axes(plant.axes):
                assigned.extend(
                    node.leaf
                    for node in axis.nodes
                    if node.leaf is not None
                )
            self.assertEqual(
                Plant.from_dict(plant.to_dict()).to_dict(),
                plant.to_dict(),
            )
            validation = validate_morphology_tree(plant)
            self.assertEqual(
                validation["checks"]["stratified_light_response"],
                "validated_additive_proxy_fields",
            )
        self.assertTrue(assigned)
        self.assertTrue(
            all(leaf.canopy_stratum in {"lower", "middle", "upper"} for leaf in assigned)
        )
        self.assertTrue(
            all(leaf.daily_light_interception_proxy is not None for leaf in assigned)
        )

    def test_guided_growth_retains_a_dense_branching_canopy(self) -> None:
        """Training guidance must not collapse a dense plant to its main axis."""
        params = get_morphology_parameters("trained_trellis")
        params["axis"]["main_node_count"]["value"] = 10
        params["axis"]["branch_node_count_range"]["value"] = [4, 6]
        params["internode"]["length_cm_range"]["value"] = [1.3, 2.7]
        params["branching"]["branch_probability"]["value"] = 0.40
        scene = create_cultivation_scene(
            18,
            "dense_trellis_synchronous",
            plant_count=20,
        )
        scene.plant_instances = scene.plant_instances[:1]
        plant_id = scene.plant_instances[0].plant_id
        assert scene.support_system is not None
        scene.support_system.ties = [
            item
            for item in scene.support_system.ties
            if item.plant_id == plant_id
        ]
        potential = generate_morphology_tree(
            scene.plant_instances[0].seed,
            params=params,
        )
        potential_axes = list(_walk_axes(potential.axes))
        _scene, plants, _report = generate_cultivation_morphologies(
            scene,
            params,
            potential_plants={plant_id: potential},
        )
        active_axes = list(_walk_axes(plants[plant_id].axes))
        active_leaves = sum(
            node.leaf is not None
            for axis in active_axes
            for node in axis.nodes
        )
        potential_leaves = sum(
            node.leaf is not None
            for axis in potential_axes
            for node in axis.nodes
        )

        self.assertGreaterEqual(len(active_axes), 5)
        self.assertGreaterEqual(active_leaves, round(potential_leaves * 0.60))

    def test_ground_plan_adds_tall_grass_kikuyu_and_weeds(self) -> None:
        plan = _ground_vegetation_plan("open_field_hybrid")
        names = {item["name"] for item in plan}
        self.assertEqual(
            names,
            {
                "lolium_perenne_like",
                "kikuyu_like",
                "broadleaf_weeds_like",
            },
        )
        self.assertGreater(sum(item["count"] for item in plan), 400)
        lolium = next(item for item in plan if item["name"] == "lolium_perenne_like")
        kikuyu = next(item for item in plan if item["name"] == "kikuyu_like")
        self.assertEqual(lolium["width_range"], (0.002, 0.006))
        self.assertEqual(kikuyu["width_range"], (0.001, 0.005))
        self.assertLessEqual(kikuyu["height_range"][1], 0.16)
        ground_tangle = _ground_vegetation_plan("ground_tangle")
        self.assertGreater(
            sum(item["count"] for item in ground_tangle),
            sum(item["count"] for item in plan),
        )
        canopy_close = _ground_vegetation_plan("canopy_close")
        self.assertGreater(sum(item["count"] for item in canopy_close), 600)
        self.assertEqual(
            _terrain_surface_profile("canopy_close"),
            "green_pasture_understory",
        )
        self.assertEqual(
            _terrain_surface_profile("isolated_neutral"),
            "neutral_soil_reference",
        )

    def test_leaf_calyx_micro_lift_raises_a_connected_petiole_direction(self) -> None:
        original = _leaf_direction_with_clearance_lift(
            (1.0, 0.0, 0.0),
            petiole_length=0.24,
            lift=0.0,
        )
        lifted = _leaf_direction_with_clearance_lift(
            (1.0, 0.0, 0.0),
            petiole_length=0.24,
            lift=0.024,
        )
        self.assertAlmostEqual(sum(value * value for value in lifted), 1.0)
        self.assertEqual(original[2], 0.0)
        self.assertGreater(lifted[2], original[2])

    def test_leaf_clearance_lift_is_serialized_in_the_morphology_tree(self) -> None:
        plant = generate_morphology_tree(91, params=self.params)
        leaf = next(
            node.leaf
            for axis in _walk_axes(plant.axes)
            for node in axis.nodes
            if node.leaf is not None
        )
        leaf.clearance_lift_cm = 0.3
        leaf.clearance_lift_reason = "leaf_calyx_soft_clearance"
        restored = Plant.from_dict(plant.to_dict())
        restored_leaf = next(
            node.leaf
            for axis in _walk_axes(restored.axes)
            for node in axis.nodes
            if node.leaf is not None
        )
        self.assertEqual(restored_leaf.clearance_lift_cm, 0.3)
        self.assertEqual(
            restored_leaf.clearance_lift_reason,
            "leaf_calyx_soft_clearance",
        )


def _walk_axes(axes):
    for axis in axes:
        yield axis
        yield from _walk_axes(axis.child_axes)


if __name__ == "__main__":
    unittest.main()
