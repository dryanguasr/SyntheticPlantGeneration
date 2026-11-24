"""Prueba ROS 2 de integración con tuberías y sin puente físico."""

from contextlib import contextmanager
import json
import queue
import subprocess
import sys
from threading import Thread
import time

import pytest

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool

from bench_2wd_drv8833.controller import ROOT
from bench_2wd_drv8833 import aruco_source


def test_source_distinguishes_latency_from_clock_skew(monkeypatch):
    now = 2_000_000_000
    monkeypatch.setattr(aruco_source.time, "time_ns", lambda: now)
    assert aruco_source.message(json.dumps([now - 250_000_000, [0, 0, 0.8]])).point.z == 0.8
    assert aruco_source.message((now, "sin_profundidad")).point.z == -3.0
    with pytest.raises(aruco_source.ObservationAgeError, match="RGB-D retrasadas"):
        aruco_source.message(json.dumps([now - 250_000_001, [0, 0, 0.8]]))
    with pytest.raises(aruco_source.ObservationAgeError, match="desalineados"):
        aruco_source.message(json.dumps([now + 30_000_001, [0, 0, 0.8]]))
    assert aruco_source.message(json.dumps([now - 500_000_000, [0, 0, 0.8]]), 800_000_000).point.z == 0.8
    with pytest.raises(aruco_source.ObservationAgeError):
        aruco_source.message(json.dumps([now - 800_000_001, [0, 0, 0.8]]), 800_000_000)


@contextmanager
def process(module, *args):
    with subprocess.Popen(
        [sys.executable, "-c", f"from bench_2wd_drv8833.{module} import main; main()", *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    ) as child:
        lines = queue.Queue()
        def read_lines():
            for line in child.stdout:
                lines.put(line.strip())

        reader = Thread(target=read_lines, daemon=True)
        reader.start()
        try:
            yield child, lines
        finally:
            child.stdin.close()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            reader.join(timeout=1)
            assert child.returncode == 0


def test_ros_with_mock_serial_boundary(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "89")
    monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")
    rclpy.init()
    node = Node("drv8833_mock_test")
    try:
        with process("controller") as (_, commands), process("aruco_source") as (source, ready):
            assert ready.get(timeout=8) == "ARUCO_READY"
            client = node.create_client(SetBool, ROOT + "/enable")
            assert client.wait_for_service(timeout_sec=8)
            seen = []
            states = []
            state_subscription = node.create_subscription(
                String, ROOT + "/state", lambda msg: states.append(msg.data), 10
            )

            def drain():
                while not commands.empty():
                    line = commands.get_nowait()
                    assert len(line.split()) == 4
                    seen.append(line.split()[-1])

            def request(data):
                future = client.call_async(SetBool.Request(data=data))
                rclpy.spin_until_future_complete(node, future, timeout_sec=2)
                assert future.done() and future.result().success

            def feed(xyz, until=None, seconds=0.3):
                end = time.monotonic() + seconds
                seen.clear()
                while time.monotonic() < end:
                    source.stdin.write(json.dumps([time.time_ns(), xyz]) + "\n")
                    source.stdin.flush()
                    time.sleep(0.035)
                    drain()
                    if until in seen:
                        return
                assert until is None, (until, seen)

            # Armar sin cámara acepta la solicitud y no emite movimiento.
            request(True)
            feed(None)
            assert not seen
            feed([0, 0, 0.50], "S", 2)
            feed([0, 0, 0.80])
            assert not seen
            feed("ausente", "CQ", 2)
            feed([0, 0, 0.80], "CF", 5)
            feed([-0.12, 0, 0.80], "CL", 2)
            feed([0.12, 0, 0.80], "CR", 2)
            feed([0, 0, 0.80], "CF", 2)
            feed([0, 0, 0.50], "S", 1)
            feed([0, 0, 0.80])
            assert not seen

            feed("ausente", "CQ", 2)
            feed([0, 0, 0.80], "CF", 2)
            feed("sin_profundidad", "S", 2)
            feed("sin_profundidad", "CQ", 2)
            feed([0, 0, 0.80], "CF", 2)
            feed(None, "S", 1)
            feed([0, 0, 0.80], "CF", 2)
            rclpy.spin_once(node, timeout_sec=0)
            states.clear()
            until = time.monotonic() + 2
            seen.clear()
            while time.monotonic() < until:
                rclpy.spin_once(node, timeout_sec=0.035)
                drain()
                if "S" in seen and states and states[-1] == "WAIT esperando_aruco":
                    break
            assert "S" in seen
            assert states[-1] == "WAIT esperando_aruco"
            assert not any("observacion_vencida" in state for state in states)
            node.destroy_subscription(state_subscription)

            request(False)
            time.sleep(0.1)
            drain()
            feed([0, 0, 0.80])
            assert not seen
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_console_monitor_discovers_and_controls_real_ros_services(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "90")
    monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")
    with process("controller", "--ros-args", "-p", "bridge_ready:=true") as (_, commands), process(
        "monitor"
    ) as (monitor, events):
        def wait_event(predicate):
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                item = json.loads(events.get(timeout=max(0.01, deadline - time.monotonic())))
                if predicate(item):
                    return item
            raise AssertionError("Evento de consola ausente")

        def ask(sequence, enable, ticket=None):
            monitor.stdin.write(json.dumps({"id": sequence, "enable": enable,
                                            "ticket": ticket}) + "\n")
            monitor.stdin.flush()
            return wait_event(lambda item: item["kind"] == "response" and item["id"] == sequence)

        assert json.loads(events.get(timeout=8))["kind"] == "ready"
        assert commands.get(timeout=8) == "CONTROLLER_READY"
        graph = wait_event(lambda item: item["kind"] == "graph" and item["ready"])
        assert "/bench_2wd_drv8833_controller" in graph["nodes"]
        assert graph["services"][ROOT + "/enable"] == ["std_srvs/srv/SetBool"]
        assert graph["publishers"][ROOT + "/aruco_target"] == 0
        assert not ask(1, True, -1)["ok"]
        assert ask(2, True, graph["ticket"])["ok"]
        assert commands.empty()

        with process("aruco_source") as (source, ready):
            assert ready.get(timeout=8) == "ARUCO_READY"
            deadline = time.monotonic() + 5
            visible = False
            while time.monotonic() < deadline and not visible:
                source.stdin.write(json.dumps([time.time_ns() - 274_000_000, [0, 0, 0.8]]) + "\n")
                source.stdin.flush()
                time.sleep(0.05)
                while not events.empty():
                    item = json.loads(events.get_nowait())
                    if item["kind"] == "graph" and item["xyz"] is not None:
                        assert item["age"] >= 274
                        visible = True
            assert visible and commands.empty()
            deadline = time.monotonic() + 5
            sent = False
            while time.monotonic() < deadline and not sent:
                source.stdin.write(json.dumps([time.time_ns(), [0.0, 0.0, 0.8]]) + "\n")
                source.stdin.flush()
                time.sleep(0.04)
                while not commands.empty():
                    if commands.get_nowait().endswith(" CF"):
                        sent = True
                        break
            assert sent
            assert ask(3, False)["ok"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if commands.get(timeout=max(0.01, deadline - time.monotonic())).endswith(" S"):
                    break
            else:
                raise AssertionError("No llegó la orden serial de parada")


def test_diagnostic_publishes_delayed_xyz_on_separate_topic(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "92")
    monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")
    params = ("--ros-args", "-p", "diagnostico:=true")
    with process("aruco_source", *params) as (source, ready), process("monitor", *params) as (monitor, events):
        assert ready.get(timeout=8) == "ARUCO_READY"
        end = time.monotonic() + 8
        observed = False
        response = False
        monitor.stdin.write(json.dumps({"id": 1, "enable": True, "sent_ns": time.time_ns()}) + "\n")
        monitor.stdin.flush()
        while time.monotonic() < end and not (observed and response):
            source.stdin.write(json.dumps([time.time_ns() - 500_000_000, [0, 0, 0.8]]) + "\n")
            source.stdin.flush()
            time.sleep(0.05)
            while not events.empty():
                event = json.loads(events.get_nowait())
                if event["kind"] == "response":
                    assert not event["ok"] and "sin actuación" in event["text"]
                    response = True
                if event["kind"] == "graph" and event["xyz"] is not None:
                    assert event["xyz"][2] == 0.8 and event["age"] >= 495
                    assert ROOT + "/aruco_target_diagnostico" in event["topics"]
                    assert ROOT + "/aruco_target" not in event["topics"]
                    observed = True
        assert observed and response


def test_first_valid_marker_wins_and_tracking_has_no_session_timeout(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "94")
    monkeypatch.setenv("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST")
    params = ("--ros-args", "-p", "ruta:=[0,1,2]")
    rclpy.init()
    node = Node("drv8833_route_mock")
    try:
        with process("controller", *params) as (_, commands), process("aruco_source", *params) as (source, ready):
            assert ready.get(timeout=8) == "ARUCO_READY"
            client = node.create_client(SetBool, ROOT + "/enable")
            assert client.wait_for_service(timeout_sec=8)

            def arm():
                future = client.call_async(SetBool.Request(data=True))
                rclpy.spin_until_future_complete(node, future, timeout_sec=2)
                assert future.done() and future.result().success

            def stream(data, until=None, duration=1.0, age_ns=0, interval=.035):
                deadline = time.monotonic() + duration
                seen = []
                while time.monotonic() < deadline:
                    source.stdin.write(json.dumps([time.time_ns() - age_ns, data]) + "\n")
                    source.stdin.flush()
                    time.sleep(interval)
                    while not commands.empty():
                        seen.append(commands.get_nowait().split()[-1])
                    if until and until in seen:
                        return seen
                assert until is None, (until, seen)
                return seen

            arm()
            assert stream(dict.fromkeys(("0", "1", "2"), "invalido"), duration=.6) == []
            for marker in ("2", "0", "1"):
                frame = dict.fromkeys(("0", "1", "2"), "ausente")
                searching = stream(frame, "CQ", 3)
                assert not ({"F", "CF", "R", "CR"} & set(searching))
                frame[marker] = [-0.15, 0, 0.8]
                left = stream(frame, "CL", 2)
                assert left.index("S") < left.index("CL")
                assert not ({"CF", "F"} & set(left))
                frame[marker] = [0.15, 0, 0.8]
                right = stream(frame, "CR", 2)
                assert "S" in right
                assert not ({"CF", "F"} & set(right))
                frame[marker] = [0, 0, 0.8]
                settling = stream(frame, "S", 1)
                assert not ({"CF", "F"} & set(settling))
                assert stream(frame, duration=.25) == []
                time.sleep(.30)
                source.stdin.write(json.dumps([time.time_ns(), frame]) + "\n")
                source.stdin.flush()
                time.sleep(.10)
                assert commands.empty(), "Un solo cuadro centrado no autoriza avanzar"
                acquired = stream(frame, "CF", 2)
                assert "CF" in acquired
                if marker == "2":
                    frame["1"] = [0.2, 0, 0.8]
                    continuing = stream(frame, duration=8.3)
                    assert "F" in continuing and set(continuing) == {"F"}
                frame[marker] = [0, 0, 0.50]
                stream(frame, "S", 2)
            absent = dict.fromkeys(("0", "1", "2"), "ausente")
            stream(absent, "CQ", 2)
            scanning = stream(absent, duration=5.5)
            assert set(scanning) == {"CQ", "Q", "S"}
            stream(absent, "CQ", 2)
            stream({"0": "ausente", "1": [0, 0, .8], "2": "ausente"}, "CF", 2)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
