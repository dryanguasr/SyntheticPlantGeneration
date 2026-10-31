"""Pure checks for a replaceable fixture; runtime acceptance remains in Gazebo."""
import math
import random
import unittest
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvester_robot import (
    ARM_JOINT_NAMES, HOME_JOINTS, HarvesterConfig, check_joint_limits,
    forward_kinematics, generic_harvester_model, inverse_kinematics,
    robot_contract, set_collision_bitmask,
)


def identity():
    return [[float(i == j) for j in range(4)] for i in range(4)]


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def inverse_pose(matrix):
    result = identity()
    for i in range(3):
        for j in range(3):
            result[i][j] = matrix[j][i]
        result[i][3] = -sum(matrix[j][i] * matrix[j][3] for j in range(3))
    return result


def axis_rotation(axis, angle):
    # Rodrigues, independent of the solver's planar trigonometry.
    x, y, z = axis
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    result = identity()
    rows = [[t*x*x+c, t*x*y-s*z, t*x*z+s*y],
            [t*x*y+s*z, t*y*y+c, t*y*z-s*x],
            [t*x*z-s*y, t*y*z+s*x, t*z*z+c]]
    for i in range(3):
        result[i][:3] = rows[i]
    return result


def pose_matrix(values):
    x, y, z, roll, pitch, yaw = values
    result = multiply(multiply(axis_rotation((0, 0, 1), yaw),
                               axis_rotation((0, 1, 0), pitch)),
                      axis_rotation((1, 0, 0), roll))
    result[0][3], result[1][3], result[2][3] = x, y, z
    return result


def evaluate_sdf_arm(model, joints):
    """Interpret emitted zero-pose frames plus articulated joint transforms.

    This deliberately reads the SDF, so changed link poses or signs cannot
    silently continue agreeing with a duplicated analytic FK formula.
    """
    links = {node.attrib['name']: node for node in model.findall('link')}
    zero = {'__model__': identity()}

    def resolve(name):
        if name not in zero:
            pose = links[name].find('pose')
            values = [float(v) for v in (pose.text if pose is not None else '0 0 0 0 0 0').split()]
            frame = pose.attrib.get('relative_to', '__model__') if pose is not None else '__model__'
            zero[name] = multiply(resolve(frame), pose_matrix(values))
        return zero[name]

    for name in links:
        resolve(name)
    moved = {'base_link': zero['base_link']}
    for name, value in zip(ARM_JOINT_NAMES, joints):
        joint = model.find(f"joint[@name='{name}']")
        parent, child = joint.findtext('parent'), joint.findtext('child')
        pose = joint.find('pose')
        frame = pose.attrib.get('relative_to', child)
        joint_zero = multiply(zero[frame], pose_matrix([float(v) for v in pose.text.split()]))
        axis = tuple(float(v) for v in joint.findtext('axis/xyz').split())
        child_now = multiply(moved[parent], inverse_pose(zero[parent]))
        child_now = multiply(child_now, joint_zero)
        child_now = multiply(child_now, axis_rotation(axis, value))
        child_now = multiply(child_now, inverse_pose(joint_zero))
        moved[child] = multiply(child_now, zero[child])
    return moved['tool_link']


class HarvesterRobotTests(unittest.TestCase):
    def assert_vectors_close(self, actual, expected, places=9):
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=places)

    def test_generated_sdf_matches_fk_at_articulated_poses(self):
        for config in (HarvesterConfig(), HarvesterConfig(upper_arm_m=.39, forearm_m=.26,
                                                        tool_length_m=.15, shoulder_height_m=.65)):
            model = generic_harvester_model(config)
            for q in ((0, 0, 0, 0, 0), HOME_JOINTS,
                      (.75, 1.1, -1.7, .3, -.8), (-1.9, -.25, .8, -.4, 1.4)):
                fk = forward_kinematics(q, config)
                expected = pose_matrix((*fk['position_m'], *fk['rpy_rad']))
                actual = evaluate_sdf_arm(model, q)
                for a, b in zip(actual, expected):
                    self.assert_vectors_close(a, b, places=8)

    def test_ik_round_trips_many_reachable_positions_and_orientations(self):
        rng = random.Random(312)
        for _ in range(50):
            q = (rng.uniform(-2.5, 2.5), rng.uniform(.25, 1.1),
                 rng.uniform(-1.6, -.4), rng.uniform(-.3, .3), rng.uniform(-2, 2))
            expected = forward_kinematics(q)
            solution = inverse_kinematics(expected['position_m'],
                pitch=expected['rpy_rad'][1], roll=expected['rpy_rad'][0])
            actual = forward_kinematics(solution)
            self.assert_vectors_close(actual['position_m'], expected['position_m'])
            self.assert_vectors_close(actual['rpy_rad'], expected['rpy_rad'])

    def test_straight_elbow_boundary_is_reachable(self):
        config = HarvesterConfig()
        target = [config.upper_arm_m + config.forearm_m + config.tool_length_m,
                  0, config.shoulder_height_m]
        result = inverse_kinematics(target)
        self.assert_vectors_close(forward_kinematics(result)['position_m'], target)

    def test_ik_rejects_unreachable_singular_nonfinite_and_joint_limited_targets(self):
        for target, kw in (((2, 0, .56), {}), ((0, 0, .6), {}),
                           ((float('nan'), 0, .6), {}), ((.55, 0, .7), {'roll': 4}),
                           ((.01, 0, .56), {'pitch': math.pi})):
            with self.assertRaises(ValueError):
                inverse_kinematics(target, **kw)
        with self.assertRaises(ValueError):
            check_joint_limits((0, 0, 0, 0))
        with self.assertRaises(ValueError):
            check_joint_limits((0, 2, 0, 0, 0))

    def test_four_drive_joints_and_five_arm_controllers_share_the_contract(self):
        config = HarvesterConfig(model_name='replacement_proxy', namespace='/alternate')
        model = generic_harvester_model(config)
        contract = robot_contract(config)
        joints = {j.attrib['name']: j for j in model.findall('joint')}
        self.assertEqual(len(joints), 9)
        drive = model.find("plugin[@name='gz::sim::systems::DiffDrive']")
        for side in ('left', 'right'):
            names = [node.text for node in drive.findall(f'{side}_joint')]
            self.assertEqual(len(names), 2)
            self.assertTrue(all(name in joints for name in names))
        self.assertEqual(drive.findtext('topic'), contract['topics']['cmd_vel'])
        self.assertEqual(drive.findtext('odom_topic'), contract['topics']['odometry'])
        controllers = model.findall("plugin[@name='gz::sim::systems::JointPositionController']")
        self.assertEqual(len(controllers), 5)
        for controller in controllers:
            name = controller.findtext('joint_name')
            self.assertEqual(controller.findtext('topic'), contract['topics']['joint_commands'][name])
        states = model.find("plugin[@name='gz::sim::systems::JointStatePublisher']")
        self.assertEqual([n.text for n in states.findall('joint_name')], list(ARM_JOINT_NAMES))
        self.assertEqual(states.findtext('topic'), contract['topics']['joint_states'])
        self.assertEqual(model.attrib['name'], contract['model_name'])
        self.assertIsNotNone(model.find(f"link[@name='{contract['tool_link']}']"))

    def test_dynamic_links_have_positive_realizable_inertias_and_wheels_touch_ground(self):
        config = HarvesterConfig()
        model = generic_harvester_model(config)
        for link in model.findall('link'):
            self.assertGreater(float(link.findtext('inertial/mass')), 0)
            tensor = [float(link.findtext(f'inertial/inertia/{key}')) for key in ('ixx', 'iyy', 'izz')]
            self.assertTrue(all(v > 0 for v in tensor))
            self.assertLessEqual(max(tensor), sum(tensor) - max(tensor) + 1e-12)
            self.assertIsNotNone(link.find('collision'))
            if link.attrib['name'].endswith('_wheel'):
                center = [float(v) for v in link.findtext('pose').split()]
                self.assertAlmostEqual(center[2] - config.wheel_radius_m, 0)
                self.assertGreater(abs(center[1]) - config.wheel_width_m/2, config.body_width_m/2)
        self.assertEqual(model.findtext('static'), 'false')

    def test_visual_only_grasp_and_optional_camera_are_explicit(self):
        model = generic_harvester_model()
        tool = model.find("link[@name='tool_link']")
        self.assertIsNotNone(tool.find("visual[@name='capture_jaw_left']"))
        self.assertIsNone(tool.find("collision[@name='capture_jaw_left_collision']"))
        self.assertEqual(len(model.findall('.//sensor')), 0)
        camera_model = generic_harvester_model(HarvesterConfig(camera=True))
        self.assertEqual(len(camera_model.findall(".//sensor[@type='camera']")), 1)
        self.assertIn('ideal constraint', robot_contract()['capture_model'])

    def test_detached_contacts_remain_possible_while_robot_self_pairs_are_filtered(self):
        model = generic_harvester_model()
        self.assertEqual(model.findtext('self_collide'), 'true')
        masks = []
        for link in model.findall('link'):
            own = {int(c.findtext('surface/contact/collide_bitmask'))
                   for c in link.findall('collision')}
            self.assertEqual(len(own), 1)
            mask = own.pop()
            self.assertGreater(mask, 0)
            self.assertEqual(mask & (mask - 1), 0)
            masks.append(mask)
        self.assertEqual(len(masks), 10)
        for index, left in enumerate(masks):
            self.assertTrue(left & 65535)  # Ground, plant, bin and fruit.
            for right in masks[index + 1:]:
                self.assertEqual(left & right, 0)
        # Explicit all-bits environment masks are necessary for wrist/tool.
        self.assertGreater(max(masks), 255)
        environment = ET.fromstring('<model><link><collision name="wall"/></link></model>')
        set_collision_bitmask(environment, 65535)
        environment_mask = int(environment.findtext('link/collision/surface/contact/collide_bitmask'))
        self.assertTrue(all(environment_mask & mask for mask in masks))
        self.assertTrue(environment_mask & environment_mask)  # Fruit-fruit.

    def test_setting_masks_preserves_friction_and_is_idempotent(self):
        model = generic_harvester_model()
        wheel = model.find("link[@name='front_left_wheel']")
        before = ET.tostring(wheel.find('collision/surface/friction'))
        set_collision_bitmask(wheel, 65535)
        set_collision_bitmask(wheel, 65535)
        self.assertEqual(before, ET.tostring(wheel.find('collision/surface/friction')))
        self.assertEqual(len(wheel.findall('collision/surface')), 1)
        self.assertEqual(len(wheel.findall('collision/surface/contact/collide_bitmask')), 1)
        for invalid in (-1, 65536, 1.5, True):
            with self.assertRaises(ValueError):
                set_collision_bitmask(wheel, invalid)
        # An existing explicit category must not override the new symmetry.
        ET.SubElement(wheel.find('collision/surface/contact'), 'category_bitmask').text = '1'
        set_collision_bitmask(wheel, 512)
        self.assertEqual(wheel.findtext('collision/surface/contact/category_bitmask'), '512')

    def test_bad_geometry_is_rejected_before_writing_sdf(self):
        for kw in ({'upper_arm_m': 0}, {'wheel_radius_m': float('nan')},
                   {'shoulder_height_m': .1}, {'wheel_separation_m': .3},
                   {'namespace': 'no_leading_slash'}):
            with self.assertRaises(ValueError):
                HarvesterConfig(**kw)


if __name__ == '__main__':
    unittest.main()
