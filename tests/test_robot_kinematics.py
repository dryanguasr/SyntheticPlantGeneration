"""SE(3) reference checks and explicit bounded-task IK, independent of Gazebo."""
import json
import math
import random
import unittest

from uchuva_gazebo.robot_spec import PROFILE_DIRECTORY, resolve_robot_profile
from uchuva_gazebo.robot_kinematics import (
    axis_quaternion, collision_shapes, compose_poses, forward_kinematics,
    inverse_pose, pose_from_rpy, pose_identity, rotate_vector, solve_ik, transform_point,
)


class RobotKinematicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.robot = resolve_robot_profile('proxy_v1')

    def assertVector(self, a, b, places=9):
        self.assertEqual(len(a),len(b))
        for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=places)

    def test_rigid_transform_inverse_and_composition(self):
        p = pose_from_rpy([1,-2,.3],[.4,-.8,.9])
        point = [.2,.3,-.4]
        self.assertVector(transform_point(inverse_pose(p),transform_point(p,point)),point)
        composed=compose_poses(p,inverse_pose(p))
        self.assertVector(composed['xyz_m'],[0,0,0])
        self.assertVector(rotate_vector(composed['quaternion_xyzw'],point),point)

    def test_proxy_matches_independent_analytic_landmarks_and_orientation(self):
        rng=random.Random(113)
        for _ in range(20):
            yaw,shoulder,elbow,wrist,roll=[rng.uniform(-.6,.6) for _ in range(5)]
            angles=[shoulder,shoulder+elbow,shoulder+elbow+wrist]
            r=sum(length*math.cos(a) for length,a in zip([.34,.30,.12],angles))
            z=.56+sum(length*math.sin(a) for length,a in zip([.34,.30,.12],angles))
            frames=forward_kinematics(self.robot,[yaw,shoulder,elbow,wrist,roll])
            self.assertVector(frames['tcp']['xyz_m'],[r*math.cos(yaw),r*math.sin(yaw),z])
            reference=pose_from_rpy([0,0,0],[roll,-sum([shoulder,elbow,wrist]),yaw])
            self.assertVector(rotate_vector(frames['tcp']['quaternion_xyzw'],[0,0,1]),rotate_vector(reference['quaternion_xyzw'],[0,0,1]))

    def test_mount_roll_and_offset_are_not_lost_by_planar_shortcuts(self):
        raw=self.robot.to_dict();raw['derived_values']=[]
        roll=next(j for j in raw['joints'] if j['name']=='wrist_roll_joint')
        roll['child_pose']['xyz_m']=[.12,.05,0]
        roll['zero_offset']=.2
        robot=resolve_robot_profile(raw)
        q=[0,0,0,0,math.pi/2-.2]
        base=pose_from_rpy([1,2,3],[.3,.2,.1])
        p=forward_kinematics(robot,q,base)['tcp']['xyz_m']
        self.assertVector(p,transform_point(base,[.76,0,.61]))

    def test_collision_shapes_follow_full_link_pose_and_preserve_open_spaces(self):
        q=[.2,.4,-.7,.2,.6]
        poses=forward_kinematics(self.robot,q)
        shapes=collision_shapes(self.robot,poses)
        self.assertEqual(len(shapes),11)
        self.assertEqual(len([row for row in shapes if 'wheel' in row['link']]),4)
        tool=next(row for row in shapes if row['name']=='tool_housing_collision')
        expected=transform_point(poses['tool_link'],[-.12*.72,0,.03])
        self.assertVector(tool['pose']['xyz_m'],expected)
        self.assertFalse(any('jaw' in row['name'] for row in shapes))

    def test_ik_solves_position_and_direction_with_reported_free_rotation(self):
        for q in ([.2,.5,-1,.3,.4],[-.4,.7,-1.3,.4,-.5],[.1,.3,-.8,.6,.2]):
            target=forward_kinematics(self.robot,q)['tcp']
            direction=rotate_vector(target['quaternion_xyzw'],[0,0,1])
            result=solve_ik(self.robot,target['xyz_m'],direction)
            self.assertTrue(result.success,result)
            self.assertLess(result.position_error_m,1e-5)
            self.assertLess(result.direction_error_rad,1e-4)
            self.assertEqual(result.unconstrained_rotation,'rotation_about_target_direction')
            observed=forward_kinematics(self.robot,result.joint_positions)['tcp']
            self.assertLess(math.dist(observed['xyz_m'],target['xyz_m']),1e-5)

    def test_ik_failure_preserves_residual_and_does_not_claim_global_infeasibility(self):
        result=solve_ik(self.robot,[20,0,20],[0,0,1],max_iterations=12)
        self.assertFalse(result.success)
        self.assertGreater(result.position_error_m,20)
        self.assertLessEqual(result.iterations,12)
        self.assertEqual(result.reason,'bounded_search_did_not_converge')
        with self.assertRaisesRegex(ValueError,'six-DOF'):
            solve_ik(self.robot,[.5,0,.7],orientation_mode='full_pose')
        with self.assertRaises(ValueError):solve_ik(self.robot,[.5,0,.7])
        with self.assertRaises(ValueError):solve_ik(self.robot,[.5,0,.7],[0,0,1],orientation_mode='position_only')
        with self.assertRaises(ValueError):forward_kinematics(self.robot,[0,9,0,0,0])
        with self.assertRaises(ValueError):forward_kinematics(self.robot,{'arm_yaw_joint':0})


if __name__=='__main__':unittest.main()
