"""Mueve servos del PCA9685 a través del puente WiFi que ya está corriendo.

El puente (scripts/drv8833_wifi_bridge.py, con ROS o con --solo-servos) tiene
la única conexión autenticada con el ESP32; este script le pasa órdenes por
127.0.0.1 y muestra el acuse del ESP32.

    python scripts/servo_wifi.py 0 1500     canal 0 a 1500 us
    python scripts/servo_wifi.py estado     posición actual/objetivo
    python scripts/servo_wifi.py off        todos los servos sin pulso

El ESP32 rechaza pulsos fuera del rango de cada canal (wifi_config.h) y limita
la velocidad de movimiento.
"""
from __future__ import annotations

import argparse
import socket
import sys

DEFAULT_PORT = 3334


def order_from(words):
    if words == ["estado"]:
        return "SVQ"
    if words == ["off"]:
        return "SVOFF"
    if len(words) == 2 and all(word.isdigit() for word in words):
        channel, pulse = map(int, words)
        if not 0 <= channel <= 15:
            raise ValueError("El canal va de 0 a 15")
        if not 500 <= pulse <= 2500:
            raise ValueError("El pulso va de 500 a 2500 us")
        return f"SV {channel} {pulse}"
    raise ValueError("Usa: <canal> <us>, estado u off")


def send(order, port=DEFAULT_PORT, timeout=3.0):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.sendall((order + "\n").encode("ascii"))
            with sock.makefile("rb") as stream:
                reply = stream.readline().decode("ascii", errors="replace").strip()
    except OSError as error:
        raise RuntimeError(
            f"No hay puente en 127.0.0.1:{port}. Inicia scripts/drv8833_wifi_bridge.py "
            f"(con ROS o con --solo-servos). Detalle: {error}"
        ) from error
    if not reply:
        raise RuntimeError("El puente cerró la conexión sin responder")
    return reply


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("orden", nargs="+", help="<canal> <us> | estado | off")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto local del puente (por defecto {DEFAULT_PORT})")
    args = parser.parse_args(argv)
    try:
        order = order_from(args.orden)
    except ValueError as error:
        parser.error(str(error))
    try:
        reply = send(order, args.port)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    print(reply)
    return 0 if reply.startswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
