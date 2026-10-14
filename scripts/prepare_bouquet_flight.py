"""Twelve close row-face passes with a physical Neo, preserving the full crop."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_gazebo.neo import neo_model
from uchuva_gazebo.field import cylinder_collision


def main():
    p=argparse.ArgumentParser();p.add_argument('--field',type=Path,required=True);p.add_argument('--clearance',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--visual',type=Path,required=True)
    p.add_argument('--conservative-axis-colliders',action='store_true',help='Enclose each main axis in one conservative cylinder, without removing occupied volume')
    a=p.parse_args();audit=json.loads(a.clearance.read_text())
    if not audit['passed']:raise ValueError('Not all row faces passed clearance; do not alter the crop')
    # Marker panels are metric boxes in field-local/world coordinates.
    check=ET.parse(a.field/'field.sdf')
    points=[s for c in audit['selected'] for s in c['samples']]+audit['transfers']
    for visual in check.findall(".//model[@name='field']/link/visual"):
        size=visual.findtext('geometry/box/size')
        if not size or visual.attrib['name']=='soil':continue
        pose=list(map(float,visual.findtext('pose','0 0 0 0 0 0').split()))
        if any(abs(v)>1e-8 for v in pose[3:]):raise ValueError('Rotated panel needs explicit box transform')
        half=[float(v)/2 for v in size.split()]
        for s in points:
            distance=math.sqrt(sum(max(abs(s['p'][i]-pose[i])-half[i],0)**2 for i in range(3)))
            if distance<s['distance']:s.update(distance=distance,obstacle=visual.attrib['name'])
    if min(s['distance'] for s in points)-audit['radius_m']-.02<.18:raise ValueError('Marker box gate blocked')
    audit['marker_boxes_checked']=True
    a.output.mkdir(parents=True,exist_ok=False)
    waypoints=[]
    for c in audit['selected']:
        row,side,z=c['row'],c['side'],c['height'];y=(row-2.5)*1.8+side*.9
        start,end=(-4.8,4.8) if side==-1 else (4.8,-4.8)
        yaw=-side*math.pi/2
        if waypoints:
            previous=waypoints[-1]
            waypoints.append({'position':[start,previous['position'][1],z],'yaw':previous['yaw'],'phase':'outside_height_change'})
        waypoints.extend([{'position':[start,y,z],'yaw':yaw,'phase':f'row_{row}_{side}_entry'},
                          {'position':[end,y,z],'yaw':yaw,'phase':f'row_{row}_{side}_pass'}])
    tree=ET.parse(a.field/'field.sdf');world=tree.getroot().find('world')
    collision_report=[]
    if a.conservative_axis_colliders:
        from collections import defaultdict
        groups=defaultdict(list);link=world.find("model[@name='field']/link")
        for i,c in enumerate(json.loads((a.field/'manifest.json').read_text())['colliders']):
            if '_internode_' in c['source_id']:
                groups[c['source_id'].split('_internode_')[0]].append((i,c))
        for axis,items in groups.items():
            ends=[p for _,c in items for p in (c['start_m'],c['end_m'])]
            x=sum(p[0] for p in ends)/len(ends);y=sum(p[1] for p in ends)/len(ends)
            radius=max(math.hypot(p[0]-x,p[1]-y)+c['radius_m'] for _,c in items for p in (c['start_m'],c['end_m']))+1e-6
            z0=min(p[2]-c['radius_m'] for _,c in items for p in (c['start_m'],c['end_m']))-1e-6
            z1=max(p[2]+c['radius_m'] for _,c in items for p in (c['start_m'],c['end_m']))+1e-6
            for i,c in items:
                # Endpoint spheres and their convex hull enclose each original cylinder.
                for endpoint in (c['start_m'],c['end_m']):
                    assert math.hypot(endpoint[0]-x,endpoint[1]-y)+c['radius_m']<=radius
                    assert z0<=endpoint[2]-c['radius_m'] and z1>=endpoint[2]+c['radius_m']
                link.remove(link.find(f"collision[@name='structural_{i}']"))
            cylinder_collision(link,'enclosing_'+axis.replace(':','_'),(x,y,z0),(x,y,z1),radius)
            for s in points:
                d=math.hypot(max(math.hypot(s['p'][0]-x,s['p'][1]-y)-radius,0),max(z0-s['p'][2],s['p'][2]-z1,0))
                if d<s['distance']:s.update(distance=d,obstacle='enclosing_'+axis)
            collision_report.append({'axis':axis,'source_cylinders':len(items),'radius_m':radius,'z_range':[z0,z1],
                'containment':'all original endpoint spheres enclosed; convex cylinder contains each original capsule'})
        if min(s['distance'] for s in points)-audit['radius_m']-.02<.18:raise ValueError('Conservative collider gate blocked')
    for model in list(world.findall('model')):
        if model.attrib['name'].endswith('camera'):world.remove(model)
    for tag in ('uri','albedo_map','roughness_map'):
        for node in world.findall('.//'+tag):
            if node.text:node.text=Path(os.path.relpath(a.field/node.text,a.output)).as_posix()
    visual=json.loads((a.visual/'visual_manifest.json').read_text());shutil.copytree(a.visual,a.output/'neo_visual')
    assets=[{**m,'uri':'neo_visual/'+m['uri']} for m in visual['meshes']]
    start=waypoints[0];neo=neo_model(start=tuple(start['position']),visual_assets=assets)
    neo.find('pose').text=' '.join(map(str,[*start['position'],0,0,start['yaw']]))
    base=neo.find("link[@name='base_link']")
    base.find("sensor[@name='onboard']/pose").text='.068 0 .005 0 .261799388 0'
    # A declared 60-degree inspection lens, not a calibrated Neo camera.
    base.find("sensor[@name='onboard']/camera/horizontal_fov").text=str(math.pi/3)
    base.find("sensor[@name='chase']/pose").text='-.7 0 .95 0 .9 0'
    for dimension,value in (('width','640'),('height','360')):
        base.find("sensor[@name='chase']/camera/image/"+dimension).text=value
    world.append(neo);world.find('physics/real_time_factor').text='1'
    ET.indent(tree);tree.write(a.output/'flight.sdf',encoding='utf-8',xml_declaration=True)
    mission={'script_version':'bouquet-row-flight/1.0','seed':230926,'parameter_preset':'individual_bouquet_crown_v4',
        'waypoints':waypoints,'speed_limit_m_s':.16,'camera_hfov_deg':60,'camera_pitch_deg':15,
        'camera_status':'ideal inspection lens, not DJI calibration','clearance_file':str(a.clearance.resolve()),
        'textures':'existing procedural albedo and roughness; no detector retraining',
        'detector_sha256':hashlib.sha256((ROOT/'mobile/android/app/src/main/assets/detector.onnx').read_bytes()).hexdigest(),
        'detector_confidence':.25,'additional_nms':False,
        'motion':'dynamic rotor thrust; no pose teleportation'}
    mission['conservative_axis_colliders']=collision_report
    (a.output/'mission.json').write_text(json.dumps(mission,indent=2))
    (a.output/'preflight.json').write_text(json.dumps(audit))
    # Controlled appearance comparison: same geometry and UVs, restore original colors.
    flat=copy.deepcopy(tree);colors={m['uri']:m['color'] for m in json.loads((a.field/'manifest.json').read_text())['meshes']}
    for visual in flat.findall('.//visual'):
        mat=visual.find('material');uri=visual.findtext('geometry/mesh/uri')
        if mat is None or mat.find('pbr') is None:continue
        mat.remove(mat.find('pbr'))
        key=Path(os.path.relpath((a.output/uri).resolve(),a.field.resolve())).as_posix()
        color=' '.join(map(str,colors[key]))
        mat.find('diffuse').text=color;mat.find('ambient').text=color
    flat.write(a.output/'flat.sdf',encoding='utf-8',xml_declaration=True)

if __name__=='__main__':main()
