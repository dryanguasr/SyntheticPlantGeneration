"""Pruebas del protocolo Windows sin abrir un puerto."""

from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_spec = spec_from_file_location("bridge", Path(__file__).parents[1] / "drv8833_ros_usb.py")
bridge = module_from_spec(_spec)
_spec.loader.exec_module(bridge)


class MockPort:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.commands = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.commands.append(data)

    def readline(self, limit):
        return next(self.replies)


class BridgeTests(unittest.TestCase):
    def test_incompatible_firmware(self):
        port = MockPort(b"DRV8833_ROS_V4\n")
        with self.assertRaisesRegex(RuntimeError, "Firmware incompatible"):
            bridge.open_link(port)
        self.assertEqual(port.commands, [b"ID\n"])

    def test_scan_uses_v5_and_its_own_commands(self):
        port = MockPort(b"DRV8833_ROS_V5\n", b"OK CQ 0110\n", b"OK Q 0110\n")
        bridge.open_link(port)
        self.assertEqual(bridge.read_command("CMD 100000000 300000000 CQ", 125000000), "CQ")
        self.assertEqual(bridge.exchange(port, "CQ"), "OK CQ 0110")
        self.assertEqual(bridge.exchange(port, "Q"), "OK Q 0110")
        self.assertEqual(port.commands, [b"ID\n", b"CQ\n", b"Q\n"])

    def test_interlock_and_invalid_ack(self):
        port = MockPort(b"OK R 0000\n", b"OK R 1001\n", b"OK R 0110\n")
        self.assertEqual(bridge.exchange(port, "R"), "OK R 0000")
        self.assertEqual(bridge.exchange(port, "R"), "OK R 1001")
        with self.assertRaisesRegex(RuntimeError, "Acuse inesperado"):
            bridge.exchange(port, "R")

    def test_deadline_and_queue(self):
        self.assertEqual(bridge.read_command("CMD 100000000 300000000 CF", 125000000), "CF")
        with self.assertRaises(ValueError):
            bridge.read_command("CMD 100000000 110000000 CF", 110000000)
        with self.assertRaises(ValueError):
            bridge.read_command("CMD 100000000 400000000 L", 250000000)
        with self.assertRaises(ValueError):
            bridge.read_command("CMD 100000000 400000000 C", 125000000)
        self.assertEqual(bridge.read_command("CMD 1 0 S", 500000000), "S")

    def test_managed_bridge_requires_its_own_controller_ready(self):
        stamp = time.monotonic_ns()
        port = MockPort(b"OK CF 1010\n", b"OK S 0000\n")
        child = SimpleNamespace(
            stdin=StringIO(),
            stdout=StringIO(f"CONTROLLER_READY\nCMD {stamp} {stamp + 500_000_000} CF\n"),
            wait=lambda timeout: 0,
        )
        args = SimpleNamespace(distro="Ubuntu-24.04", domain_id=91)
        with patch.object(bridge.subprocess, "Popen") as spawn:
            spawn.return_value.__enter__.return_value = child
            with patch.object(bridge.time, "monotonic_ns", return_value=stamp + 1):
                bridge.run(port, args, Event())
        self.assertEqual(port.commands, [b"CF\n", b"S\n"])
        self.assertTrue(child.stdin.closed)

    def test_managed_bridge_stops_if_startup_handshake_is_missing(self):
        port = MockPort(b"OK S 0000\n")
        child = SimpleNamespace(stdin=StringIO(), stdout=StringIO("CMD 1 2 CF\n"),
                                wait=lambda timeout: 0)
        args = SimpleNamespace(distro="Ubuntu-24.04", domain_id=91)
        with patch.object(bridge.subprocess, "Popen") as spawn:
            spawn.return_value.__enter__.return_value = child
            with self.assertRaisesRegex(RuntimeError, "no confirmó"):
                bridge.run(port, args, Event())
        self.assertEqual(port.commands, [b"S\n"])
