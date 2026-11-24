"""Native RGB/panoptic capture hooks, plus a bounded static diagnostic command.

The static command fixes every existing model in a copied world and removes
controllers. It never substitutes this capture for a dynamic robot experiment.
Sensor construction / the recorder can also be imported by the actual runner.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.harvest_perception import VERSION, add_instance_observer, sha256


def write_new(path, data):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')


def visibility_from_labels(data, width, height, step, label_map):
    """Decode native panoptic RGB: byte 2 is semantic; union all subvisuals."""
    if len(data) != step*height or step < width*3:
        raise ValueError('Invalid native panoptic stride')
    rows = {int(label): {'id': item['id'], 'model_name': item['model_name'], 'visible_pixels': 0,
                         'box_xyxy_px': None, 'native_instance_codes': set()}
            for label, item in label_map.items()}
    bounds = {label: [width, height, -1, -1] for label in rows}
    for y in range(height):
        for x in range(width):
            offset = y*step+x*3
            label = data[offset+2]
            if label not in rows:
                continue
            row, box = rows[label], bounds[label]
            row['visible_pixels'] += 1
            row['native_instance_codes'].add(data[offset]+256*data[offset+1])
            box[0], box[1] = min(box[0], x), min(box[1], y)
            box[2], box[3] = max(box[2], x), max(box[3], y)
    for label, row in rows.items():
        box = bounds[label]
        if row['visible_pixels']:
            row['box_xyxy_px'] = [box[0], box[1], box[2]+1, box[3]+1]
        row['native_instance_codes'] = sorted(row['native_instance_codes'])
    return list(rows.values())


class NativePerceptionRecorder:
    """Save exact-stamp pairs with disjoint public RGB and private label paths."""
    def __init__(self, output, observer, *, maximum_pairs=None, minimum_stamp_ns=0):
        from gz.transport13 import Node
        from gz.msgs10.image_pb2 import Image
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        (self.output/'public').mkdir()
        (self.output/'private').mkdir()
        self.observer = observer
        self.maximum_pairs = maximum_pairs
        self.minimum_stamp_ns = minimum_stamp_ns
        self.node = Node()
        self.lock = threading.Lock()
        self.buffers = {'rgb': {}, 'labels': {}}
        self.rows, self.private_rows, self.errors = [], [], []
        self.closed = False
        self.received = {'rgb': 0, 'labels': 0}
        self.unpaired_evictions = {'rgb': 0, 'labels': 0}
        write_new(self.output/'private/observer.json', observer)
        for kind in self.buffers:
            topic = observer[kind+'_topic']
            if not self.node.subscribe(Image, topic, lambda msg, k=kind: self.receive(k, msg)):
                raise RuntimeError('Failed subscription: '+topic)

    def receive(self, kind, message):
        with self.lock:
            if self.closed or (self.maximum_pairs is not None and len(self.rows) >= self.maximum_pairs):
                return
            try:
                self.received[kind] += 1
                if message.pixel_format_type != 3:
                    raise ValueError('Expected native RGB_INT8 for RGB / labels')
                if (message.width, message.height) != (self.observer['width'], self.observer['height']):
                    raise ValueError('Unexpected native sensor dimensions')
                stamp = message.header.stamp.sec*10**9+message.header.stamp.nsec
                if stamp < self.minimum_stamp_ns or (self.rows and stamp <= self.rows[-1]['stamp_ns']):
                    return
                self.buffers[kind][stamp] = message
                for old in sorted(self.buffers[kind])[:-16]:
                    self.buffers[kind].pop(old)
                    self.unpaired_evictions[kind] += 1
                for common in sorted(set(self.buffers['rgb']) & set(self.buffers['labels'])):
                    self._save(common, self.buffers['rgb'].pop(common), self.buffers['labels'].pop(common))
                    if self.maximum_pairs is not None and len(self.rows) >= self.maximum_pairs:
                        break
            except Exception as error:
                self.errors.append(repr(error))

    def _save(self, stamp, rgb, labels):
        import cv2
        import numpy as np
        index = len(self.rows)
        frame_id = f"{self.observer['name']}_{index:06d}"
        filename = frame_id+'.png'
        for folder, message in (('public', rgb), ('private', labels)):
            if len(message.data) != message.height*message.step or message.step < message.width*3:
                raise ValueError('Malformed native image stride')
            pixels = np.frombuffer(message.data, np.uint8).reshape(message.height, message.step)
            pixels = pixels[:, :message.width*3].reshape(message.height, message.width, 3)
            path = self.output/folder/filename
            if path.exists() or not cv2.imwrite(str(path), pixels[:, :, ::-1]):
                raise RuntimeError('Native PNG write failed or would replace existing data')
        image_sha = sha256(self.output/'public'/filename)
        row = {'frame_id': frame_id, 'stamp_ns': stamp, 'filename': filename, 'image_sha256': image_sha,
               'width': rgb.width, 'height': rgb.height}
        self.rows.append(row)
        self.private_rows.append({'frame_id': frame_id, 'stamp_ns': stamp, 'image_sha256': image_sha,
            'label_filename': filename, 'label_png_sha256': sha256(self.output/'private'/filename),
            'raw_rgb_sha256': hashlib.sha256(rgb.data).hexdigest(),
            'raw_labels_sha256': hashlib.sha256(labels.data).hexdigest(),
            'targets': visibility_from_labels(labels.data, labels.width, labels.height, labels.step, self.observer['target_label_map'])})

    def close(self):
        with self.lock:
            self.closed = True
        for kind in self.buffers:
            self.node.unsubscribe(self.observer[kind+'_topic'])
        write_new(self.output/'public/frames.json', {'schema_version': VERSION, 'camera': self.observer['name'], 'frames': self.rows})
        write_new(self.output/'private/visibility.json', {'schema_version': VERSION, 'frames': self.private_rows})
        report = {'status': 'CAPTURED_EXACT_NATIVE_PAIRS' if self.rows and not self.errors else 'FAIL',
                  'pairs': len(self.rows), 'received': self.received, 'unpaired_evictions': self.unpaired_evictions,
                  'errors': self.errors, 'timestamp_join': 'exact native header stamp nanoseconds',
                  'privileged_labels_exposed_to_rgb_inference': False,
                  'capture_script_sha256': sha256(__file__),
                  'perception_module_sha256': sha256(ROOT/'src/uchuva_gazebo/harvest_perception.py')}
        write_new(self.output/'capture_report.json', report)
        return report


def static_capture(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tree = ET.parse(args.world)
    world = tree.getroot().find('world')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    geometry_before = [ET.tostring(n).decode() for n in world.findall('.//geometry')]
    model_poses = {m.get('name'): m.findtext('pose') for m in world.findall('model')}
    # The original world remains untouched. This is explicitly a static sensor
    # observation, not a physics test of the original dynamic scene.
    for parent in list(world.iter()):
        for child in list(parent):
            if child.tag == 'sensor' or (child.tag == 'plugin' and child.get('name') not in (
                    'gz::sim::systems::Physics', 'gz::sim::systems::SceneBroadcaster', 'gz::sim::systems::Sensors')):
                parent.remove(child)
    for model in world.findall('model'):
        static = model.find('static')
        if static is None:
            static = ET.SubElement(model, 'static')
        static.text = 'true'
    if geometry_before != [ET.tostring(n).decode() for n in world.findall('.//geometry')]:
        raise ValueError('Static preparation changed geometry')
    if model_poses != {m.get('name'): m.findtext('pose') for m in world.findall('model')}:
        raise ValueError('Static preparation changed a model pose')
    assets = {}
    for entry in world.iter():
        if entry.tag in ('uri', 'albedo_map', 'normal_map', 'roughness_map', 'metalness_map'):
            path = (args.world.resolve().parent/(entry.text or '').strip()).resolve(strict=True)
            if not path.is_file():
                raise ValueError('Unsupported external asset')
            assets[str(path)] = sha256(path)
            entry.text = str(path)
    observers = []
    for index, plant in enumerate(manifest['plants']):
        x, y, _z = plant['position_m']
        observers.append(add_instance_observer(world, name=f'plant_view_{index:03d}',
            pose=[x-1., y, .68, 0., 0., 0.], targets=manifest['fruits'], fps=2))
    sdf = output/'capture.sdf'
    ET.indent(tree)
    tree.write(sdf, encoding='utf-8', xml_declaration=True)
    write_new(output/'protocol.json', {'scope': 'Static native sensor diagnostic; all original models explicitly fixed',
        'source_world': str(args.world.resolve()), 'source_world_sha256': sha256(args.world),
        'source_manifest_sha256': sha256(args.manifest), 'geometry_and_model_poses_preserved': True,
        'assets_sha256': assets, 'observers': observers, 'pairs_per_camera': args.pairs,
        'minimum_native_stamp_ns': 200_000_000, 'wall_timeout_s': args.wall_timeout,
        'capture_script_sha256': sha256(__file__), 'perception_module_sha256': sha256(ROOT/'src/uchuva_gazebo/harvest_perception.py')})
    os.environ['GZ_PARTITION'] = 'harvest_rgb_tournament_'+str(os.getpid())
    os.environ['GZ_SIM_RESOURCE_PATH'] = str(args.world.resolve().parent)
    os.environ['GALLIUM_DRIVER'] = 'd3d12'
    os.environ['MESA_D3D12_DEFAULT_ADAPTER_NAME'] = 'NVIDIA'
    os.environ['LD_LIBRARY_PATH'] = '/usr/lib/wsl/lib:'+os.environ.get('LD_LIBRARY_PATH', '')
    recorders = [NativePerceptionRecorder(output/o['name'], o, maximum_pairs=args.pairs, minimum_stamp_ns=200_000_000) for o in observers]
    command = ['gz', 'sim', '--force-version', '8', '-s', '-r', '--headless-rendering', '-v', '3', str(sdf)]
    write_new(output/'execution.json', {'command': command, 'partition': os.environ['GZ_PARTITION']})
    started = time.monotonic()
    timed_out = False
    with (output/'native.log').open('x') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None and not all(len(r.rows) >= args.pairs for r in recorders):
                if any(r.errors for r in recorders):
                    break
                if time.monotonic()-started > args.wall_timeout:
                    timed_out = True
                    break
                time.sleep(.1)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
    reports = [r.close() for r in recorders]
    unchanged = all(sha256(path) == digest for path, digest in assets.items())
    write_new(output/'result.json', {'status': 'PASS_CAPTURE_ONLY' if not timed_out and unchanged and all(r['status']=='CAPTURED_EXACT_NATIVE_PAIRS' and r['pairs']==args.pairs for r in reports) else 'FAIL',
        'wall_seconds': time.monotonic()-started, 'native_exit_code': process.returncode,
        'timed_out': timed_out, 'assets_unchanged': unchanged, 'reports': reports,
        'dynamic_robot_or_harvest_acceptance': False})
    print(json.dumps({'output': str(output), 'pairs': [r['pairs'] for r in reports], 'timed_out': timed_out}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=2)
    parser.add_argument('--wall-timeout', type=float, default=120)
    args = parser.parse_args()
    if args.pairs < 1 or not 0 < args.wall_timeout <= 180:
        parser.error('Require positive pairs and wall timeout <=180 s')
    static_capture(args)
