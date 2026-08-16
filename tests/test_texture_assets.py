from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from uchuva_lsystem.texture_assets import generate_texture_asset_library


class TextureAssetTests(unittest.TestCase):
    def test_generator_is_deterministic_and_writes_valid_pngs(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = generate_texture_asset_library(first_dir, seed=23, resolution=48)
            second = generate_texture_asset_library(second_dir, seed=23, resolution=48)
            first_file = Path(first_dir) / first["texture_sets"]["leaf_healthy"]["files"]["normal"]
            second_file = Path(second_dir) / second["texture_sets"]["leaf_healthy"]["files"]["normal"]
            self.assertEqual(_sha256(first_file), _sha256(second_file))
            self.assertEqual(_png_dimensions(first_file), (48, 48))
            self.assertEqual(first["texture_sets"], second["texture_sets"])

    def test_manifest_preserves_taxonomy_and_evidence_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = generate_texture_asset_library(directory, seed=7, resolution=32)
            leaf = manifest["venation_taxonomy"]["leaf"]
            calyx = manifest["venation_taxonomy"]["calyx"]
            self.assertEqual(leaf["secondary_category"], "semicraspedodromous")
            self.assertEqual(leaf["highest_modeled_order"], 4)
            self.assertEqual(calyx["longitudinal_ribs_or_angles"], 10)
            self.assertEqual(len(manifest["texture_sets"]), 14)
            self.assertIn("calyx_transition_v0", manifest["texture_sets"])
            self.assertIn("dataset_inferred", manifest["texture_sets"]["calyx_green_v3"]["preset"]["parameter_status"])
            self.assertGreater(
                manifest["texture_sets"]["calyx_green_v3"]["preset"]["apical_darkening"],
                manifest["texture_sets"]["calyx_green_v0"]["preset"]["apical_darkening"],
            )
            self.assertGreater(
                manifest["texture_sets"]["calyx_green_v3"]["preset"]["vein_contrast"],
                manifest["texture_sets"]["calyx_green_v0"]["preset"]["vein_contrast"],
            )
            presets = [item["preset"] for item in manifest["texture_sets"].values()]
            self.assertTrue(all(item["sheen_weight"] == 0.0 for item in presets))
            self.assertTrue(all(item["subsurface_weight"] <= 0.005 for item in presets))
            self.assertTrue(all(item["specular_ior_level"] <= 0.15 for item in presets))
            self.assertGreaterEqual(
                manifest["texture_sets"]["calyx_green_v0"]["preset"]["roughness"],
                0.93,
            )
            stored = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["seed"], 7)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("not a PNG")
    return struct.unpack(">II", data[16:24])


if __name__ == "__main__":
    unittest.main()
