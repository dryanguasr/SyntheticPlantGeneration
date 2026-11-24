"""Publish visual-only control from the same RGB pose source as fusion v3."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
old=ROOT/'outputs/continuous_row_20261008'
out=ROOT/'outputs/integral_diagnosis_20261014/public_visual_pose_control.jsonl'
rig={str(r['id']):r['canonical_id'] for r in json.loads((old/'public/calibration.json').read_text())['rig']}
with out.open('x') as target,(old/'estimates/offline_every_frame/observations.jsonl').open() as source:
    for line in source:
        row=json.loads(line);poses={}
        for decoded,pose in row['marker_poses'].items():
            key=str(rig[decoded])
            if key in poses:raise ValueError('Simultaneous canonical measurements require explicit aggregation')
            poses[key]=dict(R=pose['R'],t=pose['t'],source='RGB_ArUco')
        target.write(json.dumps(dict(stamp_ns=row['stamp_ns'],marker_poses=poses))+'\n')
print('VISUAL_CONTROL_WRITTEN',flush=True)
