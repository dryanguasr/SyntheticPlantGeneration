"""Independent energy/load identities and bounded controller revision contract."""
import copy
import importlib.util
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import forward_kinematics, transform_point


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


dynamics = module('analyze_robot_arm_dynamics')
revision = module('prepare_cad_control_revision')


class TwoLinkFixture:
    joint_names = ('one', 'two')
    frames = ()

    def __init__(self):
        identity = {'xyz_m': [0, 0, 0], 'quaternion_xyzw': [0, 0, 0, 1]}
        self.joints = []
        for name, parent, child, x in [('one', 'root', 'a', 0), ('two', 'a', 'b', 1)]:
            self.joints.append({'name': name, 'type': 'revolute', 'parent': parent, 'child': child,
                                'axis': [0, 1, 0], 'origin': {**identity, 'xyz_m': [x, 0, 0]},
                                'child_pose': identity, 'zero_offset': 0,
                                'limits': {'lower': -math.pi, 'upper': math.pi}})
        self.data = {'root_link': 'root', 'arm_home_positions': {'one': 0, 'two': 0},
                     'joints': self.joints, 'links': []}
        for name in ('root', 'a', 'b'):
            self.data['links'].append({'name': name, 'inertial': {'mass_kg': 1,
                'com_m': [0 if name == 'root' else .5, 0, 0], 'tensor_kg_m2': [.01, .01, .01, 0, 0, 0]}})

    def require_capability(self, _):
        pass

    def to_dict(self):
        return copy.deepcopy(self.data)


class ArmDynamicsTests(unittest.TestCase):
    def test_two_link_analytic_mass_matrix_and_gravity(self):
        result = dynamics.arm_dynamics(TwoLinkFixture())
        for actual, expected in zip(sum(result['mass_matrix'], []), [2.52, .76, .76, .26]):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertAlmostEqual(result['gravity_compensation_effort']['one'], -19.62)
        self.assertAlmostEqual(result['gravity_compensation_effort']['two'], -4.905)

    def test_gravity_is_potential_energy_gradient(self):
        robot = TwoLinkFixture()
        q = {'one': .37, 'two': -.28}
        calculated = dynamics.arm_dynamics(robot, q)['gravity_compensation_effort']
        def potential(coordinates):
            fk = forward_kinematics(robot, coordinates)
            return sum(9.81*body['inertial']['mass_kg']*transform_point(fk[body['name']], body['inertial']['com_m'])[2]
                       for body in robot.data['links'])
        for name in q:
            plus, minus = dict(q), dict(q)
            plus[name] += 1e-6
            minus[name] -= 1e-6
            self.assertAlmostEqual(calculated[name], (potential(plus)-potential(minus))/2e-6, places=8)

    def test_mass_matrix_matches_finite_difference_com_kinetic_energy(self):
        robot = TwoLinkFixture()
        q, velocity = {'one': .37, 'two': -.28}, {'one': .3, 'two': -.7}
        h = dynamics.arm_dynamics(robot, q)['mass_matrix']
        expected = .5*sum(velocity[a]*h[i][j]*velocity[b] for i, a in enumerate(q) for j, b in enumerate(q))
        plus = forward_kinematics(robot, {name: q[name]+1e-6*velocity[name] for name in q})
        minus = forward_kinematics(robot, {name: q[name]-1e-6*velocity[name] for name in q})
        actual = .5*.01*(velocity['one']**2+(velocity['one']+velocity['two'])**2)
        for body in robot.data['links']:
            a = transform_point(plus[body['name']], body['inertial']['com_m'])
            b = transform_point(minus[body['name']], body['inertial']['com_m'])
            actual += .5*sum(((x-y)/2e-6)**2 for x, y in zip(a, b))
        self.assertAlmostEqual(actual, expected, places=10)

    def test_revision_changes_only_control_capacity_and_provenance(self):
        robot = resolve_robot_profile('proxy_v1')
        source = robot.to_dict()
        spec = {'base_robot_spec_sha256': robot.sha256, 'revision_id': 'unit_test',
                'derivation': {'gain_selection': 'estimated unit-test PD', 'hardware_caveat': 'not hardware'},
                'arm': {name: {'p_gain': 25, 'i_gain': 0, 'd_gain': .01, 'effort_limit_nm': 2}
                        for name in robot.joint_names}}
        changed = revision.revised_profile(source, spec).to_dict()
        self.assertEqual(source, robot.to_dict())
        self.assertEqual(changed['links'], source['links'])
        self.assertEqual(changed['control']['drive'], source['control']['drive'])
        for joint in changed['joints']:
            if joint['name'] in robot.joint_names:
                self.assertEqual(joint['limits']['effort'], 2)
        with self.assertRaisesRegex(ValueError, 'immutable input'):
            revision.revised_profile(source, {**spec, 'base_robot_spec_sha256': '0'*64})


if __name__ == '__main__':
    unittest.main()
