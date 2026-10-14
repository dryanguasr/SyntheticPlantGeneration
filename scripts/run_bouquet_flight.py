"""WSL: dynamic close inspection with executed clearance monitoring and raw samples."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.flight_control import world_to_body
from uchuva_gazebo.continuous_row import inward_yaw,orientation_speed_scale
from uchuva_gazebo.low_flight_control import desired_velocity
from run_neo_flight import Recorder,yaw_of


def main():
    from gz.transport13 import Node
    from gz.msgs10.odometry_pb2 import Odometry
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.twist_pb2 import Twist
    from gz.msgs10.world_control_pb2 import WorldControl
    from gz.msgs10.boolean_pb2 import Boolean
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--name',default='flight')
    p.add_argument('--seconds',type=float,default=0);p.add_argument('--wall-timeout',type=float,default=7200)
    a=p.parse_args();package=a.package.resolve();out=package/a.name;out.mkdir(exist_ok=False);(out/'rgb').mkdir()
    mission=json.loads((package/'mission.json').read_text());audit=json.loads((package/'preflight.json').read_text())
    if not audit['passed']:raise RuntimeError('Preflight blocked')
    samples=[s for c in audit['selected'] for s in c['samples']]+audit['transfers']
    reference=np.array([s['p'] for s in samples]);distance=np.array([s['distance'] for s in samples])
    os.environ['GZ_PARTITION']=f'bouquet_{os.getpid()}';os.environ['GZ_SIM_RESOURCE_PATH']=str(package)+':'+str(package.parent/'bouquet_v4_textured')
    driver=os.environ.get('UCHUVA_RENDER_DRIVER','d3d12')
    if driver not in ('d3d12','llvmpipe'):raise ValueError('Unsupported experiment render driver')
    os.environ['GALLIUM_DRIVER']=driver
    if driver=='llvmpipe':
        os.environ['LIBGL_ALWAYS_SOFTWARE']='1'
        os.environ['MESA_LOADER_DRIVER_OVERRIDE']='swrast'
        os.environ['LP_NUM_THREADS']='4'
    else:os.environ['MESA_D3D12_DEFAULT_ADAPTER_NAME']='NVIDIA'
    os.environ['LD_LIBRARY_PATH']='/usr/lib/wsl/lib:'+os.environ.get('LD_LIBRARY_PATH','')
    node=Node();pub=node.advertise('/neo/cmd_vel',Twist);state={'odom':None,'rgb':None,'first_rgb_wall':None};lock=threading.Lock()
    def odom(msg):
        with lock:state['odom']=msg
    recorders=[Recorder(out,n,threads=2) for n in ('onboard','chase')]
    def rgb(msg):
        recorders[0].callback(msg)
        with lock:
            state['rgb']=msg
            if state['first_rgb_wall'] is None:state['first_rgb_wall']=time.monotonic()-began
    node.subscribe(Odometry,'/neo/odometry',odom);node.subscribe(Image,'/neo/onboard',rgb)
    node.subscribe(Image,'/neo/chase',recorders[1].callback)
    trace=[];frames=[];reached=[];index=0;last=None;last_saved=-1;previous=np.zeros(3);first=None;failure=None;completed=False
    previous_yaw_rate=0.
    began=time.monotonic();settled_since=None
    with (out/'server.log').open('w') as log:
        server=subprocess.Popen(['gz','sim','-s','-v','3',str(package/'flight.sdf')],stdout=log,stderr=subprocess.STDOUT)
        try:
            request=WorldControl();request.pause=True
            deadline=time.monotonic()+300
            while time.monotonic()<deadline:
                if server.poll() is not None:raise RuntimeError('Gazebo stopped during initialization')
                ok,response=node.request('/world/uchuva_field/control',request,WorldControl,Boolean,1000)
                if ok and response.data:break
                time.sleep(.2)
            else:raise RuntimeError('World unavailable')
            deadline=time.monotonic()+120
            while not pub.has_connections():
                if server.poll() is not None:raise RuntimeError('Gazebo stopped before controller handshake')
                if time.monotonic()>deadline:raise RuntimeError('Controller unavailable')
                time.sleep(.05)
            for _ in range(20):pub.publish(Twist());time.sleep(.05)
            request.pause=False;ok,response=node.request('/world/uchuva_field/control',request,WorldControl,Boolean,5000)
            if not ok or not response.data:raise RuntimeError('Unpause failed')
            while time.monotonic()-began<a.wall_timeout:
                if server.poll() is not None:raise RuntimeError('Gazebo stopped')
                with lock:msg=state['odom'];image=state['rgb']
                if msg is None:time.sleep(.01);continue
                t=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
                if t==last:time.sleep(.002);continue
                dt=.034 if last is None else t-last;last=t
                if first is None:first=t
                pos=np.array([msg.pose.position.x,msg.pose.position.y,msg.pose.position.z]);q=msg.pose.orientation
                lower=float(np.max(distance-np.linalg.norm(reference-pos,axis=1)))-audit['radius_m']
                if lower<.15:raise RuntimeError(f'Executed clearance below 15 cm: {lower}')
                roll=math.atan2(2*(q.w*q.x+q.y*q.z),1-2*(q.x*q.x+q.y*q.y))
                pitch=math.asin(max(-1,min(1,2*(q.w*q.y-q.z*q.x))))
                if max(abs(roll),abs(pitch))>math.radians(15):raise RuntimeError('Attitude exceeded 15 degrees')
                target=mission['waypoints'][index];delta=np.array(target['position'])-pos
                yaw=yaw_of(q)
                camera_position=pos+np.array([.068*math.cos(yaw),.068*math.sin(yaw),.005])
                heading=inward_yaw(camera_position,target['look_at_world_m']) if 'look_at_world_m' in target else target['yaw']
                error=math.atan2(math.sin(heading-yaw),math.cos(heading-yaw))
                desired=np.array(desired_velocity(delta))
                if 'look_at_world_m' in target:desired*=orientation_speed_scale(error)
                change=desired-previous
                previous+=change*min(1,.15*min(dt,.1)/max(np.linalg.norm(change),1e-12))
                rate=max(-.35,min(.35,error))
                if 'look_at_world_m' in target:
                    rate=previous_yaw_rate+max(-.6*min(dt,.1),min(.6*min(dt,.1),rate-previous_yaw_rate))
                previous_yaw_rate=rate
                cmd=Twist();cmd.linear.x,cmd.linear.y,cmd.linear.z=world_to_body(previous,[q.x,q.y,q.z,q.w]);cmd.angular.z=rate;pub.publish(cmd)
                trace.append({'t':t,'position':pos.tolist(),'quaternion_xyzw':[q.x,q.y,q.z,q.w],'roll':roll,'pitch':pitch,'phase':target['phase'],'clearance_lower_bound_m':lower,'desired_yaw':heading,'yaw_error':error,'look_at_world_m':target.get('look_at_world_m')})
                if image is not None:
                    stamp=image.header.stamp.sec+image.header.stamp.nsec*1e-9
                    if stamp>=last_saved+1:
                        pixels=np.frombuffer(image.data,np.uint8).reshape(image.height,image.step)[:,:image.width*3].reshape(image.height,image.width,3)
                        filename=f'{round(stamp*1e9)}.png';cv2.imwrite(str(out/'rgb'/filename),pixels[:,:,::-1]);frames.append({'filename':filename,'stamp_ns':round(stamp*1e9)});last_saved=stamp
                if any(r.error for r in recorders):raise RuntimeError('Video writer failure')
                if a.seconds and t-first>=a.seconds:completed=True;break
                pass_through=target['phase'].startswith('inward_turn_') and index+1<len(mission['waypoints'])
                settled=np.linalg.norm(delta)<(.10 if pass_through else .02) and abs(error)<(.10 if pass_through else .025)
                if settled and settled_since is None:settled_since=t
                if not settled:settled_since=None
                hold=mission.get('station_hold_seconds',0) if 'station' in target['phase'] else 0
                if settled and t-first>mission.get('initial_hold_seconds',3) and t-settled_since>=hold:
                    reached.append({'index':index,'phase':target['phase'],'t':t});index+=1
                    settled_since=None
                    print(f'Waypoint {index}/{len(mission["waypoints"])} {target["phase"]} t={t:.1f}',flush=True)
                    if index==len(mission['waypoints']):completed=True;break
            if not completed:raise TimeoutError('Flight wall timeout')
        except Exception as exc:failure=str(exc)
        finally:
            pub.publish(Twist());server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            for r in recorders:
                try:r.close()
                except Exception as exc:failure=str(exc)
            (out/'frames.json').write_text(json.dumps(frames));(out/'telemetry.json').write_text(json.dumps({'samples':trace,'reached':reached}))
            result={'completed':completed and failure is None,'failure':failure,'wall_seconds':time.monotonic()-began,'simulation_seconds':last,
                'first_rgb_wall_seconds':state['first_rgb_wall'],
                'waypoints_reached':len(reached),'waypoints_expected':len(mission['waypoints']),'original_rgb_samples':len(frames),
                'render_driver':driver,
                'motion':'dynamic rotor thrust, no teleportation','minimum_executed_margin_m':min((s['clearance_lower_bound_m'] for s in trace),default=None)}
            (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
    if failure:raise RuntimeError(failure)

if __name__=='__main__':main()
