"""Analyze original 1 Hz RGB captures; no MP4 duplicates used as observations."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import cv2
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'desktop')]
from uchuva_aruco.vision import VisionEngine,Settings


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);a=p.parse_args()
    frames=json.loads((a.run/'frames.json').read_text());engine=VisionEngine(ROOT/'mobile/android/app/src/main/assets')
    assert engine.model_hash=='19b6de32788952d77ee842cd4a1d5895212cf6f7b90d7c441f31357c392be4ca'
    settings=Settings(side_cm=10,confidence=.25,dictionary='DICT_4X4_100');counts=Counter();best=[]
    video=cv2.VideoWriter(str(a.run/'annotated_samples.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),1,(1280,720))
    if not video.isOpened():raise RuntimeError('Cannot open annotation video')
    with (a.run/'detections.jsonl').open('w') as stream:
        for i,frame in enumerate(frames):
            image=cv2.imread(str(a.run/'rgb'/frame['filename']))
            _,result=engine.analyze(image,settings,frame_id=i,media_time_ms=frame['stamp_ns']/1e6)
            annotated=image.copy()
            for detection in result['detections']:
                x0,y0,x1,y1=map(round,detection['box_xyxy_px'])
                cv2.rectangle(annotated,(x0,y0),(x1,y1),(90,245,140),2)
                cv2.putText(annotated,f"capacho {detection['confidence']:.2f}",(x0,max(45,y0-5)),cv2.FONT_HERSHEY_SIMPLEX,.55,(90,245,140),2)
            result['stamp_ns']=frame['stamp_ns'];stream.write(json.dumps(result)+'\n')
            n=len(result['detections']);counts['frames']+=1;counts['detections']+=n
            counts['frames_with_detections']+=bool(n);counts['frames_with_markers']+=bool(result['markers'])
            cv2.putText(annotated,f'RGB original 1 Hz | capachos: {n} | t={frame["stamp_ns"]/1e9:.1f}s',(12,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2)
            video.write(annotated)
            if n and (not best or n>best[-1][0]):
                cv2.imwrite(str(a.run/'best_detection.jpg'),annotated);best.append((n,i))
            if i%100==0:print(f'Frozen inference {i}/{len(frames)}',flush=True)
    video.release();(a.run/'detection_summary.json').write_text(json.dumps({'model_sha256':engine.model_hash,'confidence':.25,
        'counts':dict(counts),'scope':'Unmatched full-flight detections, not precision/recall or unique fruit counts; A/B masks evaluated separately'},indent=2))
    print(json.dumps(dict(counts)))

if __name__=='__main__':main()
