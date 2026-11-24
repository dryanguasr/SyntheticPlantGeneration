"""Bounded BVH queries must retain the physically limiting obstacle."""
from pathlib import Path
from types import SimpleNamespace
import math
import tempfile
import unittest
from unittest.mock import patch

from test_robot_mesh_geometry import cube, write_obj
from uchuva_gazebo.robot_kinematics import pose_identity
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_motion import resolved_world_clearance, pose_from_center


class MeshMotionClearanceTests(unittest.TestCase):
    def fixture(self, root):
        geometry = write_obj(Path(root)/'cube.obj', *cube())
        shapes = [{'name': 'body', 'link': name, 'geometry': geometry,
                   'pose': {'xyz_m': position, 'quaternion_xyzw': [0, 0, 0, 1]}}
                  for name, position in [('first', [0, 0, 3]),
                                         ('second', [2.05, 0, 3]),
                                         ('distant', [100, 20, 3])]]
        robot = SimpleNamespace(sha256='fixture', joints=[],
            data={'collision_policy': {'excluded_pairs': []}})
        return SimpleNamespace(robot=robot,
            mesh_repository=MeshRepository(root, [geometry]),
            world_shapes=lambda values, base: (shapes, pose_identity()))

    def test_pruning_retains_closer_fruit_than_self_pair(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            result = resolved_world_clearance([], [], [],
                [{'id': 'fruit', 'center_world_m': [0, 0, 4.2], 'radius_m': .175}],
                None, config)
            self.assertAlmostEqual(result['robot_clearance_m'], .025)
            self.assertEqual(result['limiting_robot_pair'], ['first/body', 'fruit'])

    def test_internal_touch_does_not_hide_environment_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            config=self.fixture(root)
            shapes,_=config.world_shapes([],[])
            shapes[1]['pose']['xyz_m'][0]=2
            result=resolved_world_clearance([],[],[],
                [{'id':'nearby_fruit','center_world_m':[0,0,4.2],'radius_m':.175}],None,config)
            self.assertEqual(result['self_clearance_m'],0)
            self.assertAlmostEqual(result['environment_clearance_m'],.025)
            self.assertEqual(result['limiting_environment_pair'],['first/body','nearby_fruit'])
            # The existing total and its failure remain authoritative. An
            # environment-only observation never admits internal contact.
            self.assertEqual(result['robot_clearance_m'],0)
            self.assertEqual(result['limiting_robot_pair'],result['limiting_self_pair'])

    def test_negative_minimum_does_not_hide_larger_obstacle_radius(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            fruits = [{'id': 'inside', 'center_world_m': [0, 0, 3], 'radius_m': .1},
                      {'id': 'larger', 'center_world_m': [0, 0, 4.2], 'radius_m': .5}]
            result = resolved_world_clearance([], [], [], fruits, None, config)
            self.assertAlmostEqual(result['robot_clearance_m'], -.3)
            self.assertEqual(result['limiting_robot_pair'], ['first/body', 'larger'])

    def test_segment_radius_remains_in_bounded_query(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            obstacles = [{'id': 'branch', 'start': [-2, 0, 4.2],
                          'end': [2, 0, 4.2], 'radius': .19}]
            result = resolved_world_clearance([], [], obstacles, [], None, config)
            self.assertAlmostEqual(result['robot_clearance_m'], .01)
            self.assertEqual(result['limiting_robot_pair'][1], 'branch')

    def test_first_failure_keeps_the_same_threshold_with_tuple_shapes(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            shapes, tcp = config.world_shapes([], [])
            config.world_shapes = lambda values, base: (tuple(shapes), tcp)
            fruit = {'id': 'nearby_fruit', 'center_world_m': [0, 0, 4.2], 'radius_m': .197}
            for obstacles, expected in (([fruit], False), ([], True)):
                result = resolved_world_clearance([], [], [], obstacles, None, config,
                    report_cap=.004, reject_on_first_failure=True)
                self.assertEqual(result['robot_clearance_m'] >= .004, expected)
            self.assertTrue(resolved_world_clearance([], [], [], [fruit], None, config,
                report_cap=.004, reject_on_first_failure=True)['first_failure_only'])

    def test_saturated_corner_queries_preserve_exact_four_mm_cap(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            # Each AABB axis is within .024, so the BVH must run; the actual
            # corner distance is sqrt(2)*.0175 > .024. The bounded return
            # .024-.020 rounds below .004 and used to fabricate rejection.
            point = [1.0175, 0, 4.0175]
            fruit = {'id': 'clear_fruit', 'center_world_m': point, 'radius_m': .02}
            branch = {'id': 'clear_branch', 'start': [point[0], -.1, point[2]],
                      'end': [point[0], .1, point[2]], 'radius': .02}
            first = config.world_shapes([], [])[0][0]
            true_gap = config.mesh_repository.point_distance(first, point)-.02
            self.assertGreater(true_gap, .004)
            for cylinders, fruits in (([], [fruit]), ([branch], [])):
                with self.subTest(scope='fruit' if fruits else 'branch'):
                    result = resolved_world_clearance([], [], cylinders, fruits, None, config,
                        report_cap=.004, reject_on_first_failure=True)
                    self.assertEqual(result['robot_clearance_m'], .004)
                    self.assertNotIn('first_failure_only', result)
            sphere = {'geometry': {'type': 'sphere', 'radius_m': .02}, 'pose': pose_from_center(point)}
            for a, b in ((sphere, first), (first, sphere)):
                self.assertEqual(config.mesh_repository.shape_distance(a, b, limit=.004), .004)

    def test_held_saturated_mesh_crop_and_robot_queries_preserve_cap(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            first = config.world_shapes([], [])[0][0]
            point = [1.0175, 0, 4.0175]
            held_sphere = {'id': 'held', 'radius_m': .02, 'held_offset_in_tool_m': point}
            result = resolved_world_clearance([], [], [], [], held_sphere, config, report_cap=.004)
            self.assertEqual(result['held_robot_clearance_m'], .004)
            held_mesh = {'id': 'held_mesh', 'radius_m': 1.8,
                         'collision_geometry': first['geometry'],
                         'held_pose_in_tool': pose_from_center([0, 0, 3]),
                         'held_offset_in_tool_m': [0, 0, 3]}
            branch = {'id': 'clear_branch', 'start': [point[0], -.1, point[2]],
                      'end': [point[0], .1, point[2]], 'radius': .02}
            result = resolved_world_clearance([], [], [branch], [], held_mesh, config, report_cap=.004)
            self.assertEqual(result['held_clearance_m'], .004)
            # Also exercise held mesh vs another spherical fruit, through the
            # shape_distance sphere adapter rather than the capsule adapter.
            fruit = {'id': 'other', 'center_world_m': point, 'radius_m': .02}
            result = resolved_world_clearance([], [], [], [fruit], held_mesh, config, report_cap=.004)
            self.assertEqual(result['held_clearance_m'], .004)

    def test_unsaturated_distances_including_one_ulp_breach_are_not_rounded_up(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.fixture(root)
            delta = (.02+.0039)/math.sqrt(2)
            fruit = {'id': 'too_close', 'center_world_m': [1+delta, 0, 4+delta], 'radius_m': .02}
            result = resolved_world_clearance([], [], [], [fruit], None, config,
                report_cap=.004, reject_on_first_failure=True)
            self.assertLess(result['robot_clearance_m'], .004)
            self.assertAlmostEqual(result['robot_clearance_m'], .0039)
            # A genuine raw result just one representable float below cutoff
            # must still fail. This forbids an epsilon or blanket cap snapping.
            below = math.nextafter(.004+.02, 0)
            fruit['center_world_m'] = [1.0175, 0, 4.0175]
            with patch.object(config.mesh_repository, 'point_distance', return_value=below):
                result = resolved_world_clearance([], [], [], [fruit], None, config,
                    report_cap=.004, reject_on_first_failure=True)
                self.assertEqual(result['robot_clearance_m'], below-.02)
                self.assertLess(result['robot_clearance_m'], .004)
                first = config.world_shapes([], [])[0][0]
                sphere = {'geometry': {'type': 'sphere', 'radius_m': .02},
                          'pose': pose_from_center(fruit['center_world_m'])}
                gap = config.mesh_repository.shape_distance(sphere, first, limit=.004)
                self.assertEqual(gap, below-.02)
                self.assertLess(gap, .004)


if __name__ == '__main__':
    unittest.main()
