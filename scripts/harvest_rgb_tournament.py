"""Compare frozen existing detectors on a strictly RGB-only input package.

Inference and private evaluation are separate subcommands/processes. An
evaluation with only selected labelled fruits reports selected-target coverage,
never global precision, recall of all fruits, or agronomic maturity accuracy.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.harvest_perception import VERSION, box_iou, checked_rgb_frames, sha256, target_gate


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def tile_windows(width, height, size=640, stride=448):
    def starts(length):
        return sorted(set(range(0, max(1, length-size+1), stride)) | {max(0, length-size)})
    return [(x, y, min(x+size, width), min(y+size, height)) for y in starts(height) for x in starts(width)]


def merge_boxes(detections, threshold=.5):
    """Class-agnostic capacho deduplication; preserve appearance per retained box."""
    retained, suppressed = [], []
    for item in sorted(detections, key=lambda d: -d['confidence']):
        other = next((i for i, r in enumerate(retained) if box_iou(item['box_xyxy_px'], r['box_xyxy_px']) >= threshold), None)
        if other is None:
            retained.append(item)
        else:
            suppressed.append({'detection': item, 'retained_index': other})
    return retained, suppressed


def infer(args):
    # The detector reads no capture protocol, targets, labels, calibration,
    # private camera pose, morphology, native depth, or evaluator manifest.
    packages = [(p.resolve(), checked_rgb_frames(p)) for p in args.public]
    if sha256(args.weights) != args.expected_sha256:
        raise ValueError('Checkpoint differs from the explicitly frozen hash')
    output = args.output.resolve()
    if any(output.is_relative_to(p) for p, _ in packages):
        raise ValueError('Predictions cannot be written into public RGB input')
    output.mkdir(parents=True, exist_ok=False)
    import cv2
    import numpy as np
    versions = {'python': platform.python_version(), 'opencv': cv2.__version__, 'numpy': np.__version__}
    if args.backend == 'onnx':
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        model = ort.InferenceSession(str(args.weights), options, providers=['CPUExecutionProvider'])
        if model.get_inputs()[0].shape != [1, 3, 640, 640]:
            raise ValueError('Expected the frozen end-to-end 640 RGB detector')
        versions['onnxruntime'] = ort.__version__
        names = {0: 'calyx'}
    else:
        import torch
        import ultralytics
        from ultralytics import YOLO
        torch.set_num_threads(4)
        model = YOLO(str(args.weights))
        names = model.names
        if list(names.values()) != ['pintona', 'madura', 'sobremadura']:
            raise ValueError('Unexpected appearance class contract')
        versions.update(torch=torch.__version__, ultralytics=ultralytics.__version__)
    protocol = {'schema_version': VERSION, 'model_id': args.model_id, 'model_sha256': args.expected_sha256,
        'backend': args.backend, 'versions': versions, 'confidence': args.confidence,
        'view_policy': args.views, 'tile_size': 640, 'tile_stride': 448,
        'network_size': 640 if args.backend == 'onnx' else 960,
        'box_merge_iou': None if args.backend == 'onnx' and args.views == 'full' else .5,
        'onnx_end2end_additional_nms': args.backend == 'onnx' and args.views != 'full',
        'classes_are_appearance_not_internal_maturity': True,
        'public_manifests': [{'camera': d['camera'], 'sha256': sha256(p/'frames.json')} for p, d in packages],
        'input_allowlist': 'RGB PNGs and frame id/native stamp/hash/dimensions only',
        'ground_truth_used': False, 'target_roi_used': False,
        'source_sha256': {'runner': sha256(__file__), 'module': sha256(ROOT/'src/uchuva_gazebo/harvest_perception.py')}}
    write_new(output/'protocol.json', protocol)
    records = []
    for public, manifest in packages:
        for frame in manifest['frames']:
            image = cv2.imread(str(public/frame['filename']))
            if image is None or (image.shape[1], image.shape[0]) != (frame['width'], frame['height']):
                raise ValueError('Decoded RGB dimensions differ from manifest')
            h, w = image.shape[:2]
            windows = [(0, 0, w, h)] if args.views == 'full' else tile_windows(w, h)
            proposals = []
            started = time.perf_counter()
            for tile_index, (x0, y0, x1, y1) in enumerate(windows):
                crop = image[y0:y1, x0:x1].copy()
                if args.backend == 'onnx':
                    scale = min(640/crop.shape[1], 640/crop.shape[0])
                    rw, rh = round(crop.shape[1]*scale), round(crop.shape[0]*scale)
                    left, top = (640-rw)//2, (640-rh)//2
                    padded = np.full((640, 640, 3), 114, np.uint8)
                    padded[top:top+rh, left:left+rw] = cv2.resize(crop, (rw, rh), interpolation=cv2.INTER_LINEAR)
                    tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32)/255
                    raw = model.run(None, {model.get_inputs()[0].name: tensor})[0]
                    if raw.shape != (1, 300, 6):
                        raise ValueError('Unexpected end-to-end ONNX output')
                    boxes = raw[0].astype(float)
                    boxes[:, :4] = (boxes[:, :4]-[left, top, left, top])/scale
                else:
                    result = model.predict(crop, imgsz=960, rect=False, conf=args.confidence,
                        iou=.7, retina_masks=False, max_det=300, device=args.device, verbose=False)[0]
                    boxes = result.boxes.data.cpu().numpy().astype(float)
                for raw_box in boxes:
                    if not np.isfinite(raw_box).all():
                        raise ValueError('Detector emitted a nonfinite proposal')
                    a, b, c, d, confidence, class_id = raw_box.tolist()
                    if confidence < args.confidence:
                        continue
                    if not 0 <= confidence <= 1 or class_id != int(class_id) or int(class_id) not in names:
                        raise ValueError('Invalid detector confidence/class')
                    box = [max(0, a)+x0, max(0, b)+y0, min(x1-x0, c)+x0, min(y1-y0, d)+y0]
                    if box[2] <= box[0] or box[3] <= box[1]:
                        continue
                    proposals.append({'class_id': int(class_id), 'appearance_class': names[int(class_id)],
                        'confidence': confidence, 'box_xyxy_px': box, 'tile_index': tile_index})
            # The deployed ONNX is already end-to-end: preserve its no-additional-
            # NMS contract for full frames. Exhaustive tiles need cross-tile merging.
            kept, suppressed = (proposals, []) if args.backend == 'onnx' and args.views == 'full' else merge_boxes(proposals)
            row = {'schema_version': VERSION, 'model_id': args.model_id, 'model_sha256': args.expected_sha256,
                'camera': manifest['camera'], 'frame_id': frame['frame_id'], 'stamp_ns': frame['stamp_ns'],
                'image_sha256': frame['image_sha256'], 'inference_seconds': time.perf_counter()-started,
                'detections': kept, 'suppressed': suppressed, 'ground_truth_used': False}
            records.append(row)
            print(json.dumps({'model': args.model_id, 'frame': frame['frame_id'], 'detections': len(kept), 'seconds': row['inference_seconds']}), flush=True)
    with (output/'detections.jsonl').open('x', encoding='utf-8') as stream:
        for row in records:
            stream.write(json.dumps(row, allow_nan=False)+'\n')
    write_new(output/'result.json', {'status': 'RGB_INFERENCE_COMPLETE', 'model_id': args.model_id,
        'frames': len(records), 'detections': sum(len(r['detections']) for r in records),
        'total_inference_seconds': sum(r['inference_seconds'] for r in records),
        'quality_evaluation_performed': False, 'detections_sha256': sha256(output/'detections.jsonl')})


def evaluate(args):
    import cv2
    public = checked_rgb_frames(args.public)
    private = json.loads(args.visibility.read_text(encoding='utf-8'))
    truth = {r['frame_id']: r for r in private['frames']}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for prediction_file in args.predictions:
        predictions = [json.loads(line) for line in prediction_file.read_text(encoding='utf-8').splitlines()]
        camera_predictions = [r for r in predictions if r['camera'] == public['camera']]
        predictions = {r['frame_id']: r for r in camera_predictions}
        if len(predictions) != len(camera_predictions):
            raise ValueError('Duplicate RGB prediction identity')
        if set(predictions) != {r['frame_id'] for r in public['frames']}:
            raise ValueError('Incomplete or unexpected RGB prediction coverage')
        model = next(iter(predictions.values()))['model_id']
        rows = []
        for frame in public['frames']:
            p, visible = predictions[frame['frame_id']], truth[frame['frame_id']]
            if frame['image_sha256'] != visible['image_sha256'] or frame['stamp_ns'] != visible['stamp_ns']:
                raise ValueError('Private visibility does not join the exact public frame')
            gate = target_gate(p, visible, mode='learned_rgb', now_ns=frame['stamp_ns'], maximum_age_ns=0,
                minimum_visible_pixels=args.minimum_visible_pixels, minimum_box_iou=args.minimum_box_iou)
            rows.append(gate)
            image = cv2.imread(str(args.public/frame['filename']))
            for d in p['detections']:
                x0, y0, x1, y1 = map(round, d['box_xyxy_px'])
                cv2.rectangle(image, (x0, y0), (x1, y1), (55, 220, 70), 1)
            for t in visible['targets']:
                if t['visible_pixels'] >= args.minimum_visible_pixels:
                    x0, y0, x1, y1 = map(round, t['box_xyxy_px'])
                    cv2.rectangle(image, (x0, y0), (x1, y1), (255, 130, 0), 2)
                    cv2.putText(image, t['id'].split(':')[0]+' truth', (x0, max(35, y0-4)), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 130, 0), 1)
            cv2.rectangle(image, (0, 0), (image.shape[1], 27), (20, 20, 20), -1)
            cv2.putText(image, f'{model} | RGB green / native target visibility blue | t={frame["stamp_ns"]/1e9:.3f}s',
                (8, 19), cv2.FONT_HERSHEY_SIMPLEX, .46, (245, 245, 245), 1)
            if not cv2.imwrite(str(output/(model+'_'+frame['frame_id']+'.png')), image):
                raise RuntimeError('Overlay write failed')
        eligible = sum(t['native_visible_pixels'] >= args.minimum_visible_pixels for r in rows for t in r['targets'])
        matched = sum(t['eligible'] for r in rows for t in r['targets'])
        summaries.append({'model_id': model, 'visible_selected_observations': eligible,
            'rgb_matched_selected_observations': matched, 'selected_target_coverage': matched/eligible if eligible else None,
            'total_rgb_detections': sum(len(r['detections']) for r in predictions.values()),
            'inference_seconds': sum(r['inference_seconds'] for r in predictions.values()),
            'prediction_file_sha256': sha256(prediction_file), 'gates': rows})
    write_new(output/'comparison.json', {'schema_version': VERSION, 'camera': public['camera'],
        'minimum_visible_pixels': args.minimum_visible_pixels, 'minimum_box_iou': args.minimum_box_iou,
        'scope': 'Selected-target diagnostic coverage only; unlabelled fruits are not negatives; no global precision or full-fruit recall',
        'public_manifest_sha256': sha256(args.public/'frames.json'), 'visibility_sha256': sha256(args.visibility),
        'source_sha256': {'runner': sha256(__file__), 'module': sha256(ROOT/'src/uchuva_gazebo/harvest_perception.py')},
        'models': summaries})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inference = sub.add_parser('infer')
    inference.add_argument('--public', type=Path, action='append', required=True)
    inference.add_argument('--weights', type=Path, required=True)
    inference.add_argument('--expected-sha256', required=True)
    inference.add_argument('--model-id', required=True)
    inference.add_argument('--backend', choices=['onnx', 'yolo'], required=True)
    inference.add_argument('--views', choices=['full', 'tiles'], required=True)
    inference.add_argument('--confidence', type=float, default=.25)
    inference.add_argument('--device', default='cpu')
    inference.add_argument('--output', type=Path, required=True)
    evaluation = sub.add_parser('evaluate')
    evaluation.add_argument('--public', type=Path, required=True)
    evaluation.add_argument('--visibility', type=Path, required=True)
    evaluation.add_argument('--predictions', type=Path, action='append', required=True)
    evaluation.add_argument('--minimum-visible-pixels', type=int, required=True)
    evaluation.add_argument('--minimum-box-iou', type=float, required=True)
    evaluation.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'infer':
        if not 0 < args.confidence <= 1 or not args.model_id.replace('_', '').isalnum():
            parser.error('Require finite confidence in (0,1] and portable model id')
        infer(args)
    else:
        evaluate(args)


if __name__ == '__main__':
    main()
