"""Run the supervised two-motor bench sequence once via COM3."""

import argparse
import time

import serial


def wait_for(port, expected, keep_alive=False):
    deadline = time.monotonic() + 4
    next_keep = 0
    while time.monotonic() < deadline:
        now = time.monotonic()
        if keep_alive and now >= next_keep:
            port.write(b'KEEP\n')
            next_keep = now + 0.08
        line = port.readline().decode('ascii', errors='replace').strip()
        if not line:
            continue
        print(line, flush=True)
        if line.split()[0] == expected:
            return line
        if line.startswith(('ERR', 'LINK_LOST', 'ARM_EXPIRED', 'USED')):
            raise RuntimeError(line)
    raise TimeoutError(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--run', action='store_true', help='Authorize exactly one cycle')
    args = parser.parse_args()
    port = serial.Serial(baudrate=115200, timeout=0.04, write_timeout=0.5)
    port.port = args.port
    port.dtr = False
    port.rts = False
    with port:
        try:
            port.write(b'STATUS\n')
            if wait_for(port, 'READY') != 'READY BOTH_FULL':
                raise RuntimeError('Unexpected firmware')
            if not args.run:
                return
            port.write(b'ARM BOTH_FULL\n')
            wait_for(port, 'ARMED')
            port.write(b'RUN\n')
            for expected in ('FORWARD', 'COAST', 'REVERSE', 'STOPPED'):
                wait_for(port, expected, keep_alive=True)
        finally:
            port.write(b'STOP\n')


if __name__ == '__main__':
    main()
