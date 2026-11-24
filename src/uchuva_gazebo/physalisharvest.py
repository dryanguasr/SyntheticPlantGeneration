"""Pure hand-off from PhysalisHarvest observations to the canonical robot.

This boundary consumes public PointStamped-shaped dictionaries. It does not
import ROS, transform optical points into robot coordinates or command motors.
The experimental ArUco surface point is neither a calyx nor a cutting point.
"""
from __future__ import annotations

import math
import re


VERSION = "physalisharvest-integration/1.0"
UPSTREAM_URL = "https://github.com/amayadiegoalejandro05/PhysalisHarvest"
UPSTREAM_MAIN_SHA = "0c423be793ba2145674da0a49ab7e46d8bf1f119"
UPSTREAM_BRANCH = "fix/2wd-bench-scripts"
UPSTREAM_SHA = "114ce5690e7bf024d57ce2c815b7f3afd1d82e38"
ASTRA_FRAME = "astra_depth_optical_frame"
ARUCO_TOPIC = "/bench_2wd/drv8833/aruco_target"
SECOND_NS = 1_000_000_000
MAX_AGE_NS = 250_000_000
FUTURE_TOLERANCE_NS = 30_000_000
SENTINELS = {-1.0: "invalid_sample", -2.0: "marker_absent",
             -3.0: "visible_without_local_depth"}
TIMESTAMP_SEMANTICS = (
    "Windows monotonic sample immediately after RGB read, offset to WSL monotonic; "
    "publisher preserves that age when converting to system time for the ROS stamp. "
    "Not calibrated hardware exposure time or a synchronized depth timestamp."
)


def source_metadata():
    """Pinned source evidence; the feature branch is not upstream main."""
    return {
        "repository": UPSTREAM_URL, "main_sha": UPSTREAM_MAIN_SHA,
        "selected_branch": UPSTREAM_BRANCH, "selected_sha": UPSTREAM_SHA,
        "contract_sources": [
            "ros2_ws/src/robot_locomocion/bench_2wd_drv8833/bench_2wd_drv8833/aruco_source.py",
            "ros2_ws/src/robot_locomocion/bench_2wd_drv8833/bench_2wd_drv8833/controller.py",
            "docs/interfaces/bench-2wd-drv8833.md",
        ],
    }


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label}: unexpected or missing fields")


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label}: expected an integer >= {minimum}")
    return value


def _marker_from_topic(topic):
    if not isinstance(topic, str):
        raise ValueError("Expected the operational ArUco topic")
    if topic == ARUCO_TOPIC:
        return 0
    match = re.fullmatch(re.escape(ARUCO_TOPIC) + r"_id_([1-9][0-9]*)", topic)
    if match is None or not 1 <= int(match[1]) < 50:
        raise ValueError("Unknown topic; display/diagnostic streams are not operational inputs")
    return int(match[1])


def normalize_astra_point(message, *, now_ns, message_clock_domain,
                          now_clock_domain, topic=ARUCO_TOPIC,
                          previous_stamp_ns=None):
    """Validate one public operational ArUco observation, without using truth.

    Clock domains are mandatory caller declarations, not measured calibration.
    The caller must supply now_ns in the message's synchronized clock domain.
    Windows/WSL monotonic values and Gazebo simulation time cannot be silently
    compared. No host clock is read here, which also permits explicit replays.
    The optional previous stamp rejects duplicates and out-of-order samples.
    """
    marker_id = _marker_from_topic(topic)
    for domain in (message_clock_domain, now_clock_domain):
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("Clock domains must be explicitly declared")
    if message_clock_domain != now_clock_domain:
        raise ValueError("Clock domain mismatch; an explicit calibrated time adapter is required")
    _integer(now_ns, "now_ns", minimum=1)
    _fields(message, ("header", "point"), "PointStamped")
    _fields(message["header"], ("stamp", "frame_id"), "header")
    _fields(message["header"]["stamp"], ("sec", "nanosec"), "stamp")
    _fields(message["point"], ("x", "y", "z"), "point")
    if message["header"]["frame_id"] != ASTRA_FRAME:
        raise ValueError("Unexpected optical frame; no TF calibration is available")
    stamp = message["header"]["stamp"]
    sec = _integer(stamp["sec"], "stamp.sec")
    nanosec = _integer(stamp["nanosec"], "stamp.nanosec")
    if sec > 2**31 - 1 or nanosec >= SECOND_NS:
        raise ValueError("Invalid ROS timestamp range")
    stamp_ns = sec * SECOND_NS + nanosec
    if stamp_ns == 0:
        raise ValueError("Zero timestamp is not an acquisition time")
    if previous_stamp_ns is not None:
        _integer(previous_stamp_ns, "previous_stamp_ns")
        if stamp_ns <= previous_stamp_ns:
            raise ValueError("Duplicate or out-of-order observation")
    age_ns = now_ns - stamp_ns
    if age_ns > MAX_AGE_NS:
        raise ValueError("Expired observation")
    if age_ns < -FUTURE_TOLERANCE_NS:
        raise ValueError("Future observation; check clock alignment")
    xyz = [message["point"][axis] for axis in ("x", "y", "z")]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in xyz):
        raise ValueError("Optical coordinates must be finite numbers")
    x, y, z = xyz
    if z in SENTINELS and x == 0 and y == 0:
        status = SENTINELS[z]
    elif xyz == [0, 0, 0]:
        # aruco_source.message(None) emits the historical zero point. It does
        # not distinguish absence from invalid depth, so retain that ambiguity.
        status = "unavailable_legacy_zero"
    elif z <= 0:
        raise ValueError("Invalid depth or malformed sentinel")
    else:
        status = "observed"
    return {
        "schema_version": VERSION, "source_topic": topic,
        "source_sha": UPSTREAM_SHA, "stamp_ns": stamp_ns,
        "clock_domain": message_clock_domain, "age_ns": age_ns,
        "timestamp_semantics": TIMESTAMP_SEMANTICS,
        "frame_id": ASTRA_FRAME, "units": "m", "marker_id": marker_id,
        "marker_dictionary": "DICT_4X4_50", "status": status,
        "observation_kind": "aruco_surface_point",
        "xyz_optical_m": [float(v) for v in xyz] if status == "observed" else None,
        "robot_frame_position_status": "pending_TF_calibration",
        "fruit_maturity": "unknown", "cut_point_status": "unknown",
        "motor_command_generated": False,
    }


def build_integration_plan(resolved_robot):
    """Derive inspectable bindings from robot_contract, without bridge runtime.

    Interface names here are declarations, not confirmation that a Gazebo
    producer or a ROS consumer is running. No extra robot geometry is defined.
    """
    from .robot import robot_contract

    contract = robot_contract(resolved_robot)
    data = resolved_robot.to_dict()
    joints = {row["name"]: row for row in data["joints"]}
    drive = data["control"]["drive"]
    topics = contract["topics"]
    bindings = []
    for role, ros_type in (("cmd_vel", "geometry_msgs/msg/Twist"),
                           ("odometry", "nav_msgs/msg/Odometry")):
        bindings.append({
            "role": role, "gazebo_contract_topic": topics[role],
            "ros_topic": None, "candidate_ros_type": ros_type,
            "native_endpoint_declared": False,
            "status": "contract_only_no_native_endpoint",
        })
    bindings.append({
        "role": "joint_states", "gazebo_contract_topic": topics["joint_states"],
        "gazebo_type": "gz.msgs.Model", "ros_topic": None,
        "candidate_ros_type": "sensor_msgs/msg/JointState",
        "native_endpoint_declared": True,
        "status": "native_endpoint_declared_bridge_pending",
    })
    for name in contract["arm_joint_names"]:
        bindings.append({
            "role": "arm_position_reference", "joint_name": name,
            "gazebo_contract_topic": topics["joint_commands"][name],
            "gazebo_type": "gz.msgs.Double", "ros_topic": None,
            "candidate_ros_type": "std_msgs/msg/Float64", "units": "rad",
            "native_endpoint_declared": True,
            "status": "native_endpoint_declared_bridge_pending",
        })
    # These are the actual force-controller inputs emitted by _controllers.
    # The historical proxy has no drive.joints and therefore no such endpoints.
    for name, gains in drive.get("joints", {}).items():
        bindings.append({
            "role": "wheel_velocity_reference", "joint_name": name,
            "gazebo_topic": data["namespace"] + "/drive/" + name + "/cmd_vel",
            "gazebo_type": "gz.msgs.Double", "ros_topic": None,
            "candidate_ros_type": "std_msgs/msg/Float64", "units": "rad/s",
            "joint_velocity_limit_rad_s": joints[name]["limits"]["velocity"],
            "reference_velocity_limit_rad_s": gains["command_velocity"],
            "forward_joint_sign": drive.get("joint_signs", {}).get(name),
            "native_endpoint_declared": True,
            "status": "native_endpoint_declared_bridge_pending",
        })
    for name in data["control"].get("gripper", {}):
        joint = joints[name]
        bindings.append({
            "role": "gripper_position_reference", "joint_name": name,
            "gazebo_topic": data["namespace"] + "/gripper/" + name + "/cmd_pos",
            "gazebo_type": "gz.msgs.Double", "ros_topic": None,
            "candidate_ros_type": "std_msgs/msg/Float64",
            "units": "m" if joint["type"] == "prismatic" else "rad",
            "position_limits": [joint["limits"]["lower"], joint["limits"]["upper"]],
            "native_endpoint_declared": True,
            "status": "native_endpoint_declared_bridge_pending",
        })
    return {
        "schema_version": VERSION, "source": source_metadata(),
        "status": "offline_contract_checked_runtime_pending",
        "robot": {
            "profile_id": contract["profile_id"],
            "robot_spec_sha256": contract["robot_spec_sha256"],
            "contract_schema_version": contract["schema_version"],
            "base_link": contract["base_link"],
            "tool_link": contract["tool_link"],
            "arm_joint_names": contract["arm_joint_names"],
            "joint_limits_rad": contract["joint_limits_rad"],
            "joint_velocity_limits_rad_s": contract["joint_velocity_limits_rad_s"],
            "wheel_count": contract["wheel_count"],
            "tool_frame_poses": contract["tool_frame_poses"],
            "units": {"length": "m", "angle": "rad", "mass": "kg"},
        },
        "bindings": bindings,
        "observation_contract": {
            "type": "geometry_msgs/msg/PointStamped", "frame_id": ASTRA_FRAME,
            "axes": {"x": "right", "y": "down", "z": "forward_axial"},
            "units": "m", "operational_topic": ARUCO_TOPIC,
            "max_age_ns": MAX_AGE_NS, "future_tolerance_ns": FUTURE_TOLERANCE_NS,
            "sentinels_z": {str(int(z)): state for z, state in SENTINELS.items()},
            "timestamp_semantics": TIMESTAMP_SEMANTICS,
            "clock_status": "caller_declared_synchronized_domain_required",
            "semantics": "ArUco surface observation; not calyx, berry center or cut point",
        },
        "transforms": [{"source_frame": ASTRA_FRAME,
                        "target_frame": contract["base_link"],
                        "status": "pending_measured_extrinsics_and_time_valid_TF"}],
        "drive_compatibility": {
            "upstream_bench_drive_wheels": 2,
            "robot_drive_wheels": contract["wheel_count"],
            "same_drive_train": False,
            "status": "separate_platforms_no_PWM_or_serial_mapping",
            "twist_adapter_status": "pending_Twist_to_DriveReferenceController_adapter",
            "odometry_status": "pending_observed_odometry_producer",
            "native_endpoint_semantics": "wheel velocity Double inputs; finite effort controllers",
        },
        "gates": [
            "Medir extrinsecos Astra-base y verificar TF en el instante de observacion.",
            "Caracterizar reloj, latencia, intrinsecos y registro RGB-D del montaje real.",
            "Validar limites, colisiones y trayectoria antes de cualquier actuacion.",
            "Separar banco 2WD, robot CAD y resultados del simulador.",
        ],
        "runtime": {"ROS2_executed": False, "Gazebo_executed": False,
                    "hardware_executed": False, "motor_commands_generated": False},
    }
