from __future__ import annotations

import unittest
from pathlib import Path


class RepositoryLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]

    def test_root_contains_only_current_navigation_entries(self) -> None:
        root_names = {item.name for item in self.repo_root.iterdir()}
        obsolete_root_entries = (
            "Assets",
            "generated_specs",
            "codex_migration_prompt.md",
        )
        for name in obsolete_root_entries:
            self.assertNotIn(
                name,
                root_names,
                f"Obsolete root entry returned: {name}",
            )
        for name in (
            "assets",
            "contributions",
            "legacy",
            "outputs",
            "scripts",
            "src",
        ):
            self.assertIn(name, root_names)
            self.assertTrue((self.repo_root / name).is_dir())

    def test_three_workstreams_have_explicit_boundaries(self) -> None:
        self.assertTrue((self.repo_root / "src" / "uchuva_lsystem").is_dir())
        self.assertTrue(
            (self.repo_root / "src" / "uchuva_classical_augmentation").is_dir()
        )
        self.assertTrue((self.repo_root / "src" / "uchuva_gazebo").is_dir())
        self.assertTrue(
            (
                self.repo_root
                / "contributions"
                / "diego_amaya"
                / "yolo11n_multiseed_v1"
                / "CONTRIBUTION.md"
            ).is_file()
        )

    def test_texture_library_has_explicit_current_and_legacy_paths(self) -> None:
        texture_root = self.repo_root / "assets" / "textures"
        self.assertTrue((texture_root / "current" / "manifest.json").is_file())
        self.assertTrue(
            (texture_root / "legacy" / "uchuva_v1" / "manifest.json").is_file()
        )
        self.assertTrue(
            (texture_root / "legacy" / "uchuva_v2" / "manifest.json").is_file()
        )

    def test_current_entrypoints_use_descriptive_names(self) -> None:
        scripts = self.repo_root / "scripts"
        expected = (
            "generate_morphology_tree.py",
            "generate_morphology_diagnostics.py",
            "generate_blender_cultivation_scene.py",
            "generate_blender_single_plant_preview.py",
            "render_structural_diagnostics.py",
            "run_model_variant_ablation.py",
        )
        obsolete = (
            "generate_single_plant.py",
            "generate_diagnostics.py",
            "generate_blender_scene.py",
            "generate_blender_plant.py",
            "generate_diagnostic_renders.py",
            "run_ablation_matrix.py",
            "generate_batch.py",
            "embed_internal_blend_script.py",
        )
        for name in expected:
            self.assertTrue((scripts / name).is_file(), name)
        for name in obsolete:
            self.assertFalse((scripts / name).exists(), name)

    def test_legacy_prototypes_have_explicit_names(self) -> None:
        legacy = self.repo_root / "legacy"
        self.assertTrue(
            (legacy / "prototypes" / "generic_blender_plant_v0_5.py").is_file()
        )
        self.assertTrue(
            (
                legacy
                / "scripts"
                / "embed_legacy_posthoc_generator_in_blend.py"
            ).is_file()
        )
        self.assertTrue((legacy / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
