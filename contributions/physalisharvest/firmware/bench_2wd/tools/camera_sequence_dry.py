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
import serial

HOLD = '25=0 26=0 27=0 14=0'


def wait_line(port, check, heartbeat=False, timeout=4):
    deadline = time.monotonic() + timeout
    next_keep = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if heartbeat and now >= next_keep:
            port.write(b'KEEP\n')
            next_keep = now + .1
        line = port.readline().decode('ascii', errors='replace').strip()
        if line:
            print('RX ' + line, flush=True)
            if line.startswith('DRY ') and not line.endswith('GPIO ' + HOLD):
                raise RuntimeError('GPIO fuera de bajo: ' + line)
            if check(line):
                return line
    raise RuntimeError('Respuesta serial agotada')


def expect(port, expected, heartbeat=False):
    return wait_line(port, lambda line: line == expected, heartbeat)


def state(port, expected, heartbeat=False):
    line = wait_line(port, lambda line: line.startswith('DRY ' + expected + ' '), heartbeat)
    return int(line.split()[2])


if '--arm-dry' not in sys.argv:
    raise SystemExit('Se requiere habilitacion manual --arm-dry')
port = serial.Serial(baudrate=115200, timeout=.05, write_timeout=1)
port.dtr = False
port.rts = False
port.port = 'COM3'
with port:
    port.write(b'HELLO DRY1\n')
    expect(port, 'READY DRY1')
    coords = ' '.join(format(value, '.6f') for value in received['xyz'])

    def send_point(sequence):
        payload = f'{sequence} {coords}'
        print('TX XYZ1 ' + payload, flush=True)
        port.write(('XYZ1 ' + payload + '\n').encode('ascii'))
        return payload

    def arm():
        port.write(b'ARM DRY1\n')
        state(port, 'ARMED')

    try:
        send_point(1)
        expect(port, 'ERR NOT_ARMED')
        arm()
        expect(port, 'ECHO ' + send_point(2), True)
        forward = state(port, 'FORWARD', True)
        pause = state(port, 'PAUSE', True)
        reverse = state(port, 'REVERSE', True)
        stop = state(port, 'STOP', True)
        intervals = [pause - forward, reverse - pause, stop - reverse]
        if not all(target <= actual <= target + 30
                   for target, actual in zip((1000, 250, 1000), intervals)):
            raise RuntimeError(f'Tiempos fuera de criterio: {intervals}')
        print(f'PASS secuencia seca, duraciones ms: {intervals}', flush=True)
        send_point(3)
        expect(port, 'ERR NOT_ARMED')

        arm()
        expect(port, 'ECHO ' + send_point(4))
        start = state(port, 'FORWARD')
        lost = state(port, 'LINK_LOST')
        if not 500 <= lost - start <= 530:
            raise RuntimeError(f'Expiracion incorrecta: {lost - start} ms')
        print(f'PASS perdida de enlace: {lost - start} ms', flush=True)

        arm()
        expect(port, 'ECHO ' + send_point(5))
        state(port, 'FORWARD')
        port.write(b'STOP\n')
        state(port, 'CANCEL')
        print('PASS parada y desarme manual', flush=True)
    finally:
        port.write(b'STOP\n')
