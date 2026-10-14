"""WSL: short live Gazebo camera inspection, explicitly not a physical drone flight."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import time
from run_neo_flight import Recorder

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('field',type=Path);p.add_argument('--seconds',type=float,default=12)
    p.add_argument('--output',type=Path)
    a=p.parse_args();field=a.field.resolve();out=a.output.resolve() if a.output else field/'inspection';out.mkdir(exist_ok=False)
    os.environ['GZ_PARTITION']=f'dense_crown_{os.getpid()}'
    os.environ['GZ_SIM_RESOURCE_PATH']=str(field)
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.pose_pb2 import Pose
    from gz.msgs10.boolean_pb2 import Boolean
    check=subprocess.run(['gz','sdf','-k',str(field/'field.sdf')],capture_output=True,text=True)
    (out/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise RuntimeError('Invalid SDF')
    node=Node(); recorder=Recorder(out,'inspection',fps=5,threads=2)
    state={'stamp':None,'first':None,'recording':False};poses=[];failed_requests=0;consecutive_failures=0
    def callback(msg):
        stamp=msg.header.stamp.sec+msg.header.stamp.nsec*1e-9
        state['stamp']=stamp
        if state['recording']:
            if state['first'] is None:state['first']=stamp
            recorder.callback(msg)
    node.subscribe(Image,'/uchuva/drone_camera/image',callback)
    began=time.monotonic();peak=0;first_rgb=None
    with (out/'server.log').open('w') as log:
        server=subprocess.Popen(['gz','sim','-s','-r','--headless-rendering','-v','3',str(field/'field.sdf')],stdout=log,stderr=subprocess.STDOUT)
        try:
            while time.monotonic()-began<480:
                if server.poll() is not None:raise RuntimeError('Gazebo exited')
                # Gazebo's launcher spawns the real server: account for its whole process subtree.
                processes={}
                for path in Path('/proc').glob('[0-9]*/status'):
                    try:
                        info={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in path.read_text().splitlines() if ':' in line}
                        processes[int(path.parent.name)]=(int(info['PPid']),int(info.get('VmRSS','0 kB').split()[0]))
                    except (OSError,ValueError,KeyError):pass
                descendants={server.pid}
                for _ in range(8):descendants.update(pid for pid,(parent,_) in processes.items() if parent in descendants)
                peak=max(peak,sum(processes.get(pid,(0,0))[1] for pid in descendants))
                if state['stamp'] is not None:
                    if first_rgb is None:first_rgb=time.monotonic()-began
                    elapsed=state['stamp']-state['first'] if state['first'] is not None else 0
                    request=Pose();request.name='drone_camera';request.position.x=-3.5+min(elapsed,a.seconds)*.16
                    request.position.y=0;request.position.z=1.0
                    pitch=.15;yaw=-math.pi/2
                    request.orientation.w=math.cos(pitch/2)*math.cos(yaw/2)
                    request.orientation.x=-math.sin(pitch/2)*math.sin(yaw/2)
                    request.orientation.y=math.sin(pitch/2)*math.cos(yaw/2)
                    request.orientation.z=math.cos(pitch/2)*math.sin(yaw/2)
                    ok,response=node.request('/world/uchuva_field/set_pose',request,Pose,Boolean,5000)
                    if not ok or not response.data:
                        failed_requests+=1;consecutive_failures+=1
                        if consecutive_failures>=8:raise RuntimeError('Camera pose request failed eight consecutive times')
                        continue
                    consecutive_failures=0;state['recording']=True
                    poses.append({'simulation_time':state['stamp'],'x':request.position.x,'y':0,'z':1.0})
                    if elapsed>=a.seconds:break
                time.sleep(.1)
            else:raise TimeoutError('Gazebo inspection timeout')
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            recorder.close()
    decode=subprocess.run(['ffmpeg','-v','error','-i',str(out/'inspection.mp4'),'-f','null','-'],capture_output=True,text=True)
    if decode.returncode:raise RuntimeError(decode.stderr)
    manifest=json.loads((field/'manifest.json').read_text())
    (out/'result.json').write_text(json.dumps({'script_version':'dense-inspection/1.0','seed':manifest['seed'],
        'parameter_preset':manifest['crown_preset'],'kind':'live_gazebo_camera_motion_not_drone_flight',
        'first_rgb_wall_seconds':first_rgb,'peak_server_tree_rss_kib':peak,'wall_seconds':time.monotonic()-began,
        'received_frames':recorder.received,'encoded_frames':recorder.count,'decode':'passed',
        'failed_pose_requests':failed_requests,'poses':poses},indent=2))
    print('Gazebo inspection completed',flush=True)

if __name__=='__main__':main()
