from __future__ import annotations

import unittest

from uchuva_lsystem.cultivation import adapt_cultivation_morphologies
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.scene import create_cultivation_scene
from uchuva_lsystem.validation import validate_cultivation_scene


class CultivationAdaptationTests(unittest.TestCase):
    def _build(self, seed: int = 0):
        scene = create_cultivation_scene(
            seed,
            preset_name="annotation_foreground_pilot",
            plant_count=4,
        )
        plants = {
            instance.plant_id: generate_morphology_tree(
                instance.seed,
                condition=instance.condition,
            )
            for instance in scene.plant_instances
        }
        return adapt_cultivation_morphologies(scene, plants)

    def test_joint_relaxation_is_deterministic_and_serializable(self) -> None:
        first_scene, first_plants, first_report = self._build(0)
        second_scene, second_plants, second_report = self._build(0)
        self.assertEqual(first_scene.to_dict(), second_scene.to_dict())
        self.assertEqual(
            {key: value.to_dict() for key, value in first_plants.items()},
            {key: value.to_dict() for key, value in second_plants.items()},
        )
        self.assertEqual(first_report, second_report)
        self.assertGreater(first_report["adapted_axis_count"], 0)
        self.assertGreater(first_report["visual_canopy_overlap_count"], 0)
        self.assertEqual(first_report["physical_collisions"], [])

    def test_supports_and_load_deflection_are_recorded_before_blender(self) -> None:
        scene, plants, report = self._build(0)
        self.assertEqual(len(scene.supports), len(scene.plant_instances))
        self.assertTrue(all(2 <= len(item.tie_heights) <= 3 for item in scene.supports))
        self.assertTrue(all(0.08 <= item.section_width <= 0.14 for item in scene.supports))
        self.assertTrue(
            all(abs(item.section_depth - 1.25 * item.section_width) <= 0.0002 for item in scene.supports)
        )
        self.assertTrue(all(item.kind == "wooden_rectangular_stake" for item in scene.supports))
        axes = []

        def collect(axis):
            axes.append(axis)
            for child in axis.child_axes:
                collect(child)

        for plant in plants.values():
            for root in plant.axes:
                collect(root)
        loaded = [axis for axis in axes if axis.reproductive_load > 0.0]
        self.assertTrue(loaded)
        self.assertTrue(all(axis.mechanical_deflection_deg >= 0.0 for axis in loaded))
        self.assertGreater(max(axis.mechanical_deflection_deg for axis in loaded), 0.0)
        validation = validate_cultivation_scene(scene)
        self.assertEqual(validation["summary"]["physical_collision_count"], 0)
        self.assertEqual(validation["summary"]["support_count"], len(scene.supports))
        self.assertEqual(report["support_count"], len(scene.supports))
        collision_report = report["collision_resolution"]
        self.assertEqual(collision_report["iterations"], 8)
        self.assertIn("unresolved_pair_count", collision_report)
        self.assertEqual(collision_report["physical_collisions"], [])

    def test_dense_profile_has_twenty_real_plants_and_no_legacy_canopy(self) -> None:
        scene = create_cultivation_scene(
            11,
            preset_name="dense_staked_crop",
            plant_count=3,
        )
        self.assertEqual(len(scene.plant_instances), 20)
        self.assertEqual(len(scene.supports), 20)
        self.assertEqual(scene.background_canopy["mode"], "real_morphology_instances_only")
        self.assertEqual(len({item.plant_id for item in scene.plant_instances}), 20)
        rows = {-1 if item.position[1] < 0.0 else 1 for item in scene.plant_instances}
        self.assertEqual(rows, {-1, 1})
        self.assertEqual(sum(item.position[1] < 0.0 for item in scene.plant_instances), 10)
        self.assertEqual(sum(item.position[1] > 0.0 for item in scene.plant_instances), 10)

    def test_whole_plant_condition_rate_and_color_family_are_coherent(self) -> None:
        conditions = []
        for seed in range(200):
            scene = create_cultivation_scene(
                seed,
                preset_name="foreground_plant_with_neighbors",
                plant_count=5,
            )
            conditions.extend(item.condition for item in scene.plant_instances)
        drying_rate = conditions.count("drying") / len(conditions)
        self.assertGreaterEqual(drying_rate, 0.05)
        self.assertLessEqual(drying_rate, 0.10)

        for condition in ("healthy", "drying"):
            plant = generate_morphology_tree(17, condition=condition)
            values = []

            def collect_pigmentation(axis):
                values.extend(item.pigmentation for item in axis.internodes)
                for child in axis.child_axes:
                    collect_pigmentation(child)

            collect_pigmentation(plant.axes[0])
            if condition == "healthy":
                self.assertLess(max(values), 0.52)
            else:
                self.assertGreaterEqual(min(values), 0.52)


if __name__ == "__main__":
    unittest.main()
