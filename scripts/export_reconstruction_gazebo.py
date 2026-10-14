"""Export observed MVS points as oriented visual patches and a separate box proxy.

The patches are a point-cloud visualization, NOT a watertight botanical surface.
No unseen leaves are generated. The collision box deliberately fills all gaps.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_reconstruction.geometry import read_colmap_points
from uchuva_gazebo.field import build_world, box, element, numbers


def ball(world,name,position):
    model=element(world,'model',name=name)
    element(model,'pose',numbers((*position,0,0,0)))
    link=element(model,'link',name='body')
    inertial=element(link,'inertial');element(inertial,'mass',.1)
    inertia=element(inertial,'inertia')
    for tag in ('ixx','iyy','izz'):element(inertia,tag,.0004)
    for tag in ('ixy','ixz','iyz'):element(inertia,tag,0)
    for kind in ('visual','collision'):
        item=element(link,kind,name=kind)
        element(element(element(item,'geometry'),'sphere'),'radius',.1)
    return model


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crop',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--patch-radius',type=float,default=.045)
    args=parser.parse_args()
    if not 0 < args.patch_radius < .2:raise ValueError('Invalid display patch radius')
    args.output.mkdir(parents=True,exist_ok=False);meshes=args.output/'meshes';meshes.mkdir()
    crop=json.loads((args.crop/'crop_manifest.json').read_text())
    values=read_colmap_points(args.crop/'analytical_crop.ply')
    rotation=np.asarray(crop['transform']['rotation']);translation=np.asarray(crop['transform']['translation'])
    xyz=np.column_stack([values[n] for n in ('x','y','z')])@rotation.T+translation
    normals=np.column_stack([values[n] for n in ('nx','ny','nz')])@rotation.T
    colors=np.column_stack([values[n] for n in ('red','green','blue')])
    bins=np.minimum(colors//32,7); ids=bins[:,0].astype(int)*64+bins[:,1].astype(int)*8+bins[:,2]
    records=[];patch_count=0
    for identifier in sorted(set(ids.tolist())):
        indices=np.flatnonzero(ids==identifier);color=colors[indices].mean(axis=0)/255
        path=meshes/f'patches_{identifier:03d}.obj'
        with path.open('w') as stream:
            stream.write('# Oriented MVS samples; display patches only, not an inferred closed surface\n')
            vertex_index=1;normal_index=1
            for index in indices:
                normal=normals[index];length=np.linalg.norm(normal)
                if length<1e-6:continue
                normal=normal/length
                tangent=np.cross(normal,[0,0,1] if abs(normal[2])<.9 else [1,0,0]);tangent/=np.linalg.norm(tangent)
                bitangent=np.cross(normal,tangent)
                for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:
                    point=xyz[index]+args.patch_radius*(a*tangent+b*bitangent)
                    stream.write('v '+numbers(point)+'\n')
                stream.write('vn '+numbers(normal)+'\n')
                for face in [(0,1,2),(0,2,3)]:
                    stream.write('f '+' '.join(f'{vertex_index+j}//{normal_index}' for j in face)+'\n')
                vertex_index+=4;normal_index+=1;patch_count+=1
        records.append(dict(uri=f'meshes/{path.name}',color=[*color.tolist(),1]))
    root=build_world(records,[],{},[]);world=root.find('world');link=world.find("model[@name='field']/link")
    low,high=xyz.min(axis=0),xyz.max(axis=0);size=high-low;center=(low+high)/2
    box(link,'reconstruction_collision',center,size,collision=True)
    sensor=element(link,'sensor',name='proxy_contact',type='contact')
    element(sensor,'always_on','true');element(sensor,'update_rate',100)
    element(sensor,'topic','/uchuva/reconstruction/contacts')
    element(element(sensor,'contact'),'collision','reconstruction_collision')
    element(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
    # A sphere hits the proxy; another falls through an explicitly empty column.
    ball(world,'contact_probe',[center[0],center[1],high[2]+1.0])
    ball(world,'free_probe',[high[0]+1.0,center[1],high[2]+1.0])
    poses={'overview':(10,-12,8,0,.38,2.26),'drone_camera':(0,-9,3.0,0,.08,math.pi/2)}
    for name,pose in poses.items():world.find(f"model[@name='{name}']/pose").text=numbers(pose)
    ET.indent(root);ET.ElementTree(root).write(args.output/'field.sdf',encoding='utf-8',xml_declaration=True)
    config=ET.Element('model');element(config,'name','uchuva_reconstruction_pilot');element(config,'version','0.1')
    element(config,'description','Partial observed MVS foreground; arbitrary display scale; no validated botanical collision')
    element(config,'sdf','model.sdf',version='1.9')
    model_root=ET.Element('sdf',version='1.9')
    import copy
    model_root.append(copy.deepcopy(world.find("model[@name='field']")))
    ET.indent(model_root);ET.ElementTree(model_root).write(args.output/'model.sdf',encoding='utf-8',xml_declaration=True)
    ET.indent(config);ET.ElementTree(config).write(args.output/'model.config',encoding='utf-8',xml_declaration=True)
    manifest=dict(script_version='reconstruction-pilot/0.1',seed=20261001,parameter_preset='pilot_2h',
        source_crop=str(args.crop),source_point_count=len(values),visual_patch_count=patch_count,
        triangles=patch_count*2,materials=len(records),visual_representation='oriented_point_patches_not_reconstructed_surface',
        patch_radius_arbitrary=args.patch_radius,transform=crop['transform'],
        geometry_for_measurement=str(args.crop/'analytical_crop.ply'),
        collision=dict(type='single_AABB',center=center.tolist(),size=size.tolist(),
            limitation='Fills every foliage gap; neither a botanical collision model nor evidence of safe flight'),
        scale_status='arbitrary_display_scale_not_physically_calibrated',camera_poses=poses,
        probes=dict(contact_top=float(high[2]),expected_rest_z=float(high[2]+.1),
                    free_column_x=float(high[0]+1),expected_free_rest_z=.1))
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest))


if __name__=='__main__':main()
