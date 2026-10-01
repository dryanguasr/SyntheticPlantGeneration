"""WSL/Gazebo runtime for the frozen central-aisle mission; raw timestamped capture."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.flight_control import world_to_body, angular_rate_from_poses
from uchuva_gazebo.low_flight_control import desired_velocity
from run_neo_flight import Recorder, yaw_of


class Images:
    def __init__(self, output):
        self.output=output; self.queue=queue.Queue(maxsize=180); self.error=None
        self.index={'rgb':{},'mask':{}}; self.bins=set()
        for name in self.index: (output/name).mkdir()
        self.worker=threading.Thread(target=self.run); self.worker.start()

    def receive(self, name, msg):
        stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nsec
        try:self.queue.put_nowait((name,stamp,msg.width,msg.height,msg.step,bytes(msg.data)))
        except queue.Full:self.error='Raw image queue overflow'

    def run(self):
        try:
            while True:
                item=self.queue.get()
                if item is None:break
                name,stamp,w,h,step,data=item
                # Store original sensor observations only; the MP4 is never an analysis input.
                array=np.frombuffer(data,np.uint8).reshape(h,step)[:,:w*3].reshape(h,w,3)
                filename=f'{name}/{stamp}.png'
                if not cv2.imwrite(str(self.output/filename),array[:,:,::-1]):raise RuntimeError('PNG write failed')
                self.index[name][str(stamp)]=filename
        except Exception as exc:self.error=str(exc)

    def close(self):
        self.queue.put(None); self.worker.join()
        stamps=sorted(set(self.index['rgb']) & set(self.index['mask']),key=int)
        # Choose the nearest original synchronized exposure to each 5 Hz grid time.
        chosen={}
        for s in stamps:
            bucket=round(int(s)/200_000_000)
            if bucket not in chosen or abs(int(s)-bucket*200_000_000)<abs(int(chosen[bucket])-bucket*200_000_000):
                chosen[bucket]=s
        pairs=[{'stamp_ns':int(s),'rgb':self.index['rgb'][s],'mask':self.index['mask'][s]} for s in chosen.values()]
        missing=[{'stamp_ns':int(s),'missing':'mask' if s in self.index['rgb'] else 'rgb'}
                 for s in set(self.index['rgb']) ^ set(self.index['mask'])]
        (self.output/'pairs.json').write_text(json.dumps({'pairs':pairs,'excluded':missing,'error':self.error},indent=2))


def main():
    from gz.transport13 import Node
    from gz.msgs10.odometry_pb2 import Odometry
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.twist_pb2 import Twist
    from gz.msgs10.world_control_pb2 import WorldControl
    from gz.msgs10.boolean_pb2 import Boolean
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('package',type=Path)
    p.add_argument('--technical',action='store_true'); p.add_argument('--wall-timeout',type=float,default=5400)
    p.add_argument('--name',default=None)
    args=p.parse_args(); package=args.package.resolve()
    preflight=json.loads((package/'preflight.json').read_text())
    if not preflight['passed']:raise RuntimeError('Planned route has not passed the 15 cm clearance gate')
    reference=np.array([s['center_m'] for s in preflight['samples']])
    clearances=np.array([s['envelope_clearance_lower_bound_m'] for s in preflight['samples']])
    mission=json.loads((package/'mission.json').read_text())
    if hashlib.sha256((package/'mission.json').read_bytes()).hexdigest()!=(package/'configuration.sha256').read_text().strip():
        raise RuntimeError('Frozen configuration hash mismatch')
    if not args.technical:
        approval=json.loads((package/'technical/validation.json').read_text())
        if not approval['passed']:raise RuntimeError('Technical capture has not passed validation')
        freeze=json.loads((package/'experiment_lock.json').read_text())
        for name,sha in freeze['sha256'].items():
            path=ROOT/name
            if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise RuntimeError(f'Frozen file changed: {name}')
    output=package/(args.name or ('technical' if args.technical else 'flight')); output.mkdir(exist_ok=False)
    images=Images(output); videos=[Recorder(output,n) for n in ('onboard','chase')]
    os.environ['GZ_PARTITION']=f'low_flight_{os.getpid()}'
    os.environ['GZ_SIM_RESOURCE_PATH']=str(package)
    os.environ['GALLIUM_DRIVER']='d3d12'; os.environ['MESA_D3D12_DEFAULT_ADAPTER_NAME']='NVIDIA'
    os.environ['LD_LIBRARY_PATH']='/usr/lib/wsl/lib:'+os.environ.get('LD_LIBRARY_PATH','')
    node=Node(); publisher=node.advertise('/neo/cmd_vel',Twist); state={'odom':None}; lock=threading.Lock()
    def odometry(msg):
        with lock:state['odom']=msg
    node.subscribe(Odometry,'/neo/odometry',odometry)
    def rgb(msg):videos[0].callback(msg); images.receive('rgb',msg)
    node.subscribe(Image,'/neo/onboard',rgb)
    node.subscribe(Image,'/neo/chase',videos[1].callback)
    node.subscribe(Image,'/neo/instances/labels_map',lambda msg:images.receive('mask',msg))
    trace=[]; reached=[]; index=0; previous=np.zeros(3); last_t=None; began=time.monotonic(); failure=None; completed=False
    with (output/'server.log').open('w') as log:
        server=subprocess.Popen(['gz','sim','-s','-v','3',str(package/'flight.sdf')],stdout=log,stderr=subprocess.STDOUT)
        try:
            request=WorldControl(); request.pause=False
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                ok,response=node.request('/world/uchuva_field/control',request,WorldControl,Boolean,1000)
                if ok and response.data:break
                time.sleep(.2)
            else:raise RuntimeError('World control unavailable')
            print('Low-flight simulation started',flush=True)
            while time.monotonic()-began<args.wall_timeout:
                if server.poll() is not None:raise RuntimeError('Gazebo stopped')
                with lock:msg=state['odom']
                if msg is None:time.sleep(.01);continue
                t=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
                if t==last_t:time.sleep(.003);continue
                dt=.034 if last_t is None else t-last_t; last_t=t
                pos=np.array([msg.pose.position.x,msg.pose.position.y,msg.pose.position.z])
                lower=float(np.max(clearances-np.linalg.norm(reference-pos,axis=1)))
                if lower<.16:raise RuntimeError(f'Clearance monitor below reserved margin: {lower}')
                q=msg.pose.orientation; quaternion=[q.x,q.y,q.z,q.w]; yaw=yaw_of(q)
                roll=math.atan2(2*(q.w*q.x+q.y*q.z),1-2*(q.x*q.x+q.y*q.y))
                pitch=math.asin(max(-1,min(1,2*(q.w*q.y-q.z*q.x))))
                if max(abs(roll),abs(pitch))>math.radians(15):raise RuntimeError('Attitude exceeded 15 degrees')
                if images.error or any(v.error for v in videos):raise RuntimeError(images.error or 'Video failure')
                target=mission['waypoints'][index]
                delta=np.array(target['position'])-pos
                desired=np.array(desired_velocity(delta))
                change=desired-previous; length=np.linalg.norm(change)
                previous+=change*min(1,.15*min(dt,.1)/max(length,1e-12))
                yaw_error=math.atan2(math.sin(target['yaw']-yaw),math.cos(target['yaw']-yaw))
                cmd=Twist(); cmd.linear.x,cmd.linear.y,cmd.linear.z=world_to_body(previous,quaternion)
                cmd.angular.z=max(-.35,min(.35,yaw_error)); publisher.publish(cmd)
                error=float(np.linalg.norm(delta))
                trace.append({'t':t,'position':pos.tolist(),'quaternion_xyzw':quaternion,'yaw':yaw,'roll':roll,'pitch':pitch,
                    'angular_velocity':angular_rate_from_poses(trace[-1]['quaternion_xyzw'],quaternion,dt) if trace else [0]*3,
                    'phase':target['phase'],'position_error_m':error,'target':target['position']})
                if len(trace)>1:
                    measured=np.linalg.norm(pos-np.array(trace[-2]['position']))/dt
                    if measured>.205 and t>2:raise RuntimeError(f'Measured speed exceeded 0.20 m/s tolerance: {measured}')
                if args.technical and t>=10:completed=True;break
                if error<.015 and abs(yaw_error)<.025 and t>=3:
                    reached.append({'index':index,'t':t,'position':pos.tolist()});index+=1
                    print(f'Waypoint {index}/{len(mission["waypoints"])} t={t:.2f}',flush=True)
                    if index==len(mission['waypoints']):completed=True;break
            if not completed:raise RuntimeError('Wall timeout')
        except Exception as exc:failure=str(exc)
        finally:
            publisher.publish(Twist()); server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            images.close()
            for video in videos:
                try:video.close()
                except Exception as exc:failure=str(exc)
            provenance={k:mission[k] for k in ('script_version','seed','parameter_preset')}
            (output/'telemetry.json').write_text(json.dumps({**provenance,'samples':trace,'reached':reached}))
            result={**provenance,'completed':completed and failure is None,'failure':failure,
                    'simulation_seconds':last_t,'wall_seconds':time.monotonic()-began,
                    'original_rgb_count':len(images.index['rgb']),'mask_count':len(images.index['mask'])}
            (output/'result.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result),flush=True)
    if failure:raise RuntimeError(failure)


if __name__=='__main__':main()
