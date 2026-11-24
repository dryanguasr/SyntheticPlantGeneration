"""Visor local de ArUco con la Astra Pro. Solo muestra decisiones de diagnóstico."""

import argparse
import base64
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from queue import Empty, Full, Queue
from math import atan2, degrees
from pathlib import Path
import subprocess
import sys
import time
from threading import Event, Thread

import cv2
import numpy as np


MARKERS = Path(__file__).resolve().with_name("marcadores_aruco")
CALIBRATION_HASH = "4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583"
WINDOW = "Astra Pro - ArUco 2WD"
STOP_Z_M = 0.50
CENTER_ANGLE_DEG = 3.0


def generate_markers(dictionary):
    MARKERS.mkdir(exist_ok=True)
    for marker_id in range(3):
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 480)
        page = np.full((640, 600), 255, dtype=np.uint8)
        page[60:540, 60:540] = marker
        cv2.putText(page, f"DICT_4X4_50 | ID {marker_id}", (60, 578),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, 0, 2, cv2.LINE_AA)
        cv2.putText(page, "Generado con IA (script OpenCV)", (60, 614),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
        path = MARKERS / f"aruco_4x4_50_id_{marker_id:02d}.png"
        path.write_bytes(cv2.imencode(".png", page)[1].tobytes())
        print(path)


def marker_xyz(corners, origins, raw_depth, to_xyz):
    """Toma una muestra real cerca del centro, coherente con el interior."""
    center = corners.mean(axis=0)
    interior = np.rint(center + 0.55 * (corners - center)).astype(np.int32)
    mask = np.zeros(origins.shape, dtype=np.uint8)
    cv2.fillConvexPoly(mask, interior, 1)
    rows, cols = np.nonzero((mask != 0) & (origins >= 0))
    if len(rows) < 9:
        return None

    indices = origins[rows, cols]
    depths_mm = raw_depth.ravel()[indices].astype(np.int32)
    median_mm = np.median(depths_mm)
    # Exigir consenso para evitar saltar a otra superficie dentro del contorno.
    inliers = (depths_mm > 0) & (abs(depths_mm - median_mm) <= 40)
    if np.count_nonzero(inliers) < max(9, 0.75 * len(indices)):
        return None
    offsets = np.column_stack((cols[inliers], rows[inliers])) - center
    nearest = np.argmin(np.sum(offsets ** 2, axis=1))
    row, col = divmod(int(indices[inliers][nearest]), raw_depth.shape[1])
    return to_xyz(col, row, int(raw_depth[row, col]))


def guidance(xyz):
    if xyz is None:
        return "PARAR - sin profundidad valida", None
    x, _, z = xyz
    angle = degrees(atan2(x, z))
    if z <= STOP_Z_M:
        return "PARAR - Z <= 0.50 m", angle
    if angle < -CENTER_ANGLE_DEG:
        return "CORREGIR A LA IZQUIERDA", angle
    if angle > CENTER_ANGLE_DEG:
        return "CORREGIR A LA DERECHA", angle
    return "AVANZAR RECTO", angle


def render(rgb, registered, origins, raw_depth, to_xyz, detector, expected_id, depth_status,
           on_observation=None, preview=False, route=None):
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY))
    cv2.aruco.drawDetectedMarkers(rgb, corners, ids)
    depth_ready = origins is not None and registered is not None and np.any(registered)
    observations = {}
    for marker_id in route or (expected_id,):
        matches = np.flatnonzero(ids.ravel() == marker_id) if ids is not None else []
        sample = None if depth_ready and not len(matches) else "invalido"
        if depth_ready and len(matches) == 1:
            sample = "sin_profundidad"
            target = corners[matches[0]].reshape(4, 2)
            center = tuple(np.rint(target.mean(axis=0)).astype(int))
            cv2.circle(rgb, center, 5, (0, 255, 255), -1)
            try:
                point = marker_xyz(target, origins, raw_depth, to_xyz)
                if point is not None and np.isfinite(point).all() and point[2] > 0:
                    sample = tuple(point)
            except RuntimeError:
                pass
        observations[str(marker_id)] = "ausente" if route and sample is None else sample
    sample = observations[str(expected_id)]
    xyz = sample if isinstance(sample, tuple) else None
    text, angle = guidance(xyz)
    if sample is None or sample == "ausente":
        text = "PARAR - marcador objetivo ausente"
    elif sample == "sin_profundidad":
        text = "Marcador visible sin profundidad valida"

    if on_observation is not None:
        on_observation(observations if route else xyz)

    depth_view = np.zeros_like(rgb)
    if registered is not None:
        scaled = np.clip(255 - registered.astype(np.float32) * 255 / 2500, 0, 255)
        depth_view = cv2.applyColorMap(scaled.astype(np.uint8), cv2.COLORMAP_TURBO)
        depth_view[registered == 0] = 0
    if preview:
        return np.hstack((rgb, depth_view)), text, xyz
    cv2.putText(depth_view, "Profundidad alineada" if registered is not None else depth_status,
                (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 1, cv2.LINE_AA)
    panel = np.full((130, rgb.shape[1] * 2, 3), 24, dtype=np.uint8)
    detail = "XYZ: --"
    if xyz is not None:
        x, y, z = xyz
        detail = f"X {x:+.3f} m   Y {y:+.3f} m   Z {z:.3f} m   Angulo {angle:+.1f} grados"
    color = (105, 105, 255) if text.startswith("PARAR") else (90, 235, 255)
    for line, y, scale, ink in (
        (text, 37, 0.95, color),
        (detail, 73, 0.70, (240, 240, 240)),
        (f"ID objetivo {expected_id} | Parada a 0.50 m desde la Astra | Solo visor | Esc: salir",
         108, 0.60, (210, 210, 210)),
    ):
        cv2.putText(panel, line, (14, y), cv2.FONT_HERSHEY_SIMPLEX, scale, ink, 2, cv2.LINE_AA)
    return np.vstack((np.hstack((rgb, depth_view)), panel)), text, xyz


def view(args, detector, publish=None, shutdown=None):
    sys.path.insert(0, str(args.source.resolve() / "diagnostico"))
    from emitir_xyz import xyz_optico
    from probar_profundidad import flujo_profundidad, leer_fotograma
    from probar_rgb_depth import cargar_api, copiar_profundidad, intrinsecos_depth
    from probar_profundidad import configurar_registro
    from visor_registro import ProyeccionDepth

    calibration = args.calibration.read_bytes()
    if sha256(calibration).hexdigest() != args.sha256.lower():
        raise ValueError("El SHA-256 difiere de la calibracion registrada para el banco")
    matrix = np.asarray(json.loads(calibration)["proyeccion_depth_a_rgb"], dtype=float)
    if matrix.shape != (3, 4) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix) != 3:
        raise ValueError("Se requiere una matriz de proyeccion 3x4 de rango 3")

    camera = cv2.VideoCapture(args.rgb_index, cv2.CAP_DSHOW)
    preview_frames = Queue(maxsize=1)
    preview_done = Event()

    def write_preview():
        while not preview_done.is_set():
            try:
                frame = preview_frames.get(timeout=0.1)
            except Empty:
                continue
            small = cv2.resize(frame, (960, 360), interpolation=cv2.INTER_AREA)
            ok, packet = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if ok:
                try:
                    print("FRAME " + base64.b64encode(packet).decode("ascii"), flush=True)
                except OSError:
                    preview_done.set()

    worker = None
    if args.preview_pipe:
        worker = Thread(target=write_preview, daemon=True)
        worker.start()

    def send_observation(xyz):
        offset = args.camera_clock.offset()
        if offset is not None:
            publish.write(json.dumps((stamp_ns + offset, xyz), allow_nan=False) + "\n")
            publish.flush()

    try:
        if not camera.isOpened():
            raise RuntimeError(f"No se pudo abrir RGB DirectShow (indice {args.rgb_index})")
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        with ExitStack() as depth_resources:
            projector = None
            try:
                api = cargar_api(args.sdk.resolve())
                stream = depth_resources.enter_context(flujo_profundidad(api, configurar_registro))
                projector = ProyeccionDepth(matrix, intrinsecos_depth(api, stream))
            except (OSError, RuntimeError) as error:
                depth_resources.close()
                print(f"Profundidad OpenNI no disponible: {error}", flush=True)

            if not args.preview_pipe:
                cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
                cv2.resizeWindow(WINDOW, 1120, 534)
            previous = None
            preview_at = 0.0
            while shutdown is None or not shutdown.is_set():
                ok, rgb = camera.read()
                stamp_ns = time.monotonic_ns()
                if not ok or rgb.shape != (480, 640, 3):
                    raise RuntimeError("No llego RGB a 640x480 para aplicar la calibracion")
                registered = origins = depth = None
                if projector is not None:
                    try:
                        with leer_fotograma(api, stream) as frame:
                            depth = copiar_profundidad(frame)
                        registered, origins = projector.aplicar(depth, con_origen=True)
                    except RuntimeError as error:
                        print(f"Fotograma depth descartado: {error}", flush=True)
                panel, text, xyz = render(
                    rgb, registered, origins, depth,
                    lambda u, v, z: xyz_optico(api, stream, u, v, z),
                    detector, args.id, "Sin profundidad OpenNI",
                    send_observation if publish is not None else None,
                    preview=args.preview_pipe,
                    route=args.ruta,
                )
                if text != previous:
                    position = "" if xyz is None else f" | XYZ m: {tuple(round(v, 3) for v in xyz)}"
                    print(text + position, flush=True)
                    previous = text
                if args.preview_pipe:
                    now = time.monotonic()
                    if now >= preview_at:
                        try:
                            preview_frames.get_nowait()
                        except Empty:
                            pass
                        try:
                            preview_frames.put_nowait(panel)
                        except Full:
                            pass
                        preview_at = now + 0.125
                    continue
                cv2.imshow(WINDOW, panel)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
                if cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                    break
    finally:
        preview_done.set()
        camera.release()
        if worker:
            worker.join(timeout=0.3)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generar", action="store_true", help="Guarda los IDs 0, 1 y 2 en PNG")
    parser.add_argument("--id", type=int, default=0, choices=range(50), metavar="0..49")
    parser.add_argument("--ruta", nargs="+", type=int, choices=range(50), metavar="ID")
    parser.add_argument("--rgb-index", type=int, default=1)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--sha256", default=CALIBRATION_HASH, help="Hash del perfil de calibración verificado")
    parser.add_argument("--ros", action="store_true", help="Publica el ID 0 al banco ROS 2 DRV8833")
    parser.add_argument("--preview-pipe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--diagnostico", action="store_true", help="Publica en el tópico de diagnóstico")
    parser.add_argument("--distro", default="Ubuntu-24.04")
    parser.add_argument("--domain-id", type=int, default=83, choices=range(1, 102), metavar="1..101")
    args = parser.parse_args()
    shutdown = None
    if args.preview_pipe:
        shutdown = Event()

        def watch():
            try:
                os.read(sys.stdin.fileno(), 1)
            finally:
                shutdown.set()

        Thread(target=watch, daemon=True).start()
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    if args.generar:
        generate_markers(dictionary)
        return
    if not all((args.source, args.sdk, args.calibration)):
        parser.error("Para el visor se requieren --source, --sdk y --calibration")
    if args.ruta:
        if len(set(args.ruta)) != len(args.ruta):
            parser.error("La ruta requiere IDs únicos.")
        args.id = args.ruta[0]
    elif args.ros and args.id != 0:
        parser.error("El tópico experimental DRV8833 está reservado para el ID 0")
    detector = cv2.aruco.ArucoDetector(dictionary)
    if not args.ros:
        view(args, detector, shutdown=shutdown)
        return
    if args.ruta is None:
        args.ruta = [args.id]
    cv2.setNumThreads(1)
    tools = Path(__file__).resolve().parents[4] / "firmware/bench_2wd/tools"
    sys.path.insert(0, str(tools))
    from wsl_clock import CameraClock
    workspace = Path(__file__).resolve().parents[3]
    shell = (
        "source /opt/ros/jazzy/setup.bash && source install/setup.bash && "
        f"export ROS_DOMAIN_ID={args.domain_id} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST && "
        "exec ros2 run bench_2wd_drv8833 aruco_source --ros-args -p transport_monotonic:=true"
    )
    if args.diagnostico:
        shell += " -p diagnostico:=true"
    if args.ruta:
        shell += " -p 'ruta:=[" + ",".join(map(str, args.ruta)) + "]'"
    with subprocess.Popen(
        ["wsl.exe", "-d", args.distro, "--cd", str(workspace), "--", "bash", "-lc", shell],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
    ) as publisher:
        try:
            if publisher.stdout.readline().strip() != "ARUCO_READY":
                raise RuntimeError("El publicador ROS no confirmó su inicio")
            with CameraClock(args.distro, lambda line: print(line, flush=True)) as reference:
                args.camera_clock = reference
                view(args, detector, publisher.stdin, shutdown)
        finally:
            try:
                publisher.stdin.close()
                publisher.wait(timeout=3)
            except subprocess.TimeoutExpired:
                publisher.terminate()
                raise
    if publisher.returncode:
        raise SystemExit(f"El publicador ROS terminó con código {publisher.returncode}")


if __name__ == "__main__":
    main()
