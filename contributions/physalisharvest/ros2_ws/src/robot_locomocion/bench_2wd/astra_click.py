"""Publica clics RGB calibrados vía el publicador Astra, sin puente serie."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

REFERENCE = '7b4cd1b50ddecae7ea30494160e519d9e4191038'


def show_camera(args, stream):
    sys.path.insert(0, str(args.source / 'diagnostico'))
    from emitir_xyz import xyz_optico
    from probar_rgb_depth import abrir_parejas, cargar_api, intrinsecos_depth, leer_pareja
    from visor_registro import ProyeccionDepth, preparar_superposicion

    calibration = args.calibration.read_bytes()
    if hashlib.sha256(calibration).hexdigest() != args.sha256.lower():
        raise ValueError('El SHA-256 de la calibración difiere del registrado')
    matrix = np.asarray(json.loads(calibration)['proyeccion_depth_a_rgb'], dtype=float)
    if matrix.shape != (3, 4) or not np.isfinite(matrix).all() or np.linalg.matrix_rank(matrix) != 3:
        raise ValueError('Se requiere una matriz de proyección finita 3x4 de rango 3')

    window = 'Astra Pro - clic a ROS 2'
    api = cargar_api(args.sdk.resolve())
    with abrir_parejas(api, args.rgb_index, False) as (camera, depth_stream):
        projector = ProyeccionDepth(matrix, intrinsecos_depth(api, depth_stream))
        clicks = []

        def select(event, x, y, _flags, _param):
            if event == cv2.EVENT_LBUTTONDOWN:
                clicks.append((x, y))

        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(window, select)
        try:
            while True:
                rgb, depth = leer_pareja(api, camera, depth_stream)
                stamp = time.time_ns()
                registered, origin = projector.aplicar(depth, con_origen=True)
                cv2.imshow(window, preparar_superposicion(rgb, registered))
                if cv2.waitKey(15) & 0xff == 27 or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    return
                for x, y in clicks:
                    if not (0 <= y < origin.shape[0] and 0 <= x < origin.shape[1]):
                        continue
                    index = int(origin[y, x])
                    if index < 0 or time.time_ns() - stamp > 900_000_000:
                        print('Clic descartado: profundidad ausente o muestra vencida')
                        continue
                    v, u = divmod(index, depth.shape[1])
                    try:
                        xyz = xyz_optico(api, depth_stream, u, v, int(depth[v, u]))
                    except RuntimeError as error:
                        print(f'Clic descartado: {error}')
                        continue
                    stream.write(json.dumps({'stamp_ns': stamp, 'xyz': xyz}, allow_nan=False) + '\n')
                    stream.flush()
                    print(f'Muestra enviada al publicador ROS: {xyz} m')
                clicks.clear()
        finally:
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--calibration', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--rgb-index', type=int, required=True)
    parser.add_argument('--domain-id', type=int, required=True)
    parser.add_argument('--distro', default='Ubuntu-24.04')
    args = parser.parse_args()
    if not 1 <= args.domain_id <= 101:
        parser.error('Usa un dominio ROS de banco entre 1 y 101')
    revision = subprocess.check_output(
        ['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True
    ).strip()
    if revision != REFERENCE or subprocess.check_output(
        ['git', '-C', str(args.source), 'status', '--porcelain', '--', 'diagnostico', 'ros2'],
        text=True,
    ).strip():
        parser.error(f'Se requiere el checkout {REFERENCE} con diagnostico y ros2 limpios')

    command = [
        'wsl.exe', '-d', args.distro, '--cd', str(args.source.resolve()), '--', 'bash', '-lc',
        f'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID={args.domain_id} '
        '&& export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST '
        '&& exec python3 -B ros2/astra_xyz.py',
    ]
    with subprocess.Popen(command, cwd=args.source, stdin=subprocess.PIPE, text=True,
                          encoding='utf-8') as publisher:
        try:
            show_camera(args, publisher.stdin)
        finally:
            publisher.stdin.close()
            try:
                status = publisher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                publisher.terminate()
                raise
    if status:
        raise SystemExit(f'El publicador Astra terminó con código {status}')


if __name__ == '__main__':
    main()
