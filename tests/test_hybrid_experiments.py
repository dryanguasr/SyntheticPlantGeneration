from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uchuva_lsystem.hybrid_experiments import (
    HybridExperimentSpec,
    build_hybrid_experiment_matrix,
)


class HybridExperimentTests(unittest.TestCase):
    def test_fixed_synthetic_variable_real_cohorts_are_nested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split, count in (("train", 8), ("val", 2), ("test", 2)):
                _write_pairs(real / "IMAGENES" / split, real / "LABELS" / split, count)
            _write_pairs(synthetic / "images" / "train", synthetic / "labels" / "train", 4)
            matrix = build_hybrid_experiment_matrix(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "matrix",
                seed=17,
                experiment_specs=(
                    HybridExperimentSpec(
                        "real_2_synthetic_4",
                        "fixed_synthetic_variable_real",
                        1.0,
                        synthetic_count=4,
                        selection_group="phase_b",
                        real_count=2,
                    ),
                    HybridExperimentSpec(
                        "real_4_synthetic_4",
                        "fixed_synthetic_variable_real",
                        1.0,
                        synthetic_count=4,
                        selection_group="phase_b",
                        real_count=4,
                    ),
                ),
            )
            selected: dict[str, dict[str, list[str]]] = {}
            for experiment in matrix["experiments"]:
                manifest = json.loads(
                    (Path(experiment["dataset_root"]) / "manifest.json").read_text(
                        encoding="utf-8"
                    )
                )
                selected[experiment["spec"]["name"]] = {
                    domain: [
                        item["source_sample_id"]
                        for item in manifest["records"]
                        if item["destination_split"] == "train"
                        and item["source_domain"] == domain
                    ]
                    for domain in ("real", "synthetic")
                }
            low = selected["real_2_synthetic_4"]
            high = selected["real_4_synthetic_4"]
            self.assertEqual(low["real"], high["real"][:2])
            self.assertEqual(low["synthetic"], high["synthetic"])
            self.assertEqual(len(high["synthetic"]), 4)

    def test_capped_additive_doses_are_nested(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split, count in (("train", 6), ("val", 1), ("test", 1)):
                _write_pairs(real / "IMAGENES" / split, real / "LABELS" / split, count)
            _write_pairs(synthetic / "images" / "train", synthetic / "labels" / "train", 5)
            matrix = build_hybrid_experiment_matrix(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "matrix",
                seed=13,
                experiment_specs=(
                    HybridExperimentSpec("dose_2", "additive_capped", 1.0, 2, "dose"),
                    HybridExperimentSpec("dose_4", "additive_capped", 1.0, 4, "dose"),
                ),
            )
            selected = {}
            for experiment in matrix["experiments"]:
                manifest = json.loads(
                    (Path(experiment["dataset_root"]) / "manifest.json").read_text(encoding="utf-8")
                )
                selected[experiment["spec"]["name"]] = [
                    item["source_sample_id"]
                    for item in manifest["records"]
                    if item["destination_split"] == "train"
                    and item["source_domain"] == "synthetic"
                ]
            self.assertEqual(selected["dose_2"], selected["dose_4"][:2])

    def test_matrix_keeps_validation_and_test_real_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split, count in (("train", 4), ("val", 2), ("test", 2)):
                _write_pairs(real / "IMAGENES" / split, real / "LABELS" / split, count)
            _write_pairs(synthetic / "images" / "train", synthetic / "labels" / "train", 2)
            original_real_files = sorted(path.relative_to(real) for path in real.rglob("*"))
            specs = (
                HybridExperimentSpec("natural", "natural_full", 1.0),
                HybridExperimentSpec("half", "fixed_budget", 0.5),
            )
            matrix = build_hybrid_experiment_matrix(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "matrix",
                seed=9,
                experiment_specs=specs,
            )

            half = next(item for item in matrix["experiments"] if item["spec"]["name"] == "half")
            self.assertEqual(half["counts"]["train_real"], 2)
            self.assertEqual(half["counts"]["train_synthetic"], 2)
            manifest = json.loads(
                (Path(half["dataset_root"]) / "manifest.json").read_text(encoding="utf-8")
            )
            held_out = [
                item for item in manifest["records"]
                if item["destination_split"] in {"val", "test"}
            ]
            self.assertTrue(held_out)
            self.assertTrue(all(item["source_domain"] == "real" for item in held_out))
            self.assertEqual(
                original_real_files,
                sorted(path.relative_to(real) for path in real.rglob("*")),
            )

    def test_repetition_is_deterministic_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split, count in (("train", 6), ("val", 1), ("test", 1)):
                _write_pairs(real / "IMAGENES" / split, real / "LABELS" / split, count)
            _write_pairs(synthetic / "images" / "train", synthetic / "labels" / "train", 1)
            spec = (HybridExperimentSpec("quarter", "fixed_budget", 0.25),)
            first = build_hybrid_experiment_matrix(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "first",
                seed=11,
                experiment_specs=spec,
            )
            second = build_hybrid_experiment_matrix(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "second",
                seed=11,
                experiment_specs=spec,
            )
            self.assertEqual(
                first["experiments"][0]["counts"],
                second["experiments"][0]["counts"],
            )
            self.assertGreater(first["experiments"][0]["synthetic_repeat_count"], 0)


def _write_pairs(images: Path, labels: Path, count: int) -> None:
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (images / f"{index:04d}.jpg").write_bytes(b"fixture")
        (labels / f"{index:04d}.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
