"""Actual paused Gazebo screenshots: CAD robot plus unchanged frozen V8 plants."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data):Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--robot-package',type=Path,required=True);parser.add_argument('--plant-package',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--gui-template',type=Path);args=parser.parse_args()
    robot_package,plant_package,out=[p.resolve() for p in (args.robot_package,args.plant_package,args.output)]
    out.mkdir(parents=True,exist_ok=False)
    (out/'capture_source.py').write_bytes(Path(__file__).read_bytes())
    tree=ET.parse(plant_package/'harvest.sdf');world=tree.getroot().find('world')
    original_plants={m.get('name'):ET.tostring(m) for m in world.findall('model') if m.get('name','').startswith(('plant_','fruit_plant_'))}
    for item in list(world.findall('plugin')):
        if 'HarvestSystem' in item.get('name',''):world.remove(item)
    for model in list(world.findall('model')):
        if model.get('name') in ('harvester','collection_bin'):world.remove(model)
    assets={}
    for node in world.iter():
        if node.tag in ('uri','albedo_map','normal_map','roughness_map') and node.text:
            source=(plant_package/node.text).resolve()
            if not source.is_relative_to(plant_package) or not source.is_file():raise ValueError('Unexpected frozen plant resource '+str(source))
            assets[str(source)]=sha(source);node.text=str(source)
    # Reverse only URI resolution to prove model contents/IDs/poses are intact.
    for model in world.findall('model'):
        if model.get('name') in original_plants:
            restored=copy.deepcopy(model)
            for node in restored.iter():
                if node.tag in ('uri','albedo_map','normal_map','roughness_map') and node.text:
                    node.text=Path(node.text).relative_to(plant_package).as_posix()
            if ET.tostring(restored)!=original_plants[model.get('name')]:raise ValueError('Plant XML changed beyond resource relocation')
    robot=ET.parse(robot_package/'model.sdf').getroot().find('model')
    if robot is None:raise ValueError('Robot package must contain top-level model')
    robot.find('static').text='true'
    pose=robot.find('pose').text.split();pose[0]='-1.05';pose[1]='-.25';robot.find('pose').text=' '.join(pose)
    for plugin in list(robot.findall('plugin')):robot.remove(plugin)
    for node in robot.findall('.//mesh/uri'):
        source=(robot_package/node.text).resolve()
        if not source.is_relative_to(robot_package) or not source.is_file():raise ValueError('Unexpected CAD resource '+str(source))
        assets[str(source)]=sha(source);node.text=str(source)
    world.append(robot)
    sdf=out/'inspection.sdf';tree.write(sdf,encoding='unicode',xml_declaration=True)
    gui=out/'gui.config'
    gui.write_text('''<?xml version="1.0"?><window><width>1400</width><height>900</height><menus><drawer default="false"/></menus></window>
    <plugin filename="MinimalScene" name="CAD y V8 - inspeccion estatica"><gz-gui><title>Inspeccion estatica CAD y V8</title><property type="bool" key="showTitleBar">false</property><property type="string" key="state">docked</property></gz-gui><engine>ogre2</engine><scene>scene</scene><ambient_light>.45 .45 .45</ambient_light><background_color>.8 .8 .8</background_color><camera_pose>-2.8 -3.3 2.4 0 .3 1.1</camera_pose></plugin>
    <plugin filename="GzSceneManager" name="Scene manager"><gz-gui><property key="state" type="string">floating</property><property key="width" type="double">5</property><property key="height" type="double">5</property><property key="showTitleBar" type="bool">false</property></gz-gui></plugin>
    <plugin filename="CameraTracking" name="Camera tracking"><gz-gui><property key="state" type="string">floating</property><property key="width" type="double">5</property><property key="height" type="double">5</property><property key="showTitleBar" type="bool">false</property></gz-gui></plugin>
    <plugin filename="Screenshot" name="Screenshot"><gz-gui><property key="state" type="string">floating</property><property key="width" type="double">5</property><property key="height" type="double">5</property><property key="showTitleBar" type="bool">false</property></gz-gui></plugin>''')
    if args.gui_template:
        gui.write_bytes(args.gui_template.resolve().read_bytes())
    metadata={'scope':'Paused native Gazebo graphical inspection. NO harvest, actuation, fruit detachment or dynamic validation.',
              'source_robot_model_sha256':sha(robot_package/'model.sdf'),'source_plant_sdf_sha256':sha(plant_package/'harvest.sdf'),
              'source_plant_manifest_sha256':sha(plant_package/'manifest.json'),'robot_report_sha256':sha(robot_package/'cad_import_report.json'),
              'script_sha256':sha(__file__),'inspection_sdf_sha256':sha(sdf),'gui_sha256':sha(gui),
              'plant_models_unchanged_except_resource_uri':sorted(original_plants),
              'plant_model_xml_sha256':{name:hashlib.sha256(blob).hexdigest() for name,blob in original_plants.items()},
              'derivation':['Removed historical generic robot and collection_bin','Removed harvest world plugin','Inserted exact CAD package model; static inspection; model XY relocated only','Removed CAD controller/observer plugins; no changes to link geometry, joints, internal mounting, materials or inertias','Rebased asset URIs to verified local files; source files unchanged'],
              'cad_model_pose':robot.find('pose').text,'assets_sha256':assets,'captures':[]}
    check=subprocess.run(['gz','sdf','-k',str(sdf)],capture_output=True,text=True,timeout=30)
    (out/'sdf_check.log').write_text(check.stdout+check.stderr)
    if check.returncode:raise RuntimeError('Native SDF check failed')
    env=os.environ.copy();env['GZ_PARTITION']='cad-v8-inspection-'+uuid.uuid4().hex
    env['GALLIUM_DRIVER']='d3d12';env['MESA_D3D12_DEFAULT_ADAPTER_NAME']='NVIDIA';env.pop('LIBGL_ALWAYS_SOFTWARE',None);env.pop('MESA_LOADER_DRIVER_OVERRIDE',None)
    metadata['partition']=env['GZ_PARTITION'];metadata['graphics_environment']={k:env.get(k) for k in ('GALLIUM_DRIVER','MESA_D3D12_DEFAULT_ADAPTER_NAME','DISPLAY','WAYLAND_DISPLAY')}
    os.environ['GZ_PARTITION']=env['GZ_PARTITION']
    dump(out/'metadata.json',metadata)
    from gz.transport13 import Node
    from gz.msgs10.stringmsg_pb2 import StringMsg
    from gz.msgs10.boolean_pb2 import Boolean
    from gz.msgs10.gui_camera_pb2 import GUICamera
    from gz.msgs10.world_stats_pb2 import WorldStatistics
    from gz.msgs10.pose_pb2 import Pose
    node_=Node();processes=[];logs=[];incoming=out/'incoming';incoming.mkdir()
    stats=[]
    def observe_stats(message):
        stats.append({'paused':message.paused,'sim_time':message.sim_time.sec+message.sim_time.nsec*1e-9,'iterations':message.iterations})
    stats_topic='/world/'+world.get('name')+'/stats'
    if not node_.subscribe(WorldStatistics,stats_topic,observe_stats):raise RuntimeError('World statistics subscription failed')
    camera_rows=[]
    def observe_camera(message):
        camera_rows.append({'wall_unix':time.time(),'position':[message.position.x,message.position.y,message.position.z],
                            'quaternion_xyzw':[message.orientation.x,message.orientation.y,message.orientation.z,message.orientation.w]})
    if not node_.subscribe(Pose,'/gui/camera/pose',observe_camera):raise RuntimeError('Camera observation subscription failed')
    def camera(eye,focus):
        d=[b-a for a,b in zip(eye,focus)];yaw=math.atan2(d[1],d[0]);pitch=math.atan2(-d[2],math.hypot(d[0],d[1]))
        request=GUICamera();request.pose.position.x,request.pose.position.y,request.pose.position.z=eye
        q=request.pose.orientation;q.w=math.cos(pitch/2)*math.cos(yaw/2);q.x=-math.sin(pitch/2)*math.sin(yaw/2);q.y=math.sin(pitch/2)*math.cos(yaw/2);q.z=math.cos(pitch/2)*math.sin(yaw/2)
        ok,response=node_.request('/gui/move_to/pose',request,GUICamera,Boolean,10000)
        return ok and response.data
    def capture(name,eye,focus):
        deadline=time.monotonic()+90
        last_request=0
        while True:
            now=time.monotonic()
            d=[b-a for a,b in zip(eye,focus)];yaw=math.atan2(d[1],d[0]);pitch=math.atan2(-d[2],math.hypot(d[0],d[1]))
            expected_q=[-math.sin(pitch/2)*math.sin(yaw/2),math.sin(pitch/2)*math.cos(yaw/2),math.cos(pitch/2)*math.sin(yaw/2),math.cos(pitch/2)*math.cos(yaw/2)]
            if camera_rows and math.dist(camera_rows[-1]['position'],eye)<.001 and abs(sum(a*b for a,b in zip(camera_rows[-1]['quaternion_xyzw'],expected_q)))>1-1e-6:
                break
            if now-last_request>3:
                camera(eye,focus);last_request=now
            if time.monotonic()>deadline:raise RuntimeError('Native camera did not reach the observed requested pose')
            if any(p.poll() is not None for p in processes):raise RuntimeError('Native process exited')
            time.sleep(.1)
        observed_camera=dict(camera_rows[-1])
        time.sleep(1)
        known={p.name for p in incoming.glob('*.png')};before=time.time()
        ok,response=node_.request('/gui/screenshot',StringMsg(data=str(incoming)),StringMsg,Boolean,10000)
        if not ok or not response.data:raise RuntimeError('Native screenshot service rejected request')
        deadline=time.monotonic()+20
        retry_at=time.monotonic()+4
        attempts=1
        while time.monotonic()<deadline:
            for path in incoming.glob('*.png'):
                if path.name not in known:
                    try:
                        blob=path.read_bytes()
                    except OSError:
                        # A just-created PNG on the WSL/NTFS boundary can be
                        # visible before its bytes are readable. Wait for IEND.
                        continue
                    if blob.endswith(bytes.fromhex('0000000049454e44ae426082')):
                        destination=out/(name+'.png');path.rename(destination)
                        metadata['captures'].append({'file':destination.name,'sha256':sha(destination),'eye':eye,'focus':focus,'observed_camera_pose':observed_camera,'wall_request_unix':before,'wall_observed_unix':time.time(),'request_attempts':attempts,'source':'native_gz_gui_screenshot_service','world_paused':True})
                        dump(out/'metadata.json',metadata);print(destination,flush=True);return
            if time.monotonic()>retry_at and attempts<3:
                # Some gz-gui versions apply a new output directory on the
                # first acknowledged request. Retry the same frozen view and
                # the same directory; never accept a pre-existing PNG.
                ok,response=node_.request('/gui/screenshot',StringMsg(data=str(incoming)),StringMsg,Boolean,10000)
                attempts+=1;retry_at=time.monotonic()+4
            time.sleep(.04)
        raise TimeoutError('No complete PNG after native screenshot acknowledgement')
    try:
        for name,command in [('server',['gz','sim','--force-version','8','-s','-v','3',str(sdf)]),('gui',['gz','sim','--force-version','8','-g','-v','3','--gui-config',str(gui)])]:
            log=(out/(name+'.log')).open('w');logs.append(log);processes.append(subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True))
            if name=='server':time.sleep(2)
        deadline=time.monotonic()+75
        while time.monotonic()<deadline:
            if any(p.poll() is not None for p in processes):raise RuntimeError('Native process exited before capture')
            if camera((-2.8,-3.3,2.4),(-.2,1.4,.7)):break
            time.sleep(.5)
        else:raise TimeoutError('Native GUI camera service unavailable')
        time.sleep(3)
        capture('01_overview',(-2.8,-3.3,2.4),(-.2,1.4,.7))
        capture('02_robot',(-1.8,-1.5,1.3),(-.65,-.05,.55))
        capture('03_tool',(-.3,-1.3,1.1),(-.42,-.40,.76))
        if not stats or any(not row['paused'] or row['sim_time']>0 for row in stats):raise RuntimeError('Static inspection unexpectedly advanced physics or lacks pause evidence')
        metadata['status']='CAPTURED_NATIVE_STATIC_INSPECTION'
    except Exception as error:
        metadata['status']='FAILED_NATIVE_CAPTURE'
        metadata['error']=repr(error)
        raise
    finally:
        renderer=Path.home()/'.gz/rendering/ogre2.log'
        if renderer.is_file():
            (out/'ogre2.log').write_bytes(renderer.read_bytes());metadata['renderer_log_sha256']=sha(out/'ogre2.log')
            metadata['renderer_lines']=[line for line in renderer.read_text(errors='replace').splitlines() if any(token in line for token in ('GL_RENDERER','GL_VENDOR','GL_VERSION','Device Name'))]
        for process in reversed(processes):
            if process.poll() is None:os.killpg(process.pid,signal.SIGINT)
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        for log in logs:log.close()
        node_.unsubscribe(stats_topic)
        node_.unsubscribe('/gui/camera/pose')
        metadata['observed_world_statistics']=stats
        metadata['observed_camera_poses']=camera_rows
        metadata['process_exit_codes']=[p.returncode for p in processes];dump(out/'metadata.json',metadata)
    return 0


if __name__=='__main__':raise SystemExit(main())
