"""WSL: bounded native RGB/panoptic pairs for evaluator-only static QA."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import xml.etree.ElementTree as ET

from gazebo_capture import png


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--field', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(exist_ok=False)
    tree = ET.parse(args.field / 'field.sdf')
    for name in ('overview', 'drone_camera'):
        link = tree.find(f".//model[@name='{name}']/link")
        sensor = copy.deepcopy(link.find('sensor'))
        sensor.set('name', 'instances')
        sensor.set('type', 'segmentation')
        sensor.find('topic').text = f'/qa/{name}/instances'
        ET.SubElement(sensor.find('camera'), 'segmentation_type').text = 'panoptic'
        link.append(sensor)
    tree.write(out / 'field.sdf', encoding='utf-8', xml_declaration=True)
    os.environ['GZ_PARTITION'] = f'static_pair_{os.getpid()}'
    os.environ['GZ_SIM_RESOURCE_PATH'] = str(args.field.resolve())
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    node = Node()
    lock = threading.Lock()
    pending, completed, counts, callbacks = {}, {}, {}, []

    def receive(view, kind, msg):
        if msg.pixel_format_type != 3:
            return
        stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nsec
        with lock:
            key = (view, kind)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] < 6 or view in completed:
                return
            pending[(view, kind, stamp)] = (msg.width, msg.height, bytes(msg.data), msg.step)
            if all((view, k, stamp) in pending for k in ('rgb', 'mask')):
                for k in ('rgb', 'mask'):
                    values = pending[(view, k, stamp)]
                    (out / f'{view}_{k}.png').write_bytes(png(*values))
                completed[view] = dict(stamp_ns=stamp, exact_timestamp_pair=True)
                print('PAIRED', view, stamp, flush=True)
            # Keep memory bounded even if two sensors never synchronize.
            for old in list(pending):
                if old[0] == view and old[2] < stamp - 2_000_000_000:
                    del pending[old]

    for view in ('overview', 'drone_camera'):
        for kind, topic in [('rgb', f'/uchuva/{view}/image'), ('mask', f'/qa/{view}/instances/labels_map')]:
            callback = lambda msg, v=view, k=kind: receive(v, k, msg)
            callbacks.append(callback)
            if not node.subscribe(Image, topic, callback):
                raise RuntimeError(f'Cannot subscribe {topic}')
    with (out / 'server.log').open('w') as log:
        server = subprocess.Popen(['gz', 'sim', '-s', '-r', '--headless-rendering', '-v', '3', str(out/'field.sdf')], stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError('Gazebo exited before capture')
                with lock:
                    if len(completed) == 2:
                        break
                time.sleep(.2)
            else:
                raise TimeoutError('Missing exact RGB/mask pairs')
            (out/'pairs.json').write_text(json.dumps(dict(views=completed,truth_role='evaluator_only',flight=False,accepted_for_training=False), indent=2))
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == '__main__':
    main()
