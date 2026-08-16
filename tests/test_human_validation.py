from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uchuva_lsystem.blender_review import _linear_to_srgb
from uchuva_lsystem.human_validation import (
    HumanValidationCase,
    HumanValidationSuite,
    build_validation_suite,
    evaluate_case_seed,
    evaluate_human_review,
    fixed_validation_cases,
    lock_cases_from_baseline,
    render_quality_profiles,
    select_case_seed,
    validate_protocol,
)
from uchuva_lsystem.scene import create_cultivation_scene


class HumanValidationProtocolTests(unittest.TestCase):
    def test_fixed_matrix_has_exact_diversity_and_problem_coverage(self) -> None:
        cases = fixed_validation_cases()
        report = validate_protocol(cases)
        self.assertEqual(report["status"], "valid")
        self.assertEqual(report["case_count"], 10)
        self.assertEqual(
            report["phenology_distribution"],
            {"mixed_balanced": 4, "mixed_early": 3, "mixed_late": 3},
        )
        self.assertEqual(report["problem_coverage"]["render_grain"], 3)
        self.assertEqual(report["problem_coverage"]["camera_inside_canopy"], 3)
        self.assertEqual(
            set(report["environment_distribution"]),
            {
                "canopy_close",
                "ground_tangle",
                "isolated_neutral",
                "open_field_hybrid",
            },
        )
        cases[2].locked_seed = 0
        cases[3].locked_seed = 1
        mismatch = validate_protocol(cases)
        self.assertEqual(mismatch["status"], "invalid")
        self.assertTrue(
            any("same locked seed" in item for item in mismatch["errors"])
        )

    def test_render_profiles_separate_diagnostics_from_acceptance(self) -> None:
        profiles = render_quality_profiles()
        standard = profiles["standard_eevee"]
        self.assertEqual(standard.engine, "BLENDER_EEVEE_NEXT")
        self.assertEqual(standard.samples, 128)
        self.assertEqual(standard.color_depth, "8")
        self.assertTrue(standard.acceptance_evidence)
        final = profiles["photoreal_final"]
        self.assertEqual(final.engine, "CYCLES")
        self.assertEqual(final.samples, 512)
        self.assertEqual(final.minimum_samples, 64)
        self.assertEqual(final.noise_threshold, 0.005)
        self.assertEqual(final.color_depth, "16")
        self.assertTrue(final.acceptance_evidence)
        self.assertFalse(profiles["diagnostic_eevee"].acceptance_evidence)
        self.assertAlmostEqual(_linear_to_srgb(0.18), 0.461356, places=5)

    def test_standard_render_is_default_and_cycles_remains_opt_in(self) -> None:
        suite = build_validation_suite(
            change_id="standard_render_default",
            change_categories=["render"],
            source_fingerprint="abc123",
            bootstrap=True,
        )
        self.assertEqual(suite.render_profile.name, "standard_eevee")
        scene = create_cultivation_scene(3, "single_plant_study", 1)
        self.assertEqual(scene.render.rgb_engines, ["BLENDER_EEVEE_NEXT"])
        self.assertEqual(
            scene.render.human_validation_profile,
            "standard_eevee",
        )

    def test_suite_round_trip_and_bootstrap_contract(self) -> None:
        suite = build_validation_suite(
            change_id="render_photoreal_v1",
            change_categories=["render", "materials"],
            source_fingerprint="abc123",
            bootstrap=True,
        )
        restored = HumanValidationSuite.from_dict(suite.to_dict())
        self.assertEqual(restored.to_dict(), suite.to_dict())
        self.assertEqual(len(restored.cases), 10)
        self.assertEqual(restored.status, "planned")

    def test_baseline_locks_seeds_and_rejects_condition_drift(self) -> None:
        cases = fixed_validation_cases()
        for index, case in enumerate(cases):
            case.locked_seed = case.seed_candidates[index]
        cases[3].locked_seed = cases[2].locked_seed
        payload = {
            "protocol_version": "1.0",
            "cases": [item.to_dict() for item in cases],
        }
        locked = lock_cases_from_baseline(fixed_validation_cases(), payload)
        self.assertEqual(
            [item.locked_seed for item in locked],
            [0, 1, 2, 2, 4, 5, 6, 7, 8, 9],
        )
        changed = fixed_validation_cases()
        changed[0].plant_count = 19
        with self.assertRaisesRegex(ValueError, "conditions changed"):
            lock_cases_from_baseline(changed, payload)
        changed = fixed_validation_cases()
        changed[0].problem_ids.append("render_grain")
        with self.assertRaisesRegex(ValueError, "conditions changed"):
            lock_cases_from_baseline(changed, payload)

    def test_seed_selection_is_first_eligible_and_locked_seed_is_strict(self) -> None:
        case = fixed_validation_cases()[0]

        def evaluator(
            _case: HumanValidationCase, seed: int
        ) -> tuple[bool, list[str], dict[str, int]]:
            return seed >= 2, ([] if seed >= 2 else ["too small"]), {"seed": seed}

        seed, attempts = select_case_seed(case, evaluator)
        self.assertEqual(seed, 2)
        self.assertEqual([item.seed for item in attempts], [0, 1, 2])
        case.locked_seed = 1
        with self.assertRaisesRegex(RuntimeError, "no eligible seed"):
            select_case_seed(case, evaluator)

    def test_single_plant_case_meets_pure_eligibility(self) -> None:
        case = fixed_validation_cases()[6]
        eligible, reasons, observed = evaluate_case_seed(case, 0)
        self.assertTrue(eligible, reasons)
        self.assertEqual(observed["plant_count"], 1)
        self.assertGreaterEqual(observed["leaves"], 4)

    def test_human_acceptance_requires_ten_complete_rows(self) -> None:
        rows = [
            {
                "case_id": f"case_{index:02d}",
                "decision": "pass" if index <= 8 else "minor",
            }
            for index in range(1, 11)
        ]
        accepted = evaluate_human_review(rows)
        self.assertEqual(accepted["status"], "accepted")
        rows[-1]["decision"] = "major"
        rejected = evaluate_human_review(rows)
        self.assertEqual(rejected["status"], "not_accepted")

    def test_problem_outcomes_require_majority_improvement_and_no_regression(
        self,
    ) -> None:
        rows = [
            {
                "case_id": f"case_{index:02d}",
                "decision": "pass",
                "problem_outcomes": (
                    "render_grain=improved"
                    if index <= 2
                    else "render_grain=unchanged"
                    if index == 3
                    else ""
                ),
            }
            for index in range(1, 11)
        ]
        accepted = evaluate_human_review(
            rows,
            required_problem_cases={
                "render_grain": ["case_01", "case_02", "case_03"]
            },
        )
        self.assertEqual(accepted["status"], "accepted")
        rows[2]["problem_outcomes"] = "render_grain=worse"
        rejected = evaluate_human_review(
            rows,
            required_problem_cases={
                "render_grain": ["case_01", "case_02", "case_03"]
            },
        )
        self.assertEqual(rejected["status"], "not_accepted")

    def test_only_manually_promoted_manifest_can_be_a_baseline(self) -> None:
        baseline = build_validation_suite(
            change_id="bootstrap",
            change_categories=["render"],
            source_fingerprint="baseline",
            bootstrap=True,
        )
        for index, case in enumerate(baseline.cases):
            case.locked_seed = case.seed_candidates[index]
        baseline.cases[3].locked_seed = baseline.cases[2].locked_seed
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(
                json.dumps(baseline.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "accepted_baseline"):
                build_validation_suite(
                    change_id="candidate",
                    change_categories=["render"],
                    source_fingerprint="candidate",
                    baseline_manifest=path,
                )
            baseline.status = "accepted_baseline"
            path.write_text(
                json.dumps(baseline.to_dict(), ensure_ascii=False),
                encoding="utf-8",
            )
            candidate = build_validation_suite(
                change_id="candidate",
                change_categories=["render"],
                source_fingerprint="candidate",
                baseline_manifest=path,
            )
            self.assertEqual(candidate.cases[0].locked_seed, 0)

    def test_scene_support_mode_is_additive_and_preserves_counts(self) -> None:
        scene = create_cultivation_scene(
            4,
            "row_canopy",
            12,
            support_mode="continuous_trellis",
        )
        self.assertEqual(len(scene.plant_instances), 12)
        self.assertIsNotNone(scene.support_system)
        self.assertFalse(scene.supports)
        without = create_cultivation_scene(
            4,
            "row_canopy",
            12,
            support_mode="none",
        )
        self.assertIsNone(without.support_system)
        self.assertFalse(without.supports)


if __name__ == "__main__":
    unittest.main()
