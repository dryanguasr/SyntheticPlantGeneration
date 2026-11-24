"""Compila o inicia nodos ROS de PhysalisHarvest desde una instalación común.

No abre cámara ni puerto serie. El armado sólo se solicita con la acción
explícita armar, usando el cliente original y sus confirmaciones.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from uchuva_gazebo.physalisharvest_launch import (
    ACTIONS, DEFAULT_OUTPUT, create_launch_plan, execute_launch_plan,
)
from verify_physalisharvest_snapshot import verify_snapshot


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    boundary = arguments.index("--") if "--" in arguments else len(arguments)
    node_args = arguments[boundary+1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--output-root", type=Path, default=Path(DEFAULT_OUTPUT),
                        help="Directorio común de build/install/log, dentro de outputs/")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--domain-id", type=int, default=83)
    parser.add_argument("--dry-run", action="store_true", help="Inspecciona el comando sin iniciar procesos")
    parser.epilog = "Para pasar argumentos originales al nodo, escribe -- seguido de sus argumentos ROS."
    args = parser.parse_args(arguments[:boundary])
    try:
        integrity = verify_snapshot(ROOT)
        if integrity["status"] != "PASS":
            raise ValueError("El snapshot PhysalisHarvest no coincide con su manifiesto de procedencia")
        plan = create_launch_plan(args.action, ROOT, output_root=args.output_root,
                                  distro=args.distro, domain_id=args.domain_id, node_args=node_args)
        if args.dry_run:
            print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
            return 0
        return execute_launch_plan(plan)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError) as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
