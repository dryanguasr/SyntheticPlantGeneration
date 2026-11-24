"""Inspeccion offline del contrato PhysalisHarvest y del robot canonico."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uchuva_gazebo.physalisharvest import (
    ARUCO_TOPIC, build_integration_plan, normalize_astra_point,
)
from uchuva_gazebo.robot import resolve_robot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="proxy_v1", help="Perfil robot-spec/1.0 o ruta JSON")
    parser.add_argument("--output", type=Path, required=True, help="Informe JSON nuevo, preferiblemente en outputs/")
    parser.add_argument("--point-json", type=Path, help="Mensaje PointStamped en JSON; no lee ROS")
    parser.add_argument("--topic", default=ARUCO_TOPIC)
    parser.add_argument("--now-ns", type=int)
    parser.add_argument("--message-clock-domain")
    parser.add_argument("--now-clock-domain")
    args = parser.parse_args(argv)
    clock_values = (args.now_ns, args.message_clock_domain, args.now_clock_domain)
    if args.point_json and any(value is None for value in clock_values):
        parser.error("--point-json requiere --now-ns, --message-clock-domain y --now-clock-domain")
    if not args.point_json and any(value is not None for value in clock_values):
        parser.error("Las opciones de reloj requieren --point-json")
    report = build_integration_plan(resolve_robot(args.profile))
    if args.point_json:
        payload = json.loads(args.point_json.read_text(encoding="utf-8"))
        report["observation"] = normalize_astra_point(
            payload, now_ns=args.now_ns, message_clock_domain=args.message_clock_domain,
            now_clock_domain=args.now_clock_domain, topic=args.topic,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"Contrato offline inspeccionado: {args.output}")
    print("ROS 2, Gazebo, TF y hardware: pendientes de verificacion de integracion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
