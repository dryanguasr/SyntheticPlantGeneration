"""Video detection/tracking and explicitly nonmetric marker-relative image coordinates."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess

import cv2
import numpy as np
from ultralytics import YOLO
from prepare_union_pilot import ROOT, sha, write
from inspect_union_references import image_relative_xy


def iou(a,b):
    low=np.maximum(a[:2],b[:2]); high=np.minimum(a[2:],b[2:])
    inter=float(np.maximum(high-low,0).prod())
    return inter/max(float((a[2:]-a[:2]).prod()+(b[2:]-b[:2]).prod()-inter),1e-9)


def marker_is_usable(marker):
    points=np.asarray(marker['corners_px'],np.float32)
    sides=np.linalg.norm(points-np.roll(points,1,axis=0),axis=1)
    area=abs(cv2.contourArea(points))
    return bool(sides.min()>=20 and sides.min()/sides.max()>=.25 and
                area/(sides.sum()**2)>=.02 and cv2.isContourConvex(points))


def propagate_marker(previous_gray, gray, marker):
    points=np.asarray(marker['corners_px'],np.float32).reshape(-1,1,2)
    forward,status,error=cv2.calcOpticalFlowPyrLK(previous_gray,gray,points,None,winSize=(21,21),maxLevel=3)
    if forward is None or not status.all() or float(error.max())>15:
        return None
    backward,status2,_=cv2.calcOpticalFlowPyrLK(gray,previous_gray,forward,None,winSize=(21,21),maxLevel=3)
    if backward is None or not status2.all() or np.linalg.norm(backward-points,axis=2).max()>1.5:
        return None
    pts=forward.reshape(4,2)
    result={**marker,'corners_px':pts.tolist(),'center_px':pts.mean(0).tolist(),
            'mean_side_px':float(np.linalg.norm(pts-np.roll(pts,1,axis=0),axis=1).mean()),'provenance':'optical_flow_propagated'}
    return result if marker_is_usable(result) else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm',choices=['real','mixed'],required=True)
    args=parser.parse_args()
    selection=json.loads((ROOT/'evaluation_lock.json').read_text())
    assert sha(__file__)==selection['video_evaluation_script_sha256']
    weights=ROOT/'training'/args.arm/'weights/best.pt'
    assert sha(weights)==selection['arms'][args.arm]['weights_sha256']
    model=YOLO(weights)
    cv2.setNumThreads(2)
    colors=[(70,220,50),(20,190,255),(210,60,240)]
    names=['Pintona','Madura','Sobremadura']
    summaries=[]
    for name in ['125180','125181','125182']:
        out=ROOT/'videos'/args.arm/name
        if out.exists():
            raise FileExistsError(out)
        out.mkdir(parents=True)
        references=json.loads((ROOT/'references'/f'{name}_aruco.json').read_text())
        reference_by_frame={r['frame_index']:r for r in references}
        source=Path(f'C:/Users/User/Downloads/{name}.mp4')
        cap=cv2.VideoCapture(str(source)); width,height=int(cap.get(3)),int(cap.get(4)); fps=cap.get(5)
        writer=cv2.VideoWriter(str(out/'annotated_intermediate.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),5,(width,height))
        if not writer.isOpened():raise RuntimeError('Video writer unavailable')
        frame_index=0; tracks={}; next_track=1; track_lengths=Counter(); counts=Counter(); previous_gray=None; active_markers={}
        with (out/'observations.jsonl').open('w',encoding='utf-8') as stream:
            while cap.grab():
                if frame_index not in reference_by_frame:
                    frame_index+=1;continue
                ok,frame=cap.retrieve()
                if not ok:raise RuntimeError('Video decode failed')
                timestamp=frame_index/fps
                gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
                raw=reference_by_frame[frame_index]['markers']
                accepted=[{**m,'provenance':'observed','last_observed_seconds':timestamp} for m in raw if marker_is_usable(m)]
                current={m['id']:m for m in accepted}
                if previous_gray is not None:
                    for marker_id,marker in active_markers.items():
                        if marker_id not in current and timestamp-marker['last_observed_seconds']<=1:
                            propagated=propagate_marker(previous_gray,gray,marker)
                            if propagated is not None:current[marker_id]=propagated
                active_markers=current;previous_gray=gray
                prediction=model.predict(frame,imgsz=960,conf=selection['confidence'],iou=.7,max_det=300,device=0,
                                         augment=False,verbose=False)[0]
                boxes=prediction.boxes.xyxy.cpu().numpy(); classes=prediction.boxes.cls.cpu().numpy().astype(int)
                scores=prediction.boxes.conf.cpu().numpy()
                tracks={tid:t for tid,t in tracks.items() if timestamp-t['timestamp']<=1}
                pairs=sorted(((iou(box,track['box']),j,tid) for j,box in enumerate(boxes) for tid,track in tracks.items()),reverse=True)
                used_tracks=set(); assigned={}
                for overlap,j,tid in pairs:
                    if overlap<.2:break
                    if j not in assigned and tid not in used_tracks:
                        assigned[j]=tid;used_tracks.add(tid)
                detections=[]
                for j,(box,cid,score) in enumerate(zip(boxes,classes,scores)):
                    tid=assigned.get(j)
                    if tid is None:tid=next_track;next_track+=1
                    tracks[tid]={'box':box,'timestamp':timestamp};track_lengths[tid]+=1
                    center=(box[:2]+box[2:])/2
                    relative=[]
                    for marker in current.values():
                        xy=image_relative_xy(center,marker['center_px'])
                        relative.append({'marker_id':marker['id'],'marker_provenance':marker['provenance'],
                                         'image_xy_px':xy,'image_xy_divided_by_marker_side_px':[v/marker['mean_side_px'] for v in xy],
                                         'physical_xyz_cm':None,'fruit_to_marker_identity_verified':False,
                                         'coordinate_kind':'image offsets, not physical marker-plane or 3D coordinates'})
                    detections.append({'track_id':tid,'class_id':int(cid),'confidence':float(score),'bbox_xyxy':box.tolist(),
                                       'center_px':center.tolist(),'relative_to_markers':relative})
                    x1,y1,x2,y2=map(int,box);color=colors[cid]
                    cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
                    cv2.putText(frame,f'{names[cid]} {score:.2f} #{tid}',(x1,max(65,y1-4)),cv2.FONT_HERSHEY_SIMPLEX,.4,color,1,cv2.LINE_AA)
                for marker in current.values():
                    pts=np.asarray(marker['corners_px'],np.int32)
                    color=(30,240,30) if marker['provenance']=='observed' else (0,180,255)
                    cv2.polylines(frame,[pts],True,color,2)
                    cv2.putText(frame,f"ArUco {marker['id']} {marker['provenance']}",tuple(pts[0]),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1)
                cv2.rectangle(frame,(0,0),(width,57),(25,25,25),-1)
                cv2.putText(frame,f'{args.arm} | {name} | t={timestamp:.2f}s | detections={len(detections)} | markers={len(current)}',(12,21),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
                cv2.putText(frame,'X right / Y up (pixels). Z and metric pose unavailable; no validated 3D.',(12,45),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,230,120),1)
                record={'frame_index':frame_index,'timestamp_seconds':timestamp,'detections':detections,'markers':list(current.values()),
                        'raw_marker_count':len(raw),'rejected_marker_count':len(raw)-len(accepted),'metric_pose_status':'unavailable',
                        'metric_reprojection_error_px':None,'manual_truth_used_by_estimator':False}
                stream.write(json.dumps(record)+'\n')
                writer.write(frame)
                counts.update(frames=1,detections=len(detections),frames_with_observed_marker=int(bool(accepted)),
                              frames_with_any_reference=int(bool(current)),frames_with_detection=int(bool(detections)))
                if counts['frames'] in (1,100,300):cv2.imwrite(str(out/f'preview_{counts["frames"]:04d}.jpg'),frame)
                frame_index+=1
                if counts['frames']%200==0:print(args.arm,name,dict(counts),flush=True)
        writer.release();cap.release()
        ffmpeg=shutil.which('ffmpeg')
        if not ffmpeg:raise RuntimeError('Existing ffmpeg not found')
        final=out/f'{name}_{args.arm}_annotated.mp4'
        subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-i',str(out/'annotated_intermediate.mp4'),
                        '-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(final)],check=True)
        check=cv2.VideoCapture(str(final)); frames=int(check.get(cv2.CAP_PROP_FRAME_COUNT));check.release()
        assert frames==len(references)==counts['frames']
        summary={'video':name,'arm':args.arm,**dict(counts),'track_count':len(track_lengths),
                 'track_observation_count_median':float(np.median(list(track_lengths.values()))) if track_lengths else None,
                 'tracks_seen_at_least_5_frames':sum(v>=5 for v in track_lengths.values()),
                 'tracking_method':'greedy class-agnostic IoU >=0.2, expiry 1s; no accuracy ground truth',
                 'video_path':str(final.resolve()),'video_sha256':sha(final),'source_sha256':sha(source),
                 'metric_localization_available':False,'external_AP_available':False,'confidence':selection['confidence']}
        write(out/'summary.json',summary);summaries.append(summary)
    write(ROOT/'videos'/args.arm/'summary.json',summaries)


if __name__=='__main__':main()
