"""Regression checks for the finite geometric withdrawal search."""

import json
import unittest

from uchuva_gazebo.harvest_clearance import (
    _CylinderIndex, _segment_box_distance, _world_clearance,
    audit_joint_segment, plan_harvest_motion, rigid_cylinders,
)
from uchuva_gazebo.harvest_plants import build_harvest_plants
from uchuva_gazebo.harvester_robot import HarvesterConfig, inverse_kinematics


class HarvestClearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_harvest_plants({})
        cls.plan = plan_harvest_motion(cls.bundle)

    def test_segment_box_distance_at_interior_faces_corners_and_degenerate_segments(self):
        half = [1, 1, 1]
        for a, b, expected in (([-2, 0, 0], [2, 0, 0], 0),
                               ([-2, 2, 0], [2, 2, 0], 1),
                               ([2, 2, 2], [3, 3, 3], 3 ** .5),
                               ([2, 0, 0], [2, 0, 0], 1)):
            self.assertAlmostEqual(_segment_box_distance(a, b, half), expected)

    def test_all_six_have_audited_approach_and_held_extraction(self):
        self.assertEqual(len(self.plan["targets"]), 6)
        self.assertEqual(self.plan["audit"]["rigid_cylinder_count"], 713)
        for target in self.plan["targets"].values():
            self.assertEqual(target["sequence"], ["carry", "preapproach", "cut", "extraction_0", "carry"])
            for segment in target["audit"]["segments"]:
                self.assertTrue(segment["passed"])
                self.assertEqual(segment["samples"], segment["requested_samples"])
                self.assertGreaterEqual(segment["samples"], 81)
                self.assertGreaterEqual(segment["minimum_robot_clearance_m"], .004)
                self.assertGreaterEqual(segment["minimum_joint_margin_rad"], .025)
                if segment["held"]:
                    self.assertGreaterEqual(segment["minimum_held_clearance_m"], .004)
                    self.assertGreaterEqual(segment["minimum_held_robot_clearance_m"], .004)
        json.dumps(self.plan, allow_nan=False)

    def test_upward_withdrawal_collision_is_detected_not_hidden_by_valid_ik(self):
        fruit = self.bundle["fruits"][-1]
        target = self.plan["targets"][fruit["id"]]
        cut = fruit["cut_point_world_m"]
        unsafe = inverse_kinematics([.36, 0, cut[2] + .12])
        audit = audit_joint_segment(target["joint_waypoints"]["cut"], unsafe, target["pickup_base_pose"], rigid_cylinders(self.bundle), self.bundle["fruits"], held=fruit)
        self.assertFalse(audit["passed"])
        self.assertLess(audit["minimum_held_clearance_m"], -.010)
        self.assertIn("plant_002", audit["limiting_held_obstacle"])
        self.assertNotEqual(target["extraction_offset_m"], [-.12, 0, 0])

    def test_added_obstacle_on_cut_fails_closed(self):
        fruit = self.bundle["fruits"][0]
        target = self.plan["targets"][fruit["id"]]
        cut = fruit["cut_point_world_m"]
        obstacles = rigid_cylinders(self.bundle)
        obstacles.append({"id": "deliberate_blocker", "start": [cut[0], cut[1], cut[2] - .1], "end": [cut[0], cut[1], cut[2] + .1], "radius": .04})
        audit = audit_joint_segment(target["joint_waypoints"]["cut"], target["joint_waypoints"]["extraction_0"], target["pickup_base_pose"], obstacles, self.bundle["fruits"], held=fruit, stop_on_failure=True)
        self.assertFalse(audit["passed"])
        self.assertLess(audit["samples"], audit["requested_samples"])

    def test_spatial_index_matches_exhaustive_distances_and_limiting_pairs(self):
        obstacles = rigid_cylinders(self.bundle)
        index = _CylinderIndex(obstacles)
        config = HarvesterConfig()
        for fruit in self.bundle["fruits"]:
            target = self.plan["targets"][fruit["id"]]
            for name in ("carry", "cut", "extraction_0"):
                joints = target["joint_waypoints"][name]
                for held in (None, fruit):
                    exhaustive = _world_clearance(joints, target["pickup_base_pose"], obstacles, self.bundle["fruits"], held, config)
                    indexed = _world_clearance(joints, target["pickup_base_pose"], index, self.bundle["fruits"], held, config)
                    self.assertEqual(indexed, exhaustive)


if __name__ == "__main__":
    unittest.main()
