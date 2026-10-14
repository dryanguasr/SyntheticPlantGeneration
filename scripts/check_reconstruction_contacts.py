"""Real Gazebo contact and empty-column probes; validates only the box proxy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def main():
    from gz.transport13 import Node
    from gz.msgs10.contacts_pb2 import Contacts
    from gz.msgs10.pose_v_pb2 import Pose_V
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--output-name',default='contact_test')
    args=parser.parse_args();package=args.package.resolve()
    if Path(args.output_name).name != args.output_name:raise ValueError('Expected a directory basename')
    output=package/args.output_name;output.mkdir(exist_ok=False)
    manifest=json.loads((package/'manifest.json').read_text())
    os.environ['GZ_PARTITION']=f'reconstruction_contact_{os.getpid()}'
    os.environ['GZ_SIM_RESOURCE_PATH']=str(package)+os.pathsep+os.environ.get('GZ_SIM_RESOURCE_PATH','')
    node=Node();lock=threading.Lock();poses=[];contacts=[]
    def on_pose(message):
        stamp=message.header.stamp.sec+message.header.stamp.nsec/1e9
        for pose in message.pose:
            if pose.name in ('contact_probe','free_probe'):
                with lock:poses.append(dict(time=stamp,name=pose.name,x=pose.position.x,y=pose.position.y,z=pose.position.z))
    def on_contact(message):
        for contact in message.contact:
            with lock:contacts.append(dict(time=message.header.stamp.sec+message.header.stamp.nsec/1e9,
                a=contact.collision1.name,b=contact.collision2.name,depths=list(contact.depth)))
    if not node.subscribe(Pose_V,'/world/uchuva_field/pose/info',on_pose):raise RuntimeError('Pose subscription failed')
    # Harmonic Contact system reports this scoped topic in its server log;
    # the generic <sensor><topic> value is not used by this system.
    contact_topic='/world/uchuva_field/model/field/link/field_link/sensor/proxy_contact/contact'
    if not node.subscribe(Contacts,contact_topic,on_contact):raise RuntimeError('Contact subscription failed')
    start=time.monotonic();server=None
    try:
        with (output/'server.log').open('w') as log:
            server=subprocess.Popen(['gz','sim','-s','-r','--headless-rendering','-v','3',str(package/'field.sdf')],stdout=log,stderr=subprocess.STDOUT)
            while time.monotonic()-start<args.timeout:
                if server.poll() is not None:raise RuntimeError('Gazebo stopped early')
                with lock:
                    latest={name:next((p for p in reversed(poses) if p['name']==name),None) for name in ('contact_probe','free_probe')}
                if all(p and p['time']>=3 for p in latest.values()):break
                time.sleep(.1)
            else:raise TimeoutError('No three-second simulated pose sequence received')
    finally:
        if server:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()
        with lock:
            (output/'poses.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in poses))
            (output/'contacts.jsonl').write_text(''.join(json.dumps(c)+'\n' for c in contacts))
    latest={name:next((p for p in reversed(poses) if p['name']==name),None) for name in ('contact_probe','free_probe')}
    contact_hits=[c for c in contacts if 'contact_probe' in c['a']+' '+c['b']]
    free_hits=[c for c in contacts if 'free_probe' in c['a']+' '+c['b']]
    expected=manifest['probes']
    contact_pass=bool(contact_hits and latest['contact_probe'] and abs(latest['contact_probe']['z']-expected['expected_rest_z'])<.03)
    free_pass=bool(contacts and latest['free_probe'] and abs(latest['free_probe']['z']-.1)<.03 and not free_hits)
    result=dict(script_version='reconstruction-pilot/0.1',seed=20261001,parameter_preset='pilot_2h',
        wall_seconds=time.monotonic()-start,latest_poses=latest,contact_messages=len(contacts),contact_topic=contact_topic,
        contact_probe_hits=len(contact_hits),free_probe_target_hits=len(free_hits),
        contact_on_box_proxy='passed' if contact_pass else 'failed',
        empty_vertical_column='passed' if free_pass else 'failed',
        expected=expected,physical_scale='arbitrary_display_only',
        limitation='Tests only a solid bounding box and an outside vertical column; no foliage gaps, branch contacts or safe flight validated')
    (output/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    return 0 if contact_pass and free_pass else 1


if __name__=='__main__':raise SystemExit(main())
