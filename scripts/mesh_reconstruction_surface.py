"""Reconstruct a supported, photograph-textured surface from COLMAP MVS.

Poisson interpolates between observations. Distance and edge filters remove
unsupported extrapolation; neither the retained surface nor its gaps are ground
truth plant anatomy. Requires the explicitly authorized isolated PyCOLMAP setup.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import sys
import time
import xml.etree.ElementTree as ET

import numpy as np
import pycolmap
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_reconstruction.geometry import read_colmap_points
from uchuva_gazebo.field import build_world, box, element, numbers
from export_reconstruction_gazebo import ball


def read_poisson_mesh(path):
    """Read COLMAP's triangle PLY, validating its actual declared layout."""
    with path.open('rb') as stream:
        header = []
        while True:
            raw = stream.readline()
            if not raw:
                raise ValueError('Incomplete PLY header')
            line = raw.decode('ascii').strip()
            header.append(line)
            if line == 'end_header':
                break
        if 'format binary_little_endian 1.0' not in header:
            raise ValueError('Expected binary little-endian Poisson mesh')
        vertex_count = int(next(x.split()[2] for x in header if x.startswith('element vertex ')))
        face_count = int(next(x.split()[2] for x in header if x.startswith('element face ')))
        types = {'float': '<f4', 'double': '<f8', 'uchar': 'u1'}
        properties = header[header.index(f'element vertex {vertex_count}')+1:header.index(f'element face {face_count}')]
        dtype = [(line.split()[2], types[line.split()[1]]) for line in properties if line.startswith('property ')]
        vertices = np.fromfile(stream, dtype=dtype, count=vertex_count)
        if len(vertices) != vertex_count:
            raise ValueError('Truncated mesh vertices')
        if 'property list int int vertex_indices' not in header:
            raise ValueError('Unexpected face layout')
        faces = np.fromfile(stream, dtype='<i4', count=face_count*4).reshape(-1, 4)
        if len(faces) != face_count or not np.all(faces[:, 0] == 3):
            raise ValueError('Expected complete triangular faces')
        faces = faces[:, 1:]
        if np.any(faces < 0) or np.any(faces >= vertex_count):
            raise ValueError('Invalid face index')
        return np.column_stack([vertices[n] for n in ('x', 'y', 'z')]), faces


def read_depth(path):
    with path.open('rb') as stream:
        fields = []
        for _ in range(3):
            field = bytearray()
            while True:
                char = stream.read(1)
                if not char:
                    raise ValueError('Truncated depth header')
                if char == b'&':
                    break
                field.extend(char)
            fields.append(int(field))
        width, height, channels = fields
        return np.fromfile(stream, '<f4').reshape((width, height, channels), order='F').transpose(1, 0, 2).squeeze()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crop', type=Path, required=True)
    parser.add_argument('--mvs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--depth', type=int, default=10)
    parser.add_argument('--trim', type=float, default=5)
    parser.add_argument('--support-distance', type=float, default=.045)
    parser.add_argument('--max-edge', type=float, default=.15)
    parser.add_argument('--reuse-mesh', type=Path)
    parser.add_argument('--auto-frame', action='store_true', help='Frame larger crops using their observed bounding box')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    crop = json.loads((args.crop/'crop_manifest.json').read_text())
    cloud = read_colmap_points(args.crop/'analytical_crop.ply')
    observed = np.column_stack([cloud[n] for n in ('x','y','z')])
    mesh_path = args.output/'poisson_raw.ply'
    options = pycolmap.PoissonMeshingOptions()
    options.depth, options.trim, options.num_threads = args.depth, args.trim, 6
    if args.reuse_mesh:
        shutil.copy2(args.reuse_mesh, mesh_path)
    else:
        pycolmap.poisson_meshing(args.crop/'analytical_crop.ply', mesh_path, options)
    xyz, faces = read_poisson_mesh(mesh_path)
    raw_faces = len(faces)
    tree = cKDTree(observed)
    vertex_distance = tree.query(xyz, workers=4)[0]
    centers = xyz[faces].mean(axis=1)
    center_distance = tree.query(centers, workers=4)[0]
    edges = np.stack([xyz[faces[:,i]]-xyz[faces[:,(i+1)%3]] for i in range(3)])
    longest_edge = np.linalg.norm(edges,axis=2).max(axis=0)
    keep = ((vertex_distance[faces].max(axis=1) <= args.support_distance)
            & (center_distance <= args.support_distance) & (longest_edge <= args.max_edge))
    faces = faces[keep]
    if not len(faces):
        raise ValueError('No supported triangles remain')
    centers = xyz[faces].mean(axis=1)
    normals = np.cross(xyz[faces[:,1]]-xyz[faces[:,0]], xyz[faces[:,2]]-xyz[faces[:,0]])
    normals /= np.maximum(np.linalg.norm(normals,axis=1,keepdims=True), 1e-12)
    model = pycolmap.Reconstruction(args.mvs/'sparse')
    images = sorted((model.images[i] for i in model.reg_image_ids()), key=lambda image:image.name)
    best_score = np.full(len(faces), -np.inf)
    best_camera = np.full(len(faces), -1, dtype=int)
    projections = []
    # Select a camera only when its MVS depth agrees with each face center.
    for index, image in enumerate(images):
        camera = model.cameras[image.camera_id]
        if camera.model_name != 'PINHOLE':
            raise ValueError('Expected undistorted PINHOLE camera')
        fx, fy, cx, cy = camera.params
        pose = image.cam_from_world().matrix()
        camera_xyz = xyz @ pose[:,:3].T + pose[:,3]
        uv = camera_xyz[:,:2] / np.maximum(camera_xyz[:,2,None],1e-9) * [fx,fy] + [cx,cy]
        projections.append(uv)
        center_xyz = centers @ pose[:,:3].T + pose[:,3]
        center_uv = center_xyz[:,:2] / np.maximum(center_xyz[:,2,None],1e-9) * [fx,fy] + [cx,cy]
        valid_vertex = ((camera_xyz[:,2]>0) & (uv[:,0]>=1) & (uv[:,0]<camera.width-1)
                        & (uv[:,1]>=1) & (uv[:,1]<camera.height-1))
        valid = valid_vertex[faces].all(axis=1)
        depth = read_depth(args.mvs/'stereo/depth_maps'/f'{image.name}.geometric.bin')
        pix = np.rint(center_uv * [depth.shape[1]/camera.width, depth.shape[0]/camera.height]).astype(int)
        pix[:,0] = np.clip(pix[:,0],0,depth.shape[1]-1)
        pix[:,1] = np.clip(pix[:,1],0,depth.shape[0]-1)
        measured = depth[pix[:,1],pix[:,0]]
        residual = np.abs(measured-center_xyz[:,2])
        valid &= (measured>0) & (residual < np.maximum(.035, .01*center_xyz[:,2]))
        direction = image.projection_center()-centers
        distance = np.linalg.norm(direction,axis=1)
        facing = np.abs((normals*direction).sum(axis=1)/np.maximum(distance,1e-9))
        score = facing/np.maximum(distance**2,1e-9)
        update = valid & (score>best_score)
        best_camera[update], best_score[update] = index, score[update]
    supported_faces = len(faces)
    # Untexturable geometry is retained separately, not painted from an occluder.
    np.savez_compressed(args.output/'supported_surface.npz', xyz=xyz, faces=faces,
                        camera_assignment=best_camera, vertex_support_distance=vertex_distance)
    rotation = np.asarray(crop['transform']['rotation'])
    translation = np.asarray(crop['transform']['translation'])
    transformed = xyz @ rotation.T + translation
    vertex_normals = np.zeros_like(xyz)
    for corner in range(3):
        np.add.at(vertex_normals, faces[:,corner], normals)
    vertex_normals /= np.maximum(np.linalg.norm(vertex_normals,axis=1,keepdims=True),1e-12)
    vertex_normals = vertex_normals @ rotation.T
    package = args.output/'gazebo'
    meshes = package/'meshes'
    textures = meshes/'textures'
    textures.mkdir(parents=True)
    records = []
    for index in sorted(set(best_camera.tolist())-{-1}):
        image = images[index]
        camera = model.cameras[image.camera_id]
        selected_faces = faces[best_camera==index]
        used, remap = np.unique(selected_faces, return_inverse=True)
        local_faces = remap.reshape(-1,3)+1
        path = meshes/f'surface_{index:03d}.obj'
        texture_name = f'camera_{index:03d}.jpg'
        mtl_name = f'surface_{index:03d}.mtl'
        (meshes/mtl_name).write_text('newmtl photograph\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nmap_Kd textures/'+texture_name+'\n')
        with path.open('w') as stream:
            stream.write('# Supported Poisson surface; photograph UVs with depth agreement\n')
            stream.write(f'mtllib {mtl_name}\nusemtl photograph\no surface\n')
            for point in transformed[used]:
                stream.write('v '+numbers(point)+'\n')
            for u,v in projections[index][used]/[camera.width,camera.height]:
                stream.write(f'vt {u:.8f} {1-v:.8f}\n')
            for normal in vertex_normals[used]:
                stream.write('vn '+numbers(normal)+'\n')
            for face in local_faces:
                stream.write('f '+' '.join(f'{i}/{i}/{i}' for i in face)+'\n')
        texture = textures/texture_name
        shutil.copy2(args.mvs/'images'/image.name, texture)
        records.append(dict(uri=f'meshes/{path.name}',color=[1,1,1,1],
                            texture=f'meshes/textures/{texture.name}',camera=image.name,faces=len(selected_faces)))
    root = build_world(records, [], {}, [])
    world = root.find('world')
    link = world.find("model[@name='field']/link")
    visuals = [v for v in link.findall('visual') if v.find('geometry/mesh') is not None]
    if len(visuals) != len(records):
        raise ValueError('Unexpected visual count')
    for visual, record in zip(visuals,records):
        mat = visual.find('material')
        metal = element(element(mat,'pbr'),'metal')
        element(metal,'albedo_map',record['texture'])
        element(metal,'roughness',1)
        element(metal,'metalness',0)
    observed_display = observed @ rotation.T + translation
    low, high = observed_display.min(axis=0), observed_display.max(axis=0)
    center, size = (low+high)/2, high-low
    box(link,'reconstruction_collision',center,size,collision=True)
    sensor=element(link,'sensor',name='proxy_contact',type='contact')
    element(sensor,'always_on','true');element(sensor,'update_rate',100)
    element(element(sensor,'contact'),'collision','reconstruction_collision')
    element(world,'plugin',filename='gz-sim-contact-system',name='gz::sim::systems::Contact')
    ball(world,'contact_probe',[center[0],center[1],high[2]+1])
    ball(world,'free_probe',[high[0]+1,center[1],high[2]+1])
    poses={'overview':(10,-12,8,0,.38,2.26),'drone_camera':(0,-9,3,0,.08,math.pi/2)}
    if args.auto_frame:
        distance=max(9.0,1.5*size[2]+size[1]/2,.95*size[0]+size[1]/2)
        poses={'overview':(distance,-distance,center[2]+distance*.5,0,.34,2.35619449),
               'drone_camera':(center[0],-distance,center[2],0,0,math.pi/2)}
    for name,pose in poses.items():
        world.find(f"model[@name='{name}']/pose").text=numbers(pose)
    ET.indent(root)
    ET.ElementTree(root).write(package/'field.sdf',encoding='utf-8',xml_declaration=True)
    model_root=ET.Element('sdf',version='1.9')
    model_root.append(copy.deepcopy(world.find("model[@name='field']")))
    ET.indent(model_root)
    ET.ElementTree(model_root).write(package/'model.sdf',encoding='utf-8',xml_declaration=True)
    config=ET.Element('model')
    element(config,'name','uchuva_observed_surface_pilot')
    element(config,'version','0.2')
    element(config,'sdf','model.sdf',version='1.9')
    element(config,'description','Partial photo-textured supported Poisson surface; uncalibrated scale')
    ET.indent(config)
    ET.ElementTree(config).write(package/'model.config',encoding='utf-8',xml_declaration=True)
    report=dict(script_version='reconstruction-pilot/0.2',seed=20261001,parameter_preset='pilot_improvement',
        source_crop=str(args.crop),source_mvs=str(args.mvs),source_points=len(observed),
        poisson_options=options.todict() if not args.reuse_mesh else None,
        reused_mesh=str(args.reuse_mesh) if args.reuse_mesh else None,
        raw_vertices=len(xyz),raw_triangles=raw_faces,
        supported_triangles=supported_faces,textured_triangles=int((best_camera>=0).sum()),
        rejected_untexturable_triangles=int((best_camera<0).sum()),textures=records,
        support_distance_arbitrary=args.support_distance,max_edge_arbitrary=args.max_edge,
        texture_depth_tolerance='max(0.035 arbitrary units, 1 percent camera depth)',
        parameter_provenance='engineering_heuristic',transform=crop['transform'],
        visual_representation='depth_checked_photo_textured_supported_Poisson_surface',
        limitations=['partial foreground crop; not a complete plant',
                     'Poisson interpolates observed samples; surfaces are not validated leaf anatomy',
                     'no physical scale or gravity calibration',
                     'single AABB collision fills foliage gaps; not botanical collision'],
        collision=dict(type='single_AABB',center=center.tolist(),size=size.tolist()),
        camera_poses=poses,auto_frame=args.auto_frame,
        probes=dict(contact_top=float(high[2]),expected_rest_z=float(high[2]+.1),
                    free_column_x=float(high[0]+1),expected_free_rest_z=.1),
        seconds=time.time()-started)
    (args.output/'surface_report.json').write_text(json.dumps(report,indent=2))
    (package/'manifest.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='textures'}),flush=True)


if __name__=='__main__':
    main()
