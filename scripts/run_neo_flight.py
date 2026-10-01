"""Linux/WSL: fly the dynamic approximation through waypoints and record Gazebo RGB."""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_gazebo.flight_control import world_to_body, bounded_command, flight_metrics, angular_rate_from_poses


def yaw_of(q):
    return math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))


class Recorder:
    def __init__(self, output, name, fps=15):
        self.output,self.name,self.fps=output,name,fps
        self.queue=queue.Queue(maxsize=120); self.count=0; self.received=0
        self.first=None; self.last=None; self.error=None; self.process=None
        self.worker=threading.Thread(target=self.run); self.worker.start()

    def callback(self,msg):
        if msg.pixel_format_type!=3:return
        stamp=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
        data=bytes(msg.data)
        if msg.step!=msg.width*3:
            data=b''.join(data[y*msg.step:y*msg.step+msg.width*3] for y in range(msg.height))
        try:self.queue.put_nowait((stamp,msg.width,msg.height,data))
        except queue.Full:self.error='RGB queue overflow'

    def run(self):
        try:
            while True:
                item=self.queue.get()
                if item is None:break
                stamp,width,height,data=item
                self.received+=1
                if self.process is None:
                    self.first=stamp
                    self.process=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y',
                        '-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{height}',
                        '-framerate',str(self.fps),'-i','-','-an','-c:v','libx264','-preset','veryfast',
                        '-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',
                        str(self.output/f'{self.name}.mp4')],stdin=subprocess.PIPE)
                # Resample by simulation timestamp, never by slower wall-clock arrivals.
                index=round((stamp-self.first)*self.fps)
                while self.count<index and self.last is not None:
                    self.process.stdin.write(self.last); self.count+=1
                if self.count==index:
                    self.process.stdin.write(data); self.count+=1
                self.last=data
        except Exception as error:self.error=str(error)
        finally:
            if self.process:
                self.process.stdin.close()
                if self.process.wait()!=0:self.error='FFmpeg failed'

    def close(self):
        if self.worker.is_alive():
            try:self.queue.put(None,timeout=5)
            except queue.Full:raise RuntimeError('Video writer queue did not drain')
        self.worker.join(timeout=30)
        if self.worker.is_alive():raise RuntimeError('Video writer failed to stop')
        if self.error:raise RuntimeError(self.error)


def main():
    from gz.transport13 import Node
    from gz.msgs10.odometry_pb2 import Odometry
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.twist_pb2 import Twist
    from gz.msgs10.world_control_pb2 import WorldControl
    from gz.msgs10.boolean_pb2 import Boolean
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('--probe-seconds',type=float,default=0)
    parser.add_argument('--wall-timeout',type=float,default=1800)
    parser.add_argument('--no-video',action='store_true',help='Run full mission without RGB recording')
    parser.add_argument('--graphics',choices=('egl','wsl-d3d12'),default='egl')
    args=parser.parse_args(); package=args.package.resolve()
    if args.probe_seconds and args.probe_seconds<10:
        parser.error('Hover validation requires at least 10 simulation seconds')
    output=package/('probe' if args.probe_seconds else 'flight')
    output.mkdir(exist_ok=False)
    mission=json.loads((package/'mission.json').read_text())
    provenance={k:mission[k] for k in ('script_version','seed','parameter_preset')}
    os.environ['GZ_PARTITION']=f'neo_flight_{os.getpid()}'
    os.environ['GZ_SIM_RESOURCE_PATH']=str(package)+os.pathsep+os.environ.get('GZ_SIM_RESOURCE_PATH','')
    if args.graphics=='wsl-d3d12':
        os.environ['GALLIUM_DRIVER']='d3d12'
        os.environ['MESA_D3D12_DEFAULT_ADAPTER_NAME']='NVIDIA'
        os.environ['LD_LIBRARY_PATH']='/usr/lib/wsl/lib:'+os.environ.get('LD_LIBRARY_PATH','')
    check=subprocess.run(['gz','sdf','-k',str(package/'flight.sdf')],capture_output=True,text=True)
    (output/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise RuntimeError('Invalid SDF')
    node=Node(); publisher=node.advertise('/neo/cmd_vel',Twist)
    state={'odom':None}; lock=threading.Lock()
    def odometry(msg):
        with lock:state['odom']=msg
    node.subscribe(Odometry,'/neo/odometry',odometry)
    recorders=[]
    if not args.probe_seconds and not args.no_video:
        for name in ('onboard','chase'):
            recorder=Recorder(output,name); recorders.append(recorder)
            node.subscribe(Image,f'/neo/{name}',recorder.callback)
    began=time.monotonic(); index=0; reached=[]; trace=[]; last_t=-1; first_t=None
    waypoints=mission['waypoints']; failure=None; success=False
    previous_command=(0,0,0,0)
    with (output/'server.log').open('w') as log:
        graphics_args=['--headless-rendering'] if args.graphics=='egl' else []
        server=subprocess.Popen(['gz','sim','-s',*graphics_args,'-v','3',str(package/'flight.sdf')],
                                stdout=log,stderr=subprocess.STDOUT)
        try:
            request=WorldControl(); request.pause=False
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                ok,response=node.request('/world/uchuva_field/control',request,WorldControl,Boolean,1000)
                if ok and response.data:break
                time.sleep(.2)
            else:raise RuntimeError('World control service unavailable')
            print('Simulation started',flush=True)
            while time.monotonic()-began<args.wall_timeout:
                if server.poll() is not None:raise RuntimeError('Gazebo stopped unexpectedly')
                with lock:msg=state['odom']
                if msg is None:
                    publisher.publish(Twist()); time.sleep(.03);continue
                t=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
                if t==last_t:time.sleep(.005);continue
                dt=.034 if last_t<0 else t-last_t
                last_t=t
                if first_t is None:first_t=t
                pos=(msg.pose.position.x,msg.pose.position.y,msg.pose.position.z)
                yaw=yaw_of(msg.pose.orientation)
                q=msg.pose.orientation
                roll=math.atan2(2*(q.w*q.x+q.y*q.z),1-2*(q.x*q.x+q.y*q.y))
                pitch=math.asin(max(-1,min(1,2*(q.w*q.y-q.z*q.x))))
                quaternion=[q.x,q.y,q.z,q.w]
                rates=angular_rate_from_poses(trace[-1]['quaternion_xyzw'],quaternion,dt) if trace else (0,0,0)
                tilt=math.acos(max(-1,min(1,math.cos(roll)*math.cos(pitch))))
                if tilt>math.radians(25):raise RuntimeError('Attitude exceeded 25 degree test abort limit')
                if not all(math.isfinite(v) for v in (*pos,yaw)) or pos[2]<-.1 or pos[2]>8:
                    raise RuntimeError(f'Flight left vertical test bounds: {pos}')
                if abs(pos[0])>10 or abs(pos[1])>10:raise RuntimeError('Flight left field test bounds')
                if args.probe_seconds:
                    target={'position':[-5.2,-5.6,1.2],'yaw':0,'phase':'hover_probe'}
                    if t-first_t>=args.probe_seconds:
                        success=flight_metrics(trace)['hover_settled']
                        if not success:raise RuntimeError(f'Hover probe did not converge: {pos}')
                        break
                else:
                    if any(r.error for r in recorders):raise RuntimeError('Video recording failed')
                    # Hold above launch pad while rendering initializes.
                    if not all(r.received>=3 for r in recorders):
                        target={'position':[-5.2,-5.6,.15],'yaw':0,'phase':'sensor_warmup'}
                    else:target=waypoints[index]
                delta=[a-b for a,b in zip(target['position'],pos)]
                error=math.sqrt(sum(v*v for v in delta))
                yaw_error=math.atan2(math.sin(target['yaw']-yaw),math.cos(target['yaw']-yaw))
                previous_command=bounded_command(delta,yaw_error,previous_command,dt)
                cmd=Twist()
                cmd.linear.x,cmd.linear.y,cmd.linear.z=world_to_body(previous_command[:3],(q.x,q.y,q.z,q.w))
                cmd.angular.z=previous_command[3]
                publisher.publish(cmd)
                trace.append({'t':t,'position':pos,'yaw':yaw,'target':target['position'],
                              'roll':roll,'pitch':pitch,
                              'quaternion_xyzw':quaternion,
                              'linear_velocity':[msg.twist.linear.x,msg.twist.linear.y,msg.twist.linear.z],
                              'angular_velocity':rates,
                              'angular_velocity_raw_odom':[msg.twist.angular.x,msg.twist.angular.y,msg.twist.angular.z],
                              'command_body':[cmd.linear.x,cmd.linear.y,cmd.linear.z,cmd.angular.z],
                              'phase':target['phase'],'position_error_m':error})
                if not args.probe_seconds and target['phase']!='sensor_warmup' and error<.13 and abs(yaw_error)<.15:
                    reached.append({'index':index,'phase':target['phase'],'t':t,'position':pos})
                    print(f'Waypoint {index+1}/{len(waypoints)} {target["phase"]} t={t:.1f}',flush=True)
                    index+=1
                    if index==len(waypoints):success=True;break
            if not success:raise TimeoutError('Mission did not complete within wall timeout')
            if not flight_metrics(trace)['attitude_envelope_pass']:
                success=False;raise RuntimeError('Flight exceeded 15 degree attitude acceptance limit')
        except KeyboardInterrupt:
            failure='operator_interrupted'
        except Exception as error:
            failure=str(error)
        finally:
            publisher.publish(Twist())
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            for recorder in recorders:
                try:recorder.close()
                except Exception as error:failure=str(error);success=False
            (output/'telemetry.json').write_text(json.dumps({**provenance,'samples':trace,'reached':reached}))
            result={**provenance,'completed':success,'failure':failure,'waypoints_reached':len(reached),
                'waypoints_expected':len(waypoints),'wall_seconds':time.monotonic()-began,
                'simulation_seconds':None if first_t is None else last_t-first_t,
                'stability':flight_metrics(trace),
                'angular_velocity_source':'shortest_quaternion_interval_body_estimate; raw odometry retained',
                'motion':'dynamic_rotor_thrust_no_pose_teleportation','graphics':args.graphics,
                'videos':{r.name:{'encoded_frames':r.count,'received_frames':r.received,'fps':r.fps} for r in recorders}}
            (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    if failure:raise RuntimeError(failure)


if __name__=='__main__':main()
