"""Mueve los servos del brazo (PCA9685) a través del puente WiFi en marcha.

El puente (scripts/drv8833_wifi_bridge.py, con ROS o con --solo-servos) tiene
la única conexión autenticada con el ESP32; este script le pasa órdenes por
127.0.0.1 y muestra el acuse del ESP32.

    python scripts/servo_wifi.py J2 1500      articulación por nombre (J1-J5, gripper)
    python scripts/servo_wifi.py hombro 1500  o por alias (base, hombro, codo...)
    python scripts/servo_wifi.py 1 1500       o por canal del PCA9685
    python scripts/servo_wifi.py estado       posición actual/objetivo
    python scripts/servo_wifi.py off          todos los servos sin pulso
    python scripts/servo_wifi.py encoders     ángulo crudo de los AS5600 (J1-J5)
    python scripts/servo_wifi.py mapa         articulaciones, canales y rangos

Los nombres, canales y rangos vienen de configs/robots/brazo_5gdl_servos.json.
El ESP32 aplica esos rangos y velocidades por su cuenta; este script los
comprueba antes solo para dar un error más claro.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys

DEFAULT_PORT = 3334
ROOT = Path(__file__).resolve().parents[1]
SERVO_MAP = ROOT / "configs/robots/brazo_5gdl_servos.json"


def load_servo_map(path=SERVO_MAP):
    """Articulaciones del brazo validadas: nombre, alias, canal, rango y velocidad."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    joints = data["joints"]
    seen_channels = set()
    seen_names = set()
    seen_encoders = set()
    for joint in joints:
        channel = joint["pca9685_channel"]
        low, high = joint["pulse_min_us"], joint["pulse_max_us"]
        names = {joint["name"].lower(), joint["alias"].lower()}
        if not isinstance(channel, int) or not 0 <= channel <= 15:
            raise ValueError(f"{joint['name']}: canal fuera de 0-15")
        if channel in seen_channels:
            raise ValueError(f"{joint['name']}: canal {channel} repetido")
        if not (isinstance(low, int) and isinstance(high, int) and 500 <= low < high <= 2500):
            raise ValueError(f"{joint['name']}: rango de pulso inválido ({low}-{high} us)")
        if not isinstance(joint["slew_us_per_s"], int) or not 0 < joint["slew_us_per_s"] <= 5000:
            raise ValueError(f"{joint['name']}: velocidad inválida")
        if names & seen_names:
            raise ValueError(f"{joint['name']}: nombre o alias repetido")
        encoder = joint.get("encoder_channel")
        if encoder is not None:
            if not isinstance(encoder, int) or not 0 <= encoder <= 7:
                raise ValueError(f"{joint['name']}: canal de encoder fuera de 0-7")
            if encoder in seen_encoders:
                raise ValueError(f"{joint['name']}: canal de encoder {encoder} repetido")
            seen_encoders.add(encoder)
        seen_channels.add(channel)
        seen_names |= names
    return joints


def resolve_channel(target, joints):
    """Canal del PCA9685 para un nombre, alias o número de canal."""
    if target.isdigit():
        channel = int(target)
        if not 0 <= channel <= 15:
            raise ValueError("El canal va de 0 a 15")
        joint = next((item for item in joints if item["pca9685_channel"] == channel), None)
        return channel, joint
    for joint in joints:
        if target.lower() in (joint["name"].lower(), joint["alias"].lower()):
            return joint["pca9685_channel"], joint
    names = ", ".join(f"{item['name']} ({item['alias']})" for item in joints)
    raise ValueError(f"Articulación desconocida: {target}. Usa {names} o un canal 0-15")


def order_from(words, joints=None):
    joints = [] if joints is None else joints
    if words == ["estado"]:
        return "SVQ"
    if words == ["off"]:
        return "SVOFF"
    if words == ["encoders"]:
        return "ENQ"
    if len(words) == 2 and words[1].isdigit():
        channel, joint = resolve_channel(words[0], joints)
        pulse = int(words[1])
        if not 500 <= pulse <= 2500:
            raise ValueError("El pulso va de 500 a 2500 us")
        if joint and not joint["pulse_min_us"] <= pulse <= joint["pulse_max_us"]:
            raise ValueError(
                f"{joint['name']} admite {joint['pulse_min_us']}-{joint['pulse_max_us']} us "
                f"({joint['pulse_limits_status']}; ver {SERVO_MAP.relative_to(ROOT)})"
            )
        return f"SV {channel} {pulse}"
    raise ValueError("Usa: <articulación o canal> <us>, estado, off, encoders o mapa")


def describe_state(reply, joints):
    """Añade el nombre de la articulación a cada canal de un acuse SVQ."""
    if not reply.startswith("OK SVQ "):
        return reply
    names = {item["pca9685_channel"]: item["name"] for item in joints}
    parts = []
    for entry in reply[len("OK SVQ "):].split():
        channel, _, rest = entry.partition(":")
        name = names.get(int(channel)) if channel.isdigit() else None
        parts.append(f"{name}={rest}" if name else entry)
    return "OK SVQ " + " ".join(parts)


MAGNET = {"OK": "imán OK", "MH": "imán muy cerca", "ML": "imán muy lejos", "NM": "sin imán"}


def describe_encoders(reply, joints):
    """Una línea por encoder: articulación, ángulo crudo del imán y estado."""
    if not reply.startswith("OK ENQ"):
        return reply
    names = {item["encoder_channel"]: item["name"] for item in joints
             if item.get("encoder_channel") is not None}
    lines = []
    for entry in reply[len("OK ENQ"):].split():
        fields = entry.split(":")
        channel = int(fields[0])
        name = names.get(channel, "sin articulación")
        if len(fields) == 3:
            raw = int(fields[1])
            lines.append(f"{name:<8} enc {channel}: {raw * 360 / 4096:6.1f}° (raw {raw:4}) "
                         f"{MAGNET.get(fields[2], fields[2])}")
        else:
            lines.append(f"{name:<8} enc {channel}: sin sensor")
    lines.append("Ángulo del imán sin calibrar: no es aún el ángulo de la articulación.")
    return "\n".join(lines)


def describe_map(joints):
    lines = ["Articulación  Alias          Canal  Encoder  Rango (us)   Velocidad   Actuador"]
    for joint in joints:
        encoder = joint.get("encoder_channel")
        lines.append(
            f"{joint['name']:<13} {joint['alias']:<14} {joint['pca9685_channel']:>5}  "
            f"{'-' if encoder is None else encoder:>7}  "
            f"{joint['pulse_min_us']}-{joint['pulse_max_us']:<7} {joint['slew_us_per_s']:>5} us/s  "
            f"{joint['actuator']}"
        )
    lines.append("Rangos y velocidades: valores iniciales sin medir. Ver docs/guides/esp32_wifi.md.")
    return "\n".join(lines)


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
    parser.add_argument("orden", nargs="+", help="<articulación o canal> <us> | estado | off | mapa")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Puerto local del puente (por defecto {DEFAULT_PORT})")
    parser.add_argument("--mapa", type=Path, default=SERVO_MAP, help="Mapa de articulaciones (JSON)")
    args = parser.parse_args(argv)
    try:
        joints = load_servo_map(args.mapa)
    except (OSError, KeyError, ValueError) as error:
        parser.error(f"Mapa de articulaciones inválido ({args.mapa}): {error}")
    if args.orden == ["mapa"]:
        print(describe_map(joints))
        return 0
    try:
        order = order_from(args.orden, joints)
    except ValueError as error:
        parser.error(str(error))
    try:
        reply = send(order, args.port)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    print(describe_encoders(reply, joints) if order == "ENQ" else describe_state(reply, joints))
    return 0 if reply.startswith("OK") else 1


if __name__ == "__main__":
    sys.exit(main())
