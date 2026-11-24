import copy
import math
import unittest

from uchuva_gazebo.harvest_validation import deposited_interval, world_point


class OnboardBasketTests(unittest.TestCase):
    basket = {'frame': 'robot_base', 'inner_min_m': [.12, -.13, .114],
              'inner_max_m': [.34, .13, .190]}

    def test_deposit_stays_in_rotating_and_translating_basket(self):
        rows = []
        for index in range(21):
            yaw = index * .05
            base = [index*.01, 1., .3, 0., 0., math.sin(yaw/2), math.cos(yaw/2)]
            fruit = {'id': 'a', 'position': world_point([.20, 0., .147], base),
                     'state': 'RELEASED', 'joint_present': False,
                     'joint_parent': 'none', 'removal_pending': False}
            rows.append({'sim_time': index*.05, 'robot_pose': base, 'fruits': [fruit]})
        self.assertTrue(deposited_interval(rows, 'a', .03, self.basket)['passed'])
        escaped = copy.deepcopy(rows)
        escaped[-1]['fruits'][0]['position'] = world_point([.40, 0., .147], rows[-1]['robot_pose'])
        self.assertFalse(deposited_interval(escaped, 'a', .03, self.basket)['passed'])

    def test_closed_mesh_uses_the_native_pose_and_shape(self):
        base = [0., 2., .25, 0., 0., 0., 1.]
        position = world_point([.21, 0., .13], base)
        fruit = {'id': 'a', 'position': position, 'pose': [*position, 0., 0., 0., 1.],
                 'state': 'RELEASED', 'joint_present': False,
                 'joint_parent': 'none', 'removal_pending': False}
        rows = [{'sim_time': index*.05, 'robot_pose': base, 'fruits': [fruit]} for index in range(21)]
        vertices = ((0., 0., -.017), (.03, 0., 0.), (0., .01, 0.), (0., 0., .01))
        self.assertTrue(deposited_interval(rows, 'a', .03, self.basket, mesh_vertices=vertices)['passed'])
        self.assertFalse(deposited_interval(rows, 'a', .03, self.basket)['passed'])
