"""Propose recoverable video reserves from direct geometric/appearance matches.

Engineering heuristics, not proof of object-scale coverage. No detector is used.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from uchuva_dataset_curation import read_rows, write_json

CONFIG = dict(long_side=480, max_scale_change=.15, min_overlap=.65,
              max_rotation_degrees=8, min_inliers=20, min_inlier_fraction=.30,
              max_aligned_mae=28, min_grid_cells=4, recent_references=3)


def features(parent, row, sizes, orb):
    p = parent / 'images_640x640' / row['split'] / (Path(row['candidate_path']).stem + '.png')
    im = cv2.imread(str(p))
    if im is None:
        raise ValueError(f'Cannot read {p}')
    meta = sizes[p.stem]
    x, y = int(meta['pad_left']), int(meta['pad_top'])
    im = im[y:y+int(meta['resized_height']), x:x+int(meta['resized_width'])]
    h, w = im.shape[:2]
    im = cv2.resize(im, (round(w*480/max(h,w)), round(h*480/max(h,w))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    kp, desc = orb.detectAndCompute(gray, None)
    return dict(gray=gray, points=np.float32([k.pt for k in kp]), desc=desc)


def similar(a, b):
    if a['gray'].shape != b['gray'].shape:
        return None
    if a['desc'] is None or b['desc'] is None:
        return None
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(a['desc'], b['desc'], k=2)
    good = [m for pair in matches if len(pair)==2 for m,n in [pair] if m.distance < .72*n.distance]
    if len(good) < CONFIG['min_inliers']:
        return None
    p = np.float32([a['points'][m.queryIdx] for m in good])
    q = np.float32([b['points'][m.trainIdx] for m in good])
    cv2.setRNGSeed(20260922)
    transform, mask = cv2.estimateAffinePartial2D(p,q,method=cv2.RANSAC,ransacReprojThreshold=2.5)
    if transform is None:
        return None
    inliers = mask.ravel().astype(bool)
    if inliers.sum()<CONFIG['min_inliers'] or inliers.mean()<CONFIG['min_inlier_fraction']:
        return None
    scale = float(np.hypot(transform[0,0],transform[1,0]))
    angle = float(np.degrees(np.arctan2(transform[1,0],transform[0,0])))
    if abs(scale-1) > CONFIG['max_scale_change'] or abs(angle)>CONFIG['max_rotation_degrees']:
        return None
    h,w = a['gray'].shape
    cells = {(min(3,int(x/w*4)),min(3,int(y/h*4))) for x,y in p[inliers]}
    if len(cells)<CONFIG['min_grid_cells']:
        return None
    valid = cv2.warpAffine(np.ones((h,w),np.uint8),transform,(w,h)).astype(bool)
    overlap = min(float(valid.mean()), float(valid.mean()/scale**2))
    if overlap<CONFIG['min_overlap']:
        return None
    warped = cv2.warpAffine(cv2.GaussianBlur(a['gray'],(5,5),0),transform,(w,h))
    delta = np.abs(warped.astype(float)-cv2.GaussianBlur(b['gray'],(5,5),0).astype(float))
    mae = float(delta[valid].mean())
    if mae>CONFIG['max_aligned_mae']:
        return None
    return dict(scale=scale,rotation_degrees=angle,overlap=overlap,aligned_mae=mae,
                inliers=int(inliers.sum()),grid_cells=len(cells))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    cv2.setNumThreads(2)
    rows = read_rows(args.parent/'manifest.jsonl')
    sizes = {Path(r['output_path']).stem:r for r in read_rows(args.parent/'images_640x640/manifest.csv')}
    groups = defaultdict(list)
    for r in rows:
        if r['kind']=='video' and r['selection']=='include':
            groups[r['source_id']].append(r)
    orb = cv2.ORB_create(nfeatures=1800,fastThreshold=10)
    decisions=[]
    for sid, sequence in groups.items():
        kept=[]
        for r in sorted(sequence,key=lambda r:(r['timestamp_seconds'],r['image_id'])):
            f = features(args.parent,r,sizes,orb)
            match=None
            for other,other_f in reversed(kept[-CONFIG['recent_references']:]):
                metrics=similar(f,other_f)
                if metrics is not None:
                    match=dict(image_id=r['image_id'],representative=other['image_id'],source=r['source'],
                               timestamp_seconds=r['timestamp_seconds'],representative_time=other['timestamp_seconds'],**metrics)
                    break
            if match is None:
                kept.append((r,f))
            else:
                decisions.append(match)
        print(f"{sequence[0]['source']}: {len(sequence)} -> {len(kept)}",flush=True)
    write_json(args.output,dict(config=CONFIG,parent=args.parent.name,video_before=sum(map(len,groups.values())),
                              reserved=len(decisions),decisions=decisions))


if __name__=='__main__':
    main()
