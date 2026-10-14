"""Add a telemetry-synchronized exterior reconstruction to the diagnostic video."""
import json, subprocess, hashlib
from pathlib import Path
import cv2
import numpy as np
r=Path('outputs/continuous_row_20261008');out=r/'presentation/exterior_inset'
meta=json.loads((out/'camera.json').read_text());proj=np.array(meta['projection']);bg=cv2.imread(str(out/'field.png'))
samples=json.loads((r/'flight/full/telemetry.json').read_text())['samples'];times=np.array([s['t'] for s in samples]);positions=np.array([s['position'] for s in samples])
quats=np.array([s['quaternion_xyzw'] for s in samples]);yaw=np.unwrap(np.arctan2(2*(quats[:,3]*quats[:,2]+quats[:,0]*quats[:,1]),1-2*(quats[:,1]**2+quats[:,2]**2)))
pairs=json.loads((r/'flight/full/paired/pairs.json').read_text())['pairs'];stamps=np.array([p['stamp_ns']/1e9 for p in pairs])
def project(points):
 p=np.c_[np.atleast_2d(points),np.ones(len(np.atleast_2d(points)))]@proj.T;p=p[:,:3]/p[:,3:4]
 return np.rint(np.c_[(p[:,0]+1)*240,(1-p[:,1])*160]).astype(int)
cap=cv2.VideoCapture(str(r/'presentation/diagnostico.mp4'));target=out/'diagnostico_con_vista_exterior.mp4'
proc=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-n','-f','rawvideo','-pixel_format','bgr24','-video_size','1280x720','-framerate','30','-i','-','-an','-c:v','libx264','-threads','2','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],stdin=subprocess.PIPE)
trace=[]
for i,t in enumerate(stamps):
 ok,frame=cap.read()
 if not ok:raise RuntimeError(f'Missing diagnostic frame {i}')
 pos=np.array([np.interp(t,times,positions[:,j]) for j in range(3)]);angle=np.interp(t,times,yaw)
 inset=bg.copy();trace.append(project(pos)[0])
 cv2.polylines(inset,[np.array(trace)],False,(240,210,40),1,cv2.LINE_AA)
 # Clearly visible drone glyph, exaggerated in size; pose is recorded, not planned.
 c=project(pos)[0];ground=project([pos[0],pos[1],0])[0];cv2.line(inset,tuple(c),tuple(ground),(180,180,180),1)
 rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
 arms=np.array([[-.22,-.22],[.22,.22],[-.22,.22],[.22,-.22]])@rot.T
 pts=project(np.c_[arms+pos[:2],np.full(4,pos[2])])
 for a,b in [(0,1),(2,3)]:cv2.line(inset,tuple(pts[a]),tuple(pts[b]),(10,20,245),3,cv2.LINE_AA)
 for point in pts:cv2.circle(inset,tuple(point),3,(245,245,245),1,cv2.LINE_AA)
 nose=project(pos+[.75*np.cos(angle),.75*np.sin(angle),0])[0];cv2.arrowedLine(inset,tuple(c),tuple(nose),(0,240,255),2,cv2.LINE_AA,tipLength=.3)
 cv2.rectangle(inset,(0,0),(480,24),(20,25,25),-1);cv2.putText(inset,'VISTA EXTERIOR | reconstruccion sincronizada',(8,16),cv2.FONT_HERSHEY_SIMPLEX,.40,(255,255,255),1,cv2.LINE_AA)
 cv2.rectangle(inset,(0,296),(480,320),(20,25,25),-1);cv2.putText(inset,f't={t:.2f}s | traza azul | flecha: orientacion',(8,312),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1,cv2.LINE_AA)
 # Upper right, below original timestamp header; keep diagnostic footer visible.
 x,y=790,42;frame[y:y+320,x:x+480]=inset;cv2.rectangle(frame,(x,y),(x+480,y+320),(230,230,230),2)
 proc.stdin.write(frame.tobytes())
 if i in [0,3000,4200,5500,len(stamps)-1]:cv2.imwrite(str(out/f'preview_{i:05d}.jpg'),frame)
 if i%500==0:print('COMPOSE',i,len(stamps),flush=True)
assert not cap.read()[0];cap.release();proc.stdin.close();assert proc.wait()==0
subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(target),'-f','null','-'],check=True,capture_output=True)
c=cv2.VideoCapture(str(target));n=0;fps=c.get(cv2.CAP_PROP_FPS)
while c.read()[0]:n+=1
c.release();assert n==len(pairs) and fps==30
(out/'verification.json').write_text(json.dumps({'passed':True,'decoded_frames':n,'fps':fps,'source':'Existing diagnostic video; original per-frame timestamps; recorded Gazebo telemetry; same field SDF geometry','exterior':'Fixed exterior reconstruction, not a simultaneously recorded camera. Drone glyph enlarged for legibility; telemetry interpolated only for inset.','telemetry_range_s':[float(times[0]),float(times[-1])],'initial_clamped_frames':int(sum(stamps<times[0])),'source_frames_duplicated':0,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()},indent=2))
print('VERIFIED',target,flush=True)
