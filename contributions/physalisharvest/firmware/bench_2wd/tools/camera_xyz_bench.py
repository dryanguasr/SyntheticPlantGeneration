import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

root = Path('../COORDENADAS_ORBBECASTRA').resolve()
sys.path.insert(0, str(root / 'diagnostico'))
from emitir_xyz import xyz_optico
from probar_rgb_depth import abrir_parejas, cargar_api, intrinsecos_depth, leer_pareja
from visor_registro import ProyeccionDepth

calibration = (root / 'resultados/calibracion_caja_evaluada.json').read_bytes()
assert hashlib.sha256(calibration).hexdigest() == '4b06398231164640534c33fe549be33a85165a2ca5e61eb9fdc1819a79ce0583'
matrix = np.asarray(json.loads(calibration)['proyeccion_depth_a_rgb'])
sdk = next(Path('C:/Astra/SDK').glob('OpenNI_2.3.0.86*/Win64-Release/tools/NiViewer'))
evidence = Path(__file__).resolve().parent
command = ['wsl.exe', '-d', 'Ubuntu-24.04', '--cd', str(evidence), '--', 'bash', '-lc',
           'source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=85 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST && exec python3 -B ros_xyz_bench.py']

with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                      encoding='utf-8') as ros:
    try:
        if ros.stdout.readline().strip() != 'ROS_READY':
            raise RuntimeError('El entorno ROS no inició')
        api = cargar_api(sdk)
        with abrir_parejas(api, 1, False) as (camera, stream):
            projector = ProyeccionDepth(matrix, intrinsecos_depth(api, stream))
            for _ in range(20):
                rgb, depth = leer_pareja(api, camera, stream)
            stamp = time.time_ns()
            registered, origins = projector.aplicar(depth, con_origen=True)
            y, x = np.nonzero(origins[120:360, 160:480] >= 0)
            if not len(x):
                raise RuntimeError('No hay profundidad proyectada en la región central')
            x, y = x + 160, y + 120
            best = np.argmin((x - 320)**2 + (y - 240)**2)
            color_x, color_y = int(x[best]), int(y[best])
            v, u = divmod(int(origins[color_y, color_x]), 640)
            xyz = xyz_optico(api, stream, u, v, int(depth[v,u]))
            sample = {'stamp_ns': stamp, 'xyz': list(xyz)}
            ros.stdin.write(json.dumps(sample) + '\n')
            ros.stdin.flush()
        received = json.loads(ros.stdout.readline())
        expected = {'frame': 'astra_depth_optical_frame', **sample}
        if received != expected:
            raise RuntimeError(f'Muestra ROS distinta: {received}')
        if ros.wait(timeout=5):
            raise RuntimeError('El proceso ROS falló')
    finally:
        if ros.poll() is None:
            ros.terminate()
print(f'Pixel RGB ({color_x}, {color_y}); depth ({u}, {v}) = {depth[v,u]} mm', flush=True)
print(f'ROS /astra/xyz: {received}', flush=True)
if '--camera-only' not in sys.argv:
    import serial
    with serial.Serial(baudrate=115200, timeout=0.35, write_timeout=1) as port:
        port.dtr = False
        port.rts = False
        port.port = 'COM3'
        port.open()
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            port.write(b'HELLO XYZ1\n')
            if port.readline().decode('ascii', errors='replace').strip() == 'READY XYZ1':
                print('RX READY XYZ1', flush=True)
                break
        else:
            raise RuntimeError('COM3 no respondió READY XYZ1')
        payload = '1 ' + ' '.join(format(value, '.6f') for value in received['xyz'])
        print(f'TX XYZ1 {payload}', flush=True)
        port.write(f'XYZ1 {payload}\n'.encode('ascii'))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            line = port.readline().decode('ascii', errors='replace').strip()
            if line:
                print(f'RX {line}', flush=True)
            if line.startswith('ECHO '):
                if line != 'ECHO ' + payload:
                    raise RuntimeError(f'XYZ distinto: {line}')
                print('PASS: XYZ confirmado por ESP32 a seis decimales', flush=True)
                break
        else:
            raise RuntimeError('COM3 no devolvió el XYZ')
