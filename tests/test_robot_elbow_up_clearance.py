import tempfile
import unittest
from pathlib import Path

from scripts.audit_cad_v8_demo_arm import check_motion, planned_state
from uchuva_gazebo.elbow_up_clearance import ElbowUpClearance
from uchuva_gazebo.robot_kinematics import pose_from_rpy, pose_identity


class ElbowSweepFixture:
    """Small articulated vehicle with a box obstacle on the swing arc."""

    joint_names = ('arm_yaw_joint', 'arm_shoulder_joint', 'arm_elbow_joint',
                   'wrist_pitch_joint', 'wrist_roll_joint')
    frames = ()

    def __init__(self):
        rows = (
            ('mount', 'base', 'arm_mount', 'fixed', None, (0, 0, 0)),
            (self.joint_names[0], 'arm_mount', 'yaw', 'revolute', (0, 0, 1), (0, 0, 0)),
            (self.joint_names[1], 'yaw', 'upper', 'revolute', (0, -1, 0), (0, 0, .1)),
            (self.joint_names[2], 'upper', 'lower', 'revolute', (0, -1, 0), (.30, 0, 0)),
            (self.joint_names[3], 'lower', 'pitch', 'revolute', (0, -1, 0), (.25, 0, 0)),
            (self.joint_names[4], 'pitch', 'roll', 'revolute', (1, 0, 0), (.10, 0, 0)),
            ('jaw', 'roll', 'finger', 'prismatic', (0, 1, 0), (0, 0, 0)),
        )
        self.joints = [
            {'name': name, 'parent': parent, 'child': child, 'type': kind, 'axis': axis,
             'origin': pose_from_rpy(xyz, (0, 0, 0)), 'child_pose': pose_identity(),
             'zero_offset': 0., 'limits': {'lower': -2., 'upper': 2.}}
            for name, parent, child, kind, axis, xyz in rows]
        boxes = [('base', 'basket_floor', (.3, 0, .1)), ('upper', 'arm_head', (.3, 0, 0))]
        links = [{'name': link, 'collisions': [{
            'name': name, 'pose': pose_from_rpy(xyz, (0, 0, 0)),
            'geometry': {'type': 'box', 'size_m': [.035] * 3},
        }]} for link, name, xyz in boxes]
        self.data = {'root_link': 'base', 'joints': self.joints, 'links': links,
                     'collision_policy': {'excluded_pairs': []}}
        self.task = {'demo_fixture': {'gripper': {'joint': 'jaw'}},
                     'auxiliary_joint_positions': {'jaw': 0.}}

    def to_dict(self):
        return self.data

    def require_capability(self, name):
        if name != 'fk':
            raise ValueError(f'Fixture has no {name}')


class ElbowUpClearanceTests(unittest.TestCase):
    def test_rejects_hidden_collision_between_clear_samples(self):
        fixture = ElbowSweepFixture()
        q = lambda yaw: [yaw, 0., -.8, 0., 0.]
        with tempfile.TemporaryDirectory() as root:
            clearance = ElbowUpClearance(fixture, fixture.task, asset_root=root)
            self.assertTrue(all(clearance.pose(q(yaw))['passed'] for yaw in (-.6, .3, 1.2)))
            result = clearance.segment(q(-.6), q(1.2))
            self.assertFalse(result['passed'])
            self.assertEqual(result['pair'], ['base/basket_floor', 'upper/arm_head'])
            self.assertEqual(result['distance_m'], 0.)
            self.assertGreater(result['evaluated_midpoints'], 1)
            self.assertTrue(clearance.segment(q(-.6), q(-.9))['passed'])

    def test_rejects_downward_elbow_even_if_geometry_is_clear(self):
        fixture = ElbowSweepFixture()
        with tempfile.TemporaryDirectory() as root:
            clearance = ElbowUpClearance(fixture, fixture.task, asset_root=root)
            posture = [-.6, 0., .8, 0., 0.]
            self.assertTrue(clearance.pose(posture, check_branch=False)['passed'])
            self.assertEqual(clearance.pose(posture)['reason'], 'elbow_branch')

    def test_nominal_bound_cannot_hide_a_native_tracking_collision(self):
        fixture = ElbowSweepFixture()
        times = [0., .1, .2]
        poses = [[-.6, 0., -.8, 0., 0., 0.], [-.7, 0., -.8, 0., 0., 0.],
                 [-.8, 0., -.8, 0., 0., 0.]]
        stamps = [0., .05, .1, .15, .2]
        with tempfile.TemporaryDirectory() as root:
            clearance = ElbowUpClearance(fixture, fixture.task, asset_root=root)
            native = Path(root) / 'native_motion.tsv'
            header = 'time ' + ' '.join(f'{name}_position' for name in clearance.coordinates)
            measured = [planned_state(times, poses, t) for t in stamps]

            def write_samples():
                body = [' '.join(map(str, (t, *pose))) for t, pose in zip(stamps, measured)]
                native.write_text('\n'.join((header, *body)) + '\n', encoding='utf-8')

            write_samples()
            report = check_motion(clearance, times, poses, native, .004)
            self.assertTrue(report['passed'])
            self.assertEqual(report['exact_pose_fallbacks'], 0)
            measured[2][0] = 0.
            write_samples()
            report = check_motion(clearance, times, poses, native, .004)
            self.assertFalse(report['passed'])
            self.assertEqual(report['exact_pose_fallbacks'], 1)
            self.assertEqual(report['failures'][0]['pair'], ['base/basket_floor', 'upper/arm_head'])

            measured[2][0] = .13
            write_samples()
            self.assertTrue(check_motion(clearance, times, poses, native, .004)['passed'])
            report = check_motion(clearance, times, poses, native, .004,
                                  require_nominal_clearance=True)
            self.assertFalse(report['passed'])
            self.assertEqual(report['required_clearance_m'], .004)
            self.assertLess(report['failures'][0]['distance_m'], .004)
            self.assertGreater(report['failures'][0]['distance_m'], 0.)

            measured[2][0] = -.6999
            write_samples()
            report = check_motion(clearance, times, poses, native, .004,
                                  require_nominal_clearance=True)
            self.assertTrue(report['passed'])
            self.assertEqual(report['exact_pose_fallbacks'], 1)
