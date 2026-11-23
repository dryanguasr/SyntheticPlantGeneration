"""Transform and rejection contracts; mocked geometry is not native evidence."""
import copy
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from uchuva_gazebo.robot_harvest_planning import plan_resolved_harvest
from uchuva_gazebo.robot_kinematics import pose_identity


class PlanningFixture:
    def __init__(self):
        self.robot = SimpleNamespace(joint_names=('a', 'b', 'c', 'd', 'e'),
            data={'arm_home_positions': dict.fromkeys('abcde', 0)}, sha256='artificial')
        self.task = {'planning_base_height_m': .3, 'carry_joints_rad': [0]*5,
            'pickup_base_candidates': {'target': [[2, 3, .3, math.pi/2]]},
            'cut_axis_bidirectional': True}
        self.calls = []

    def fk(self, values):
        return {'position_m': [.2, 0, .4]}

    def for_direction(self, direction):
        self.calls.append(('direction', direction))
        return self

    def solve(self, point, *, seed):
        self.calls.append(('solve', list(point), list(seed)))
        return [*point, 0, 0]

    def world_shapes(self, values, base):
        return [], pose_identity()


class ResolvedPlanningTests(unittest.TestCase):
    def bundle(self):
        return {'fruits': [{'id': 'target', 'cut_point_world_m': [2, 3.5, .8],
            'center_world_m': [2, 3.5, .78], 'radius_m': .01,
            'pedicel_start_world_m': [2, 3.4, .8], 'pedicel_end_world_m': [2, 3.5, .8]}]}

    def test_robot_height_and_yaw_apply_to_points_and_directions(self):
        c, bundle = PlanningFixture(), self.bundle()
        before = copy.deepcopy(bundle)
        admitted = {'passed': True, 'minimum_robot_clearance_m': .1,
                    'minimum_held_clearance_m': .1, 'minimum_held_robot_clearance_m': .1}
        with patch('uchuva_gazebo.harvest_clearance.rigid_cylinders', return_value=[]), \
             patch('uchuva_gazebo.harvest_clearance.audit_joint_segment', return_value=admitted.copy()):
            result = plan_resolved_harvest(bundle, c)
        self.assertTrue(result['audit']['passed'])
        direction = c.calls[0][1]
        for a, b in zip(direction, [1, 0, 0]):
            self.assertAlmostEqual(a, b)
        for a, b in zip(c.calls[1][1], [.5, 0, .5]):
            self.assertAlmostEqual(a, b)
        target = result['targets']['target']
        self.assertEqual(target['joint_waypoints']['carry'], [0]*5)
        for a, b in zip(target['tcp_waypoints_world_m']['cut'], [2, 3.5, .8]):
            self.assertAlmostEqual(a, b)
        self.assertEqual(bundle, before)

    def test_failed_targets_remain_in_report_and_do_not_move(self):
        c, bundle = PlanningFixture(), self.bundle()
        bundle['fruits'].append({**copy.deepcopy(bundle['fruits'][0]), 'id': 'second'})
        before = copy.deepcopy(bundle)
        with patch('uchuva_gazebo.harvest_clearance.rigid_cylinders', return_value=[]), \
             patch.object(c, 'solve', side_effect=ValueError('inaccessible')):
            result = plan_resolved_harvest(bundle, c)
        self.assertFalse(result['audit']['passed'])
        self.assertEqual(set(result['targets']), {'target', 'second'})
        self.assertTrue(all(t['status'] == 'FAIL' for t in result['targets'].values()))
        self.assertEqual(bundle, before)

    def test_missing_robot_height_is_not_silently_ground_zero(self):
        c = PlanningFixture()
        del c.task['planning_base_height_m']
        with self.assertRaisesRegex(ValueError, 'planning_base_height'):
            plan_resolved_harvest(self.bundle(), c)


if __name__ == '__main__':
    unittest.main()
