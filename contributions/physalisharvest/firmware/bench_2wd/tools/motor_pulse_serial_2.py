import sys
import time

import serial

mode = sys.argv[1]
side = sys.argv[2] if len(sys.argv) > 2 else 'L'
if mode not in ('preflight', 'pulse') or side not in ('L', 'R'):
    raise SystemExit('Expected preflight or pulse [L|R]')

port = serial.Serial(baudrate=115200, timeout=.12, write_timeout=1)
port.port = 'COM3'
port.rts = False
port.dtr = False


def send(command):
    port.write((command + '\n').encode('ascii'))


def expect(expected, limit):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        line = port.readline().decode('ascii', errors='replace').strip()
        if line:
            print('RX', line, flush=True)
        if line == expected:
            return True
    return False


with port:
    for _ in range(8):
        send('STATUS')
        if expect('READY PULSE1 150ms 35%', .4):
            break
    else:
        raise RuntimeError('Firmware not ready')
    send('STOP')
    if not expect('STOPPED', .6):
        raise RuntimeError('STOP not acknowledged')
    if mode == 'preflight':
        send('PULSE')
        if not expect('ERR COMMAND OR STATE', .6):
            raise RuntimeError('Unarmed interlock not acknowledged')
        print('PASS firmware ready and pulse rejected without arming', flush=True)
    else:
        try:
            send('ARM ' + side)
            if not expect('ARMED ' + side, .6):
                raise RuntimeError('Arming not acknowledged')
            send('PULSE')
            if not expect('PULSE START', .6) or not expect('PULSE END', .6):
                raise RuntimeError('Pulse or cutoff not acknowledged')
        finally:
            send('STOP')
            expect('STOPPED', .6)
