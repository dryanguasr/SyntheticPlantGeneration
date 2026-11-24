"""Control experimental de un ArUco con armado manual y salida por tubería."""

import fcntl
from functools import partial
from math import atan2, degrees, isfinite
import os
from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
import time

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import SetBool


ROOT = "/bench_2wd/drv8833"
TARGET = ROOT + "/aruco_target"
FRAME = "astra_depth_optical_frame"
MAX_AGE_NS = 250_000_000
START_MAX_AGE_NS = 180_000_000
TRACK_MAX_AGE_NS = 450_000_000
FUTURE_NS = 30_000_000
STOP_Z_M = 0.50
TURN_BURST_S = 0.10
TURN_REST_S = 0.50
INTERLOCK_S = 0.20


def topic_for(marker_id):
    return TARGET if marker_id == 0 else f"{TARGET}_id_{marker_id}"


def read_route(node):
    route = tuple(node.declare_parameter("ruta", [0]).value)
    if not route or len(set(route)) != len(route) or any(not 0 <= item < 50 for item in route):
        raise ValueError("La ruta debe usar IDs únicos de 0 a 49.")
    return route


class Controller(Node):
    def __init__(self, disconnected):
        super().__init__("bench_2wd_drv8833_controller")
        self.disconnected = disconnected
        self.route = read_route(self)
        self.armed = self.driving = self.turning = False
        self.active_id = None
        self.reached = set()
        self.searchable = {}
        self.last_stamps = {}
        self.target = None
        self.scan_until = self.resume_after = 0.0
        self.align_until = 0.0
        self.center_frames = 0
        self.activated_at = 0
        self.last_command = None
        self.last_state = None
        self.state = self.create_publisher(String, ROOT + "/state", 10)
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        for marker_id in self.route:
            self.create_subscription(PointStamped, topic_for(marker_id),
                                     partial(self.receive, marker_id=marker_id), qos)
        self.create_service(SetBool, ROOT + "/enable", self.enable)
        self.create_timer(0.05, self.tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def send(self, command, deadline=0):
        print(f"CMD {time.monotonic_ns()} {deadline} {command}", flush=True)

    def report(self, text):
        if self.last_state == text:
            return
        self.last_state = text
        self.state.publish(String(data=text))
        self.get_logger().info(text)

    def stop(self, reason):
        self.armed = self.driving = self.turning = False
        self.scan_until = self.resume_after = 0.0
        self.align_until = 0.0
        self.center_frames = 0
        self.active_id = self.target = self.last_command = None
        self.send("S")
        self.report(f"STOP {reason}")

    def receive(self, msg, marker_id):
        if not self.armed:
            return
        if self.active_id is not None and marker_id != self.active_id:
            return
        stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        age = time.time_ns() - stamp
        capture = time.monotonic_ns() - age
        xyz = (msg.point.x, msg.point.y, msg.point.z)
        if capture < self.activated_at or stamp <= self.last_stamps.get(marker_id, 0):
            return
        valid = msg.header.frame_id == FRAME and all(map(isfinite, xyz)) and -FUTURE_NS <= age <= MAX_AGE_NS
        explicitly_absent = valid and xyz == (0.0, 0.0, -2.0)
        visible_without_depth = valid and xyz == (0.0, 0.0, -3.0)
        if marker_id in self.reached:
            if not explicitly_absent:
                return
            self.reached.remove(marker_id)
        if valid:
            self.last_stamps[marker_id] = stamp
        self.searchable.pop(marker_id, None)
        if not valid or xyz[2] <= 0:
            if explicitly_absent or visible_without_depth:
                self.searchable[marker_id] = capture
            if self.active_id == marker_id:
                self.target = None
                self.pause("esperando_aruco")
            return
        if self.active_id is None:
            if age > START_MAX_AGE_NS:
                return
            self.active_id = marker_id
            if self.scan_until:
                self.rest_after_turn()
            self.report(f"TARGET {marker_id}")
        if not self.driving and capture >= round(self.resume_after * 1e9):
            center_limit = 2.0 if self.turning else 4.0
            if self.target is None or capture - self.target[0] > MAX_AGE_NS:
                self.center_frames = 0
            if abs(degrees(atan2(xyz[0], xyz[2]))) <= center_limit:
                self.center_frames = min(self.center_frames + 1, 2)
            else:
                self.center_frames = 0
        self.target = (capture, xyz)
        if xyz[2] <= STOP_Z_M:
            self.arrived()

    def arrived(self):
        marker = self.active_id
        self.reached.add(marker)
        self.pause("umbral_z")
        self.report(f"ARRIVED {marker}")

    def pause(self, reason):
        if self.align_until or self.scan_until:
            self.rest_after_turn()
        else:
            self.send("S")
        self.active_id = self.target = self.last_command = None
        self.driving = self.turning = False
        self.center_frames = 0
        self.resume_after = max(self.resume_after, time.monotonic() + INTERLOCK_S)
        self.activated_at = time.monotonic_ns()
        self.searchable.clear()
        self.report(f"WAIT {reason}")

    def rest_after_turn(self):
        self.send("S")
        self.scan_until = self.align_until = 0.0
        self.driving = False
        self.center_frames = 0
        self.resume_after = time.monotonic() + TURN_REST_S

    def enable(self, request, response):
        if not request.data:
            self.stop("orden_manual")
            response.success, response.message = True, "Parada solicitada"
        elif self.disconnected.is_set():
            response.success, response.message = False, "Puente desconectado"
        elif self.armed:
            response.success, response.message = False, "Sesión ya armada"
        else:
            self.armed = True
            self.reached.clear()
            self.last_stamps.clear()
            self.searchable.clear()
            self.activated_at = time.monotonic_ns()
            self.report("ARMED esperando_aruco")
            response.success, response.message = True, "Armado. Esperando el primer ArUco válido"
        return response

    def drive(self, starting=False):
        stamp, (x, _, z) = self.target
        age_limit = MAX_AGE_NS if starting else TRACK_MAX_AGE_NS
        angle = degrees(atan2(x, z))
        needs_turn = abs(angle) > (2.0 if self.turning else 4.0)
        direction = ("L" if angle < 0 else "R") if needs_turn else "F"
        now = time.monotonic()
        if self.align_until:
            if now >= self.align_until or direction != self.last_command:
                self.rest_after_turn()
                return
        elif needs_turn:
            if self.driving:
                self.send("S")
                self.driving = False
                self.center_frames = 0
                self.resume_after = now + INTERLOCK_S
                return
            self.align_until = now + TURN_BURST_S
        elif starting and self.center_frames < 2:
            return
        self.turning = needs_turn
        self.driving = True
        self.send("C" + direction if starting else direction, stamp + age_limit)
        if direction != self.last_command:
            self.report(f"DRIVE {direction} x={x:.3f} z={z:.3f} angulo={angle:.1f}")
            self.last_command = direction

    def tick(self):
        if self.disconnected.is_set():
            raise ExternalShutdownException()
        if not self.armed:
            return
        now = time.monotonic()
        if self.target is not None:
            stamp, xyz = self.target
            age = time.monotonic_ns() - stamp
            if self.driving:
                if -FUTURE_NS <= age <= TRACK_MAX_AGE_NS:
                    self.drive()
                else:
                    self.pause("esperando_aruco")
            elif (now >= self.resume_after and stamp >= round(self.resume_after * 1e9)
                  and -FUTURE_NS <= age <= START_MAX_AGE_NS):
                if xyz[2] > STOP_Z_M:
                    self.drive(starting=True)
                else:
                    self.arrived()
            elif age > TRACK_MAX_AGE_NS:
                self.active_id = self.target = None
                self.report("WAIT esperando_aruco")
        elif now >= self.resume_after:
            self.scan(now)

    def scan(self, now):
        oldest = min((self.searchable.get(mid, 0) for mid in self.route if mid not in self.reached), default=0)
        age = time.monotonic_ns() - oldest
        deadline = oldest + TRACK_MAX_AGE_NS
        fresh = oldest and -FUTURE_NS <= age <= TRACK_MAX_AGE_NS
        if self.scan_until:
            if now >= self.scan_until or not fresh:
                self.rest_after_turn()
            else:
                self.send("Q", deadline)
        elif fresh and age <= MAX_AGE_NS and oldest >= round(self.resume_after * 1e9):
            self.scan_until = now + TURN_BURST_S
            self.send("CQ", deadline)
            self.report("SCAN buscando_aruco")
        if not fresh and self.last_state != "ARMED esperando_aruco":
            self.report("WAIT esperando_aruco")


def watch_parent(disconnected):
    try:
        # El puente conserva stdin abierto hasta terminar. No hay comandos por stdin.
        os.read(sys.stdin.fileno(), 1)
    finally:
        disconnected.set()


def main():
    domain = int(os.getenv("ROS_DOMAIN_ID", "0"))
    lock = Path(tempfile.gettempdir()) / f"physalis-drv8833-{os.getuid()}-{domain}.lock"
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Ya hay un controlador DRV8833 en este dominio ROS")
        disconnected = Event()
        Thread(target=watch_parent, args=(disconnected,), daemon=True).start()
        rclpy.init()
        node = Controller(disconnected)
        try:
            if node.declare_parameter("bridge_ready", False).value:
                print("CONTROLLER_READY", flush=True)
            rclpy.spin(node)
        except (ExternalShutdownException, KeyboardInterrupt):
            pass
        finally:
            try:
                node.send("S")
            except OSError:
                pass
            node.destroy_node()
            rclpy.try_shutdown()
