"""Explicit RGB / simulator-visibility boundary for the harvest diagnostic.

The Gazebo label map is privileged observation, never detector input. Model
identity association uses that map even in the RGB gate and is labelled as such.
No function here changes plant geometry, rigid dynamics, or robot state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET

VERSION = "harvest-perception/1.0"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _element(parent, tag, value=None, **attributes):
    child = ET.SubElement(parent, tag, attributes)
    if value is not None:
        child.text = str(value)
    return child


def add_instance_observer(world, *, name, pose, targets, width=1280, height=720,
                          horizontal_fov_rad=1.2, fps=5):
    """Add a static co-located RGB/panoptic pair and unique target labels.

    ``targets`` contains ``id`` and ``model_name`` from the harvest manifest.
    All existing surfaces remain in the render scene and occlude normally.
    Labels cover the complete reproductive-unit model, including its pedicel.
    The callback must join native timestamps exactly; sensor rate is not a join.
    """
    if len(pose) != 6 or not all(math.isfinite(x) for x in pose):
        raise ValueError("Observer needs a finite SDF xyz/rpy pose")
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError("Observer name must be a portable identifier")
    if type(width) is not int or type(height) is not int or min(width, height) < 16:
        raise ValueError("Invalid camera dimensions")
    if not 0 < horizontal_fov_rad < math.pi or not math.isfinite(fps) or fps <= 0:
        raise ValueError("Invalid camera field of view or rate")
    if not 1 <= len(targets) <= 254 or len({t['id'] for t in targets}) != len(targets) or len({t['model_name'] for t in targets}) != len(targets):
        raise ValueError("Targets need unique identities/models and at most 254 labels")
    if world.find(f"model[@name='{name}']") is not None:
        raise ValueError("Observer already exists")
    labels = {}
    target_models = {target['model_name'] for target in targets}
    assigned_labels = {str(i) for i in range(1, len(targets)+1)}
    for model in world.findall('model'):
        if model.get('name') not in target_models:
            if any(p.get('name') == 'gz::sim::systems::Label' and p.findtext('label') in assigned_labels for p in model.findall('plugin')):
                raise ValueError('A non-target model already uses a target semantic label')
    # Validate every target before mutating the XML.
    selected = []
    for label, target in enumerate(targets, 1):
        model = next((m for m in world.findall('model') if m.get('name') == target['model_name']), None)
        if model is None:
            raise ValueError("Missing target model: " + target['model_name'])
        existing = [p for p in model.findall('plugin') if p.get('name') == 'gz::sim::systems::Label']
        if len(existing) > 1 or (existing and existing[0].findtext('label') != str(label)):
            raise ValueError("Target has a conflicting native label")
        selected.append((model, existing, label, target))
    for model, existing, label, target in selected:
        if not existing:
            plugin = _element(model, 'plugin', filename='gz-sim-label-system', name='gz::sim::systems::Label')
            _element(plugin, 'label', label)
        labels[str(label)] = {'id': target['id'], 'model_name': target['model_name']}
    if not any(p.get('name') == 'gz::sim::systems::Sensors' for p in world.findall('plugin')):
        plugin = _element(world, 'plugin', filename='gz-sim-sensors-system', name='gz::sim::systems::Sensors')
        _element(plugin, 'render_engine', 'ogre2')
    model = _element(world, 'model', name=name)
    _element(model, 'static', 'true')
    _element(model, 'pose', ' '.join(format(x, '.17g') for x in pose))
    link = _element(model, 'link', name='camera_link')
    sensor = _element(link, 'sensor', name='rgb', type='camera')
    _element(sensor, 'always_on', 'true')
    _element(sensor, 'update_rate', fps)
    topic = '/harvest/perception/' + name
    _element(sensor, 'topic', topic + '/rgb')
    camera = _element(sensor, 'camera')
    _element(camera, 'horizontal_fov', format(horizontal_fov_rad, '.17g'))
    image = _element(camera, 'image')
    _element(image, 'width', width)
    _element(image, 'height', height)
    _element(image, 'format', 'R8G8B8')
    clip = _element(camera, 'clip')
    _element(clip, 'near', .02)
    _element(clip, 'far', 100)
    focal = width / (2 * math.tan(horizontal_fov_rad / 2))
    # Explicit pinhole intrinsics, shared by the RGB and label render cameras.
    intrinsics = _element(_element(camera, 'lens'), 'intrinsics')
    for key, value in (('fx', focal), ('fy', focal), ('cx', width/2), ('cy', height/2), ('s', 0)):
        _element(intrinsics, key, format(value, '.17g'))
    segmentation = copy.deepcopy(sensor)
    segmentation.set('name', 'instances')
    segmentation.set('type', 'segmentation')
    segmentation.find('topic').text = topic + '/instances'
    _element(segmentation.find('camera'), 'segmentation_type', 'panoptic')
    link.append(segmentation)
    return {'schema_version': VERSION, 'name': name, 'pose_world_xyzrpy': list(pose),
            'width': width, 'height': height, 'fps': fps,
            'intrinsic_matrix': [[focal, 0., width/2], [0., focal, height/2], [0., 0., 1.]],
            'distortion_coefficients': [0.] * 5, 'camera_model': 'pinhole',
            'optical_axes': 'SDF camera +X forward, +Y left, +Z up; image u right, v down',
            'rgb_topic': topic + '/rgb', 'labels_topic': topic + '/instances/labels_map',
            'target_label_map': labels, 'label_channels_rgb': 'instance_lo,instance_hi,semantic',
            'visibility_scope': 'native visible pixels of the labelled complete reproductive unit; not full silhouette or occlusion fraction'}


def checked_rgb_frames(public_root):
    """Strict public allowlist: only RGB filenames, hashes and native stamps."""
    root = Path(public_root).resolve()
    payload = json.loads((root/'frames.json').read_text(encoding='utf-8'))
    if set(payload) != {'schema_version', 'camera', 'frames'} or payload['schema_version'] != VERSION:
        raise ValueError('Unexpected fields in public RGB manifest')
    if not isinstance(payload['camera'], str) or not payload['frames']:
        raise ValueError('Missing public camera identity / frames')
    previous = -1
    identifiers = set()
    for row in payload['frames']:
        if set(row) != {'frame_id', 'stamp_ns', 'filename', 'image_sha256', 'width', 'height'}:
            raise ValueError('RGB input contains nonpublic or unexpected fields')
        if type(row['stamp_ns']) is not int or row['stamp_ns'] <= previous:
            raise ValueError('RGB timestamps must strictly increase')
        previous = row['stamp_ns']
        if row['frame_id'] in identifiers:
            raise ValueError('Duplicate RGB frame identity')
        identifiers.add(row['frame_id'])
        uri = PurePosixPath(row['filename'])
        if uri.is_absolute() or '..' in uri.parts or ':' in row['filename'] or '\\' in row['filename']:
            raise ValueError('RGB path must be contained and portable')
        path = (root/uri).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != '.png' or sha256(path) != row['image_sha256']:
            raise ValueError('RGB hash/path mismatch')
        if any(type(row[k]) is not int or row[k] < 1 for k in ('width', 'height')):
            raise ValueError('RGB dimensions must be positive integers')
    return payload


def box_iou(a, b):
    if len(a) != 4 or len(b) != 4 or not all(math.isfinite(v) for v in (*a, *b)):
        raise ValueError('Boxes must contain finite xyxy coordinates')
    if any(v[2] <= v[0] or v[3] <= v[1] for v in (a, b)):
        return 0.
    intersection = max(0., min(a[2], b[2])-max(a[0], b[0])) * max(0., min(a[3], b[3])-max(a[1], b[1]))
    return intersection / ((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)


def target_gate(prediction, visibility, *, mode, now_ns, maximum_age_ns,
                minimum_visible_pixels, minimum_box_iou):
    """Fail-closed, explicit target-identity association after RGB inference.

    A prediction cannot establish a morphology ID by itself. In ``learned_rgb``
    mode the identity match remains simulator-assisted, while presence requires
    an independently inferred RGB box. The fallback never claims RGB detection.
    """
    if mode not in ('learned_rgb', 'gazebo_instance_visibility'):
        raise ValueError('An explicit supported perception mode is required')
    if type(now_ns) is not int or type(maximum_age_ns) is not int or maximum_age_ns < 0:
        raise ValueError('Invalid freshness bounds')
    if type(minimum_visible_pixels) is not int or minimum_visible_pixels < 1 or not 0 < minimum_box_iou <= 1:
        raise ValueError('Invalid explicit detection/visibility thresholds')
    stamp = visibility['stamp_ns']
    if type(stamp) is not int or not 0 <= now_ns-stamp <= maximum_age_ns:
        raise ValueError('Native visibility is stale or from the future')
    if mode == 'learned_rgb':
        if prediction is None or prediction['stamp_ns'] != stamp or prediction['image_sha256'] != visibility['image_sha256'] or prediction['frame_id'] != visibility['frame_id']:
            raise ValueError('RGB prediction and native visibility require an exact frame/hash join')
    detections = [] if prediction is None else prediction['detections']
    if len({t['id'] for t in visibility['targets']}) != len(visibility['targets']):
        raise ValueError('Duplicate native target identity')
    for target in visibility['targets']:
        if type(target['visible_pixels']) is not int or target['visible_pixels'] < 0:
            raise ValueError('Visible pixel count must be a nonnegative integer')
        if target['visible_pixels'] and (target['box_xyxy_px'] is None or box_iou(target['box_xyxy_px'], target['box_xyxy_px']) != 1):
            raise ValueError('Visible target needs a valid native bounding box')
    candidates = []
    for target in visibility['targets']:
        if target['visible_pixels'] < minimum_visible_pixels:
            continue
        box = target['box_xyxy_px']
        candidates.append((target, box))
    assignments = {}
    if mode == 'learned_rgb':
        used = set()
        for index in sorted(range(len(detections)), key=lambda i: -detections[i]['confidence']):
            detection = detections[index]
            if not math.isfinite(detection['confidence']) or not 0 <= detection['confidence'] <= 1:
                raise ValueError('Invalid RGB confidence')
            choices = [(box_iou(detection['box_xyxy_px'], box), target['id']) for target, box in candidates if target['id'] not in used]
            if choices:
                overlap, identity = max(choices)
                if overlap >= minimum_box_iou:
                    assignments[identity] = {'detection_index': index, 'box_iou': overlap}
                    used.add(identity)
    rows = []
    for target in visibility['targets']:
        visible = target['visible_pixels'] >= minimum_visible_pixels
        match = assignments.get(target['id'])
        rows.append({'id': target['id'], 'eligible': visible and (mode == 'gazebo_instance_visibility' or match is not None),
                     'native_visible_pixels': target['visible_pixels'], 'rgb_match': match})
    return {'schema_version': VERSION, 'mode': mode, 'stamp_ns': stamp,
            'source': 'RGB_detection_with_simulator_identity_association' if mode == 'learned_rgb' else 'privileged_native_Gazebo_visibility',
            'autonomous_3d_perception': False, 'targets': rows}
