"""Render each original frame exactly once; truth annotations diagnostic only."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb
from uchuva_lsystem.segmentation_cycles import write,sha


def contours(image,mask,color):
    lines,_=cv2.findContours(mask.astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(image,lines,-1,color,1,cv2.LINE_AA)


def main():
    p=argparse.ArgumentParser()
    for name in ('flight','cache','estimates','evaluation','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    integrity=json.loads((a.flight/'continuous_validation.json').read_text())
    if not integrity['passed']:raise ValueError('Cannot hide invalid or missing frames in a fluent video')
    pairs=json.loads((a.flight/'paired/pairs.json').read_text())['pairs']
    observations={f['stamp_ns']:f for f in map(json.loads,(a.estimates/'observations.jsonl').read_text().splitlines())}
    if set(observations)!={p['stamp_ns'] for p in pairs}:raise ValueError('Main video requires predictions for every original frame')
    diagnosis={f['stamp_ns']:f for f in map(json.loads,(a.evaluation/'frame_diagnostics.jsonl').read_text().splitlines())}
    objects=json.loads((a.estimates/'map.json').read_text())['objects'];by_track={tid:o for o in objects for tid in o['track_ids']}
    map_errors={r['map_id']:r for r in json.loads((a.evaluation/'map_diagnostics.json').read_text())}
    detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100))
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:raise RuntimeError('Existing FFmpeg not found')
    videos={}
    for name in ('principal','diagnostico'):
        videos[name]=subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-n','-f','rawvideo','-pixel_format','bgr24',
            '-video_size','1280x720','-framerate','30','-i','-','-an','-c:v','libx264','-threads','2','-preset','veryfast',
            '-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(a.output/f'{name}.mp4')],stdin=subprocess.PIPE)
    try:
        for number,pair in enumerate(pairs):
            stamp=pair['stamp_ns'];image=cv2.imread(str(a.flight/'paired'/pair['rgb']));main=image.copy();diagnostic=image.copy()
            record=json.loads((a.cache/f'{stamp}.json').read_text());proposals=record['proposals'];lookup={p['observation_id']:i for i,p in enumerate(proposals)}
            with np.load(a.cache/f'{stamp}.npz') as pack:
                h,w=map(int,pack['shape']);masks=np.unpackbits(pack['packed_masks'],axis=1,count=h*w).reshape(-1,h,w).astype(bool)
            rows={r['observation_id']:r for r in diagnosis[stamp]['matches']}
            for detection in observations[stamp]['detections']:
                tid=detection['track_id'];item=by_track.get(tid);mask=masks[lookup[detection['observation_id']]]
                color=(30,210,80) if item and item['state']=='confirmed' else (0,180,240)
                # Principal shows public estimator assignment only: never truth
                # used to erase a background object mistakenly mapped as target.
                contours(main,mask,color if item else (140,140,140));x,y=map(int,detection['center_px'])
                label=tid+' sin ArUco' if item is None else f"{item['map_id']} A{item['marker_id']}"
                if item:
                    if item['state']=='confirmed':label+=' '+','.join(f'{v:.2f}' for v in item['position_marker_m'])+' m'
                    else:label+=' provisional'
                cv2.putText(main,label,(max(0,x),max(16,y)),cv2.FONT_HERSHEY_SIMPLEX,.32,color if item else (140,140,140),1,cv2.LINE_AA)
                match=rows[detection['observation_id']];error=map_errors.get(item['map_id'],{}) if item else {}
                diagnostic_color=(255,50,255) if error.get('background_intrusion') else ((30,210,80) if match['role']=='target' else (150,150,150))
                contours(diagnostic,mask,diagnostic_color)
                x,y=map(int,detection['center_px']);cv2.putText(diagnostic,tid,(max(0,x),max(15,y)),cv2.FONT_HERSHEY_SIMPLEX,.32,diagnostic_color,1)
            native=cv2.imread(str(a.flight/'paired'/pair['mask']));codes=decode_panoptic_rgb(native[:,:,::-1])
            for missed in diagnosis[stamp]['missed_target']:contours(diagnostic,codes==int(missed['code']),(30,30,245))
            corners,ids,_=detector.detectMarkers(image)
            for canvas in (main,diagnostic):
                if ids is not None:cv2.aruco.drawDetectedMarkers(canvas,corners,ids)
                cv2.rectangle(canvas,(0,0),(1280,34),(15,15,15),-1)
                elapsed=(stamp-pairs[0]['stamp_ns'])/1e9
                cv2.putText(canvas,f'Gazebo | captura original 30 Hz | t={elapsed:.3f}s | frame {number+1}/{len(pairs)}',(12,23),cv2.FONT_HERSHEY_SIMPLEX,.52,(240,240,240),1,cv2.LINE_AA)
            cv2.putText(diagnostic,'EVALUADOR: rojo=FN objetivo | magenta=intrusion de fondo | gris=contexto/no asignado',(10,703),cv2.FONT_HERSHEY_SIMPLEX,.43,(255,255,255),1,cv2.LINE_AA)
            videos['principal'].stdin.write(main.tobytes());videos['diagnostico'].stdin.write(diagnostic.tobytes())
            if number in (0,len(pairs)//2,len(pairs)-1):cv2.imwrite(str(a.output/f'representative_{number:06d}.jpg'),main)
            if number%100==0:print('VIDEO_FRAME',number,len(pairs),flush=True)
    finally:
        for process in videos.values():
            process.stdin.close()
            if process.wait()!=0:raise RuntimeError('FFmpeg encoding failed')
    checks={}
    for name in videos:
        path=a.output/f'{name}.mp4'
        subprocess.run([ffmpeg,'-v','error','-xerror','-i',str(path),'-f','null','-'],check=True,capture_output=True)
        cap=cv2.VideoCapture(str(path));count=0;fps=cap.get(cv2.CAP_PROP_FPS)
        while cap.read()[0]:count+=1
        cap.release()
        if count!=len(pairs) or abs(fps-30)>.001:raise ValueError('Video frame count or rate differs')
        checks[name]=dict(decoded_frames=count,fps=fps,sha256=sha(path))
    write(a.output/'verification.json',dict(passed=True,original_frames=len(pairs),videos=checks,
        source_duration_seconds=(pairs[-1]['stamp_ns']-pairs[0]['stamp_ns'])/1e9,
        encoded_duration_seconds=len(pairs)/30,interpolated_or_duplicated_frames=0,
        source='Original synchronized PNGs; capture-time preview MP4 not used'))


if __name__=='__main__':main()
