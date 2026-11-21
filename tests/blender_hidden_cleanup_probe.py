"""CPU-only regression: repeated private generation must not retain hidden fruit."""
from pathlib import Path
import sys
import unittest

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_lsystem.blender_scene import cleanup_scene


def fruit(name="uchuva_fixture_fruit"):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["uchuva_organ_kind"] = "fruit"
    obj.hide_render = obj.hide_viewport = True
    obj.hide_set(True)
    return obj


class CleanupTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_private_cleanup_removes_hidden_fruit_and_orphan_mesh(self):
        obj = fruit()
        name, mesh_name = obj.name, obj.data.name
        cleanup_scene(include_hidden=True)
        self.assertNotIn(name, bpy.data.objects)
        self.assertNotIn(mesh_name, bpy.data.meshes)

    def test_repeated_build_does_not_accumulate_internal_fruit(self):
        for _ in range(3):
            cleanup_scene(include_hidden=True)
            fruit()
            self.assertEqual(len(bpy.context.scene.objects), 1)

    def test_other_scene_objects_remain(self):
        other = bpy.data.scenes.new("fixture_other_scene")
        obj = fruit("unrelated_private_object")
        bpy.context.scene.collection.objects.unlink(obj)
        other.collection.objects.link(obj)
        name = obj.name
        cleanup_scene(include_hidden=True)
        self.assertIn(name, bpy.data.objects)
        self.assertIn(name, other.objects)
        bpy.data.scenes.remove(other)

    def test_shared_object_rejected_before_any_deletion(self):
        other = bpy.data.scenes.new("fixture_shared_scene")
        obj = fruit()
        other.collection.objects.link(obj)
        count = len(bpy.context.scene.objects)
        with self.assertRaisesRegex(ValueError, "exclusive"):
            cleanup_scene(include_hidden=True)
        self.assertEqual(len(bpy.context.scene.objects), count)
        self.assertTrue(obj.hide_render)
        bpy.data.scenes.remove(other)

    def test_legacy_default_retains_historical_selection_behavior(self):
        name = fruit().name
        cleanup_scene()
        self.assertIn(name, bpy.data.objects)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CleanupTests))
    if not result.wasSuccessful():
        raise RuntimeError("Hidden-scene cleanup regression failed")
