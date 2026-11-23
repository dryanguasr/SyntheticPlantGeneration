"""Pure checks of the native comparison protocol; no Gazebo dependency."""
import importlib.util
import math
from pathlib import Path
import unittest

from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_gazebo.robot_kinematics import forward_kinematics, pose_from_rpy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_fk_probe',ROOT/'scripts/probe_robot_kinematics.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class RobotNativeProbeTests(unittest.TestCase):
    def setUp(self):
        self.robot = resolve_robot_profile('proxy_v1')

    def test_comparison_uses_observed_joint_state_and_detects_pose_disagreement(self):
        q = {j['name']:0.0 for j in self.robot.joints if j['type'] != 'fixed'}
        q[self.robot.joint_names[0]] = .07
        model_pose = pose_from_rpy([.4,-.2,.8],[.15,-.2,.3])
        local_fk = forward_kinematics(self.robot,q)
        row = {'positions':q,'model_pose':model_pose}
        observed = {'links':{link['name']:local_fk[link['name']] for link in self.robot.links}}
        errors = probe.compare_sample(self.robot,row,observed)
        self.assertLess(max(x['position_error_m'] for x in errors.values()),1e-12)
        tool = next(link['name'] for link in self.robot.links if link['name']=='tool_link')
        observed['links'][tool]['xyz_m'][0] += .002
        errors = probe.compare_sample(self.robot,row,observed)
        self.assertAlmostEqual(errors[tool]['position_error_m'],.002,places=10)
        del observed['links'][tool]
        with self.assertRaisesRegex(ValueError,'link pose set'):
            probe.compare_sample(self.robot,row,observed)

    def test_protocol_covers_both_directions_and_derivation_is_explicit(self):
        criteria = probe.protocol(self.robot)
        self.assertEqual(len(criteria['cases']),11)
        for name in self.robot.joint_names:
            values = [case['target'][name] for case in criteria['cases']]
            self.assertGreater(max(values),0)
            self.assertLess(min(values),0)
        world,removed = probe.make_world(self.robot,criteria,False)
        self.assertGreater(removed['collisions'],0)
        self.assertEqual(world.findall('.//collision'),[])
        self.assertEqual(world.findtext('world/gravity'),'0 0 0')
        model = world.find('world/model')
        self.assertIsNotNone(model.find("joint[@name='diagnostic_world_anchor']"))
        for plugin in model.findall('plugin'):
            if plugin.attrib['name'].endswith('JointPositionController'):
                self.assertEqual(plugin.findtext('use_velocity_commands'),'false')

    def test_quaternion_sign_equivalence_and_nonfinite_rejection(self):
        self.assertEqual(probe.quaternion_distance([0,0,0,1],[0,0,0,-1]),0)
        self.assertAlmostEqual(probe.quaternion_distance([0,0,0,1],[0,0,math.sin(.1),math.cos(.1)]),.2)
        with self.assertRaises(ValueError):
            probe.quaternion_distance([0,0,0,1],[0,0,0,0])


if __name__ == '__main__':
    unittest.main()
