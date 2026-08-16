from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from uchuva_gazebo import (
    GazeboExportConfig,
    build_gazebo_export_plan,
    write_gazebo_export_plan,
)
from uchuva_lsystem.grammar import generate_morphology_tree


class GazeboInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plant = generate_morphology_tree(seed=73)

    def test_lods_preserve_visual_identity_and_control_physics_scope(self) -> None:
        lod0 = build_gazebo_export_plan(self.plant, GazeboExportConfig(lod=0))
        lod1 = build_gazebo_export_plan(self.plant, GazeboExportConfig(lod=1))
        lod2 = build_gazebo_export_plan(self.plant, GazeboExportConfig(lod=2))

        self.assertEqual(len(lod0.physics_items), 0)
        self.assertGreater(len(lod1.physics_items), 0)
        self.assertGreater(len(lod2.physics_items), len(lod1.physics_items))
        self.assertTrue(any(item.kind == "leaf" for item in lod2.visual_items))
        self.assertTrue(
            all(item.kind != "leaf" for item in lod2.physics_items)
        )
        self.assertTrue(any(item.detachable for item in lod2.physics_items))
        self.assertTrue(
            all(item.semantic_class == "calyx" for item in lod2.visual_items if item.kind == "calyx")
        )

    def test_plan_is_serializable_and_declares_limitations(self) -> None:
        plan = build_gazebo_export_plan(self.plant, GazeboExportConfig(lod=2))
        with tempfile.TemporaryDirectory() as temporary:
            output = write_gazebo_export_plan(plan, Path(temporary) / "plan.json")
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["source_seed"], 73)
        self.assertEqual(payload["config"]["lod"], 2)
        self.assertIn("No SDF", " ".join(payload["limitations"]))

    def test_invalid_lod_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_gazebo_export_plan(self.plant, GazeboExportConfig(lod=3))

    def test_gazebo_interface_has_no_runtime_blender_or_gazebo_dependency(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "uchuva_gazebo"
            / "interfaces.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import bpy", source)
        self.assertNotIn("import gz", source)
        self.assertNotIn("import gazebo", source)


if __name__ == "__main__":
    unittest.main()
