"""Puente local Windows ↔ controlador ROS 2 en WSL ↔ ESP32 por USB."""

import argparse
from contextlib import nullcontext, suppress
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Event, Thread
import time


FIRMWARE = "DRV8833_ROS_V5"
PATTERNS = {"F": "1010", "L": "0110", "R": "1001", "Q": "0110", "S": "0000"}
MOVEMENT = {"CF", "CL", "CR", "CQ", "F", "L", "R", "Q"}
MAX_QUEUE_NS = 125_000_000


class CommandAgeError(ValueError):
    pass


def open_link(port):
    # El ESP32 puede tardar en salir del reinicio al abrir USB.
    until = time.monotonic() + 4
    while time.monotonic() < until:
        port.reset_input_buffer()
        port.write(b"ID\n")
        reply = port.readline(80).decode("ascii", errors="replace").strip()
        if reply == FIRMWARE:
            print(reply, flush=True)
            return
        if "_ROS_V" in reply:
            raise RuntimeError(f"Firmware incompatible ({reply}). Carga {FIRMWARE} con VM cortada.")
        if reply == "ERR PWM":
            raise RuntimeError("El ESP32 bloqueó el movimiento por un fallo de inicialización PWM.")
        time.sleep(0.15)
    raise RuntimeError(
        f"Sin respuesta {FIRMWARE}. Confirma la carga y pulsa EN/RESET con BOOT suelto y VM cortada."
    )


def exchange(port, command):
    port.write((command + "\n").encode("ascii"))
    reply = port.readline(80).decode("ascii", errors="replace").strip()
    expected = {f"OK {command} {PATTERNS[command[-1]]}"}
    if command in MOVEMENT:
        expected.add(f"OK {command} 0000")
    if reply not in expected:
        raise RuntimeError(f"Acuse inesperado para {command}: {reply or 'sin respuesta'}")
    return reply


def read_command(line, now_ns):
    prefix, stamp, deadline, command = line.split()
    if prefix != "CMD" or command not in MOVEMENT | {"S"}:
        raise ValueError("Orden interna inválida")
    if command in MOVEMENT and (
        not -30_000_000 <= now_ns - int(stamp) <= MAX_QUEUE_NS or now_ns >= int(deadline)
    ):
        age = (now_ns - int(stamp)) / 1e6
        remaining = (int(deadline) - now_ns) / 1e6
        raise CommandAgeError(f"Orden vencida (edad {age:.0f} ms, margen {remaining:.0f} ms). Revisa Windows/WSL.")
    return command


def run(port, args, shutdown=None, measure=None):
    root = Path(__file__).resolve().parents[3]
    shell = (
        "source /opt/ros/jazzy/setup.bash && source install/setup.bash && "
        f"export ROS_DOMAIN_ID={args.domain_id} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST && "
        "exec ros2 run bench_2wd_drv8833 controller"
    )
    parameters = ["-p bridge_ready:=true"] if shutdown is not None else []
    if route := getattr(args, "ruta", None):
        parameters.append("-p 'ruta:=[" + ",".join(map(str, route)) + "]'")
    if parameters:
        shell += " --ros-args " + " ".join(parameters)
    with subprocess.Popen(
        ["wsl.exe", "-d", args.distro, "--cd", str(root / "ros2_ws"), "--", "bash", "-lc", shell],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
    ) as controller:
        try:
            last_reply = None
            def lines():
                if shutdown is None:
                    yield from controller.stdout
                    return
                pending = Queue()

                def read():
                    for line in controller.stdout:
                        pending.put(line)
                    pending.put(None)

                Thread(target=read, daemon=True).start()
                while not shutdown.is_set():
                    try:
                        line = pending.get(timeout=0.05)
                    except Empty:
                        continue
                    if line is None:
                        return
                    yield line

            ready = shutdown is None
            for line in lines():
                if shutdown is not None and shutdown.is_set():
                    break
                if not ready and line.strip() == "CONTROLLER_READY":
                    ready = True
                    print("CONTROLLER_READY", flush=True)
                    continue
                if not ready:
                    raise RuntimeError("El controlador administrado no confirmó su inicio")
                offset = getattr(args, "clock_offset_ns", 0)
                if measure is not None and line.rstrip().endswith((" CF", " CL", " CR")):
                    offset = args.clock_offset_ns = measure(warm=True)
                try:
                    command = read_command(line, time.monotonic_ns() + offset)
                except CommandAgeError:
                    if measure is None:
                        raise
                    offset = args.clock_offset_ns = measure(warm=True)
                    command = read_command(line, time.monotonic_ns() + offset)
                reply = exchange(port, command)
                if reply != last_reply or command == "S":
                    print(reply, flush=True)
                    last_reply = reply
            if not (shutdown is not None and shutdown.is_set()) and controller.wait(timeout=2):
                raise RuntimeError("El controlador ROS terminó. Revisa su diagnóstico en esta terminal.")
        finally:
            try:
                print(exchange(port, "S"), flush=True)
            except (OSError, RuntimeError) as error:
                print(f"Sin acuse de parada. Usa el corte físico. {error}", file=sys.stderr)
            with suppress(OSError):
                controller.stdin.close()
            try:
                controller.wait(timeout=2)
            except subprocess.TimeoutExpired:
                controller.terminate()


def main():
    import serial
    from wsl_clock import clock_probe

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--domain-id", type=int, default=83, choices=range(1, 102), metavar="1..101")
    parser.add_argument("--check", action="store_true", help="Comprueba identidad y parada sin iniciar ROS")
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ruta", nargs="+", type=int, choices=range(50), metavar="ID")
    args = parser.parse_args()
    if args.ruta and len(set(args.ruta)) != len(args.ruta):
        parser.error("La ruta requiere IDs únicos.")
    shutdown = Event() if args.managed else None
    if shutdown is not None:
        def watch():
            try:
                os.read(sys.stdin.fileno(), 1)
            finally:
                shutdown.set()

        Thread(target=watch, daemon=True).start()
    try:
        reference = nullcontext(None) if args.check else clock_probe(args.distro)
        with reference as measure, serial.Serial(baudrate=115200, timeout=0.10, write_timeout=0.10) as port:
            if measure:
                args.clock_offset_ns = measure()
            port.dtr = port.rts = False
            port.port = args.port
            try:
                port.open()
            except serial.SerialException as error:
                raise RuntimeError(
                    f"No se pudo abrir {args.port}. Confirma el puerto y cierra el Monitor Serie "
                    f"o el puente anterior. Detalle: {error}"
                ) from error
            open_link(port)
            print(exchange(port, "S"), flush=True)
            if not args.check and (shutdown is None or not shutdown.is_set()):
                run(port, args, shutdown, measure)
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"Puente DRV8833 cerrado: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
