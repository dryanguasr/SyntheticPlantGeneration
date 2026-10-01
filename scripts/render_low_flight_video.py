"""Presentation-only RGB overlay of frozen planar and posterior multiview estimates."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--estimates',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    records=[json.loads(l) for l in (args.estimates/'observations.jsonl').read_text().splitlines()]
    reconstructions={}
    for line in (args.estimates/'reconstructions.jsonl').read_text().splitlines():
        r=json.loads(line)
        if r['status']!='estimated':continue
        old=reconstructions.get(r['track_id'])
        if old is None or r['observations']>old['observations']:reconstructions[r['track_id']]=r
    config=json.loads((args.run/'estimator_config.json').read_text());K=np.array(config['camera']['K'],float)
    video=cv2.VideoWriter(str(args.output),cv2.VideoWriter_fourcc(*'mp4v'),5,(1280,720))
    if not video.isOpened():raise RuntimeError('Cannot open annotation video')
    for index,record in enumerate(records):
        image=cv2.imread(str(args.run/'rgb'/f'{record["stamp_ns"]}.png'))
        marker_centers={m['id']:np.mean(m['corners_px'],axis=0) for m in record['markers']}
        for m in record['markers']:
            points=np.array(m['corners_px'],np.int32)
            cv2.polylines(image,[points],True,(255,180,20),2)
            cv2.putText(image,f'ArUco {m["id"]}',tuple(points[0]),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,180,20),1)
            pose=record['marker_poses'].get(str(m['id']))
            if pose and pose['status']=='estimated':
                cv2.drawFrameAxes(image,K,None,cv2.Rodrigues(np.array(pose['R']))[0],np.array(pose['t']),.05,2)
        for d in record['detections']:
            x1,y1,x2,y2=map(round,d['box_xyxy_px']);cv2.rectangle(image,(x1,y1),(x2,y2),(80,240,160),2)
            lines=[f'{d["track_id"]} | capacho {d["confidence"]:.2f}']
            available=[r for r in d['positions_by_marker'] if r['position_cm'] is not None]
            if available:
                nearest=min(available,key=lambda r:np.linalg.norm(marker_centers[r['marker_id']]-d['center_px']))
                pos=nearest['position_cm']
                lines.append(f'ArUco {nearest["marker_id"]}: X {pos["x"]:+.1f} Y {pos["y"]:+.1f} cm (plano)')
            else:lines.append('Posicion planar no disponible')
            r=reconstructions.get(d['track_id'])
            if r:
                x,y,z=np.array(r['position_marker_m'])*100
                lines.append(f'3D posterior, ArUco {r["marker_id"]}: {x:+.1f}, {y:+.1f}, {z:+.1f} cm')
            else:lines.append('3D no disponible')
            left=max(0,min(x1,850));top=max(68,min(y2+4,652))
            width=min(1280-left,8+max(cv2.getTextSize(l,cv2.FONT_HERSHEY_SIMPLEX,.42,1)[0][0] for l in lines))
            cv2.rectangle(image,(left,top),(left+width,top+len(lines)*18+4),(28,28,28),-1)
            for n,line in enumerate(lines):
                cv2.putText(image,line,(left+4,top+16+n*18),cv2.FONT_HERSHEY_SIMPLEX,.42,(240,240,240),1)
        cv2.rectangle(image,(0,0),(1280,60),(22,30,25),-1)
        cv2.putText(image,f'Vuelo bajo | t={record["stamp_ns"]/1e9:.2f}s | {len(record["detections"])} detecciones | {len(record["markers"])} ArUcos',
                    (12,25),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),1)
        cv2.putText(image,'Planar: profundidad desconocida. 3D: reconstruccion multivista posterior. Sin verdad sintetica en el estimador.',
                    (12,49),cv2.FONT_HERSHEY_SIMPLEX,.48,(220,230,220),1)
        video.write(image)
        if index in (len(records)//4,len(records)//2,3*len(records)//4):
            cv2.imwrite(str(args.output.with_name(f'anotado_{index:05d}.png')),image)
    video.release()
    print(args.output)


if __name__=='__main__':main()
