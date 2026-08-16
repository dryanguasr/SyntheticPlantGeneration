from __future__ import annotations

import unittest

from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.validation import validate_morphology_tree


STAGE_INDEX = {
    "flower": 0,
    "young_fruit_with_calyx": 1,
    "mature_fruit_with_calyx": 2,
    "exposed_fruit": 3,
}


def _units(plant: Plant):
    result = []

    def visit(axis) -> None:
        result.extend(
            node.reproductive_unit
            for node in axis.nodes
            if node.reproductive_unit is not None
        )
        for child in axis.child_axes:
            visit(child)

    for axis in plant.axes:
        visit(axis)
    return result


class LiteratureCohortPhenologyTests(unittest.TestCase):
    def test_new_model_is_deterministic_and_round_trips(self) -> None:
        first = generate_morphology_tree(77, phenology_model="literature_cohort_v1")
        second = generate_morphology_tree(77, phenology_model="literature_cohort_v1")
        self.assertEqual(first.to_dict(), second.to_dict())
        restored = Plant.from_dict(first.to_dict())
        self.assertEqual(first.to_dict(), restored.to_dict())
        self.assertEqual(first.schema_version, "1.2")

    def test_old_payload_remains_readable(self) -> None:
        payload = generate_morphology_tree(
            18, phenology_model="legacy_independent"
        ).to_dict()
        payload["schema_version"] = "1.1"
        for unit in _units(Plant.from_dict(payload)):
            self.assertEqual(unit.phenology_model, "legacy_independent")

    def test_topological_cohorts_have_no_major_inversion(self) -> None:
        plant = generate_morphology_tree(23, phenology_model="literature_cohort_v1")
        ordered = sorted(
            _units(plant),
            key=lambda unit: (-float(unit.ontogenetic_rank or 0.0), unit.id),
        )
        for older, younger in zip(ordered, ordered[1:]):
            self.assertFalse(
                STAGE_INDEX[older.stage] + 1 < STAGE_INDEX[younger.stage]
            )
        report = validate_morphology_tree(plant)
        self.assertEqual(report["summary"]["phenology"]["severe_inversion_count"], 0)

    def test_joint_maturity_traits_are_monotonic(self) -> None:
        plant = generate_morphology_tree(
            31,
            phenology_profile="mixed_late",
            phenology_model="literature_cohort_v1",
        )
        fruiting = sorted(
            (unit for unit in _units(plant) if unit.calyx is not None),
            key=lambda unit: float(unit.estimated_days_after_anthesis or 0.0),
        )
        self.assertGreaterEqual(len(fruiting), 4)
        areas = [unit.calyx.projected_area_scale for unit in fruiting]
        circularities = [unit.calyx.circularity_target for unit in fruiting]
        turgors = [unit.calyx.turgor for unit in fruiting]
        self.assertEqual(areas, sorted(areas, reverse=True))
        self.assertEqual(circularities, sorted(circularities, reverse=True))
        self.assertEqual(turgors, sorted(turgors, reverse=True))
        for unit in fruiting:
            if unit.calyx.state == "transitioning_yellow":
                self.assertTrue(unit.calyx.texture_variant.startswith("calyx_transition_"))

    def test_first_bifurcation_respects_literature_bound(self) -> None:
        plant = generate_morphology_tree(91, phenology_model="literature_cohort_v1")
        threshold = plant.metadata["phenology_snapshot"]["first_bifurcation_node"]
        self.assertGreaterEqual(threshold, 8)
        self.assertLessEqual(threshold, 12)
        for main_axis in plant.axes:
            positions = {node.id: node.position_index + 1 for node in main_axis.nodes}
            for child in main_axis.child_axes:
                self.assertGreaterEqual(positions[child.parent_node_id], threshold)


if __name__ == "__main__":
    unittest.main()
