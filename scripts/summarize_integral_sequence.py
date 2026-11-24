"""Audit matched inputs before summarizing development comparisons."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def detection_digest(path):
    digest=hashlib.sha256();stamps=[]
    with path.open() as stream:
        for line in stream:
            row=json.loads(line);stamps.append(row['stamp_ns'])
            digest.update(json.dumps([row['stamp_ns'],row['detections']],sort_keys=True,separators=(',',':')).encode())
    return digest.hexdigest(),stamps


def main():
    root=ROOT/'outputs/integral_diagnosis_20261014'
    names=('full_1280','tiles_640','visual_pose_control','fused_pose_v3')
    expected=[f['stamp_ns'] for f in json.loads((root/'public_sequence_1hz/frames.json').read_text())]
    fingerprints={};errors=[];rows=[]
    fields=('target_visible_unique','localized_unique','confirmed_predictions','precision_3d','recall_3d',
            'association_precision','background_intrusions','duplicates','wrong_marker','error_median_m',
            'error_p95_m','precision_2d','recall_2d')
    for name in names:
        digest,stamps=detection_digest(root/'sequence_estimates'/name/'observations.jsonl')
        fingerprints[name]=digest
        if stamps!=expected:errors.append(name+': exposure mismatch')
        metrics=json.loads((root/'sequence_evaluation'/name/'metrics.json').read_text())
        rows.append(dict(variant=name,**{k:metrics[k] for k in fields}))
    for name in ('visual_pose_control','fused_pose_v3'):
        if fingerprints[name]!=fingerprints['full_1280']:errors.append(name+': detections or track identities changed')
    if len({r['target_visible_unique'] for r in rows})!=1:errors.append('Different denominators')
    write(root/'sequence_comparison.json',dict(version='matched-development-comparison/1.0',
        passed=not errors,errors=errors,frames=len(expected),detection_sha256=fingerprints,rows=rows,
        comparisons={'perception':['full_1280','tiles_640'],'pose_cadence':['full_1280','visual_pose_control'],
                     'fusion':['visual_pose_control','fused_pose_v3']},
        limitation='Development 1Hz detections; visual control and fusion share 30Hz RGB pose source. No reserved or real-crop conclusion.'))
    if errors:raise ValueError('; '.join(errors))
    print('MATCHED_COMPARISON_PASSED',len(expected),'frames',flush=True)


if __name__=='__main__':main()
