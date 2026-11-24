"""Post-hoc diagnosis: saved detections, scale profiles and bounded ArUco probes.

No retraining, no threshold selection, no replacement of frozen pilot outputs.
Video probes are development diagnostics, not external validation.
"""
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from prepare_union_pilot import ROOT, write
from evaluate_union_detector import fixed_match
from evaluate_union_videos import iou, marker_is_usable

OUT = ROOT / 'diagnosis_v1'


def sizes(image, label):
    with Image.open(image) as im:
        w, h = im.size
    scale = 960 / max(w, h)
    return [(int(p[0]), min(float(p[3])*w, float(p[4])*h)*scale)
            for line in label.read_text().splitlines() if (p := line.split())]


def main():
    OUT.mkdir(exist_ok=False)
    cv2.setNumThreads(2)
    manifest = json.loads((ROOT/'manifest.json').read_text())['records']
    profiles = {}
    for name, folder in [('real_train','dataset'),('mixed_train','mixed_dataset'),('real_test','dataset')]:
        split = 'test' if name == 'real_test' else 'train'
        domains = defaultdict(list); counts = Counter(); empty = 0
        for label in (ROOT/folder/'labels'/split).glob('*.txt'):
            image = next((ROOT/folder/'images'/split).glob(label.stem+'.*'))
            domain = 'synthetic' if label.stem.startswith('synthetic_') else 'real'
            objects = sizes(image,label); empty += not bool(objects)
            domains[domain].extend(s for _,s in objects); counts[domain] += 1
        profiles[name] = {'empty_images':empty, 'domains':{
            d:{'images':counts[d],'instances':len(v),'min_side_at_960_quantiles':np.quantile(v,[.1,.5,.9]).tolist(),
               'fraction_below_16px':float(np.mean(np.array(v)<16)), 'fraction_below_32px':float(np.mean(np.array(v)<32))}
            for d,v in domains.items()}}
    diagnostics = {}
    by_row = {r['source_row']:r for r in manifest if r['status']=='included'}
    for arm in ['real','mixed']:
        bins = defaultdict(Counter)
        for record in json.loads((ROOT/'evaluation'/arm/'test_predictions.json').read_text()):
            row = by_row[record['source_row']]
            with Image.open(ROOT/row['image']) as im:w,h=im.size
            truths=[]
            for line in (ROOT/row['label']).read_text().splitlines():
                c,x,y,bw,bh=map(float,line.split())
                truths.append({'class_id':int(c),'bbox':[(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h],
                               'size':min(bw*w,bh*h)*960/max(w,h)})
            available=set(range(len(truths))); matches={}
            for pred in sorted(record['predictions'],key=lambda p:p['confidence'],reverse=True):
                score,j=max(((iou(np.array(pred['bbox']),np.array(truths[j]['bbox'])),j) for j in available),default=(0,None))
                if score>=.5:matches[j]=pred;available.remove(j)
            for j,gt in enumerate(truths):
                key='<16' if gt['size']<16 else '16–32' if gt['size']<32 else '32–64' if gt['size']<64 else '>=64'
                bins[key]['ground_truth']+=1
                bins[key]['spatial_match']+=j in matches
                bins[key]['correct_class']+=j in matches and matches[j]['class_id']==gt['class_id']
        with (ROOT/'training'/arm/'results.csv').open() as stream: epochs=list(csv.DictReader(stream))
        epochs=[{k.strip():float(v) for k,v in r.items()} for r in epochs]
        best=max(epochs,key=lambda r:r['metrics/mAP50-95(B)'])
        diagnostics[arm]={'size_bins':dict(bins),'best_validation_epoch':best,'first_epoch':epochs[0],'last_epoch':epochs[-1]}
    write(OUT/'detector_diagnosis.json',{'profiles':profiles,'arms':diagnostics,
          'test_analysis_is_posthoc':True,'matching':'confidence-ordered class-agnostic one-to-one IoU>=0.5; frozen confidence',
          'bins_unit':'minimum GT box side after resizing longest image side to 960'})
    probes=[]
    for video in ['125180','125181','125182']:
        refs=json.loads((ROOT/'references'/f'{video}_aruco.json').read_text())[::15]
        cap=cv2.VideoCapture(str(ROOT/'inputs'/f'{video}.mp4'))
        configs={}
        for name, dictionary, max_window, half in [('baseline',cv2.aruco.DICT_4X4_50,23,False),
                ('wide_window',cv2.aruco.DICT_4X4_50,153,False),('half_size',cv2.aruco.DICT_4X4_50,23,True),
                ('dictionary_5x5',cv2.aruco.DICT_5X5_1000,23,False),('dictionary_6x6',cv2.aruco.DICT_6X6_1000,23,False)]:
            p=cv2.aruco.DetectorParameters();p.cornerRefinementMethod=cv2.aruco.CORNER_REFINE_SUBPIX
            p.adaptiveThreshWinSizeMax=max_window
            configs[name]=(cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(dictionary),p),half)
        for r in refs:
            cap.set(cv2.CAP_PROP_POS_FRAMES,r['frame_index']);ok,frame=cap.read()
            if not ok:raise RuntimeError('Cannot decode diagnostic frame')
            result={'video':video,'frame_index':r['frame_index'],'timestamp_seconds':r['timestamp_seconds'],'variants':{}}
            for name,(detector,half) in configs.items():
                sample=cv2.resize(frame,None,fx=.5,fy=.5) if half else frame
                corners,ids,rejected=detector.detectMarkers(sample)
                accepted=[]
                if ids is not None:
                    for c,mid in zip(corners,ids.ravel()):
                        pts=c.reshape(4,2)*(2 if half else 1)
                        if marker_is_usable({'corners_px':pts.tolist()}):accepted.append({'id':int(mid),'corners_px':pts.tolist()})
                result['variants'][name]={'accepted':accepted,'raw_ids':[] if ids is None else ids.ravel().tolist(),'rejected_quads':len(rejected)}
            probes.append(result)
            if not result['variants']['baseline']['accepted'] and result['variants']['wide_window']['accepted']:
                preview=frame.copy()
                markers=result['variants']['wide_window']['accepted']
                cv2.aruco.drawDetectedMarkers(preview,[np.array(m['corners_px'],np.float32).reshape(1,4,2) for m in markers],np.array([[m['id']] for m in markers]))
                cv2.imwrite(str(OUT/f'{video}_{r["frame_index"]}_wide_recovered.jpg'),preview)
        cap.release()
        print('marker probe complete',video,flush=True)
    write(OUT/'marker_probes.json',probes)
    summary={v:{name:{'frames':sum(r['video']==v for r in probes),
             'frames_with_usable_marker':sum(bool(r['variants'][name]['accepted']) for r in probes if r['video']==v),
             'ids':dict(Counter(m['id'] for r in probes if r['video']==v for m in r['variants'][name]['accepted']))}
        for name in configs} for v in ['125180','125181','125182']}
    write(OUT/'marker_probe_summary.json',summary)
    print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
