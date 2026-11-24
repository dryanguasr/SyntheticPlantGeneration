"""Reuse broad phase and reject early without admitting an incomplete check."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from uchuva_gazebo.harvest_clearance import _CylinderIndex, audit_joint_segment
from uchuva_gazebo.robot_kinematics import pose_identity
from uchuva_gazebo.robot_motion import resolved_world_clearance
from uchuva_gazebo.robot_crop_collision_policy import FINGER_BLADE_CROP_SHAPES


def config_fixture():
    shape = {'name': 'body', 'link': 'arm', 'geometry': {'type': 'box', 'size_m': [.1]*3},
             'pose': {'xyz_m': [0, 0, 1], 'quaternion_xyzw': [0, 0, 0, 1]}}
    robot = SimpleNamespace(sha256='fixture', joints=[], data={'collision_policy': {'excluded_pairs': []}})
    return SimpleNamespace(robot=robot, joint_limits=[(-1, 1)], task={}, mesh_repository=None,
        world_shapes=lambda q, base: ([shape], pose_identity()))


class ResolvedSamplingTests(unittest.TestCase):
    def test_reuses_index_across_segments_and_preserves_complete_accepted_report(self):
        config = config_fixture()
        rows = [{'id': 'far', 'start': [2, 2, 1], 'end': [2, 2, 1.1], 'radius': .01}]
        index = _CylinderIndex(rows)
        parameters = dict(config=config, samples=3, clearance_m=.004, report_cap=.004)
        reference = audit_joint_segment([0], [.01], [0, 0, 0, 0], rows, [], **parameters)
        with patch.object(_CylinderIndex, '__init__', side_effect=AssertionError('Index rebuilt')):
            for _ in range(2):
                result = audit_joint_segment([0], [.01], [0, 0, 0, 0], index, [],
                    stop_on_failure=True, **parameters)
                self.assertEqual(result, reference)
                self.assertTrue(result['passed'])
                self.assertEqual(result['samples'], result['requested_samples'])

    def test_early_rejection_is_only_used_at_the_exact_acceptance_cap(self):
        config = config_fixture()
        fruit = {'id': 'blocker', 'center_world_m': [0, 0, 1], 'radius_m': .02}
        for stop, cap, expected in ((True, .004, True), (False, .004, False), (True, .5, False)):
            with self.subTest(stop=stop, cap=cap), patch(
                    'uchuva_gazebo.robot_motion.resolved_world_clearance', wraps=resolved_world_clearance) as query:
                result = audit_joint_segment([0], [0], [0, 0, 0, 0], [], [fruit],
                    config=config, samples=3, clearance_m=.004, report_cap=cap, stop_on_failure=stop)
                self.assertFalse(result['passed'])
                self.assertTrue(query.call_args_list)
                self.assertTrue(all(call.kwargs.get('reject_on_first_failure', False) is expected
                                    for call in query.call_args_list))
                self.assertEqual(result.get('first_failure_only', False), expected)
                self.assertEqual(result['samples'], 1 if stop else 3)

    def test_partial_failure_does_not_claim_unobserved_held_clearance(self):
        config = config_fixture()
        fruit = {'id': 'blocker', 'center_world_m': [0, 0, 1], 'radius_m': .02}
        held = {'id': 'held', 'center_world_m': [2, 0, 1], 'cut_point_world_m': [2, 0, 1],
                'held_offset_in_tool_m': [2, 0, 1], 'radius_m': .01}
        result = audit_joint_segment([0], [0], [0, 0, 0, 0], [], [fruit], held=held,
            config=config, samples=3, clearance_m=.004, report_cap=.004, stop_on_failure=True)
        self.assertFalse(result['passed'])
        self.assertEqual(result['first_failure_scope'], 'fruit')
        self.assertIsNone(result['minimum_held_clearance_m'])
        self.assertIsNone(result['minimum_held_robot_clearance_m'])
        self.assertEqual(set(result['unobserved_fields_at_failure']),
                         {'held_clearance_m', 'held_robot_clearance_m'})

    def test_exempt_shape_skips_crop_iteration_but_ground_still_fails(self):
        class CountingExclusions(set):
            calls = 0
            def __contains__(self, item):
                self.calls += 1
                return super().__contains__(item)

        class ForbiddenQuery(list):
            def near(self, center, extent):
                raise AssertionError('Exempt shape queried the crop index')

        config = config_fixture()
        shapes, _ = config.world_shapes([], [])
        shapes[0].update(name='part_104_bounds', link='gripper_right_jaw')
        config.world_shapes = lambda q, base: (shapes, pose_identity())
        config.crop_collision_excluded_shapes = CountingExclusions(FINGER_BLADE_CROP_SHAPES)
        fruits = [{'id': str(index), 'center_world_m': [0, 0, 1], 'radius_m': .02} for index in range(1027)]
        result = resolved_world_clearance([], [], ForbiddenQuery(), fruits, None, config, report_cap=.004)
        self.assertEqual(result['robot_clearance_m'], .004)
        self.assertEqual(config.crop_collision_excluded_shapes.calls, 1)
        shapes[0]['pose']['xyz_m'][2] = .02
        result = resolved_world_clearance([], [], ForbiddenQuery(), fruits, None, config, report_cap=.004)
        self.assertLess(result['robot_clearance_m'], .004)
        self.assertEqual(result['limiting_robot_pair'][1], 'ground')


if __name__ == '__main__':
    unittest.main()
