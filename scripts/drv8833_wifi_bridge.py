"""Puente WiFi: controlador ROS 2 (WSL) ↔ ESP32 con firmware/drv8833_wifi.

Reutiliza sin cambios el protocolo del puente USB de PhysalisHarvest
(open_link, exchange, read_command y la medición del reloj WSL); solo
sustituye el puerto serie por una conexión TCP autenticada.

Comprobar identidad y parada sin ROS ni movimiento:

    python scripts/drv8833_wifi_bridge.py --host 192.168.4.1 --check

Servos del PCA9685: mientras el puente corre (con ROS o con --solo-servos),
escucha en 127.0.0.1:3334 y reenvía al ESP32 las órdenes de
scripts/servo_wifi.py por la misma conexión autenticada.

El token se lee de DRV8833_WIFI_TOKEN o de firmware/drv8833_wifi/wifi_config.h.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from queue import Empty, Queue
import re
import socket
import subprocess
import sys
from threading import Thread
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "contributions/physalisharvest/firmware/bench_2wd/tools"
CONFIG = ROOT / "firmware/drv8833_wifi/wifi_config.h"
DEFAULT_PORT = 3333
KEEPALIVE_S = 1.0  # menor que la expiración por inactividad del ESP32 (3 s)
BUSY_PROBE_S = 0.15  # espera de un rechazo inmediato antes de enviar el token
SERVO_PORT = 3334  # puerto local para scripts/servo_wifi.py
SERVO_REPLY_S = 2.0
SERVO_LINE = re.compile(r"(SV \d{1,2} \d{3,4}|SVOFF|SVQ|ENQ)")  # servos y encoders


def load_usb_bridge():
    """Carga el puente USB original como módulo, sin modificar el snapshot."""
    spec = spec_from_file_location("drv8833_ros_usb", TOOLS / "drv8833_ros_usb.py")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TcpPort:
    """Interfaz mínima de pyserial que usa el puente original, sobre TCP."""

    def __init__(self, sock: socket.socket, timeout: float):
        self.sock = sock
        self.timeout = timeout
        self.pending = bytearray()

    @classmethod
    def connect(cls, host, port, token, timeout=0.25, connect_timeout=3.0):
        sock = socket.create_connection((host, port), timeout=connect_timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        link = cls(sock, timeout)
        busy = "El ESP32 ya tiene un puente conectado. Cierra el otro primero."
        try:
            # El ESP32 rechaza con "ERR BUSY" al aceptar y cierra; se lee antes
            # de enviar el token, porque tras el cierre el SO puede descartarlo.
            try:
                greeting = link.readline(80, timeout=BUSY_PROBE_S)
            except ConnectionError:
                raise RuntimeError(busy) from None
            if greeting.strip() == b"ERR BUSY":
                raise RuntimeError(busy)
            if greeting:
                raise RuntimeError(f"Saludo inesperado del ESP32: {greeting!r}")
            try:
                link.write(f"AUTH {token}\n".encode("ascii"))
                reply = link.readline(80, timeout=connect_timeout).decode("ascii", "replace").strip()
            except ConnectionError as error:
                raise RuntimeError(
                    "El ESP32 cerró la conexión al autenticar: otro puente conectado o token incorrecto."
                ) from error
            if reply == "ERR BUSY":
                raise RuntimeError(busy)
            if reply != "AUTH OK":
                raise RuntimeError(f"El ESP32 rechazó el token ({reply or 'sin respuesta'}).")
        except BaseException:
            link.close()
            raise
        return link

    def write(self, data: bytes):
        self.sock.sendall(data)
        return len(data)

    def readline(self, limit, timeout=None):
        """Como pyserial: devuelve lo leído hasta '\\n', el límite o el plazo."""
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while b"\n" not in self.pending and len(self.pending) < limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(256)
            except socket.timeout:
                break
            if not chunk:
                raise ConnectionError("El ESP32 cerró la conexión")
            self.pending += chunk
        end = self.pending.find(b"\n")
        size = min(limit, end + 1 if end >= 0 else len(self.pending))
        line = bytes(self.pending[:size])
        del self.pending[:size]
        return line

    def reset_input_buffer(self):
        self.pending.clear()
        self.sock.setblocking(False)
        try:
            while self.sock.recv(256):
                pass
        except (BlockingIOError, InterruptedError):
            pass
        finally:
            self.sock.setblocking(True)

    def close(self):
        self.sock.close()


def servo_exchange(port, line):
    """Envía una orden SV/SVOFF/SVQ/ENQ y devuelve el acuse del ESP32."""
    if not SERVO_LINE.fullmatch(line):
        raise ValueError(f"Orden de servo inválida: {line!r}")
    port.write((line + "\n").encode("ascii"))
    reply = port.readline(256).decode("ascii", errors="replace").strip()
    if not reply.startswith(("OK SV", "ERR SV", "OK ENQ", "ERR EN")):
        raise RuntimeError(f"Acuse inesperado para {line}: {reply or 'sin respuesta'}")
    return reply


def probe_servos(port):
    """Estado de los servos, o None si el firmware cargado no los maneja."""
    try:
        return servo_exchange(port, "SVQ")
    except RuntimeError:
        return None


def probe_encoders(port):
    """Lectura de los encoders AS5600, o None si el firmware no los maneja."""
    try:
        return servo_exchange(port, "ENQ")
    except RuntimeError:
        return None


class ServoServer:
    """Recibe órdenes de servo en 127.0.0.1 y las encola para el bucle principal.

    Solo escucha en la máquina local; el bucle principal las envía por la
    conexión autenticada, intercaladas con las órdenes de los motores.
    """

    def __init__(self, events, port=SERVO_PORT):
        self.events = events
        self.sock = socket.create_server(("127.0.0.1", port))
        self.port = self.sock.getsockname()[1]
        Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                connection, _ = self.sock.accept()
            except OSError:
                return
            Thread(target=self._serve, args=(connection,), daemon=True).start()

    def _serve(self, connection):
        with connection, connection.makefile("rwb", buffering=0) as stream:
            for raw in stream:
                line = raw.decode("ascii", errors="replace").strip()
                if not line:
                    continue
                if SERVO_LINE.fullmatch(line):
                    replies = Queue()
                    self.events.put(("servo", line, replies))
                    try:
                        reply = replies.get(timeout=SERVO_REPLY_S)
                    except Empty:
                        reply = "ERR SV SIN RESPUESTA"
                else:
                    reply = "ERR SV FORMATO"
                try:
                    stream.write((reply + "\n").encode("ascii"))
                except OSError:
                    return

    def close(self):
        self.sock.close()


def answer_servo(port, line, replies):
    try:
        replies.put(servo_exchange(port, line))
    except BaseException:
        replies.put("ERR SV ENLACE")
        raise


def hold(port, usb, events):
    """Sin ROS: mantiene el enlace con "S" y atiende solo órdenes de servo."""
    while True:
        try:
            _, line, replies = events.get(timeout=KEEPALIVE_S)
        except Empty:
            usb.exchange(port, "S")
            continue
        answer_servo(port, line, replies)


def read_config(path=CONFIG):
    """Token y puerto de wifi_config.h, si existe."""
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8")
    token = re.search(r'#define\s+BRIDGE_TOKEN\s+"([^"]*)"', text)
    port = re.search(r"#define\s+BRIDGE_PORT\s+(\d+)", text)
    return (token.group(1) if token else None), (int(port.group(1)) if port else None)


def controller_command(distro, domain_id, route):
    sys.path.insert(0, str(ROOT / "src"))
    from uchuva_gazebo.physalisharvest_launch import create_launch_plan

    node_args = ["--ros-args", "-p", "bridge_ready:=true"]
    if route:
        node_args += ["-p", "ruta:=[" + ",".join(map(str, route)) + "]"]
    plan = create_launch_plan("controlador", ROOT, distro=distro, domain_id=domain_id,
                              node_args=node_args)
    if not plan.setup.is_file():
        raise RuntimeError("Falta la instalación ROS. Ejecuta: python scripts/physalisharvest_ros.py compilar")
    return plan.command


def relay(port, usb, command, measure, offset, events=None):
    """Reenvía las órdenes del controlador y de servos; mantiene viva la conexión."""
    events = Queue() if events is None else events
    with subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True, encoding="utf-8") as controller:

        def read():
            for line in controller.stdout:
                events.put(("ctl", line))
            events.put(("ctl", None))

        Thread(target=read, daemon=True).start()
        try:
            ready = False
            last_reply = None
            while True:
                try:
                    event = events.get(timeout=KEEPALIVE_S)
                except Empty:
                    # Sin órdenes durante 1 s el watchdog de 250 ms ya paró los
                    # motores; "S" confirma la parada y evita la expiración TCP.
                    usb.exchange(port, "S")
                    continue
                if event[0] == "servo":
                    answer_servo(port, event[1], event[2])
                    continue
                line = event[1]
                if line is None:
                    raise RuntimeError("El controlador ROS terminó. Revisa su diagnóstico.")
                if not ready:
                    if line.strip() != "CONTROLLER_READY":
                        raise RuntimeError("El controlador no confirmó su inicio")
                    ready = True
                    print("CONTROLLER_READY", flush=True)
                    continue
                try:
                    order = usb.read_command(line, time.monotonic_ns() + offset)
                except usb.CommandAgeError:
                    offset = measure(warm=True)
                    order = usb.read_command(line, time.monotonic_ns() + offset)
                reply = usb.exchange(port, order)
                if reply != last_reply or order == "S":
                    print(reply, flush=True)
                    last_reply = reply
        finally:
            try:
                controller.stdin.close()
                controller.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                controller.terminate()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True, help="IP del ESP32 (192.168.4.1 en modo punto de acceso)")
    parser.add_argument("--port", type=int, help=f"Puerto TCP (por defecto {DEFAULT_PORT} o el de wifi_config.h)")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--domain-id", type=int, default=83, choices=range(1, 102), metavar="1..101")
    parser.add_argument("--check", action="store_true", help="Comprueba identidad y parada sin iniciar ROS")
    parser.add_argument("--ruta", nargs="+", type=int, choices=range(50), metavar="ID")
    parser.add_argument("--solo-servos", action="store_true",
                        help="Sin ROS: mantiene el enlace y atiende solo órdenes de servo")
    parser.add_argument("--servo-port", type=int, default=SERVO_PORT,
                        help=f"Puerto local para scripts/servo_wifi.py (por defecto {SERVO_PORT}; 0 lo desactiva)")
    args = parser.parse_args(argv)
    if args.ruta and len(set(args.ruta)) != len(args.ruta):
        parser.error("La ruta requiere IDs únicos.")
    if args.solo_servos and (args.check or args.ruta):
        parser.error("--solo-servos no se combina con --check ni --ruta.")
    config_token, config_port = read_config()
    token = os.environ.get("DRV8833_WIFI_TOKEN") or config_token
    if not token:
        parser.error("Define DRV8833_WIFI_TOKEN o crea firmware/drv8833_wifi/wifi_config.h")
    port_number = args.port or config_port or DEFAULT_PORT

    usb = load_usb_bridge()
    port = None
    servo_server = None
    without_ros = args.check or args.solo_servos
    try:
        if not without_ros:
            sys.path.insert(0, str(TOOLS))
            from wsl_clock import clock_probe
        reference = nullcontext(None) if without_ros else clock_probe(args.distro)
        with reference as measure:
            offset = measure() if measure else 0
            try:
                port = TcpPort.connect(args.host, port_number, token)
            except OSError as error:
                raise RuntimeError(
                    f"No se pudo conectar a {args.host}:{port_number}. Confirma la red WiFi "
                    f"del ESP32 y su IP (el ESP32 la imprime por USB). Detalle: {error}"
                ) from error
            usb.open_link(port)
            print(usb.exchange(port, "S"), flush=True)
            servos = probe_servos(port)
            print(servos or "Firmware sin servos: carga la versión actual de firmware/drv8833_wifi.",
                  flush=True)
            if args.check:
                print(probe_encoders(port) or "Firmware sin encoders.", flush=True)
                return 0
            events = Queue()
            if servos and args.servo_port:
                servo_server = ServoServer(events, args.servo_port)
                print(f"SERVOS 127.0.0.1:{servo_server.port}", flush=True)
            elif args.solo_servos:
                raise RuntimeError("--solo-servos necesita un firmware con servos y --servo-port")
            if args.solo_servos:
                hold(port, usb, events)
            else:
                relay(port, usb, controller_command(args.distro, args.domain_id, args.ruta),
                      measure, offset, events)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Puente WiFi DRV8833 cerrado: {error}", file=sys.stderr)
        return 1
    finally:
        if servo_server is not None:
            servo_server.close()
        if port is not None:
            try:
                print(usb.exchange(port, "S"), flush=True)
            except (OSError, RuntimeError):
                print("Sin acuse de parada. Usa el corte físico; el watchdog del ESP32 "
                      "para los motores en 250 ms sin órdenes.", file=sys.stderr)
            port.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
