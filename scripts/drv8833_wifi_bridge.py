"""Puente WiFi: controlador ROS 2 (WSL) ↔ ESP32 con firmware/drv8833_wifi.

Reutiliza sin cambios el protocolo del puente USB de PhysalisHarvest
(open_link, exchange, read_command y la medición del reloj WSL); solo
sustituye el puerto serie por una conexión TCP autenticada.

Comprobar identidad y parada sin ROS ni movimiento:

    python scripts/drv8833_wifi_bridge.py --host 192.168.4.1 --check

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


def relay(port, usb, command, measure, offset):
    """Reenvía las órdenes del controlador; mantiene viva la conexión en reposo."""
    with subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          text=True, encoding="utf-8") as controller:
        lines = Queue()

        def read():
            for line in controller.stdout:
                lines.put(line)
            lines.put(None)

        Thread(target=read, daemon=True).start()
        try:
            ready = False
            last_reply = None
            while True:
                try:
                    line = lines.get(timeout=KEEPALIVE_S)
                except Empty:
                    # Sin órdenes durante 1 s el watchdog de 250 ms ya paró los
                    # motores; "S" confirma la parada y evita la expiración TCP.
                    usb.exchange(port, "S")
                    continue
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
    args = parser.parse_args(argv)
    if args.ruta and len(set(args.ruta)) != len(args.ruta):
        parser.error("La ruta requiere IDs únicos.")
    config_token, config_port = read_config()
    token = os.environ.get("DRV8833_WIFI_TOKEN") or config_token
    if not token:
        parser.error("Define DRV8833_WIFI_TOKEN o crea firmware/drv8833_wifi/wifi_config.h")
    port_number = args.port or config_port or DEFAULT_PORT

    usb = load_usb_bridge()
    port = None
    try:
        if not args.check:
            sys.path.insert(0, str(TOOLS))
            from wsl_clock import clock_probe
        reference = nullcontext(None) if args.check else clock_probe(args.distro)
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
            if not args.check:
                relay(port, usb, controller_command(args.distro, args.domain_id, args.ruta),
                      measure, offset)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Puente WiFi DRV8833 cerrado: {error}", file=sys.stderr)
        return 1
    finally:
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
