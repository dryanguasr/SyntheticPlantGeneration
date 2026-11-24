"""Publica observaciones de ArUco recibidas por stdin desde la Astra."""

import json
from math import isfinite
import sys
import time

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from bench_2wd_drv8833.controller import FUTURE_NS, MAX_AGE_NS, read_route, topic_for

DISPLAY_MAX_AGE_NS = 800_000_000
NON_TARGET_DEPTH = {"invalido": -1.0, "ausente": -2.0, "sin_profundidad": -3.0}

class ObservationAgeError(ValueError):
    pass


def message(line, max_age_ns=MAX_AGE_NS, monotonic=False):
    stamp, xyz = json.loads(line) if isinstance(line, str) else line
    if type(stamp) is not int:
        raise ValueError("Sello inválido")
    age = (time.monotonic_ns() if monotonic else time.time_ns()) - stamp
    if age < -FUTURE_NS:
        raise ObservationAgeError(f"Relojes Windows/WSL desalineados ({age / 1e6:.0f} ms)")
    if age > max_age_ns:
        raise ObservationAgeError(f"Lecturas RGB-D retrasadas ({age / 1e6:.0f} ms)")
    if monotonic:
        stamp = time.time_ns() - age
    msg = PointStamped()
    msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamp, 10**9)
    msg.header.frame_id = "astra_depth_optical_frame"
    if isinstance(xyz, str):
        if xyz not in NON_TARGET_DEPTH:
            raise ValueError("Estado de profundidad desconocido")
        msg.point.z = NON_TARGET_DEPTH[xyz]
    elif xyz is not None:
        x, y, z = xyz
        if not all(map(isfinite, (x, y, z))) or z <= 0:
            raise ValueError("XYZ inválido")
        msg.point.x, msg.point.y, msg.point.z = map(float, (x, y, z))
    return msg


def main():
    rclpy.init()
    node = Node("bench_2wd_drv8833_aruco")
    try:
        diagnostic = node.declare_parameter("diagnostico", False).value
        monotonic = node.declare_parameter("transport_monotonic", False).value
        route = read_route(node)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        suffix = "_diagnostico" if diagnostic else "_visual"
        publishers = {mid: node.create_publisher(PointStamped, topic_for(mid) + suffix, qos) for mid in route}
        controls = {} if diagnostic else {mid: node.create_publisher(PointStamped, topic_for(mid), qos) for mid in route}
        print("ARUCO_READY", flush=True)
        delayed = 0
        for line in sys.stdin:
            try:
                stamp, samples = json.loads(line)
                for mid, publisher in publishers.items():
                    sample = samples.get(str(mid), "invalido") if isinstance(samples, dict) else (
                        samples if len(route) == 1 else "invalido"
                    )
                    reading = (stamp, sample)
                    publisher.publish(message(reading, DISPLAY_MAX_AGE_NS, monotonic))
                    if mid in controls:
                        try:
                            controls[mid].publish(message(reading, MAX_AGE_NS, monotonic))
                        except ObservationAgeError:
                            pass
                if delayed >= 3:
                    node.get_logger().info(f"Flujo recuperado tras {delayed} lecturas descartadas.")
                delayed = 0
            except ObservationAgeError as error:
                delayed += 1
                if delayed == 3:
                    node.get_logger().warning(str(error) + ". ROS descarta las lecturas vencidas.")
            except (ValueError, TypeError, OverflowError) as error:
                node.get_logger().warning(str(error), throttle_duration_sec=2)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
