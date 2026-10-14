"""Frozen RGB detector; masks enter only the post-inference evaluator."""
import argparse
import csv
import json
import math
from collections import defaultdict,Counter
from pathlib import Path
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'desktop'),str(ROOT/'scripts')]
from uchuva_aruco.vision import VisionEngine,Settings
from uchuva_gazebo.evaluation import visible_boxes
from uchuva_gazebo.multiview import match_detections
from validate_low_capture import decode_mask


def main():
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);a=p.parse_args()
    engine=VisionEngine(ROOT/'mobile/android/app/src/main/assets')
    assert engine.model_hash=='19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca'
    settings=Settings(side_cm=10,confidence=.25,dictionary='DICT_4X4_100');rows=[];observations=[];size_groups=defaultdict(Counter)
    flat_frames=json.loads((a.package/'ab_flat_pbr/frames.json').read_text())
    texture_frames=json.loads((a.package/'ab_textured/frames.json').read_text())
    if len(flat_frames)!=24 or len(texture_frames)!=24:raise ValueError('Expected 24 paired original views')
    mask_agreement=[]
    for f,t in zip(flat_frames,texture_frames):
        if {k:v for k,v in f.items() if k!='stamp_ns'}!={k:v for k,v in t.items() if k!='stamp_ns'}:
            raise ValueError('Paired camera configuration differs')
        stem=f'{f["index"]:03d}'
        fm=decode_mask(a.package/'ab_flat_pbr'/(stem+'_mask.png'))>0
        tm=decode_mask(a.package/'ab_textured'/(stem+'_mask.png'))>0
        agreement=float(np.logical_and(fm,tm).sum()/max(1,np.logical_or(fm,tm).sum()))
        if agreement<.999:raise ValueError(f'Paired view geometry mismatch {stem}: {agreement}')
        mask_agreement.append(agreement)
    for variant in ('flat_legacy','flat_pbr','textured'):
        folder=a.package/('ab_flat' if variant=='flat_legacy' else 'ab_'+variant)
        for frame in json.loads((folder/'frames.json').read_text()):
            stem=f'{frame["index"]:03d}';image=cv2.imread(str(folder/(stem+'_rgb.png')))
            annotated,result=engine.analyze(image,settings,frame_id=frame['index'])
            references=[r for r in visible_boxes(decode_mask(folder/(stem+'_mask.png'))) if r['pixels']>=16]
            boxes=[d['box_xyxy_px'] for d in result['detections']]
            matches,duplicates=match_detections(boxes,[r['box'] for r in references])
            if variant!='flat_legacy':
                found=set(matches.values())
                for j,reference in enumerate(references):
                    x0,y0,x1,y1=reference['box'];side=math.sqrt((x1-x0)*(y1-y0))
                    group='<16' if side<16 else '16-31' if side<32 else '32-63' if side<64 else '>=64'
                    size_groups[(variant,group)]['visible']+=1;size_groups[(variant,group)]['tp']+=j in found
            row={'variant':variant,'index':frame['index'],'row':frame['row'],'side':frame['side'],'visible':len(references),
                 'detections':len(boxes),'tp':len(matches),'fp':len(boxes)-len(matches),'fn':len(references)-len(matches),'duplicates':len(duplicates),'markers':len(result['markers'])}
            rows.append(row);observations.append({'variant':variant,**result})
            cv2.imwrite(str(folder/(stem+'_annotated.jpg')),annotated)
    summary={}
    for variant in ('flat_legacy','flat_pbr','textured'):
        totals={key:sum(r[key] for r in rows if r['variant']==variant) for key in ('visible','detections','tp','fp','fn','markers')}
        totals.update(precision=totals['tp']/totals['detections'] if totals['detections'] else None,recall=totals['tp']/totals['visible'] if totals['visible'] else None)
        summary[variant]=totals
    (a.package/'texture_ab.json').write_text(json.dumps({'model_sha256':engine.model_hash,'confidence':.25,'summary':summary,'frames':rows,'paired_mask_iou':mask_agreement,
        'scope':'24 paired exploratory views for flat_pbr/textured; flat_legacy is diagnostic with different rendered visibility. Visible masks >=16px, one-to-one IoU >=0.5; not real-world validation'},indent=2))
    (a.package/'texture_ab_observations.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in observations))
    size_rows=[{'variant':v,'sqrt_bbox_area_px':b,**dict(g),'recall':g['tp']/g['visible']} for (v,b),g in size_groups.items()]
    (a.package/'texture_size_analysis.json').write_text(json.dumps({'scope':'Post-hoc descriptive size stratification; same fixed detections, all visible field plants including background','rows':size_rows},indent=2))
    with (a.package/'texture_ab.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary))

if __name__=='__main__':main()
