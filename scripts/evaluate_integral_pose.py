"""Evaluator-only pose errors. Never exports truth to the estimator."""
import json
import argparse
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from diagnose_continuous_geometry import true_marker_pose
from uchuva_lsystem.segmentation_cycles import write


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-name',default='pose_fusion_v2');args=parser.parse_args()
    if Path(args.input_name).name!=args.input_name:raise ValueError('Input must be a directory name')
    root = ROOT / 'outputs/integral_diagnosis_20261014'
    old = ROOT / 'outputs/continuous_row_20261008'
    samples = json.loads((old / 'flight/full/telemetry.json').read_text())['samples']
    times = np.array([s['t'] for s in samples])
    markers = {str(m['id']): m for m in json.loads((old / 'flight/preflight.json').read_text())['markers']}
    baseline = old / 'estimates/offline_every_frame/observations.jsonl'
    canonical = {str(r['id']):str(r['canonical_id']) for r in json.loads((old/'public/calibration.json').read_text())['rig']}
    visible = {}
    with baseline.open() as stream:
        for line in stream:
            row = json.loads(line)
            visible[row['stamp_ns']] = {canonical[k] for k in row['marker_poses']}
    paths = {'visual': baseline, **{p: root / args.input_name / f'{p}.jsonl' for p in ('low', 'nominal', 'high')}}
    results = {}
    for name, path in paths.items():
        groups = {'all': [], 'visually_observed': [], 'propagated_only': []}
        time_errors = []
        with path.open() as stream:
            for line in stream:
                row = json.loads(line)
                stamp = row['stamp_ns']; t = stamp / 1e9
                if t < times[0] or t > times[-1]:
                    continue
                j = int(np.clip(np.searchsorted(times, t), 1, len(times)-1))
                a = (t-times[j-1])/(times[j]-times[j-1])
                s0, s1 = samples[j-1], samples[j]
                q0 = np.asarray(s0['quaternion_xyzw']); q1 = np.asarray(s1['quaternion_xyzw'])
                if q0 @ q1 < 0: q1 = -q1
                q = (1-a)*q0+a*q1; q /= np.linalg.norm(q)
                sample = {'position': (1-a)*np.asarray(s0['position'])+a*np.asarray(s1['position']), 'quaternion_xyzw': q}
                time_errors.append(float(times[j]-times[j-1]))
                for marker, pose in row['marker_poses'].items():
                    if name == 'visual': marker = canonical[marker]
                    if marker not in markers: continue
                    truth = true_marker_pose(sample, markers[marker])
                    R, tr = np.asarray(pose['R']), np.asarray(pose['t'])
                    Rt, tt = np.asarray(truth['R']), np.asarray(truth['t'])
                    center_error = float(np.linalg.norm(-R.T@tr + Rt.T@tt))
                    angular_error = float(np.rad2deg(np.linalg.norm(cv2.Rodrigues(R@Rt.T)[0])))
                    value = [center_error, angular_error]
                    groups['all'].append(value)
                    groups['visually_observed' if marker in visible[stamp] else 'propagated_only'].append(value)
        summaries = {}
        for group, values in groups.items():
            v = np.asarray(values)
            summaries[group] = dict(marker_frames=len(values),
                median_position_m=float(np.median(v[:, 0])) if len(v) else None,
                p95_position_m=float(np.percentile(v[:, 0], 95)) if len(v) else None,
                median_rotation_deg=float(np.median(v[:, 1])) if len(v) else None,
                p95_rotation_deg=float(np.percentile(v[:, 1], 95)) if len(v) else None)
        results[name] = dict(groups=summaries, maximum_interpolation_bracket_s=max(time_errors, default=None))
    write(root / args.input_name / 'evaluator_pose_errors.json', dict(version='pose-errors/1.1', results=results,
        privileged_evaluator_only=True, configuration_selection_scope='development',
        limitation='Interpolated simulator truth; pose errors are not capacho localization scores. All-frame groups have unequal coverage; compare visually_observed on common support.'))
    print(json.dumps(results, indent=2))


if __name__ == '__main__': main()
