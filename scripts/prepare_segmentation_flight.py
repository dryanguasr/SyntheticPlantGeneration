"""Prepare safe exterior whole-crown passes with native Gazebo instance masks."""
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
from uchuva_gazebo.neo import neo_model,LENGTH,WIDTH,HEIGHT
from uchuva_lsystem.segmentation_cycles import VERSION,write,sha,check_deadline,class_for_grade


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--field',type=Path,required=True);p.add_argument('--full-mesh-field',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tight-framing',action='store_true')
    p.add_argument('--target-only',action='store_true')
    p.add_argument('--continuous-turn',action='store_true')
    p.add_argument('--sensor-rate',type=int,default=5)
    a=p.parse_args();check_deadline(a.root);a.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((a.field/'manifest.json').read_text())
    if not manifest.get('individual_calyces'):raise ValueError('Individual calyces required')
    full=json.loads((a.full_mesh_field/'manifest.json').read_text())
    source_payload=json.loads(Path(full['source_input']).read_text())
    roles=source_payload.get('instance_roles',{})
    target_ids={key for key,value in roles.items() if value['role']=='target'}
    if a.target_only and len(target_ids)!=6:raise ValueError('Explicit six-plant target row required')
    if full['source_sha256']!=manifest['source_sha256']:raise ValueError('Full meshes and visual source differ')
    lo=[float('inf')]*3;hi=[-float('inf')]*3;plant_bounds={};plant_hulls={}
    if a.tight_framing:
        hull_record=json.loads((a.full_mesh_field/'framing_hulls.json').read_text())
        if hull_record['manifest_sha256']!=sha(a.full_mesh_field/'manifest.json'):
            raise ValueError('Framing hull source changed')
        plant_hulls=hull_record['plants']
    for mesh in full['meshes']:
        stem=Path(mesh['uri']).stem
        identifier='_'.join(stem.split('_')[:2]) if stem.startswith('plant_') else None
        if identifier:plant_bounds.setdefault(identifier,[[float('inf')]*3,[-float('inf')]*3])
        with (a.full_mesh_field/mesh['uri']).open() as f:
            for line in f:
                if line.startswith('v '):
                    point=list(map(float,line.split()[1:4]))
                    for d in range(3):lo[d]=min(lo[d],point[d]);hi[d]=max(hi[d],point[d])
                    if identifier:
                        for d in range(3):
                            plant_bounds[identifier][0][d]=min(plant_bounds[identifier][0][d],point[d])
                            plant_bounds[identifier][1][d]=max(plant_bounds[identifier][1][d],point[d])
    # Ground is audited separately, so giant terrain extents are not obstacles.
    # Marker rectangles are also enclosed explicitly by their true dimensions.
    for marker in manifest['markers']:
        for d,value in enumerate(marker['center_world_m']):
            half=marker['side_m']/2+.02;lo[d]=min(lo[d],value-half);hi[d]=max(hi[d],value+half)
    all_bounds=[list(lo),list(hi)]
    if a.target_only:
        lo=[min(plant_bounds[k][0][d] for k in target_ids) for d in range(3)]
        hi=[max(plant_bounds[k][1][d] for k in target_ids) for d in range(3)]
    radius=math.sqrt(LENGTH**2+WIDTH**2+HEIGHT**2)/2
    xleft=min(-5.8,lo[0]-.7);xright=max(5.8,hi[0]+.7)
    marker_centers={}
    for marker in manifest['markers']:
        if a.target_only and marker['plant_id'] not in target_ids:continue
        marker_centers.setdefault(marker['plant_id'],[]).append(marker['center_world_m'])
    centers={key:[sum(p[d] for p in points)/len(points) for d in range(3)] for key,points in marker_centers.items()}
    row_y=sorted(set(round(point[1],4) for point in centers.values()))
    front=min(row_y[0]-3.5,lo[1]-.7);back=max(row_y[-1]+3.5,hi[1]+.7)
    z=.7;waypoints=[];framing=[]
    for row,side,y,start,end in [(0,-1,front,xleft,xright),(len(row_y)-1,1,back,xright,xleft)]:
        stations=sorted([(point[0],identifier) for identifier,point in centers.items()
                         if abs(point[1]-row_y[row])<.001],reverse=side==1)
        row_stations=[]
        for x,identifier in stations:
            lower,upper=plant_bounds[identifier]
            points=(list(plant_hulls[identifier]) if a.tight_framing else
                    [[px,py,pz] for px in (lower[0],upper[0]) for py in (lower[1],upper[1]) for pz in (lower[2],upper[2])])
            for marker in manifest['markers']:
                if marker['plant_id']==identifier:
                    center=marker['center_world_m'];half=marker['side_m']/2
                    points.extend([[center[0]+sx*half,center[1],center[2]+sz*half] for sx in (-1,1) for sz in (-1,1)])
            sx,sy,sz=x,y,z
            if a.tight_framing:
                from uchuva_lsystem.camera_framing import fit_level_camera
                fit=fit_level_camera(points,side=side,margin=.07)
                sx,sy,sz=fit['position']
                sy+=side*.068;sz-=.005  # Body position from camera optical center.
                sy=min(sy,lo[1]-.35) if side<0 else max(sy,hi[1]+.35)
            projections=[]
            for px,py,pz in points:
                depth=abs(py-sy)-.068
                u=.5+(px-sx)/(2*depth*math.tan(math.pi/6))
                v=.5+(pz-sz-.005)/(2*depth*math.tan(math.pi/6)*720/1280)
                projections.append([u,v,depth])
            complete=all(.05<=u<=.95 and .05<=v<=.95 and depth>0 for u,v,depth in projections)
            framing.append({'plant_id':identifier,'whole_mesh_and_markers_with_5_percent_margin':complete,'projected_bounds_points':projections})
            if not complete:raise ValueError(f'Whole-plant framing failed: {identifier}')
            row_stations.append({'position':[sx,sy,sz],'yaw':-side*math.pi/2,'phase':f'row_{row}_{side}_station_{x}',
                              'target_plant_id':identifier})
        first=row_stations[0]['position'];last=row_stations[-1]['position']
        if waypoints:
            if a.continuous_turn:
                from uchuva_gazebo.continuous_row import terminal_arc
                identifier=stations[0][1];center=centers[identifier]
                points=plant_hulls[identifier]
                extent=max(math.hypot(p[0]-center[0],p[1]-center[1]) for p in points)
                vertical=max(abs(p[2]-first[2]-.005) for p in points)
                arc_radius=max(abs(first[1]-center[1]),abs(waypoints[-1]['position'][1]-center[1]),
                    extent+vertical/(math.tan(math.pi/6)*720/1280*.9)+.15,
                    extent+extent/(math.tan(math.pi/6)*.9)+.15)
                waypoints.extend(terminal_arc(center,arc_radius,first[2],identifier))
            else:waypoints.append({'position':[start,first[1],first[2]],'yaw':0,'phase':'outside_transfer'})
        waypoints.append({'position':list(first),'yaw':-side*math.pi/2,'phase':f'row_{row}_{side}_entry',
                          'target_plant_id':stations[0][1]})
        waypoints.extend(row_stations)
        if not a.continuous_turn:
            waypoints.append({'position':[end,last[1],last[2]],'yaw':-side*math.pi/2,'phase':f'row_{row}_{side}_pass'})
    if a.continuous_turn:
        from uchuva_gazebo.continuous_row import inward_yaw
        from uchuva_gazebo.segmentation_evaluation import whole_plant_in_frame
        for point in waypoints:
            if point.get('target_plant_id'):
                identifier=point['target_plant_id'];point['look_at_world_m']=centers[identifier]
                point['yaw']=inward_yaw(point['position'],point['look_at_world_m'])
                yaw=point['yaw'];quaternion=[0,0,math.sin(yaw/2),math.cos(yaw/2)]
                markers=[m for m in manifest['markers'] if m['plant_id']==identifier]
                complete=whole_plant_in_frame(plant_bounds[identifier],markers,point['position'],quaternion,
                    hull_points=plant_hulls[identifier],margin=.05)
                if not complete:raise ValueError(f'Inward orientation loses whole plant: {point["phase"]}')
                point['planned_whole_plant_with_margin']=complete
    samples=[]
    for left,right in zip(waypoints,waypoints[1:]):
        start,end=left['position'],right['position'];distance=math.dist(start,end)
        for j in range(max(2,math.ceil(distance/.04)+1)):
            u=j/max(1,math.ceil(distance/.04));point=[v+(w-v)*u for v,w in zip(start,end)]
            if a.target_only:
                from uchuva_gazebo.continuous_row import obstacle_distance
                bound=obstacle_distance(point,list(plant_bounds.values()),full['colliders'])
            else:bound=math.sqrt(sum(max(lo[d]-point[d],0,point[d]-hi[d])**2 for d in range(3)))
            samples.append({'p':point,'distance':min(bound,point[2]),'obstacle':'individual_obstacles_or_ground' if a.target_only else 'full_mesh_field_envelope_or_ground'})
    minimum=min(s['distance'] for s in samples)-radius-.02
    if minimum<.18:raise ValueError('Exterior route clearance failed')
    tree=ET.parse(a.field/'field.sdf');world=tree.getroot().find('world')
    if a.sensor_rate==30:
        # Twenty integration steps per exposure; avoid accumulating a 34 ms
        # sensor period when using the historical 2 ms physics step.
        world.find('physics/max_step_size').text=str(1/600)
    source=json.loads(Path(manifest['source_input']).read_text())
    grades={}
    def visit(axes,plant_id):
        for axis in axes:
            for node in axis['nodes']:
                unit=node.get('reproductive_unit')
                if unit and unit.get('synthetic_reference_grade') is not None:
                    grades[plant_id+':'+unit['id']]=unit['synthetic_reference_grade']
            visit(axis['child_axes'],plant_id)
    for plant_id,plant in source['plants'].items():visit(plant['axes'],plant_id)
    inventory=json.loads((a.field/'inventory.json').read_text())
    for organ in inventory['calyces']:
        cls=class_for_grade(grades[organ['reproductive_id']])
        plant_index=int(organ['plant_id'].split('_')[-1])
        label=1+3*plant_index+cls
        world.find(f"model[@name='{organ['model_name']}']/plugin/label").text=str(label)
        organ.update(class_id=cls,semantic_label=label,role=roles.get(organ['plant_id'],{}).get('role','target'))
    for model in list(world.findall('model')):
        if model.attrib['name'].endswith('camera'):world.remove(model)
    for tag in ('uri','albedo_map','roughness_map','normal_map'):
        for node in world.findall('.//'+tag):
            if node.text and not '://' in node.text:
                node.text=Path(os.path.relpath((a.field/node.text).resolve(),a.output.resolve())).as_posix()
    neo=neo_model(start=tuple(waypoints[0]['position']))
    neo.find('pose').text=' '.join(map(str,[*waypoints[0]['position'],0,0,waypoints[0]['yaw']]))
    base=neo.find("link[@name='base_link']");camera=base.find("sensor[@name='onboard']")
    camera.find('pose').text='.068 0 .005 0 0 0'
    camera.find('camera/horizontal_fov').text=str(math.pi/3)
    camera.find('update_rate').text=str(a.sensor_rate)
    segmentation=copy.deepcopy(camera);segmentation.set('name','instances');segmentation.set('type','segmentation')
    segmentation.find('topic').text='/neo/instances'
    ET.SubElement(segmentation.find('camera'),'segmentation_type').text='panoptic';base.append(segmentation)
    world.append(neo);ET.indent(tree);tree.write(a.output/'flight.sdf',encoding='utf-8',xml_declaration=True)
    common=dict(script_version=VERSION,seed=manifest['seed'],parameter_preset=manifest['parameter_preset'])
    write(a.output/'mission.json',{**common,'waypoints':waypoints,'speed_limit_m_s':.16,
        'sensor_rate_hz':a.sensor_rate,'retain_all_sensor_pairs':a.sensor_rate==30,
        'target_plant_ids':sorted(target_ids) if a.target_only else sorted(centers),
        'orientation_policy':'continuous_inward_look_at' if a.continuous_turn else 'fixed_waypoint_yaw',
        'initial_hold_seconds':7 if a.tight_framing else 3,
        'station_hold_seconds':2 if a.tight_framing else 0,
        'framing_policy':'tight_plant_and_marker_user_revision' if a.tight_framing else 'original_wide',
        'camera_hfov_deg':60,'camera_pitch_deg':0,'resolution':[1280,720],
        'selected_faces':[{'row':0,'side':-1},{'row':len(row_y)-1,'side':1}],
        'unavailable_faces':max(0,2*len(row_y)-2),'bush_view_stations':len(framing),
        'coverage_note':'Two exterior row faces; bush view stations are counted separately from row faces',
        'source_morphology_sha256':manifest['source_sha256'],'flight_masks_evaluator_only':True})
    write(a.output/'preflight.json',{**common,'passed':True,'radius_m':radius,'selected':[],
        'transfers':samples,'minimum_margin_m':minimum,'full_mesh_bounds_m':all_bounds,
        'clearance_policy':'individual_plant_boxes_and_support_capsules' if a.target_only else 'whole_field_envelope',
        'station_framing':framing,'plant_mesh_bounds_m':plant_bounds,'markers':manifest['markers'],
        'plant_mesh_hulls_m':plant_hulls,
        'framing_basis':'full individual mesh AABB and both markers; ideal level camera; actual flight requires verification',
        'full_mesh_manifest_sha256':sha(a.full_mesh_field/'manifest.json')})
    write(a.output/'inventory.json',inventory)
    write(a.output/'provenance.json',{**common,'visual_field':str(a.field.resolve()),
        'manifest_sha256':sha(a.field/'manifest.json'),'input':manifest['source_input']})
    print(json.dumps({'margin_m':minimum,'faces':2,'bounds':[lo,hi]}))


if __name__=='__main__':main()
