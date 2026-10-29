"""CPU-only Blender regression for hidden-organ evaluated world envelopes.

Run with Blender --background --factory-startup --python-exit-code 1 --python
tests/blender_hidden_envelope_probe.py. This performs no render.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from uchuva_lsystem.blender_geometry import audit_scene_geometry_envelopes


def box(name, radius, location, semantic, hidden=False):
    data = bpy.data.meshes.new(name+'_mesh')
    data.from_pydata([(x*radius,y*radius,z*radius) for x in (-1,1)
                     for y in (-1,1) for z in (-1,1)], [],
                    [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)])
    data.update()
    obj = bpy.data.objects.new(name,data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj['uchuva_plant_id'] = 'fixture'
    obj['uchuva_semantic_class'] = semantic
    obj['uchuva_reproductive_instance_id'] = 'fixture:unit'
    if semantic == 'ignore':
        obj['uchuva_organ_kind'] = 'fruit'
    obj.hide_render = hidden
    obj.hide_viewport = hidden
    obj.hide_set(hidden)
    return obj


class HiddenEnvelopeTests(unittest.TestCase):
    def setUp(self):
        for obj in list(bpy.data.objects):
            bpy.data.objects.remove(obj,do_unlink=True)
        self.calyx = box('fixture_calyx',2,(3,4,5),'calyx')
        self.fruit = box('fixture_fruit',.5,(3,4,5),'ignore',True)
        bpy.context.scene.unit_settings.scale_length = .125
        bpy.context.view_layer.update()

    def test_hidden_fruit_uses_world_transform_and_restores_visibility(self):
        before = (self.fruit.hide_viewport,self.fruit.hide_get(),self.fruit.hide_render)
        matrix = self.calyx.matrix_world.copy()
        vertices = [tuple(v.co) for v in self.fruit.data.vertices]
        report = audit_scene_geometry_envelopes()
        fruit = next(r for r in report['objects'] if r['semantic']=='fruit')
        self.assertEqual(fruit['bounds']['minimum'],[2.5,3.5,4.5])
        self.assertEqual(fruit['bounds']['maximum'],[3.5,4.5,5.5])
        self.assertEqual(report['fruit_outside_calyx_envelope_count'],0)
        self.assertTrue(fruit['hidden_in_rgb'])
        self.assertEqual((self.fruit.hide_viewport,self.fruit.hide_get(),self.fruit.hide_render),before)
        self.assertEqual(self.calyx.matrix_world,matrix)
        self.assertEqual([tuple(v.co) for v in self.fruit.data.vertices],vertices)

    def test_exception_restores_global_local_and_render_visibility(self):
        before = (self.fruit.hide_viewport,self.fruit.hide_get(),self.fruit.hide_render)
        with patch('uchuva_lsystem.geometry_contracts.bounds_from_points',side_effect=RuntimeError('fixture failure')):
            with self.assertRaisesRegex(RuntimeError,'fixture failure'):
                audit_scene_geometry_envelopes()
        self.assertEqual((self.fruit.hide_viewport,self.fruit.hide_get(),self.fruit.hide_render),before)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HiddenEnvelopeTests))
    if not result.wasSuccessful():
        raise RuntimeError('Hidden envelope regression failed')
