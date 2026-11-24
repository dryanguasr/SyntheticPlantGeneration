"""Development ablation: preserve RGB poses, use v3 only for missing markers.

No evaluator inputs. This isolates propagation from replacement of observed
visual poses; it is not a selected deployment configuration.
"""
import hashlib
import json
from itertools import zip_longest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def combine(visual, fused):
    if visual['stamp_ns'] != fused['stamp_ns']:
        raise ValueError('Pose timestamps differ')
    poses = dict(fused['marker_poses'])
    poses.update(visual['marker_poses'])
    return dict(stamp_ns=visual['stamp_ns'], marker_poses=poses)


def main():
    root = ROOT / 'outputs/integral_diagnosis_20261014'
    visual = root / 'public_visual_pose_control.jsonl'
    fused = root / 'pose_fusion_v3/nominal.jsonl'
    output = root / 'public_gap_pose_ablation_v1.jsonl'
    count = additions = 0
    with visual.open() as a, fused.open() as b, output.open('x') as out:
        for va, fb in zip_longest(a, b):
            if va is None or fb is None:
                raise ValueError('Pose stream lengths differ')
            v, f = json.loads(va), json.loads(fb)
            row = combine(v, f)
            assert all(row['marker_poses'][k] == p for k, p in v['marker_poses'].items())
            additions += len(set(f['marker_poses']) - set(v['marker_poses']))
            count += 1
            out.write(json.dumps(row) + '\n')
    manifest = dict(version='gap-pose-ablation/1.0', frames=count,
                    propagated_additions=additions, visual_poses_preserved_exactly=True,
                    status='development_ablation_not_selected',
                    inputs={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (visual, fused)})
    output.with_suffix('.manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest), flush=True)


if __name__ == '__main__':
    main()
