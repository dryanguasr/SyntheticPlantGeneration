from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from uchuva_lsystem.hybrid_training import (
    TrainingConfig,
    build_training_summary,
    extract_detection_metrics,
)


class HybridTrainingTests(unittest.TestCase):
    def test_extracts_detection_metrics(self) -> None:
        metrics = SimpleNamespace(
            box=SimpleNamespace(map=0.41, map50=0.73, map75=0.39, mp=0.68, mr=0.62)
        )
        self.assertEqual(
            extract_detection_metrics(metrics),
            {
                "map50_95": 0.41,
                "map50": 0.73,
                "map75": 0.39,
                "precision": 0.68,
                "recall": 0.62,
            },
        )

    def test_summary_ranks_candidates_against_natural_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = [
                {"experiment": "natural_full", "test_metrics": {"map50_95": 0.40}},
                {"experiment": "hybrid_50", "test_metrics": {"map50_95": 0.43}},
                {"experiment": "hybrid_75", "test_metrics": {"map50_95": 0.38}},
            ]
            summary = build_training_summary(
                matrix_root=root / "matrix",
                output_root=root / "runs",
                config=TrainingConfig(),
                results=results,
            )
            self.assertTrue(summary["target_achieved"])
            self.assertEqual(summary["ranking"][0]["experiment"], "hybrid_50")
            self.assertAlmostEqual(summary["ranking"][0]["delta_vs_natural"], 0.03)


if __name__ == "__main__":
    unittest.main()
