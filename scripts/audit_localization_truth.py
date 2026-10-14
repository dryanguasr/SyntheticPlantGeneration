"""Evaluator-only anatomical mapping audit and all-visible denominator cache."""
import argparse,collections,json,sys
from pathlib import Path
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.segmentation_cycles import write,sha
from uchuva_gazebo.segmentation_evaluation import decode_panoptic_rgb
from uchuva_gazebo.flight_control import world_to_body


def main():
    p=argparse.ArgumentParser();p.add_argument('--flight',type=Path,required=True);p.add_argument('--field',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    inventory=json.loads((a.flight.parent/'inventory.json').read_text())['calyces']
    markers=json.loads((a.flight.parent/'preflight.json').read_text())['markers']
    groups=collections.defaultdict(list)
    for organ in inventory:groups[organ['semantic_label']].append(organ)
    candidates=[]
    for reverse in [True,False]:
        candidates.append({label*65536+index:organ for label,organs in groups.items() for index,organ in enumerate(sorted(organs,key=lambda o:o['model_name'],reverse=reverse),1)})
    boxes={}
    for organ in inventory:
        vertices=[]
        for uri in organ['meshes']:
            active=False
            with (a.field/uri).open() as stream:
                for line in stream:
                    if line.startswith('# source '):active=line.strip()[9:]==organ['object']
                    elif active and line.startswith('v '):vertices.append(list(map(float,line.split()[1:4])))
        points=np.asarray(vertices)
        if not len(points):raise ValueError('Missing source mesh for '+organ['reproductive_id'])
        lo=points.min(axis=0);hi=points.max(axis=0)
        boxes[organ['reproductive_id']]=np.array([[x,y,z] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])
    pairs=json.loads((a.flight/'paired/pairs.json').read_text())['pairs'];telemetry=json.loads((a.flight/'telemetry.json').read_text())['samples'];times=np.array([s['t'] for s in telemetry]);focal=1280/(2*np.tan(np.pi/6))
    checks=[[],[]];frames=[];visible=set()
    for frame_index,pair in enumerate(pairs):
        native=cv2.imread(str(a.flight/'paired'/pair['mask']))
        if native is None:raise ValueError('Unreadable native mask')
        codes=decode_panoptic_rgb(native[:,:,::-1]);entries=[]
        for code in np.unique(codes):
            if not code:continue
            ys,xs=np.nonzero(codes==code);entries.append(dict(code=int(code),pixels=len(xs),bbox=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]));visible.add(int(code))
        frames.append(dict(stamp_ns=pair['stamp_ns'],instances=entries))
        if frame_index%20==0:
            sample=telemetry[int(np.argmin(abs(times-pair['stamp_ns']/1e9)))];position=sample['position'];q=sample['quaternion_xyzw']
            for mapping,values in zip(candidates,checks):
                for entry in entries:
                    if entry['code'] not in mapping:raise ValueError('Native counter outside inventory')
                    corners=boxes[mapping[entry['code']]['reproductive_id']]
                    body=np.array([world_to_body(point-position,q) for point in corners]);depth=body[:,0]-.068
                    if depth.min()<=0:values.append(False);continue
                    uv=np.column_stack((640-focal*body[:,1]/depth,360-focal*(body[:,2]-.005)/depth))
                    lo=uv.min(axis=0)-4;hi=uv.max(axis=0)+4;x,y,xx,yy=entry['bbox']
                    values.append(bool(lo[0]<=x and lo[1]<=y and hi[0]>=xx-1 and hi[1]>=yy-1))
        if frame_index%200==0:print('TRUTH_CACHE',frame_index,flush=True)
    rates=[float(np.mean(c)) for c in checks];best=int(np.argmax(rates))
    passed=rates[best]>=.98 and rates[best]-rates[1-best]>=.2
    write(a.output/'mapping_audit.json',dict(passed=passed,method='Label-wise lexical native instance ordering independently checked against projected exact-mesh AABBs on sampled frames',reverse_and_forward_agreement=rates,chosen_reverse=best==0,pixel_tolerance=4,required_agreement=.98,scope='geometric consistency audit; inspect exceptions, not merely counter ranges',source_inventory_sha256=sha(a.flight.parent/'inventory.json')))
    if not passed:raise ValueError('Anatomical native mapping not verified: '+str(rates))
    objects={}
    for code,organ in candidates[best].items():
        marker=next(m for m in markers if m['plant_id']==organ['plant_id'] and m['face']=='front')
        normal=np.array(marker['normal_world']);up=np.array([0,0,1]);right=np.cross(up,normal)
        position=np.column_stack((right,up,normal)).T@(np.asarray(organ['center_world_m'])-marker['center_world_m'])
        objects[str(code)]=dict(**organ,canonical_marker_id=marker['id'],position_marker_m=position.tolist(),ever_visible=code in visible)
    write(a.output/'truth.json',dict(version='localization-evaluator-truth/1.0',objects=objects,frames=frames,visible_unique=len(visible),hidden_unique=len(objects)-len(visible),pairs_sha256=sha(a.flight/'paired/pairs.json'),all_visible_pixels_in_denominator=True))
    print('TRUTH_AUDIT_PASSED',rates,len(visible),flush=True)


if __name__=='__main__':main()
