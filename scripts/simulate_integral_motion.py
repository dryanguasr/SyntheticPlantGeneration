"""Simulator-side noisy sensor adapter. Exact world poses never leave this script.

Noise is an engineering sensitivity model, NOT a calibrated physical IMU.
Publishes camera-relative odometry; no global origin, truth mask or organ IDs.
"""
import json
from pathlib import Path
import sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.flight_control import world_to_body
from uchuva_gazebo.motion_observations import RelativeMotion
from uchuva_lsystem.segmentation_cycles import write,sha


def main():
    root=ROOT/'outputs/integral_diagnosis_20261014';old=ROOT/'outputs/continuous_row_20261008'
    output=root/'public_motion';output.mkdir(exist_ok=False)
    telemetry_path=old/'flight/full/telemetry.json';samples=json.loads(telemetry_path.read_text())['samples']
    times=np.array([s['t'] for s in samples]);positions=np.array([s['position'] for s in samples])
    quats=np.array([s['quaternion_xyzw'] for s in samples])
    for i in range(1,len(quats)):
        if quats[i-1]@quats[i]<0:quats[i]*=-1
    frames=json.loads((old/'public/frames.json').read_text());stamps=np.array([f['stamp_ns'] for f in frames],dtype=np.int64)
    cv_from_body=np.array([[0,-1,0],[0,0,-1],[1,0,0]])
    offset=np.array([.068,0,.005])
    def camera(t):
        j=int(np.clip(np.searchsorted(times,t),1,len(times)-1));a=float(np.clip((t-times[j-1])/(times[j]-times[j-1]),0,1))
        q=quats[j-1]*(1-a)+quats[j]*a;q/=np.linalg.norm(q)
        world_from_body=np.column_stack([world_to_body(np.eye(3)[:,i],q) for i in range(3)]).T
        position=positions[j-1]*(1-a)+positions[j]*a
        return world_from_body@cv_from_body.T,position+world_from_body@offset
    for name,scale in [('low',.5),('nominal',1.),('high',2.)]:
        rng=np.random.default_rng(20261014);bias=np.zeros(6);previous=None;previous_stamp=None;written=0
        with (output/f'{name}.jsonl').open('w') as stream:
            for stamp in stamps:
                sensor_time=stamp/1e9-.02
                if sensor_time<times[0] or sensor_time>times[-1]:continue
                R,t=camera(sensor_time)
                if previous is not None:
                    Rp,tp=previous;dt=(int(stamp)-previous_stamp)/1e9
                    bias+=rng.normal(size=6)*np.array([.001]*3+[.0002]*3)*scale*np.sqrt(dt)
                    sigmas=np.array([.005]*3+[.002]*3)*scale*np.sqrt(dt)
                    noise=rng.normal(size=6)*sigmas+bias*dt
                    delta_t=Rp.T@(t-tp)+noise[:3]
                    delta_R=(Rp.T@R)@cv2.Rodrigues(noise[3:])[0]
                    delta_r=cv2.Rodrigues(delta_R)[0].ravel()
                    # Marginal bias variance; temporal correlation is not modeled
                    # by the pilot EKF, explicitly retained as a limitation.
                    elapsed=sensor_time-times[0]
                    variance=sigmas**2+(np.array([.001]*3+[.0002]*3)*scale)**2*elapsed*dt**2
                    row=RelativeMotion(previous_stamp,int(stamp),tuple(delta_t),tuple(delta_r),tuple(map(tuple,np.diag(variance)))).to_dict()
                    stream.write(json.dumps(row)+'\n');written+=1
                previous=(R,t);previous_stamp=int(stamp)
        write(output/f'{name}_configuration.json',dict(version='noisy-relative-odometry/1.0',seed=20261014,
            noise_scale=scale,records=written,time_offset_s=.02,frame='previous_camera',
            rotation_convention='new_camera_to_previous_camera',
            parameter_status='engineering_heuristic_not_hardware_calibrated',
            translational_white_noise_m_per_sqrt_s=.005*scale,
            angular_white_noise_rad_per_sqrt_s=.002*scale,
            velocity_bias_random_walk_m_per_s_per_sqrt_s=.001*scale,
            angular_velocity_bias_random_walk_rad_per_s_per_sqrt_s=.0002*scale,
            limitation='correlated bias represented only by marginal covariance; not raw physical IMU',
            absolute_world_origin_included=False))
    write(root/'sensor_adapter_private_provenance.json',dict(source_sha256=sha(telemetry_path),
        adapter='simulator_side_only',public_output=str(output),
        camera_offset_body_m=offset.tolist(),camera_from_body=cv_from_body.tolist(),
        source_frames_sha256=sha(old/'public/frames.json')))
    print('NOISY_MOTION',len(stamps),'frame timestamps',flush=True)


if __name__=='__main__':main()
