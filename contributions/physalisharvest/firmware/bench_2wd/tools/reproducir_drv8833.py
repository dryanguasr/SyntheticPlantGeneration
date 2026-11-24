"""Inicia los procesos del banco DRV8833 desde Windows sin scripts PowerShell."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = ROOT / "ros2_ws"
BENCH = WORKSPACE / "src/robot_locomocion/bench_2wd"


def wsl(args, shell):
    return ["wsl.exe", "-d", args.distro, "--cd", str(WORKSPACE), "--", "bash", "-lc", shell]


def viewer(args):
    source = args.astra.resolve()
    calibration = args.calibracion or source / "resultados/calibracion_caja_evaluada.json"
    if not (source / "diagnostico/visor_registro.py").is_file():
        raise ValueError(f"No encuentro el clon Astra en {source}. Usa --astra.")
    if not calibration.is_file():
        raise ValueError(f"Falta la calibración {calibration}. Consulta la guía de clonación.")
    sdk = args.sdk
    if sdk is None:
        candidates = [
            folder for folder in Path("C:/Astra/SDK").rglob("NiViewer")
            if "2.3.0.86" in str(folder) and "Win64-Release" in str(folder)
            and (folder / "OpenNI2.dll").is_file()
        ]
        if len(candidates) != 1:
            raise ValueError("Indica la carpeta NiViewer de OpenNI x64 con --sdk.")
        sdk = candidates[0]
    command = [
        sys.executable, "-B", str(BENCH / "astra_aruco.py"), "--ros", "--id", "0",
        "--source", str(source), "--calibration", str(calibration.resolve()), "--sdk", str(sdk.resolve()),
        "--rgb-index", str(args.indice_rgb), "--distro", args.distro, "--domain-id", str(args.dominio),
    ]
    if args.sha256:
        command.extend(("--sha256", args.sha256))
    if route := getattr(args, "ruta", None):
        command.extend(("--ruta", *map(str, route)))
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("compilar", "visor", "identificar", "puente", "estado", "armar", "parar"))
    parser.add_argument("--puerto", default="COM3")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--dominio", type=int, default=83, choices=range(1, 102), metavar="1..101")
    parser.add_argument("--indice-rgb", type=int, default=1)
    parser.add_argument("--astra", type=Path, default=ROOT.parent / "COORDENADAS_ORBBECASTRA")
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--calibracion", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--ruta", nargs="+", type=int, choices=range(50), metavar="ID")
    args = parser.parse_args()
    try:
        if args.accion == "compilar":
            command = wsl(args, "source /opt/ros/jazzy/setup.bash && colcon build --packages-select bench_2wd bench_2wd_drv8833")
        elif args.accion == "visor":
            command = viewer(args)
        elif args.accion in ("puente", "identificar"):
            command = [
                sys.executable, "-B", str(Path(__file__).with_name("drv8833_ros_usb.py")),
                "--port", args.puerto, "--distro", args.distro, "--domain-id", str(args.dominio),
            ]
            if args.accion == "identificar":
                command.append("--check")
            elif args.ruta:
                command.extend(("--ruta", *map(str, args.ruta)))
        else:
            setup = (
                "source /opt/ros/jazzy/setup.bash && source install/setup.bash && "
                f"export ROS_DOMAIN_ID={args.dominio} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST && "
            )
            action = (
                "exec ros2 topic echo /bench_2wd/drv8833/state"
                if args.accion == "estado" else f"exec ros2 run bench_2wd_drv8833 session {args.accion}"
            )
            command = wsl(args, setup + action)
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
