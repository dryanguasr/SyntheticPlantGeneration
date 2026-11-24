"""Bounded BVH queries must retain the physically limiting obstacle."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from test_robot_mesh_geometry import cube, write_obj
from uchuva_gazebo.robot_kinematics import pose_identity
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_motion import resolved_world_clearance


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


if __name__ == '__main__':
    unittest.main()
