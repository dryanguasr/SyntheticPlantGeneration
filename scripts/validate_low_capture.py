"""Evaluator-only technical gates: stamps, native instance IDs, projection and clearance."""
import argparse
import json
import math
from pathlib import Path
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.evaluation import visible_boxes as mask_boxes


def rotation(q):
    x,y,z,w=np.asarray(q)/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def camera_pose(samples, stamp, pitch=math.radians(20)):
    times=np.array([s['t'] for s in samples]); t=stamp*1e-9
    j=int(np.searchsorted(times,t)); j=max(1,min(j,len(times)-1))
    a,b=samples[j-1],samples[j]; u=(t-a['t'])/(b['t']-a['t'])
    if u<-.01 or u>1.01:raise ValueError('Camera stamp outside telemetry interval')
    qa,qb=np.array(a['quaternion_xyzw']),np.array(b['quaternion_xyzw'])
    if np.dot(qa,qb)<0:qb=-qb
    R=rotation((1-u)*qa+u*qb); pos=(1-u)*np.array(a['position'])+u*np.array(b['position'])
    Ry=np.array([[math.cos(pitch),0,math.sin(pitch)],[0,1,0],[-math.sin(pitch),0,math.cos(pitch)]])
    optical=np.array([[0,0,1],[-1,0,0],[0,-1,0]])
    return R@Ry@optical, pos+R@np.array([.068,0,.005]), b['t']-a['t']


def decode_mask(path):
    rgb=cv2.imread(str(path),cv2.IMREAD_COLOR)[:,:,::-1].astype(np.int32)
    return np.where(rgb[:,:,2]==1,rgb[:,:,0]+256*rgb[:,:,1],0)


def audit_executed(samples,preflight):
    distance=[]
    for s in samples:
        p=np.array(s['position']); nearest=float('inf')
        for segment in preflight['segments']:
            a,b=np.array(segment['from_m']),np.array(segment['to_m']);v=b-a
            u=np.clip(np.dot(p-a,v)/np.dot(v,v),0,1)
            nearest=min(nearest,float(np.linalg.norm(p-(a+u*v))))
        distance.append(nearest)
    speed=[np.linalg.norm(np.array(b['position'])-a['position'])/(b['t']-a['t']) for a,b in zip(samples,samples[1:])]
    interval=max(b['t']-a['t'] for a,b in zip(samples,samples[1:]))
    # Conservative sampled-curve correction at measured maximum speed.
    if 'samples' in preflight:
        reference=np.array([s['center_m'] for s in preflight['samples']])
        clearance=np.array([s['envelope_clearance_lower_bound_m'] for s in preflight['samples']])
        lower=min(float(np.max(clearance-np.linalg.norm(reference-s['position'],axis=1))) for s in samples)
        lower-=max(speed)*interval/2
    else:lower=preflight['minimum_clearance_lower_bound_m']-max(distance)-max(speed)*interval/2
    return {'passed':bool(lower>=.15),'clearance_lower_bound_m':float(lower),'max_route_deviation_m':max(distance),
            'sample_interval_max_s':interval,'max_interval_speed_m_s':float(max(speed)),
            'method':'planned continuous swept sphere lower bound minus observed route deviation and sample correction'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--run',default='technical')
    args=p.parse_args();package=args.package; run=package/args.run
    config=json.loads((package/'mission.json').read_text());K=np.array(config['camera']['K'])
    inventory=json.loads((package/'evaluator/inventory.json').read_text())['calyces']
    by_label={o['panoptic_instance']:o for o in inventory}
    pairs=json.loads((run/'pairs.json').read_text());samples=json.loads((run/'telemetry.json').read_text())['samples']
    bounds={}
    for o in inventory:
        v=np.array([list(map(float,l.split()[1:4])) for l in (package/o['uri']).read_text().splitlines() if l.startswith('v ')])
        lo,hi=v.min(axis=0),v.max(axis=0)
        bounds[o['panoptic_instance']]=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    checks=[]; outside=[]; pose_rows=[]
    for pair in pairs['pairs']:
        try:R,C,interval=camera_pose(samples,pair['stamp_ns'])
        except ValueError:outside.append(pair['stamp_ns']);continue
        pose_rows.append({'stamp_ns':pair['stamp_ns'],'R_world_optical':R.tolist(),'center_world_m':C.tolist(),
                          'telemetry_interpolation_interval_s':interval})
        for box in mask_boxes(decode_mask(run/pair['mask'])):
            if box['pixels']<16:continue
            identifier=box['instance']
            if identifier not in by_label:checks.append(False);continue
            camera=(bounds[identifier]-C)@R
            if camera[:,2].min()<=0:continue
            projected=camera@K.T;projected=projected[:,:2]/projected[:,2,None]
            lo,hi=projected.min(axis=0)-3,projected.max(axis=0)+3
            x1,y1,x2,y2=box['box']
            checks.append(bool(x1>=lo[0] and y1>=lo[1] and x2<=hi[0] and y2<=hi[1]))
    clearance=audit_executed(samples,json.loads((package/'preflight.json').read_text()))
    passes=[s for s in samples if s['phase'].startswith('pass_')]
    altitude_error=max((abs(s['position'][2]-s['target'][2]) for s in passes),default=float('inf'))
    pass_speed=max((np.linalg.norm(np.array(b['position'])-a['position'])/(b['t']-a['t'])
                    for a,b in zip(samples,samples[1:]) if b['phase'].startswith('pass_')),default=float('inf'))
    result=json.loads((run/'result.json').read_text())
    validation={'passed':bool(result['completed'] and clearance['passed'] and altitude_error<=.03 and pass_speed<=.20 and len(pairs['pairs'])>=40 and
                              len(checks)>=5 and all(checks) and not pairs['error']),
                'max_pass_height_error_m':float(altitude_error),'max_pass_speed_m_s':float(pass_speed),
                'synchronized_pairs':len(pairs['pairs']),'missing_pairs':len(pairs['excluded']),
                'identity_projection_checks':len(checks),'identity_projection_passes':sum(checks),
                'pose_out_of_interval_stamps':outside,'clearance':clearance,
                'id_contract':'Ogre2 descending scoped visual names; R=instance low byte G=high B=class=1',
                'pose_source':'evaluator-only interpolated Gazebo odometry; never estimator input'}
    (run/'validation.json').write_text(json.dumps(validation,indent=2))
    (package/'evaluator'/f'{args.run}_camera_poses.json').write_text(json.dumps(pose_rows))
    print(json.dumps(validation,indent=2))


if __name__=='__main__':main()
