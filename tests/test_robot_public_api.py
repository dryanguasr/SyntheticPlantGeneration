import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from uchuva_gazebo.robot import resolve_robot, forward_kinematics, solve_task, build_robot_sdf
from uchuva_gazebo.robot_kinematics import rotate_vector


class PublicRobotTests(unittest.TestCase):
    def test_task_residual_and_collision_are_independent(self):
        robot = resolve_robot("proxy_v1")
        tool = forward_kinematics(robot)["tcp"]
        task = {"target_position_m": tool["xyz_m"],
                "target_direction": rotate_vector(tool["quaternion_xyzw"], [0, 0, 1])}
        result = solve_task(robot, task)
        self.assertTrue(result["success"])
        blocked = copy.deepcopy(task)
        blocked["obstacles"] = [{"name": "occupied_workcell", "pose": tool,
                                 "geometry": {"type": "box", "size_m": [4, 4, 4]}}]
        result = solve_task(robot, blocked)
        self.assertFalse(result["success"])
        self.assertLess(result["position_error_m"], 1e-8)
        self.assertEqual(result["collision_status"], "FAIL")
        self.assertTrue(result["collision_pairs"])

    def test_unreachable_preserves_residual_and_no_collision_claim(self):
        robot = resolve_robot("proxy_v1")
        result = solve_task(robot, {"target_position_m": [20, 0, 20], "target_direction": [0, 0, 1]})
        self.assertFalse(result["success"])
        self.assertGreater(result["position_error_m"], 10)
        self.assertEqual(result["collision_status"], "NO EJECUTADO")
        self.assertEqual(build_robot_sdf(robot).tag, "model")


if __name__ == "__main__":
    unittest.main()
