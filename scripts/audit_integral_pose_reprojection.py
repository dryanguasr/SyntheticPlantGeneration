"""Public-input diagnostic of pose substitution on RGB-control map supports.

The reference positions are RGB estimates, not truth. Residuals diagnose
compatibility only and must not be reported as absolute pose accuracy.
"""
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.offline_reconciliation import residuals, fit_sequence
from summarize_integral_sequence import detection_digest


def main():
    root = ROOT / 'outputs/integral_diagnosis_20261014'
    names = ('visual_pose_control', 'fused_pose_v3', 'gap_pose_v1')
    paths = {n: root / 'sequence_estimates' / n / 'observations.jsonl' for n in names}
    digests = {n: detection_digest(p) for n, p in paths.items()}
    if any(v != digests[names[0]] for v in digests.values()):
        raise ValueError('Different observations or track identities')
    streams = {n: [json.loads(line) for line in p.open()] for n, p in paths.items()}
    calibration = json.loads((root / 'public_sequence_1hz/calibration.json').read_text())
    K = calibration['K']
    objects = json.loads((root / 'sequence_estimates/visual_pose_control/map.json').read_text())['objects']
    rows = []
    for obj in objects:
        if obj['state'] != 'confirmed':
            continue
        marker = str(obj['marker_id'])
        tracks = set(obj['track_ids'])
        variants = {}
        for name, frames in streams.items():
            observations = []
            for frame in frames:
                pose = frame['marker_poses'].get(marker)
                if pose is None:
                    continue
                for d in frame['detections']:
                    if d['track_id'] in tracks:
                        observations.append(dict(**pose, marker_id=obj['marker_id'], point_px=d['center_px'],
                            stamp_ns=frame['stamp_ns'], observation_id=d['observation_id']))
            errors = residuals(obj['position_marker_m'], observations, K)
            finite = errors[np.isfinite(errors)]
            fit = fit_sequence(observations, K)
            variants[name] = dict(support=len(observations),
                fraction_within_3px=float(np.mean(errors <= 3)),
                median_finite_px=float(np.median(finite)) if len(finite) else None,
                refit_status=fit['status'], refit_reason=fit.get('reason'))
        rows.append(dict(map_id=obj['map_id'], marker_id=obj['marker_id'], variants=variants))
    output = dict(version='public-pose-reprojection-audit/1.1', objects=len(rows), rows=rows,
        identical_detections_and_tracks=True,
        limitation='RGB-control-selected estimates; compatibility diagnostic, not ground-truth accuracy or independent evaluation')
    destination = root / 'pose_reprojection_audit_v2.json'
    with destination.open('x') as stream:
        json.dump(output, stream, indent=2)
    for name in names:
        values = [r['variants'][name] for r in rows]
        print(name, 'refits', sum(v['refit_status']=='estimated' for v in values), '/', len(values),
              'median consistency', float(np.median([v['fraction_within_3px'] for v in values])), flush=True)


if __name__ == '__main__':
    main()
