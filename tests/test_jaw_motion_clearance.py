"""Regression of a jaw stroke using real clearance calculations, without Gazebo."""
from copy import deepcopy
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from uchuva_gazebo.harvest_clearance import audit_joint_segment
from uchuva_gazebo.robot import forward_kinematics
from uchuva_gazebo.robot_harvest_planning import _position_joints, audit_jaw_transition, plan_resolved_harvest
from test_robot_task_regressions import robot_with_passive_mount


class JawMotionFixture:
    """Synthetic geometry/IK fixture; distances and path audits are not mocked."""
    def __init__(self, positions=None, seen=None):
        self.aux_positions = dict(positions or {'jaw': 0., 'support': .17})
        self.seen = [] if seen is None else seen
        self.joint_limits = [(-1., 1.)]*5
        self.robot = SimpleNamespace(
            sha256='synthetic-jaw-regression', joint_names=tuple('abcde'),
            joints=[{'name': 'jaw', 'type': 'prismatic', 'group': 'gripper',
                     'limits': {'lower': 0., 'upper': .008}}],
            data={'arm_home_positions': dict.fromkeys('abcde', 0.),
                  'collision_policy': {'excluded_pairs': []}})
        self.task = {'planning_base_height_m': .3, 'carry_joints_rad': [0.]*5,
            'pickup_base_candidates': {'target': [[0., 0., .3, 0.]]},
            'demo_fixture': {'minimum_joint_margin_rad': .025,
                'gripper': {'joint': 'jaw', 'closed_position_m': 0., 'open_position_m': .008},
                'bin': {'inner_min_m': [0., 0., 0.], 'inner_max_m': [1., 1., 1.]}}}
        self.mesh_repository = None

    def for_observed_joints(self, positions):
        clone = JawMotionFixture(positions, self.seen)
        clone.task = deepcopy(self.task)
        return clone

    def for_direction(self, direction):
        return self

    def for_target_cut(self, identifier):
        return self

    def solve(self, point, *, seed):
        return [0.]*5

    def fk(self, joints):
        return {'position_m': [joints[0], 0., .5], 'quaternion_xyzw': [0., 0., 0., 1.]}

    def world_shapes(self, joints, base):
        self.seen.append(dict(self.aux_positions))
        jaw = self.aux_positions['jaw']
        shape = {'name': 'pad', 'link': 'jaw',
                 'geometry': {'type': 'box', 'size_m': [.0002]*3},
                 'pose': {'xyz_m': [joints[0]+jaw, 0., .5],
                          'quaternion_xyzw': [0., 0., 0., 1.]}}
        return [shape], {'xyz_m': [joints[0], 0., .5], 'quaternion_xyzw': [0., 0., 0., 1.]}


class JawTransitionTests(unittest.TestCase):
    joints = [0.]*5
    base = [0., 0., .3, 0.]

    def neighbor(self, x=.004):
        return {'id': 'neighbor', 'center_world_m': [x, .004, .5], 'radius_m': .0001}

    def transition(self, config, fruits, *, start=0., end=.008, held=None, samples=2):
        return audit_jaw_transition(self.joints, self.base, [], fruits, config,
            joint_name='jaw', start_m=start, end_m=end, held=held,
            samples=samples, clearance_m=.004)

    def test_endpoints_pass_but_closing_and_opening_reject_intermediate_margin(self):
        config = JawMotionFixture()
        fruits = [self.neighbor()]
        for position in (0., .008):
            endpoint = config.for_observed_joints({**config.aux_positions, 'jaw': position})
            self.assertTrue(audit_joint_segment(self.joints, self.joints, self.base, [], fruits,
                config=endpoint, samples=2, clearance_m=.004)['passed'])
        midpoint = config.for_observed_joints({**config.aux_positions, 'jaw': .004})
        middle = audit_joint_segment(self.joints, self.joints, self.base, [], fruits,
            config=midpoint, samples=2, clearance_m=.004)
        self.assertAlmostEqual(middle['minimum_robot_clearance_m'], .0038)
        for start, end in ((0., .008), (.008, 0.)):
            with self.subTest(start=start, end=end):
                report = self.transition(config, fruits, start=start, end=end)
                self.assertFalse(report['passed'])
                self.assertLess(report['minimum_robot_clearance_m'], .004)
                self.assertGreater(report['failed_auxiliary_fraction'], 0.)
                self.assertLess(report['failed_auxiliary_fraction'], 1.)

    def test_clear_stroke_preserves_auxiliaries_and_requested_density(self):
        config = JawMotionFixture()
        original = dict(config.aux_positions)
        report = self.transition(config, [], samples=81)
        self.assertTrue(report['passed'])
        self.assertEqual(report['auxiliary_samples'], 81)
        self.assertLessEqual(report['maximum_auxiliary_sample_step_m'], .001)
        self.assertFalse(report['continuous_clearance_certified'])
        self.assertEqual(config.aux_positions, original)
        self.assertTrue(all(positions['support'] == .17 for positions in config.seen))
        self.assertIn(.004, [positions['jaw'] for positions in config.seen])

    def test_opening_audits_the_held_fruit_against_the_moving_jaw(self):
        config = JawMotionFixture()
        held = {**self.neighbor(), 'id': 'held', 'cut_point_world_m': [0., 0., .5],
                'held_offset_in_tool_m': [.004, .004, 0.]}
        report = self.transition(config, [held], held=held)
        self.assertFalse(report['passed'])
        self.assertEqual(report['minimum_robot_clearance_m'], .004)
        self.assertLess(report['minimum_held_robot_clearance_m'], .004)
        self.assertEqual(report['limiting_held_robot_link'], 'jaw/pad')

    def test_invalid_stroke_is_rejected_without_an_admitted_report(self):
        config = JawMotionFixture()
        for start, end in ((float('nan'), .008), (0., .009), (-.001, .008)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.transition(config, [], start=start, end=end)

    def bundle(self, neighbor):
        return {'models': [], 'fruits': [{'id': 'target',
            'cut_point_world_m': [.2, .2, .8], 'center_world_m': [.2, .2, .8],
            'pedicel_start_world_m': [.2, .2, .7], 'pedicel_end_world_m': [.2, .2, .8],
            'radius_m': .001}], 'static_fruit_obstacles': [neighbor]}

    def test_planner_rejects_a_closure_with_clear_endpoints(self):
        config = JawMotionFixture()
        # Only release IK is fixed for this synthetic fixture. All posture
        # and stroke clearances use the production geometry/auditor.
        with patch('uchuva_gazebo.robot_harvest_planning.onboard_release_joints', return_value=iter([[0.]*5])):
            plan = plan_resolved_harvest(self.bundle(self.neighbor()), config, samples=2)
        self.assertFalse(plan['audit']['passed'])
        rejected = plan['targets']['target']['audit']['rejected_candidates']
        self.assertEqual(rejected[0]['reason'], 'jaw_closure_collision_or_margin')
        self.assertLess(rejected[0]['segments'][0]['minimum_robot_clearance_m'], .004)

    def test_planner_rejects_basket_opening_with_clear_endpoints(self):
        config = JawMotionFixture()
        release = [.5, 0., 0., 0., 0.]
        with patch('uchuva_gazebo.robot_harvest_planning.onboard_release_joints', return_value=iter([release])):
            plan = plan_resolved_harvest(self.bundle(self.neighbor(.504)), config, samples=2)
        self.assertFalse(plan['audit']['passed'])
        rejected = plan['targets']['target']['audit']['rejected_candidates']
        self.assertTrue(any(row['reason'] == 'no_safe_onboard_deposit_pose' for row in rejected))
        opening = next(row['segments'][0] for row in rejected
                       if row['reason'] == 'jaw_opening_collision_or_margin')
        self.assertTrue(opening['held'])
        self.assertLess(opening['minimum_robot_clearance_m'], .004)
        opening_positions = [row['jaw'] for row in config.seen]
        self.assertTrue(any(0. < position < .008 for position in opening_positions))

    def test_planner_retains_a_clear_pickup_and_held_release(self):
        config = JawMotionFixture()
        release = [.5, 0., 0., 0., 0.]
        with patch('uchuva_gazebo.robot_harvest_planning.onboard_release_joints', return_value=iter([release])):
            plan = plan_resolved_harvest(self.bundle(self.neighbor(4.)), config, samples=2)
        self.assertTrue(plan['audit']['passed'])
        segments = plan['targets']['target']['audit']['segments']
        close = next(row for row in segments if row['from'] == 'cut_open')
        opening = next(row for row in segments if row['from'] == 'above_basket_closed')
        self.assertGreater(close['auxiliary_samples'], 2)
        self.assertGreater(opening['auxiliary_samples'], 2)
        self.assertTrue(opening['held'])
        self.assertEqual(opening['minimum_held_clearance_m'], .004)
        self.assertEqual(opening['minimum_held_robot_clearance_m'], .004)


class PlanningFallbackStateTests(unittest.TestCase):
    def test_position_only_waypoint_uses_the_observed_auxiliary_state(self):
        robot = robot_with_passive_mount()
        auxiliary = {'mount_slide': .2}
        home = [robot.data['arm_home_positions'][name] for name in robot.joint_names]
        target = forward_kinematics(robot, {**auxiliary, **dict(zip(robot.joint_names, home))})['tcp']
        config = SimpleNamespace(robot=robot, frame='tcp', aux_positions=auxiliary)
        joints = _position_joints(config, target['xyz_m'], home)
        actual = forward_kinematics(robot, {**auxiliary, **dict(zip(robot.joint_names, joints))})['tcp']
        self.assertLess(math.dist(actual['xyz_m'], target['xyz_m']), 1e-5)


if __name__ == '__main__':
    unittest.main()
