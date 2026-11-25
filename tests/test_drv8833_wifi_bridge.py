"""WiFi bridge against a local fake ESP32; no radio, ROS or motors."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import os
from pathlib import Path
import socket
import sys
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
_spec = spec_from_file_location("drv8833_wifi_bridge", ROOT / "scripts/drv8833_wifi_bridge.py")
wifi = module_from_spec(_spec)
_spec.loader.exec_module(wifi)

TOKEN = "token-de-prueba-0123456789"
REPLIES = {"ID": "DRV8833_ROS_V5", "S": "OK S 0000", "CF": "OK CF 1010", "F": "OK F 1010"}


class FakeEsp32:
    """Acepta un cliente, exige AUTH y responde como DRV8833_ROS_V5."""

    def __init__(self, busy=False, close_after=None):
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.busy = busy
        self.close_after = close_after
        self.received = []
        self.thread = Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        connection, _ = self.server.accept()
        with connection, connection.makefile("rwb", buffering=0) as stream:
            if self.busy:
                stream.write(b"ERR BUSY\n")
                return
            auth = stream.readline().decode().strip()
            if auth != f"AUTH {TOKEN}":
                stream.write(b"AUTH ERR\n")
                return
            stream.write(b"AUTH OK\n")
            for raw in stream:
                command = raw.decode().strip()
                self.received.append(command)
                if self.close_after is not None and len(self.received) >= self.close_after:
                    return
                stream.write((REPLIES.get(command, "ERR COMMAND") + "\n").encode())

    def stop(self):
        self.server.close()
        self.thread.join(timeout=2)


class TcpPortTests(unittest.TestCase):
    def test_auth_identity_and_stop_with_original_protocol(self):
        esp = FakeEsp32()
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        with redirect_stdout(StringIO()):
            usb.open_link(port)
        self.assertEqual(usb.exchange(port, "S"), "OK S 0000")
        self.assertEqual(usb.exchange(port, "CF"), "OK CF 1010")
        port.close()
        esp.stop()
        self.assertEqual(esp.received, ["ID", "S", "CF"])

    def test_wrong_token_and_busy_slot_are_rejected(self):
        esp = FakeEsp32()
        with self.assertRaisesRegex(RuntimeError, "rechazó el token"):
            wifi.TcpPort.connect("127.0.0.1", esp.port, "otro-token-cualquiera")
        esp.stop()
        busy = FakeEsp32(busy=True)
        with self.assertRaisesRegex(RuntimeError, "ya tiene un puente"):
            wifi.TcpPort.connect("127.0.0.1", busy.port, TOKEN)
        busy.stop()

    def test_readline_matches_pyserial_timeouts_and_drain(self):
        left, right = socket.socketpair()
        port = wifi.TcpPort(left, timeout=0.05)
        self.assertEqual(port.readline(80), b"")  # plazo vencido sin datos
        right.sendall(b"OK S 0000\nresto")
        self.assertEqual(port.readline(80), b"OK S 0000\n")
        self.assertEqual(port.readline(80), b"resto")  # línea parcial al vencer
        right.sendall(b"basura\n")
        port.reset_input_buffer()
        self.assertEqual(port.readline(80), b"")
        right.close()
        with self.assertRaises(ConnectionError):
            port.readline(80)
        port.close()

    def test_exchange_fails_when_esp32_disconnects(self):
        esp = FakeEsp32(close_after=1)
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        with self.assertRaises((ConnectionError, RuntimeError)):
            usb.exchange(port, "S")
        port.close()
        esp.stop()


class BridgeFlowTests(unittest.TestCase):
    def test_check_mode_reads_token_from_environment(self):
        esp = FakeEsp32()
        output = StringIO()
        with patch.dict(os.environ, {"DRV8833_WIFI_TOKEN": TOKEN}), redirect_stdout(output):
            code = wifi.main(["--host", "127.0.0.1", "--port", str(esp.port), "--check"])
        esp.stop()
        self.assertEqual(code, 0)
        self.assertEqual(esp.received, ["ID", "S", "S"])  # identidad, parada, parada final
        self.assertIn("DRV8833_ROS_V5", output.getvalue())

    def test_unreachable_host_reports_network_hint(self):
        unused = socket.create_server(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        unused.close()
        errors = StringIO()
        with patch.dict(os.environ, {"DRV8833_WIFI_TOKEN": TOKEN}), redirect_stderr(errors):
            code = wifi.main(["--host", "127.0.0.1", "--port", str(port), "--check"])
        self.assertEqual(code, 1)
        self.assertIn("No se pudo conectar", errors.getvalue())

    def test_relay_forwards_controller_orders_and_keeps_link_alive(self):
        esp = FakeEsp32()
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        controller = (
            "import time\n"
            "print('CONTROLLER_READY', flush=True)\n"
            "now = time.monotonic_ns()\n"
            "print(f'CMD {now} {now + 300_000_000} CF', flush=True)\n"
            "time.sleep(0.5)\n"
        )
        with patch.object(wifi, "KEEPALIVE_S", 0.15), redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "controlador ROS terminó"):
                wifi.relay(port, usb, [sys.executable, "-c", controller], lambda warm=False: 0, 0)
        port.close()
        esp.stop()
        self.assertEqual(esp.received[0], "CF")
        self.assertIn("S", esp.received[1:])  # keepalive en reposo

    def test_stale_controller_order_never_reaches_esp32(self):
        esp = FakeEsp32()
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        controller = (
            "import time\n"
            "print('CONTROLLER_READY', flush=True)\n"
            "old = time.monotonic_ns() - 2_000_000_000\n"
            "print(f'CMD {old} {old + 300_000_000} CF', flush=True)\n"
            "time.sleep(0.3)\n"
        )
        with redirect_stdout(StringIO()):
            with self.assertRaises(ValueError):
                wifi.relay(port, usb, [sys.executable, "-c", controller], lambda warm=False: 0, 0)
        port.close()
        esp.stop()
        self.assertNotIn("CF", esp.received)


class ConfigTests(unittest.TestCase):
    def test_token_and_port_come_from_wifi_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "wifi_config.h"
            path.write_text('#define BRIDGE_PORT 4444\n#define BRIDGE_TOKEN "abc-0123456789xyz"\n',
                            encoding="utf-8")
            self.assertEqual(wifi.read_config(path), ("abc-0123456789xyz", 4444))
            self.assertEqual(wifi.read_config(Path(folder) / "missing.h"), (None, None))


if __name__ == "__main__":
    unittest.main()
