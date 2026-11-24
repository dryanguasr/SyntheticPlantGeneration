"""Lazy planning surfaces retain the frozen renderer and strict clearance."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_plants import (
    _config, build_harvest_plants, calyx_collider,
    static_calyx_clearance_recipe, static_calyx_clearance_shape,
)
from uchuva_gazebo.harvest_visuals import detailed_calyx_mesh
from uchuva_gazebo.robot_kinematics import pose_identity
from uchuva_gazebo.robot_mesh_geometry import MeshRepository, parse_collision_obj
from uchuva_gazebo.robot_motion import resolved_world_clearance, pose_from_center


class StaticCalyxRefinementTests(unittest.TestCase):
    def fruit(self):
        proxy = SimpleNamespace(half_extents=(.16, .048, .048),
                                axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        return {'id': 'static', 'center_world_m': [0, 0, 1], 'radius_m': .02,
                **static_calyx_clearance_recipe(proxy)}

    def config(self, root, *, robot_y=None):
        shapes = ([] if robot_y is None else
                  [{'name': 'test_box', 'link': 'body',
                    'geometry': {'type': 'box', 'size_m': [.002]*3},
                    'pose': pose_from_center([0, robot_y, 1])}])
        return SimpleNamespace(robot=SimpleNamespace(sha256='test', joints=[],
            data={'collision_policy': {'excluded_pairs': []}}),
            mesh_repository=MeshRepository(root, []),
            world_shapes=lambda q, base: (shapes, pose_identity()))

    def test_option_is_explicit_and_strictly_boolean(self):
        self.assertFalse(_config({})['refine_static_calyx_clearance'])
        for invalid in (1, 'true', None):
            with self.assertRaisesRegex(ValueError, 'boolean'):
                _config({'refine_static_calyx_clearance': invalid})
        with self.assertRaisesRegex(ValueError, 'explicitly targeted'):
            _config({'refine_static_calyx_clearance': True})

    def test_export_option_preserves_all_native_xml_and_mesh_bytes(self):
        settings = {'seeds': [1031], 'positions_m': [[0, 0, 0]], 'rotations_deg': [0],
                    'max_dynamic_fruits_per_plant': 1}
        first = build_harvest_plants(settings, collision_screen=True)
        settings.update(explicit_targets_allow_partial=True,
                        target_ids=[first['fruits'][0]['id']])
        old = build_harvest_plants(settings)
        new = build_harvest_plants({**settings, 'refine_static_calyx_clearance': True})
        self.assertEqual(old['meshes'], new['meshes'])
        self.assertEqual(old['fruits'], new['fruits'])
        self.assertEqual(old['plants'], new['plants'])
        self.assertEqual([ET.tostring(m) for m in old['models']],
                         [ET.tostring(m) for m in new['models']])
        self.assertTrue(new['static_fruit_obstacles'])
        for before, after in zip(old['static_fruit_obstacles'], new['static_fruit_obstacles']):
            self.assertNotIn('planning_calyx_recipe', before)
            self.assertEqual({key: after[key] for key in before}, before)
            self.assertIn('planning_calyx_recipe_sha256', after)
        self.assertEqual(new['provenance']['static_calyx_clearance']['scope'],
                         'planning_only_native_static_calyces_remain_visual_only')

    def test_bound_encloses_the_exact_rounded_render_surface(self):
        angle = .781
        proxy = SimpleNamespace(half_extents=(.15877952, .104137, .109143),
            axes=((math.cos(angle), math.sin(angle), 0),
                  (-math.sin(angle), math.cos(angle), 0), (0, 0, 1+1e-12)))
        recipe = static_calyx_clearance_recipe(proxy)
        vertices, _, _, _ = parse_collision_obj(detailed_calyx_mesh(proxy))
        self.assertLessEqual(max(math.dist(p, (0, 0, 0)) for p in vertices),
                             recipe['planning_broadphase_radius_m'])
        with tempfile.TemporaryDirectory() as root:
            fruit = {'id': 'static', 'center_world_m': [2, 3, 4], 'radius_m': .02, **recipe}
            repo = MeshRepository(root, [])
            shape = static_calyx_clearance_shape(fruit, repo)
            expected = calyx_collider(detailed_calyx_mesh(proxy))
            self.assertEqual(shape['geometry']['sha256'], hashlib.sha256(expected.encode()).hexdigest())
            self.assertEqual(shape['pose']['xyz_m'], [2, 3, 4])
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_far_pairs_do_not_materialize_and_near_pairs_share_one_mesh(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root, robot_y=10)
            fruit = self.fruit()
            with patch('uchuva_gazebo.harvest_plants.detailed_calyx_mesh', wraps=detailed_calyx_mesh) as render:
                result = resolved_world_clearance([], [], [], [fruit], None, config, report_cap=.004)
                self.assertEqual(result['robot_clearance_m'], .004)
                self.assertEqual(render.call_count, 0)
                shapes, _ = config.world_shapes([], [])
                shapes[0]['pose']['xyz_m'][1] = .015
                for _ in range(2):
                    result = resolved_world_clearance([], [], [], [fruit], None, config,
                        report_cap=.004, reject_on_first_failure=True)
                    self.assertEqual(result['robot_clearance_m'], .004)
                self.assertEqual(render.call_count, 1)
                self.assertEqual(len(config.mesh_repository.generated_recipes), 1)

    def test_robot_and_held_refinement_remove_only_envelope_false_rejection(self):
        for scope in ('robot', 'held'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as root:
                config = self.config(root, robot_y=.015 if scope == 'robot' else None)
                fruit = self.fruit()
                held = ({'id': 'held', 'radius_m': .001,
                         'held_offset_in_tool_m': [0, .015, 1]} if scope == 'held' else None)
                key = 'held_clearance_m' if held else 'robot_clearance_m'
                coarse = {key: value for key, value in fruit.items() if not key.startswith('planning_')}
                result = resolved_world_clearance([], [], [], [coarse], held, config, report_cap=.004)
                self.assertLess(result[key], .004)
                result = resolved_world_clearance([], [], [], [fruit], held, config, report_cap=.004)
                self.assertEqual(result[key], .004)
                if held:
                    held['held_offset_in_tool_m'][1] = .008
                else:
                    config.world_shapes([], [])[0][0]['pose']['xyz_m'][1] = .008
                result = resolved_world_clearance([], [], [], [fruit], held, config, report_cap=.004)
                self.assertLess(result[key], .004)

    def test_recipe_tampering_and_underbounding_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            repo = MeshRepository(root, [])
            fruit = self.fruit()
            bad = deepcopy(fruit)
            bad['planning_calyx_recipe']['half_extents'][0] *= 2
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                static_calyx_clearance_shape(bad, repo)
            bad = deepcopy(fruit)
            bad['planning_broadphase_radius_m'] = 0
            with self.assertRaisesRegex(ValueError, 'does not enclose'):
                static_calyx_clearance_shape(bad, repo)


if __name__ == '__main__':
    unittest.main()
