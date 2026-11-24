"""Verify V187 native annotations and export allowlisted public sensor inputs."""
import hashlib,json,shutil,sys
from pathlib import Path
import cv2,numpy as np
from PIL import Image
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.motion_observations import RelativeMotion
r=ROOT/'outputs/integral_diagnosis_20261014';out=r/'field_tracking_v187';private=out/'evaluator_private';public=out/'public'
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2),encoding='utf-8')
protocol=read(out/'route_protocol.json');mapping=read(private/'class_mapping_private.json')
folders=sorted(private.glob('view_*/capture.json'));assert len(folders)==8
for plant in protocol['source_scene']['plants']:
 assert hashlib.sha256(Path(plant['path']).read_bytes()).hexdigest()==plant['sha256']
(public/'rgb').mkdir(parents=True,exist_ok=True)
frames=[];poses=[];decodes=[];checks=0;identities=None
for cp in folders:
 folder=cp.parent;c=read(cp);a=read(folder/'annotations_private.json');cam=read(folder/'camera_private.json')
 assert hashlib.sha256((folder/'rgb.png').read_bytes()).hexdigest()==c['rgb_sha256']
 assert hashlib.sha256((folder/'mask_calyx_crisp_v2.png').read_bytes()).hexdigest()==c['mask_sha256']
 rgbmask=np.array(Image.open(folder/'mask_calyx_crisp_v2.png').convert('RGB'));covered=np.zeros(rgbmask.shape[:2],bool)
 ids={}
 for key,item in a['items'].items():
  pixels=np.all(rgbmask==a['palette'][key],axis=2);assert int(pixels.sum())==item['visible_pixels'];covered|=pixels;checks+=1
  if key!='0':
   ids[key]=item['instance_id']
   if item['semantic_class']=='calyx':assert item['instance_id'] in mapping;assert mapping[item['instance_id']]['class_id'] in (0,1,2)
   else:assert item['visible_pixels']==0, 'Non-calyx pixels in calyx mask'
 assert covered.all()
 if identities is None:identities=ids
 else:assert identities==ids
 filename=str(c['stamp_ns'])+'.png';shutil.copy2(folder/'rgb.png',public/'rgb'/filename);frames.append(dict(stamp_ns=c['stamp_ns'],filename=filename))
 detector=cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50));corners,found,_=detector.detectMarkers(cv2.imread(str(public/'rgb'/filename)))
 decodes.append(dict(stamp_ns=c['stamp_ns'],decoded_ids=[] if found is None else found.flatten().tolist(),corners=[v.tolist() for v in corners]))
 M=np.array(cam['matrix_world']);poses.append((M[:3,:3]@np.diag([1,-1,-1]),M[:3,3]*.125))
write(public/'frames.json',frames);write(public/'calibration.json',dict(K=cam['intrinsic_matrix'],width=cam['width'],height=cam['height']))
write(public/'board.json',dict(dictionary='DICT_4X4_50',marker_id=8,black_square_side_m=.2,white_margin_m=.2/6,physical_calibration=False,parameter_status='engineering_heuristic'))
# Sensor simulator is evaluator-side; only relative, perturbed increments leave it.
rng=np.random.default_rng(1872026);sigma=np.array([.005]*3+[.002]*3)*np.sqrt(.5);rows=[]
for i,((R,t),(Rn,tn)) in enumerate(zip(poses,poses[1:])):
 e=rng.normal(size=6)*sigma;dr=cv2.Rodrigues(e[3:])[0]@R.T@Rn
 rows.append(RelativeMotion(frames[i]['stamp_ns'],frames[i+1]['stamp_ns'],tuple(R.T@(tn-t)+e[:3]),tuple(cv2.Rodrigues(dr)[0].ravel()),tuple(map(tuple,np.diag(sigma**2)))).to_dict())
(public/'relative_motion.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
allowed={'frames.json','calibration.json','board.json','relative_motion.jsonl'}|{'rgb/'+f['filename'] for f in frames}
assert {p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file()}==allowed
write(out/'marker_decodes.json',decodes)
write(out/'verification.json',dict(frames=8,native_pixel_checks=checks,stable_instance_palette=True,source_plant_hashes_unchanged=True,public_allowlist_passed=True,decoded_marker_frames=sum(8 in d['decoded_ids'] for d in decodes),relative_noisy_increments=7,noise_seed=1872026,training_eligible=False,next_action='Frozen V186 ROI inference and tracking on public RGB; evaluate native masks privately.'))
print(json.dumps(read(out/'verification.json')))
