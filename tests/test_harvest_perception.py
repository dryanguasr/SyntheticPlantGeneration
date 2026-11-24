"""Isolation, native timestamp, occlusion and target-gate contracts."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
from uchuva_gazebo.harvest_perception import VERSION, add_instance_observer, checked_rgb_frames, sha256, target_gate
from harvest_perception_capture import NativePerceptionRecorder, visibility_from_labels
from harvest_rgb_tournament import merge_boxes, tile_windows


class PerceptionContracts(unittest.TestCase):
    def setUp(self):
        self.visible = {'frame_id': 'one', 'stamp_ns': 123, 'image_sha256': 'a'*64,
            'targets': [{'id': 'a', 'visible_pixels': 100, 'box_xyxy_px': [10, 10, 20, 20]},
                        {'id': 'b', 'visible_pixels': 0, 'box_xyxy_px': None}]}
        self.prediction = {'frame_id': 'one', 'stamp_ns': 123, 'image_sha256': 'a'*64,
            'detections': [{'confidence': .9, 'box_xyxy_px': [10, 10, 20, 20]}]}
        self.parameters = dict(mode='learned_rgb', now_ns=123, maximum_age_ns=0,
                               minimum_visible_pixels=16, minimum_box_iou=.5)

    def test_rgb_gate_requires_visible_identity_and_matching_detection(self):
        result = target_gate(self.prediction, self.visible, **self.parameters)
        self.assertEqual([r['eligible'] for r in result['targets']], [True, False])
        self.assertIn('simulator_identity', result['source'])
        self.prediction['detections'] = []
        self.assertFalse(target_gate(self.prediction, self.visible, **self.parameters)['targets'][0]['eligible'])

    def test_privileged_fallback_is_explicit_and_does_not_claim_detection(self):
        result = target_gate(None, self.visible, **(self.parameters | {'mode': 'gazebo_instance_visibility'}))
        self.assertTrue(result['targets'][0]['eligible'])
        self.assertIsNone(result['targets'][0]['rgb_match'])
        self.assertEqual(result['source'], 'privileged_native_Gazebo_visibility')
        self.assertFalse(result['autonomous_3d_perception'])

    def test_exact_timestamp_hash_identity_and_freshness(self):
        for key, replacement in [('stamp_ns', 124), ('image_sha256', 'b'*64), ('frame_id', 'other')]:
            with self.subTest(key=key):
                altered = self.prediction | {key: replacement}
                with self.assertRaises(ValueError):
                    target_gate(altered, self.visible, **self.parameters)
        for now in (122, 124):
            with self.assertRaises(ValueError):
                target_gate(self.prediction, self.visible, **(self.parameters | {'now_ns': now}))

    def test_one_box_cannot_gate_two_targets(self):
        self.visible['targets'][1] = {'id': 'b', 'visible_pixels': 100, 'box_xyxy_px': [10, 10, 20, 20]}
        result = target_gate(self.prediction, self.visible, **self.parameters)
        self.assertEqual(sum(r['eligible'] for r in result['targets']), 1)

    def test_native_label_byte_order_stride_and_occluded_target(self):
        # RGB panoptic = low-instance, high-instance, semantic, including padding.
        data = bytes([11, 0, 1, 12, 0, 1, 99, 99, 0, 9, 9, 9])
        result = visibility_from_labels(data, 3, 1, 12, {'1': {'id': 'a', 'model_name': 'fruit_a'}, '2': {'id': 'b', 'model_name': 'fruit_b'}})
        self.assertEqual(result[0]['visible_pixels'], 2)
        self.assertEqual(result[0]['native_instance_codes'], [11, 12])
        self.assertEqual(result[0]['box_xyxy_px'], [0, 0, 2, 1])
        self.assertEqual(result[1]['visible_pixels'], 0)
        self.assertIsNone(result[1]['box_xyxy_px'])

    def test_recorder_never_joins_nearby_native_timestamps(self):
        recorder = NativePerceptionRecorder.__new__(NativePerceptionRecorder)
        recorder.lock = threading.Lock()
        recorder.closed = False
        recorder.maximum_pairs = None
        recorder.minimum_stamp_ns = 0
        recorder.rows, recorder.errors = [], []
        recorder.buffers = {'rgb': {}, 'labels': {}}
        recorder.received = {'rgb': 0, 'labels': 0}
        recorder.unpaired_evictions = {'rgb': 0, 'labels': 0}
        recorder.observer = {'width': 16, 'height': 16}
        recorder._save = lambda stamp, rgb, label: recorder.rows.append({'stamp_ns': stamp})
        def message(stamp):
            return SimpleNamespace(pixel_format_type=3, width=16, height=16,
                header=SimpleNamespace(stamp=SimpleNamespace(sec=0, nsec=stamp)))
        recorder.receive('rgb', message(100))
        recorder.receive('labels', message(101))
        self.assertEqual(recorder.rows, [])
        recorder.receive('labels', message(100))
        self.assertEqual(recorder.rows, [{'stamp_ns': 100}])
        self.assertEqual(recorder.errors, [])

    def test_rejects_malformed_visibility_instead_of_accepting_fallback(self):
        for value in (float('nan'), -1, True):
            visibility = copy.deepcopy(self.visible)
            visibility['targets'][0]['visible_pixels'] = value
            with self.assertRaises(ValueError):
                target_gate(None, visibility, **(self.parameters | {'mode': 'gazebo_instance_visibility'}))

    def test_non_target_cannot_share_the_selected_semantic_label(self):
        world = ET.fromstring('<world name="w"><model name="fruit"/><model name="other"><plugin name="gz::sim::systems::Label"><label>1</label></plugin></model></world>')
        before = ET.tostring(world)
        with self.assertRaisesRegex(ValueError, 'non-target'):
            add_instance_observer(world, name='eye', pose=[0]*6, targets=[{'id': 'a', 'model_name': 'fruit'}])
        self.assertEqual(before, ET.tostring(world))

    def test_camera_sensor_pair_does_not_move_or_replace_geometry(self):
        world = ET.fromstring('<world name="test"><model name="fruit"><pose>1 2 3 0 0 0</pose><link name="l"><visual name="v"><geometry><sphere><radius>.02</radius></sphere></geometry></visual></link></model></world>')
        before = ET.tostring(world.find('model/link/visual'))
        observer = add_instance_observer(world, name='eye', pose=[0]*6, targets=[{'id': 'target', 'model_name': 'fruit'}])
        self.assertEqual(before, ET.tostring(world.find("model[@name='fruit']/link/visual")))
        self.assertEqual(world.findtext("model[@name='fruit']/pose"), '1 2 3 0 0 0')
        sensors = world.findall("model[@name='eye']/link/sensor")
        first, second = [copy.deepcopy(s.find('camera')) for s in sensors]
        second.remove(second.find('segmentation_type'))
        self.assertEqual(ET.tostring(first), ET.tostring(second))
        self.assertEqual(observer['target_label_map']['1']['id'], 'target')

    def test_rgb_manifest_rejects_privileged_fields_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root/'frame.png'
            image.write_bytes(b'opaque-image-bytes-validation-is-in-decoder')
            data = {'schema_version': VERSION, 'camera': 'eye', 'frames': [{'frame_id': 'f', 'stamp_ns': 1, 'filename': 'frame.png', 'image_sha256': sha256(image), 'width': 20, 'height': 20}]}
            manifest = root/'frames.json'
            manifest.write_text(json.dumps(data))
            self.assertEqual(len(checked_rgb_frames(root)['frames']), 1)
            data['frames'][0]['target_id'] = 'hidden_truth'
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'nonpublic'):
                checked_rgb_frames(root)
            del data['frames'][0]['target_id']
            manifest.write_text(json.dumps(data))
            image.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash/path'):
                checked_rgb_frames(root)

    def test_exhaustive_tiles_and_cross_class_deduplication(self):
        windows = tile_windows(1280, 720)
        self.assertEqual(len(windows), 6)
        for x, y in [(0, 0), (1279, 719), (700, 300)]:
            self.assertTrue(any(a <= x < c and b <= y < d for a, b, c, d in windows))
        boxes = [{'confidence': .7, 'class_id': 0, 'box_xyxy_px': [0, 0, 10, 10]},
                 {'confidence': .9, 'class_id': 1, 'box_xyxy_px': [0, 0, 10, 10]}]
        kept, suppressed = merge_boxes(boxes)
        self.assertEqual(kept[0]['class_id'], 1)
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(suppressed), 1)


if __name__ == '__main__':
    unittest.main()
