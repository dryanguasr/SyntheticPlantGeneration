import time
import serial

port = serial.Serial(baudrate=115200, timeout=.04, write_timeout=.5)
port.port = 'COM3'
port.dtr = False
port.rts = False


def send(command):
    port.write((command + '\n').encode('ascii'))


def wait(label, heartbeat=False):
    end = time.monotonic() + 4
    keep = 0
    while time.monotonic() < end:
        now = time.monotonic()
        if heartbeat and now >= keep:
            send('KEEP')
            keep = now + .08
        row = port.readline().decode('ascii', errors='replace').strip()
        if not row:
            continue
        print('RX', row, flush=True)
        if row.split()[0] == label:
            return row.split()
        if row.startswith(('ERR', 'LINK_LOST')):
            raise RuntimeError(row)
    raise TimeoutError(label)


with port:
    send('STATUS')
    if wait('READY') != ['READY', 'PWM10', 'L']:
        raise RuntimeError('Firmware incorrecto')
    send('STOP')
    wait('CANCELLED')
    send('ARM PWM10 L')
    wait('ARMED')
    try:
        send('RUN')
        results = [wait(label, True) for label in ('FORWARD','PAUSE','REVERSE','STOPPED')]
        elapsed = [int(b[1]) - int(a[1]) for a,b in zip(results,results[1:])]
        expected = [['HZ','10000','DUTY','89','0'], ['HZ','0','DUTY','0','0'],
                    ['HZ','10000','DUTY','0','89'], ['HZ','0','DUTY','0','0']]
        if [row[2:] for row in results] != expected:
            raise RuntimeError(f'Estado PWM inesperado: {results}')
        if not all(minimum <= value <= minimum+25
                   for minimum,value in zip((1000,250,1000),elapsed)):
            raise RuntimeError(f'Tiempos inesperados: {elapsed}')
        print('PASS lecturas LEDC 10000 Hz; duraciones ms:', elapsed, flush=True)
    finally:
        send('STOP')
        wait('CANCELLED')
