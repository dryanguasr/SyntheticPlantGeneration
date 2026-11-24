"""Public observation boundaries and canonical robot bindings, without ROS."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_gazebo.physalisharvest import (
    ARUCO_TOPIC, ASTRA_FRAME, FUTURE_TOLERANCE_NS, MAX_AGE_NS,
    UPSTREAM_MAIN_SHA, UPSTREAM_SHA, build_integration_plan, normalize_astra_point,
)
from uchuva_gazebo.robot import build_robot_sdf, resolve_robot, robot_contract


class AstraPointTests(unittest.TestCase):
    def setUp(self):
        self.message = {"header": {"stamp": {"sec": 10, "nanosec": 50},
                                   "frame_id": ASTRA_FRAME},
                        "point": {"x": .2, "y": -.1, "z": 1.5}}
        self.options = {"now_ns": 10_000_000_100,
                        "message_clock_domain": "ros_system",
                        "now_clock_domain": "ros_system"}

    def normalize(self, message=None, **options):
        return normalize_astra_point(self.message if message is None else message,
                                     **dict(self.options, **options))

    def test_surface_point_remains_optical_aruco_with_unknown_fruit_semantics(self):
        result = self.normalize(topic=ARUCO_TOPIC + "_id_12")
        self.assertEqual(result["xyz_optical_m"], [.2, -.1, 1.5])
        self.assertEqual(result["marker_id"], 12)
        self.assertEqual(result["frame_id"], ASTRA_FRAME)
        self.assertEqual(result["age_ns"], 50)
        self.assertEqual(result["observation_kind"], "aruco_surface_point")
        self.assertEqual(result["fruit_maturity"], "unknown")
        self.assertEqual(result["cut_point_status"], "unknown")
        self.assertFalse(result["motor_command_generated"])

    def test_all_sentinels_and_legacy_zero_preserve_missing_coordinates(self):
        for z, status in ((-1, "invalid_sample"), (-2, "marker_absent"),
                          (-3, "visible_without_local_depth"), (0, "unavailable_legacy_zero")):
            message = copy.deepcopy(self.message)
            message["point"] = {"x": 0, "y": 0, "z": z}
            result = self.normalize(message)
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["xyz_optical_m"])

    def test_invalid_coordinates_and_malformed_sentinels_fail(self):
        for point in ({"x": float("nan"), "y": 0, "z": 1},
                      {"x": 0, "y": 0, "z": float("inf")},
                      {"x": True, "y": 0, "z": 1},
                      {"x": 1, "y": 0, "z": -2},
                      {"x": 0, "y": 0, "z": -4},
                      {"x": 1, "y": 0, "z": 0}):
            message = copy.deepcopy(self.message)
            message["point"] = point
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.normalize(message)

    def test_explicit_clock_domain_and_freshness_boundaries(self):
        stamp = 10_000_000_050
        self.normalize(now_ns=stamp + MAX_AGE_NS)
        self.normalize(now_ns=stamp - FUTURE_TOLERANCE_NS)
        for options in ({"now_ns": stamp + MAX_AGE_NS + 1},
                        {"now_ns": stamp - FUTURE_TOLERANCE_NS - 1},
                        {"now_clock_domain": "gazebo_simulation"},
                        {"message_clock_domain": ""}, {"now_ns": True},
                        {"previous_stamp_ns": stamp}, {"previous_stamp_ns": stamp + 1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.normalize(**options)

    def test_invalid_ros_stamps_and_frames_fail(self):
        for stamp in ({"sec": -1, "nanosec": 0}, {"sec": 0, "nanosec": 0},
                      {"sec": 10, "nanosec": -1}, {"sec": 10, "nanosec": 10**9},
                      {"sec": 10., "nanosec": 1}, {"sec": 2**31, "nanosec": 1}):
            message = copy.deepcopy(self.message)
            message["header"]["stamp"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                self.normalize(message)
        message = copy.deepcopy(self.message)
        message["header"]["frame_id"] = "base_link"
        with self.assertRaises(ValueError):
            self.normalize(message)

    def test_reject_diagnostic_stream_and_unknown_marker(self):
        for topic in (ARUCO_TOPIC + "_visual", ARUCO_TOPIC + "_diagnostico",
                      ARUCO_TOPIC + "_id_50", ARUCO_TOPIC + "_id_01", "/astra/xyz"):
            with self.subTest(topic=topic), self.assertRaises(ValueError):
                self.normalize(topic=topic)

    def test_reject_truth_at_every_input_level(self):
        for location in ("root", "header", "stamp", "point"):
            message = copy.deepcopy(self.message)
            target = {"root": message, "header": message["header"],
                      "stamp": message["header"]["stamp"], "point": message["point"]}[location]
            target["truth_world_position"] = [0, 0, 0]
            with self.subTest(location=location), self.assertRaises(ValueError):
                self.normalize(message)


class IntegrationPlanTests(unittest.TestCase):
    def test_contract_twist_and_odometry_do_not_imply_native_endpoints(self):
        robot = resolve_robot("proxy_v1")
        plan = build_integration_plan(robot)
        by_role = {binding["role"]: binding for binding in plan["bindings"]}
        for role in ("cmd_vel", "odometry"):
            self.assertEqual(by_role[role]["status"], "contract_only_no_native_endpoint")
            self.assertFalse(by_role[role]["native_endpoint_declared"])
        self.assertTrue(by_role["joint_states"]["native_endpoint_declared"])
        self.assertFalse(any(b["role"] == "wheel_velocity_reference" for b in plan["bindings"]))
        self.assertIn("pending_Twist", plan["drive_compatibility"]["twist_adapter_status"])
        self.assertIn("pending_observed", plan["drive_compatibility"]["odometry_status"])

    def test_wheel_bindings_match_emitted_sdf_and_preserve_limits_and_sign(self):
        data = resolve_robot("proxy_v1").to_dict()
        drive = data["control"]["drive"]
        driven = drive["left_joints"] + drive["right_joints"]
        drive["joints"] = {name: {"p_gain": 1., "i_gain": 0., "d_gain": 0.,
                                 "i_min": 0., "i_max": 0., "cmd_min": -1.,
                                 "cmd_max": 1., "command_velocity": 2.}
                           for name in driven}
        drive["joint_signs"] = {name: -1 if name in drive["left_joints"] else 1 for name in driven}
        robot = resolve_robot(data)
        plan = build_integration_plan(robot)
        wheels = [b for b in plan["bindings"] if b["role"] == "wheel_velocity_reference"]
        model = build_robot_sdf(robot)
        native = {p.findtext("joint_name"): p.findtext("topic") for p in model.findall("plugin")
                  if p.get("name") == "gz::sim::systems::JointController"}
        self.assertEqual({b["joint_name"]: b["gazebo_topic"] for b in wheels}, native)
        for binding in wheels:
            name = binding["joint_name"]
            self.assertEqual(binding["units"], "rad/s")
            self.assertEqual(binding["gazebo_type"], "gz.msgs.Double")
            self.assertEqual(binding["candidate_ros_type"], "std_msgs/msg/Float64")
            self.assertEqual(binding["reference_velocity_limit_rad_s"], 2.)
            self.assertEqual(binding["forward_joint_sign"], drive["joint_signs"][name])

    def test_bindings_come_from_canonical_robot_and_remain_unexecuted(self):
        resolved = resolve_robot("proxy_v1")
        contract = robot_contract(resolved)
        plan = build_integration_plan(resolved)
        self.assertEqual(plan["robot"]["robot_spec_sha256"], resolved.sha256)
        self.assertEqual(plan["robot"]["arm_joint_names"], contract["arm_joint_names"])
        arm = [binding for binding in plan["bindings"] if binding["role"] == "arm_position_reference"]
        self.assertEqual({b["joint_name"]: b["gazebo_contract_topic"] for b in arm},
                         contract["topics"]["joint_commands"])
        self.assertTrue(all(b["ros_topic"] is None for b in plan["bindings"]))
        self.assertEqual(plan["drive_compatibility"]["robot_drive_wheels"], 4)
        self.assertFalse(plan["drive_compatibility"]["same_drive_train"])
        self.assertFalse(any(plan["runtime"].values()))
        self.assertEqual(plan["source"]["selected_sha"], UPSTREAM_SHA)
        self.assertEqual(plan["source"]["main_sha"], UPSTREAM_MAIN_SHA)
        self.assertNotEqual(UPSTREAM_SHA, UPSTREAM_MAIN_SHA)
        json.dumps(plan, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
