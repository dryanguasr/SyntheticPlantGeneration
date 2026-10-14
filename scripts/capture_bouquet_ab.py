"""WSL paired static Gazebo views; RGB and panoptic truth at identical stamps."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.field import camera,element


def main():
    from gz.transport13 import Node
    from gz.msgs10.image_pb2 import Image
    from gz.msgs10.pose_pb2 import Pose
    from gz.msgs10.boolean_pb2 import Boolean
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--variant',choices=['flat','flat_pbr','textured'],required=True)
    a=p.parse_args();package=a.package.resolve();out=package/('ab_'+a.variant);out.mkdir(exist_ok=False)
    tree=ET.parse(package/('flat.sdf' if a.variant=='flat' else 'flight.sdf'));world=tree.getroot().find('world')
    if a.variant=='flat_pbr':
        cv2.imwrite(str(package/'control_white.png'),np.full((4,4,3),255,np.uint8))
        colors={v.attrib['name']:v.findtext('material/diffuse') for v in ET.parse(package/'flat.sdf').findall('.//visual')}
        for v in world.findall('.//visual'):
            mat=v.find('material')
            if mat is None or mat.find('pbr') is None:continue
            mat.find('pbr/metal/albedo_map').text='control_white.png'
            mat.find('diffuse').text=colors[v.attrib['name']]
            mat.find('ambient').text=colors[v.attrib['name']]
    world.remove(world.find("model[@name='neo_approx']"))
    camera(world,'probe',(0,0,.8,0,.261799388,0),1280,720)
    link=world.find("model[@name='probe']/link");rgb=link.find('sensor');rgb.find('update_rate').text='5'
    segmentation=copy.deepcopy(rgb);segmentation.set('name','instances');segmentation.set('type','segmentation')
    segmentation.find('topic').text='/probe/instances';element(segmentation.find('camera'),'segmentation_type','panoptic');link.append(segmentation)
    # Keep world at package root so relative asset paths remain identical.
    sdf=package/f'probe_{a.variant}.sdf';tree.write(sdf,encoding='utf-8',xml_declaration=True)
    os.environ['GZ_PARTITION']=f'ab_{os.getpid()}';os.environ['GZ_SIM_RESOURCE_PATH']=str(package)
    os.environ['GALLIUM_DRIVER']='d3d12';os.environ['MESA_D3D12_DEFAULT_ADAPTER_NAME']='NVIDIA'
    os.environ['LD_LIBRARY_PATH']='/usr/lib/wsl/lib:'+os.environ.get('LD_LIBRARY_PATH','')
    node=Node();received={'rgb':{},'mask':{}}
    def receive(kind,msg):
        stamp=msg.header.stamp.sec*10**9+msg.header.stamp.nsec
        received[kind][stamp]=msg
        for key in sorted(received[kind])[:-10]:received[kind].pop(key,None)
    node.subscribe(Image,'/uchuva/probe/image',lambda msg:receive('rgb',msg))
    node.subscribe(Image,'/probe/instances/labels_map',lambda msg:receive('mask',msg))
    mission=json.loads((package/'mission.json').read_text());poses=[]
    for c in json.loads((package/'preflight.json').read_text())['selected']:
        for x in (-2.1,.7):
            poses.append({'row':c['row'],'side':c['side'],'position':[x,(c['row']-2.5)*1.8+c['side']*.9,c['height']],
                          'pitch':math.radians(15),'yaw':-c['side']*math.pi/2})
    records=[]
    with (out/'server.log').open('w') as log:
        server=subprocess.Popen(['gz','sim','-s','-r','-v','3',str(sdf)],stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+480
            while not (received['rgb'] and received['mask']):
                if server.poll() is not None:raise RuntimeError('Gazebo exited before first RGB')
                if time.monotonic()>deadline:raise TimeoutError('First RGB/mask initialization timeout')
                time.sleep(.2)
            for index,pose in enumerate(poses):
                request=Pose();request.name='probe';request.position.x,request.position.y,request.position.z=pose['position']
                pitch,yaw=pose['pitch'],pose['yaw'];request.orientation.w=math.cos(pitch/2)*math.cos(yaw/2)
                request.orientation.x=-math.sin(pitch/2)*math.sin(yaw/2);request.orientation.y=math.sin(pitch/2)*math.cos(yaw/2);request.orientation.z=math.cos(pitch/2)*math.sin(yaw/2)
                deadline=time.monotonic()+300
                while time.monotonic()<deadline:
                    ok,response=node.request('/world/uchuva_field/set_pose',request,Pose,Boolean,5000)
                    if ok and response.data:break
                else:raise RuntimeError('Probe pose unavailable')
                # Wait for fresh exposures after service completion, including render propagation.
                baseline=max(received['rgb'],default=0);deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    common=sorted(set(received['rgb'])&set(received['mask']))
                    common=[s for s in common if s>baseline+600_000_000]
                    if common:break
                    if server.poll() is not None:raise RuntimeError('Gazebo exited')
                    time.sleep(.05)
                else:raise RuntimeError('Synchronized RGB and mask missing')
                stamp=common[-1]
                for kind in ('rgb','mask'):
                    msg=received[kind][stamp];array=np.frombuffer(msg.data,np.uint8).reshape(msg.height,msg.step)[:,:msg.width*3].reshape(msg.height,msg.width,3)
                    if not cv2.imwrite(str(out/f'{index:03d}_{kind}.png'),array[:,:,::-1]):raise RuntimeError('PNG save failed')
                records.append({'index':index,'stamp_ns':stamp,**pose});print(f'{a.variant} paired pose {index+1}/{len(poses)}',flush=True)
        finally:
            server.terminate()
            try:server.wait(timeout=15)
            except subprocess.TimeoutExpired:server.kill();server.wait()
            (out/'frames.json').write_text(json.dumps(records,indent=2))

if __name__=='__main__':main()
