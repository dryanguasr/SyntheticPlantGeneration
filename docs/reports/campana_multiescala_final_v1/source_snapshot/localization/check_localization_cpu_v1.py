"""Deterministic geometry fixtures; no campaign observations used as tuning data."""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
from localize_public_v1 import load_frozen, read, write, require


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--frozen-src',type=Path,required=True)
    a=p.parse_args();protocol=read(a.root/'protocol.json')
    multi,fusion,local,motion=load_frozen(a.frozen_src,protocol)
    tests=[]
    K=np.array([[900.,0,640],[0,900.,360],[0,0,1]])
    point=np.array([.03,.04,.2]);observations=[]
    for i,x in enumerate([0.,.2,.4,.6]):
        t=np.array([-x,0,2.]);v=K@(point+t)
        observations.append(dict(R=np.eye(3).tolist(),t=t.tolist(),point_px=(v[:2]/v[2]).tolist(),
                                 marker_id=8,observation_id=str(i)))
    result=local.robust_triangulate(observations,K)
    require(result['status']=='estimated' and np.linalg.norm(np.array(result['position_marker_m'])-point)<1e-8,'Metric triangulation fixture failed')
    tests.append('Known four-view 3D geometry recovered with fixed gates')
    require(multi.triangulate(observations[:2],K)['status']!='estimated','Two views accepted')
    tests.append('Fewer than three observations rejected')
    flat=[dict(observations[0],observation_id=str(i)) for i in range(4)]
    require(multi.triangulate(flat,K)['reason']=='insufficient_parallax','Parallax gate weakened')
    tests.append('Zero-parallax observations rejected')
    f=fusion.MarkerMotionFusion(8,gate=16.8)
    row=motion.RelativeMotion(0,250000000,(.2,0.,0.),(0.,0.,0.),tuple(map(tuple,np.eye(6)*1e-6))).to_dict()
    try:f.predict(row);raise AssertionError('Unanchored motion accepted')
    except ValueError:pass
    tests.append('No metric pose before decoded marker anchor')
    f.correct(0,8,np.eye(3),[0,0,2],np.eye(6)*1e-4);f.predict(row)
    require(np.allclose(f.camera_from_marker()['t'],[-.2,0,2]),'Relative translation convention wrong')
    tests.append('Previous-camera increment and 0.25s timestamp correctly propagated')
    for bad in [dict(row,start_stamp_ns=1),dict(row,world_pose=[1,2,3])]:
        try:f.predict(bad);raise AssertionError('Invalid motion accepted')
        except ValueError:pass
    tests.append('Motion gaps and private extra fields rejected')
    try:f.correct(250000000,9,np.eye(3),[0,0,2],np.eye(6));raise AssertionError('Unknown marker accepted')
    except ValueError:pass
    tests.append('Uncalibrated marker identity rejected')
    require(not f.correct(250000000,8,np.eye(3),[20,0,2],np.eye(6)*1e-4),'Innovation gate weakened')
    tests.append('Large marker innovation rejected by frozen 16.8 gate')
    write(a.root/'cpu_check_v1.json',dict(passed=True,tests=tests,number_of_tests=len(tests),campaign_data_used=False))
    print(json.dumps(dict(passed=True,tests=len(tests))))


if __name__=='__main__':main()
