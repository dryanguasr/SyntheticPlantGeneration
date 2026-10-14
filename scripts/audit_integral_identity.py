"""Independently recount ID changes from historical evaluator correspondences."""
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write


def main():
    base=ROOT/'outputs/continuous_row_20261008'
    out=ROOT/'outputs/integral_diagnosis_20261014'
    previous={};changes=Counter();examples=[];frames=0;duplicates=0;support=Counter()
    for line in (base/'evaluation/offline_every_frame/frame_diagnostics.jsonl').open():
        r=json.loads(line);current={};frames+=1
        for m in r['matches']:
            if m['role']!='target' or m['matched_code'] is None:continue
            code=str(m['matched_code']);tid=m['track_id'];support[code]+=1
            if code in current:duplicates+=1
            current[code]=tid
            if code in previous and previous[code][1]!=tid:
                last_frame,last_tid,last_stamp=previous[code]
                kind='adjacent_captured_frame' if last_frame==frames-1 else 'after_detection_gap'
                changes[kind]+=1
                if len(examples)<30:examples.append(dict(code=code,from_track=last_tid,to_track=tid,
                    from_stamp=last_stamp,to_stamp=r['stamp_ns'],kind=kind))
            previous[code]=(frames,tid,r['stamp_ns'])
    expected=json.loads((base/'evaluation/offline_every_frame/metrics.json').read_text())['identity_switches']
    write(out/'identity_audit.json',dict(version='identity-audit/1.0',frames=frames,
        reported_switches=expected,recounted_switches=sum(changes.values()),counts=dict(changes),
        agrees=sum(changes.values())==expected,duplicate_truth_matches_same_frame=duplicates,
        examples=examples,manual_clip_review='pending',
        limitation='Recount validates accounting only, not correctness of mask correspondences'))
    print(dict(changes),flush=True)


if __name__=='__main__':main()
