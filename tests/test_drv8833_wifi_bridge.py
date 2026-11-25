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
_servo_spec = spec_from_file_location("servo_wifi", ROOT / "scripts/servo_wifi.py")
servo_cli = module_from_spec(_servo_spec)
_servo_spec.loader.exec_module(servo_cli)

TOKEN = "token-de-prueba-0123456789"
REPLIES = {"ID": "DRV8833_ROS_V5", "S": "OK S 0000", "CF": "OK CF 1010", "F": "OK F 1010",
           "SVQ": "OK SVQ -", "SVOFF": "OK SVOFF", "SV 0 1500": "OK SV 0 1500",
           "SV 0 2400": "ERR SV RANGO 1000-2000"}


class FakeEsp32:
    """Acepta un cliente, exige AUTH y responde como DRV8833_ROS_V5."""

    def __init__(self, busy=False, close_after=None, servos=True):
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.busy = busy
        self.close_after = close_after
        self.servos = servos
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
                reply = REPLIES.get(command, "ERR COMMAND")
                if not self.servos and command.startswith("SV"):
                    reply = "ERR COMMAND"  # firmware anterior, sin servos
                stream.write((reply + "\n").encode())

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
        self.assertEqual(esp.received, ["ID", "S", "SVQ", "S"])  # identidad, parada, servos, parada
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


class ServoTests(unittest.TestCase):
    def test_servo_exchange_and_probe(self):
        esp = FakeEsp32()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        self.assertEqual(wifi.probe_servos(port), "OK SVQ -")
        self.assertEqual(wifi.servo_exchange(port, "SV 0 1500"), "OK SV 0 1500")
        self.assertEqual(wifi.servo_exchange(port, "SV 0 2400"), "ERR SV RANGO 1000-2000")
        with self.assertRaises(ValueError):
            wifi.servo_exchange(port, "CF")  # no se pueden colar órdenes de motor
        port.close()
        esp.stop()
        self.assertEqual(esp.received, ["SVQ", "SV 0 1500", "SV 0 2400"])

    def test_old_firmware_without_servos_is_detected(self):
        esp = FakeEsp32(servos=False)
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        self.assertIsNone(wifi.probe_servos(port))
        port.close()
        esp.stop()

    def test_servo_cli_reaches_esp32_through_running_relay(self):
        esp = FakeEsp32()
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        events = wifi.Queue()
        server = wifi.ServoServer(events, 0)
        replies = []
        controller = (
            "import time\n"
            "print('CONTROLLER_READY', flush=True)\n"
            "time.sleep(0.6)\n"
        )

        def operator():
            replies.append(servo_cli.send("SV 0 1500", server.port))
            replies.append(servo_cli.send("CF", server.port))  # rechazado localmente
            replies.append(servo_cli.send("SVOFF", server.port))

        Thread(target=operator, daemon=True).start()
        with redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "controlador ROS terminó"):
                wifi.relay(port, usb, [sys.executable, "-c", controller], lambda warm=False: 0, 0,
                           events)
        server.close()
        port.close()
        esp.stop()
        self.assertEqual(replies, ["OK SV 0 1500", "ERR SV FORMATO", "OK SVOFF"])
        self.assertIn("SV 0 1500", esp.received)
        self.assertNotIn("CF", esp.received)

    def test_servo_only_mode_keeps_link_alive_and_stops_on_link_loss(self):
        esp = FakeEsp32(close_after=3)
        usb = wifi.load_usb_bridge()
        port = wifi.TcpPort.connect("127.0.0.1", esp.port, TOKEN)
        events = wifi.Queue()
        replies = wifi.Queue()
        events.put(("servo", "SV 0 1500", replies))
        with patch.object(wifi, "KEEPALIVE_S", 0.05):
            with self.assertRaises((ConnectionError, RuntimeError)):
                wifi.hold(port, usb, events)
        port.close()
        esp.stop()
        self.assertEqual(replies.get_nowait(), "OK SV 0 1500")
        self.assertEqual(esp.received[:2], ["SV 0 1500", "S"])

    def test_cli_validates_orders_before_sending(self):
        self.assertEqual(servo_cli.order_from(["3", "1500"]), "SV 3 1500")
        self.assertEqual(servo_cli.order_from(["estado"]), "SVQ")
        self.assertEqual(servo_cli.order_from(["off"]), "SVOFF")
        for words in (["16", "1500"], ["0", "3000"], ["0"], ["mover"]):
            with self.assertRaises(ValueError):
                servo_cli.order_from(words)

    def test_cli_reports_missing_bridge(self):
        unused = socket.create_server(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        unused.close()
        errors = StringIO()
        with redirect_stderr(errors):
            self.assertEqual(servo_cli.main(["estado", "--port", str(port)]), 1)
        self.assertIn("No hay puente", errors.getvalue())


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
