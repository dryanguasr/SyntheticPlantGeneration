"""Telemetría del grafo y cliente de control para la consola Windows."""

from collections import deque
from functools import partial
import json
from math import isfinite
import os
from queue import Empty, Queue
import sys
from threading import Thread
import time

from geometry_msgs.msg import PointStamped
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import SetBool

from bench_2wd_drv8833.controller import FRAME, ROOT, read_route, topic_for


def output(kind, **fields):
    print(json.dumps(dict(kind=kind, **fields), ensure_ascii=True, allow_nan=False), flush=True)


class Monitor(Node):
    def __init__(self, commands):
        super().__init__("bench_2wd_drv8833_console")
        self.commands = commands
        self.pending = {}
        self.observation = None
        self.arrivals = deque()
        self.diagnostic = self.declare_parameter("diagnostico", False).value
        self.route = read_route(self)
        self.active_id = None
        self.observed_id = None
        self.suffix = "_diagnostico" if self.diagnostic else "_visual"
        self.tickets = {}
        self.ticket_id = 0
        self.client = self.create_client(SetBool, ROOT + "/enable")
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)
        for marker_id in self.route:
            self.create_subscription(PointStamped, topic_for(marker_id) + self.suffix,
                                     partial(self.receive, marker_id=marker_id), qos)
        self.create_subscription(String, ROOT + "/state", self.state, 10)
        steady = Clock(clock_type=ClockType.STEADY_TIME)
        self.create_timer(0.5, self.snapshot, clock=steady)
        self.create_timer(0.05, self.poll, clock=steady)

    def state(self, msg):
        action, _, value = msg.data.partition(" ")
        if action == "TARGET" and value.isdecimal() and int(value) in self.route:
            self.active_id = int(value)
            self.observation = None
            self.arrivals.clear()
        elif action in {"WAIT", "SCAN", "STOP", "ARMED"}:
            self.active_id = None
        output("state", text=msg.data)

    def receive(self, msg, marker_id):
        if self.active_id is not None and marker_id != self.active_id:
            return
        xyz = [msg.point.x, msg.point.y, msg.point.z]
        self.arrivals.append(time.monotonic())
        if msg.header.frame_id != FRAME or xyz[2] <= 0 or not all(map(isfinite, xyz)):
            if marker_id == self.observed_id:
                self.observation = None
        else:
            stamp = msg.header.stamp
            age = time.time_ns() - (stamp.sec * 10**9 + stamp.nanosec)
            self.observation = (xyz, age, time.monotonic_ns())
            self.observed_id = marker_id

    def snapshot(self):
        now = time.monotonic()
        self.tickets = {ticket: end for ticket, end in self.tickets.items() if end >= now}
        ticket = None
        if not self.diagnostic and self.client.service_is_ready():
            self.ticket_id += 1
            ticket = self.ticket_id
            self.tickets[ticket] = now + 2.5
        while self.arrivals and now - self.arrivals[0] > 2.0:
            self.arrivals.popleft()
        hz = None
        if len(self.arrivals) > 1:
            hz = (len(self.arrivals) - 1) / max(0.001, self.arrivals[-1] - self.arrivals[0])
        xyz = age = None
        if self.observation:
            xyz, age_at_receive, received = self.observation
            age = (age_at_receive + time.monotonic_ns() - received) / 1e6
        topics = [topic_for(mid) for mid in self.route]
        topics += [topic + self.suffix for topic in topics]
        output(
            "graph", nodes=sorted(f"{ns.rstrip('/')}/{name}" for name, ns in self.get_node_names_and_namespaces()),
            topics=dict(self.get_topic_names_and_types()),
            services=dict(self.get_service_names_and_types()),
            ready=self.client.service_is_ready(),
            publishers={topic: self.count_publishers(topic) for topic in (*topics, ROOT + "/state")},
            hz=hz, xyz=xyz, age=age, ticket=ticket, marker=self.observed_id if xyz is not None else None,
        )

    def poll(self):
        for sequence, (future, deadline) in list(self.pending.items()):
            if future.done():
                response = future.result()
                output("response", id=sequence, ok=response.success, text=response.message)
            elif time.monotonic() >= deadline:
                self.client.remove_pending_request(future)
                output("response", id=sequence, ok=False, text="El servicio ROS no respondió a tiempo.")
            else:
                continue
            del self.pending[sequence]
        try:
            line = self.commands.get_nowait()
        except Empty:
            return
        if line is None:
            raise ExternalShutdownException()
        try:
            request = json.loads(line)
            sequence, enabled, ticket = request["id"], request["enable"], request.get("ticket")
            if type(sequence) is not int or type(enabled) is not bool:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            output("error", text="Solicitud local inválida.")
            return
        if self.diagnostic:
            output("response", id=sequence, ok=False, text="Modo de diagnóstico sin actuación.")
        elif enabled and (type(ticket) is not int or self.tickets.pop(ticket, 0) < time.monotonic()):
            output("response", id=sequence, ok=False, text="Se perdió la conexión con el monitor. Vuelve a pulsar Armar.")
        elif not self.client.service_is_ready():
            output("response", id=sequence, ok=False, text="Servicio de control ausente.")
        else:
            self.tickets.clear()
            future = self.client.call_async(SetBool.Request(data=enabled))
            self.pending[sequence] = (future, time.monotonic() + 1.5)


def main():
    commands = Queue()

    def read():
        buffered = b""
        while chunk := os.read(sys.stdin.fileno(), 4096):
            lines = (buffered + chunk).split(b"\n")
            buffered = lines.pop()
            for line in lines:
                commands.put(line)
        commands.put(None)

    rclpy.init()
    node = Monitor(commands)
    Thread(target=read, daemon=True).start()
    try:
        output("ready")
        rclpy.spin(node)
    except (ExternalShutdownException, KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
