"""Aggregate the private selected-target diagnostic and explicit fallback proof."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts')]
from uchuva_gazebo.harvest_perception import checked_rgb_frames, sha256, target_gate
from harvest_perception_overlay import aligned_overlay


def main():
    import cv2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--comparisons', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    reports = sorted(args.comparisons.glob('*/comparison.json'))
    if not reports:
        raise ValueError('Missing per-camera evaluations')
    models, fallback, bindings = {}, [], {}
    for path in reports:
        comparison = json.loads(path.read_text(encoding='utf-8'))
        camera = comparison['camera']
        public_root = args.capture/camera/'public'
        frames = checked_rgb_frames(public_root)['frames']
        visibility_path = args.capture/camera/'private/visibility.json'
        private = json.loads(visibility_path.read_text(encoding='utf-8'))
        truth = {r['frame_id']: r for r in private['frames']}
        bindings[str(path.resolve())] = sha256(path)
        bindings[str(visibility_path.resolve())] = sha256(visibility_path)
        for model in comparison['models']:
            total = models.setdefault(model['model_id'], {'matched_selected_observations': 0,
                'visible_selected_observations': 0, 'rgb_detections': 0, 'inference_seconds': 0., 'cameras': []})
            total['matched_selected_observations'] += model['rgb_matched_selected_observations']
            total['visible_selected_observations'] += model['visible_selected_observations']
            total['rgb_detections'] += model['total_rgb_detections']
            total['inference_seconds'] += model['inference_seconds']
            total['cameras'].append(camera)
        for index, frame in enumerate(frames):
            row = truth[frame['frame_id']]
            if any(row[k] != frame[k] for k in ('frame_id', 'stamp_ns', 'image_sha256')):
                raise ValueError('Fallback visibility does not match the public RGB frame')
            proof = target_gate(None, row, mode='gazebo_instance_visibility', now_ns=frame['stamp_ns'], maximum_age_ns=0,
                minimum_visible_pixels=comparison['minimum_visible_pixels'], minimum_box_iou=comparison['minimum_box_iou'])
            fallback.append({'camera': camera, 'frame_id': frame['frame_id'], 'image_sha256': frame['image_sha256'], **proof})
            if index == 0:
                image = cv2.imread(str(public_root/frame['filename']))
                annotated = aligned_overlay(image, frame, visibility=row, gate=proof)
                if not cv2.imwrite(str(args.output/(camera+'_native_visibility.png')), annotated):
                    raise RuntimeError('Fallback overlay write failed')
    for result in models.values():
        denominator = result['visible_selected_observations']
        result['selected_target_coverage'] = result['matched_selected_observations']/denominator if denominator else None
    sources = ['src/uchuva_gazebo/harvest_perception.py', 'scripts/harvest_perception_capture.py',
        'scripts/harvest_rgb_tournament.py', 'scripts/harvest_perception_overlay.py',
        'scripts/report_harvest_rgb_tournament.py', 'tests/test_harvest_perception.py']
    source_hashes = {}
    for relative in sources:
        target = args.output/'source_snapshot'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, target)
        source_hashes[relative] = sha256(target)
    report = {'schema_version': 'harvest-rgb-tournament-summary/1.0', 'models': models,
        'fallback_proof': fallback, 'source_files_sha256': source_hashes, 'evidence_sha256': bindings,
        'fallback_is_privileged_simulation': True, 'detector_input_was_rgb_only': True,
        'selection_scope': 'Existing selected reproductive units only; three distinct fixed camera views, two repeated exposures per view',
        'limitations': ['Unlabelled capachos cannot be used as negative detections; global precision unavailable',
            'Static repeated exposures are not independent scenes or validation of moving-camera tracking',
            'Camera intrinsics are explicit SDF pinhole settings, not real-camera calibration',
            'Fallback means native instance visibility, not learned detection or autonomous 3D localization',
            'The native capture exit status and all warnings remain in its original result/log']}
    with (args.output/'summary.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(models), flush=True)


if __name__ == '__main__':
    main()
