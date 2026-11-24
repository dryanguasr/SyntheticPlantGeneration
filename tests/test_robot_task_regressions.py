"""Regression cases for observed mechanisms and fail-closed obstacle inputs."""
from copy import deepcopy
import itertools
import math
import unittest
from unittest.mock import patch

from uchuva_gazebo.robot import forward_kinematics, resolve_robot, solve_task
from uchuva_gazebo.robot_kinematics import pose_identity, rotate_vector, solve_ik
from uchuva_gazebo.robot_motion import ResolvedMotionConfig


def robot_with_passive_mount():
    """A valid synthetic moving mount; it is not a measurement of the CAD."""
    data = resolve_robot("proxy_v1").to_dict()
    data["links"].append({
        "name": "passive_arm_mount",
        "inertial": {"mass_kg": .01, "com_m": [0, 0, 0],
                     "tensor_kg_m2": [.001, .001, .001, 0, 0, 0]},
        "visuals": [], "collisions": [],
    })
    next(j for j in data["joints"] if j["name"] == "arm_yaw_joint")["parent"] = "passive_arm_mount"
    data["joints"].append({
        "name": "mount_slide", "parent": "base_link", "child": "passive_arm_mount",
        "type": "prismatic", "group": "passive", "origin": pose_identity(),
        "child_pose": pose_identity(), "axis": [1, 0, 0], "zero_offset": 0,
        "limits": {"lower": -.3, "upper": .3, "velocity": .1, "effort": 1},
    })
    # This fixture isolates pose/residual consistency from proxy self contacts.
    data["collision_policy"]["excluded_pairs"] = [
        {"links": [a["name"], b["name"]], "reason": "Pose-only regression fixture"}
        for a, b in itertools.combinations(data["links"], 2)
    ]
    return resolve_robot(data)


class ObservedMechanismRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.robot = robot_with_passive_mount()
        cls.auxiliary = {"mount_slide": .2}
        cls.reference = [.2, .5, -1., .3, .4]
        positions = {**cls.auxiliary, **dict(zip(cls.robot.joint_names, cls.reference))}
        cls.target = forward_kinematics(cls.robot, positions)["tcp"]

    def actual_pose(self, coordinates):
        return forward_kinematics(self.robot, {
            **self.auxiliary, **dict(zip(self.robot.joint_names, coordinates))})["tcp"]

    def test_ik_uses_observed_mount_in_iteration_and_reported_residual(self):
        direction = rotate_vector(self.target["quaternion_xyzw"], [0, 0, 1])
        result = solve_ik(self.robot, self.target["xyz_m"], direction,
                          auxiliary_joint_positions=self.auxiliary)
        self.assertTrue(result.success, result)
        actual = self.actual_pose(result.joint_positions)
        self.assertAlmostEqual(result.position_error_m, math.dist(actual["xyz_m"], self.target["xyz_m"]), places=12)
        self.assertLess(result.position_error_m, 1e-5)
        observed_direction = rotate_vector(actual["quaternion_xyzw"], [0, 0, 1])
        error = math.acos(max(-1., min(1., sum(a*b for a,b in zip(direction, observed_direction)))))
        self.assertAlmostEqual(result.direction_error_rad, error, places=12)

    def test_public_task_never_claims_zero_error_for_displaced_mount(self):
        target = forward_kinematics(self.robot)["tcp"]["xyz_m"]
        result = solve_task(self.robot, {
            "target_position_m": target, "orientation_mode": "position_only",
            "auxiliary_joint_positions": self.auxiliary,
        })
        actual_error = math.dist(self.actual_pose(result["joint_positions"])["xyz_m"], target)
        self.assertAlmostEqual(result["position_error_m"], actual_error, places=12)
        if result["success"]:
            self.assertLessEqual(actual_error, 1e-5)
        else:
            self.assertEqual(result["collision_status"], "NO EJECUTADO")

    def test_motion_adapter_uses_same_auxiliary_state_for_solve_and_fk(self):
        direction = rotate_vector(self.target["quaternion_xyzw"], [0, 0, 1])
        config = ResolvedMotionConfig(self.robot, {
            "orientation_mode": "position_direction", "target_direction": direction,
            "tool_axis": [0, 0, 1], "orientation_tolerance_rad": .01,
            "auxiliary_joint_positions": self.auxiliary,
        })
        coordinates = config.solve(self.target["xyz_m"])
        self.assertLess(math.dist(config.fk(coordinates)["position_m"], self.target["xyz_m"]), 1e-5)

    def test_auxiliary_coordinates_reject_invalid_names_values_and_limits(self):
        for auxiliary in ({"mount_slide": float("nan")}, {"mount_slide": float("inf")},
                          {"mount_slide": True}, {"mount_slide": .31},
                          {"unknown": 0.}, {self.robot.joint_names[0]: 0.}, []):
            with self.subTest(auxiliary=auxiliary), self.assertRaises(ValueError):
                solve_ik(self.robot, self.target["xyz_m"], orientation_mode="position_only",
                         auxiliary_joint_positions=auxiliary)


class ObstacleInputRegressionTests(unittest.TestCase):
    def setUp(self):
        self.robot = resolve_robot("proxy_v1")
        tcp = forward_kinematics(self.robot)["tcp"]
        self.task = {"target_position_m": tcp["xyz_m"], "orientation_mode": "position_only"}
        self.obstacle = {"name": "occupied_workcell", "pose": tcp,
                         "geometry": {"type": "box", "size_m": [4., 4., 4.]}}

    def solve(self, obstacle):
        return solve_task(self.robot, {**self.task, "obstacles": [obstacle]})

    def test_valid_obstacle_still_blocks_the_posture(self):
        result = self.solve(self.obstacle)
        self.assertFalse(result["success"])
        self.assertEqual(result["collision_status"], "FAIL")
        self.assertTrue(result["collision_pairs"])

    def test_box_dimensions_reject_nonfinite_nonpositive_and_non_numeric(self):
        for value in (float("nan"), float("inf"), -4., 0., True, "4"):
            obstacle = deepcopy(self.obstacle)
            obstacle["geometry"]["size_m"] = [value]*3
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.solve(obstacle)

    def test_obstacle_pose_rejects_invalid_position_and_quaternion(self):
        for key, value in (("xyz_m", [float("nan")]*3), ("xyz_m", [float("inf")]*3),
                           ("xyz_m", [True, 0, 0]), ("xyz_m", [0, 0]),
                           ("quaternion_xyzw", [0, 0, 0, 0]),
                           ("quaternion_xyzw", [0, 0, 0, 2]),
                           ("quaternion_xyzw", [0, 0, float("nan"), 1])):
            obstacle = deepcopy(self.obstacle)
            obstacle["pose"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.solve(obstacle)

    def test_sphere_and_cylinder_reject_invalid_dimensions(self):
        for geometry in ({"type": "sphere", "radius_m": -1},
                         {"type": "sphere", "radius_m": float("nan")},
                         {"type": "cylinder", "radius_m": .1, "length_m": float("inf")},
                         {"type": "cylinder", "radius_m": .1, "length_m": 0}):
            obstacle = {**self.obstacle, "geometry": geometry}
            with self.subTest(geometry=geometry), self.assertRaises(ValueError):
                self.solve(obstacle)

    def test_invalid_format_is_rejected_even_when_target_is_unreachable(self):
        for obstacles in (None, {}, [None], [{**self.obstacle, "geometry": {"type": []}}],
                          [{**self.obstacle, "pose": None}], [self.obstacle, self.obstacle]):
            with self.subTest(obstacles=obstacles), self.assertRaises(ValueError):
                solve_task(self.robot, {"target_position_m": [20, 0, 20],
                    "orientation_mode": "position_only", "obstacles": obstacles})

    def test_mesh_identity_and_scale_are_validated_before_asset_access(self):
        valid = {"type": "mesh", "uri": "meshes/obstacle.obj", "sha256": "a"*64,
                 "scale": [1, 1, 1]}
        for key, value in (("uri", "../escape.obj"), ("uri", "C:/absolute.obj"),
                           ("sha256", "unknown"), ("scale", [1, float("nan"), 1]),
                           ("scale", [2, 1, 1])):
            geometry = {**valid, key: value}
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                solve_task(self.robot, {"target_position_m": [20, 0, 20],
                    "orientation_mode": "position_only",
                    "obstacles": [{**self.obstacle, "geometry": geometry}]})

    def test_nonfinite_separation_never_becomes_a_pass(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), patch("uchuva_gazebo.robot_motion.box_separation", return_value=value), \
                    self.assertRaises(ValueError):
                self.solve(self.obstacle)


if __name__ == "__main__":
    unittest.main()
