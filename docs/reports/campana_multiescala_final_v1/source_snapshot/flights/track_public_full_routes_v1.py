"""CPU tracking of persisted RGB-only predictions; no private evaluator inputs."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    campaign = Path(__file__).resolve().parent
    helper_path = campaign.parents[1] / 'multiscale_dataset_20261020/evaluate_multiscale_v1.py'
    import hashlib
    assert hashlib.sha256(helper_path.read_bytes()).hexdigest() == '111f4359578dae14adaef24626b82bc94b644efef82d1b4076d54a7906b34527'
    spec = importlib.util.spec_from_file_location('frozen_mask_cache', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    frozen = campaign.parents[1] / 'frozen_field_pilot_20261019/frozen/src'
    sys.path.insert(0, str(frozen))
    from uchuva_gazebo.mask_tracking import MaskTracker
    tracker_files = [frozen / 'uchuva_gazebo' / name for name in
                     ('mask_tracking.py', 'localization.py', 'multiview.py')]
    frames = helper.read(args.public / 'frames.json')
    summary = helper.read(args.predictions / 'summary.json')
    assert len(frames) == len(summary['frames']) and len(frames)>0
    assert not args.output.exists(), 'Keep existing tracking output; never overwrite completed work'
    args.output.mkdir(parents=True)
    binding = dict(prediction_summary_sha256=helper.sha(args.predictions/'summary.json'),
                   public_frames_sha256=helper.sha(args.public/'frames.json'),
                   tracker_sources={str(p): helper.sha(p) for p in tracker_files},
                   max_gap_seconds=2.0, cpu_only=True, private_inputs=False)
    helper.write(args.output/'binding.json', binding)
    cv2.setNumThreads(4)
    tracker = MaskTracker()
    observations = []
    minimum_free = float('inf')
    for i, frame in enumerate(frames):
        minimum_free = min(minimum_free, helper.memory_guard())
        rgb_path = args.public / 'rgb' / frame['filename']
        assert rgb_path.resolve().is_relative_to(args.public.resolve())
        assert helper.sha(rgb_path) == frame['rgb_sha256']
        stem = f'frame_{i:03d}'
        record = helper.read(args.predictions/'predictions'/(stem+'.json'))
        cb = record['binding']
        assert cb['frame'] == i and cb['stamp_ns'] == frame['stamp_ns']
        assert cb['rgb_sha256'] == frame['rgb_sha256']
        assert cb['run_binding'] == summary['run_binding']
        predictions = helper.load_predictions(args.predictions/'predictions', stem, cb)
        image = cv2.imread(str(rgb_path))
        assert image is not None and image.shape == (720,1280,3)
        masks, detections = [], []
        for prediction in predictions:
            x1,y1,x2,y2 = prediction['bbox']
            mask = np.zeros((720,1280), dtype=bool)
            mask[y1:y2,x1:x2] = prediction['mask']
            yy,xx = np.nonzero(mask)
            masks.append(mask)
            detections.append(dict(prediction['label'],box_xyxy_px=prediction['bbox'],
                                   center_px=[float(xx.mean()),float(yy.mean())]))
        tracker.update(image, detections, frame['stamp_ns'], masks)
        canvas = image.copy()
        for mask, det in zip(masks, detections):
            identifier = int(det['track_id'].split('_')[-1])
            color = np.array([(identifier*67+70)%230,(identifier*113+90)%230,(identifier*41+140)%230])
            canvas[mask] = (canvas[mask]*.5+color*.5).astype(np.uint8)
            x,y = det['box_xyxy_px'][:2]
            cv2.putText(canvas,str(identifier),(x,max(12,y)),cv2.FONT_HERSHEY_SIMPLEX,.35,(255,255,255),1,cv2.LINE_AA)
        cv2.putText(canvas,'Multiscale full route | predicted masks + track IDs | frame '+str(i),(12,24),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1,cv2.LINE_AA)
        assert cv2.imwrite(str(args.output/(stem+'.jpg')),canvas)
        observations.append(dict(frame=i,stamp_ns=frame['stamp_ns'],filename=frame['filename'],
                                 prediction_record_sha256=helper.sha(args.predictions/'predictions'/(stem+'.json')),
                                 detections=detections))
        helper.write(args.output/'observations.json',observations)
        print(stem,len(detections),flush=True)
    helper.write(args.output/'rejections.json',tracker.rejections)
    helper.write(args.output/'summary.json',dict(frames=len(frames),detections=sum(len(f['detections']) for f in observations),
                  allocated_track_ids=tracker.next_id,minimum_free_gib=minimum_free,
                  tracking_complete=True,identity_accuracy_evaluated=False,
                  localization_performed=False,private_inputs=False,
                  next='Private original-mask detection and adjacent-match identity evaluation; no scientific promotion.'))


if __name__ == '__main__':
    main()
