"""Presentation-only replay of frozen segmentation, IDs and marker-local maps."""
import argparse
import collections
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import check_deadline,sha,write
from uchuva_gazebo.roi_tiling import predict_roi
from uchuva_gazebo.multiview import match_detections


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root;out=root/'presentation';out.mkdir(exist_ok=False)
    run=json.loads((root/'run.json').read_text());selection=json.loads((root/'winner_selection.json').read_text())
    if sha(run['model'])!=selection['model_sha256']:raise ValueError('Frozen model changed')
    for path,digest in selection['source_hashes'].items():
        if sha(path)!=digest:raise ValueError('Frozen estimator changed')
    public=root/'public/reserved';calibration=json.loads((public/'calibration.json').read_text())
    frames={v['stamp_ns']:v['filename'] for v in json.loads((public/'frames.json').read_text())}
    records=[json.loads(line) for line in (root/'reserved_estimates/winner_raw/observations.jsonl').read_text().splitlines()]
    mapping=json.loads((root/'reserved_estimates/winner_qualified/support_8/map.json').read_text())
    lookup={}
    for item in sorted(mapping['objects'],key=lambda v:v['state']=='confirmed'):
        for identifier in item['observation_ids']:lookup[identifier]=item
    model=YOLO(run['model']);provenance=json.loads((root/'reserved_estimates/winner_raw/provenance.json').read_text())
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100))
    width,height=calibration['resolution'];video=cv2.VideoWriter(str(out/'localizacion_reservada.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),1.,(width,height))
    if not video.isOpened():raise RuntimeError('Video encoder unavailable')
    shown=collections.Counter()
    try:
        for index,record in enumerate(records):
            check_deadline(root)
            rgb=cv2.imread(str(public/'rgb'/frames[record['stamp_ns']]))
            corners,ids,_=detector.detectMarkers(rgb)
            result=predict_roi(model,rgb,mode='all_tiles',tile_size=960)
            data=result.boxes.data.numpy();indices=[i for i,b in enumerate(data) if b[4]>=provenance['confidence']]
            detections=record['detections']
            matches,_=match_detections([data[i,:4].tolist() for i in indices],[d['box_xyxy_px'] for d in detections],threshold=.8)
            overlay=rgb.copy();active={}
            for local,source in enumerate(indices):
                d=detections[matches[local]] if local in matches else None
                item=lookup.get(d['observation_id']) if d else None
                confirmed=bool(item and item['state']=='confirmed')
                color=(70,220,60) if confirmed else (0,180,255)
                mask=result.masks.data[source].numpy()>.5
                overlay[mask]=np.asarray(color,np.uint8)
                x,y,xx,yy=map(int,data[source,:4]);cv2.rectangle(rgb,(x,y),(xx,yy),color,1)
                label=item['map_id'] if item else (d['track_id'] if d else 'sin enlace')
                cv2.putText(rgb,label,(x,max(36,y-3)),cv2.FONT_HERSHEY_SIMPLEX,.3,color,1,cv2.LINE_AA)
                if item:active[item['map_id']]=item
                shown['confirmed_observations' if confirmed else 'unconfirmed_observations']+=1
            rgb=cv2.addWeighted(rgb,.75,overlay,.25,0)
            if ids is not None:cv2.aruco.drawDetectedMarkers(rgb,corners,ids)
            cv2.rectangle(rgb,(0,0),(width,29),(20,20,20),-1)
            cv2.putText(rgb,f'POSTPROCESO | muestras 1 Hz | t={record["stamp_ns"]/1e9:.1f}s | verde=confirmado por estimador, naranja=provisional',(8,20),cv2.FONT_HERSHEY_SIMPLEX,.44,(255,255,255),1,cv2.LINE_AA)
            for row,item in enumerate(sorted(active.values(),key=lambda v:v['state']!='confirmed')[:5]):
                xyz=', '.join(f'{v:.3f}' for v in item['position_marker_m'])
                label=f'{item["map_id"]} ArUco {item["marker_id"]}: [{xyz}] m'
                cv2.putText(rgb,label,(10,height-12-row*17),cv2.FONT_HERSHEY_SIMPLEX,.42,(255,255,255),1,cv2.LINE_AA)
            video.write(rgb)
            if index in (30,100,180):cv2.imwrite(str(out/f'ejemplo_{index:03d}.png'),rgb)
            if index%25==0:print('PRESENTATION_FRAME',index,len(records),flush=True)
    finally:video.release()
    write(out/'video_provenance.json',dict(version='localization-presentation/1.0',frames=len(records),fps=1.,
        note='Exact segmentation sample frames only; 1 Hz presentation, not online throughput. Masks replayed from frozen RGB model; identities joined to saved observations. Green denotes algorithm confirmation, not evaluator correctness.',counts=dict(shown)))


if __name__=='__main__':main()
