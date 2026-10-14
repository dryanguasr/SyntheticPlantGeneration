"""Blender-only visual simplification, retaining textures and deviation evidence."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import numpy as np


def samples(mesh,limit=1200):
    indices=np.linspace(0,len(mesh.vertices)-1,min(limit,len(mesh.vertices)),dtype=int)
    return [mesh.vertices[int(i)].co.copy() for i in indices]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ratio',type=float,default=.3)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not 0<args.ratio<=1:raise ValueError('Invalid ratio')
    started=time.time();args.output.mkdir(parents=True,exist_ok=False)
    source=args.package.resolve();target=args.output.resolve()
    manifest=json.loads((source/'manifest.json').read_text())
    for name in ['field.sdf','model.sdf','model.config']:
        shutil.copy2(source/name,target/name)
    shutil.copytree(source/'meshes/textures',target/'meshes/textures')
    for path in (source/'meshes').glob('*.mtl'):shutil.copy2(path,target/'meshes'/path.name)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    forward=[];backward=[];before=0;after=0;per_mesh=[]
    for record in manifest['textures']:
        bpy.ops.wm.obj_import(filepath=str(source/record['uri']),forward_axis='Y',up_axis='Z')
        obj=bpy.context.object;mesh=obj.data;mesh.calc_loop_triangles()
        original_count=len(mesh.loop_triangles);before+=original_count
        old_samples=samples(mesh)
        old_bvh=BVHTree.FromPolygons([v.co for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],all_triangles=True)
        modifier=obj.modifiers.new('visual_only_simplification','DECIMATE')
        modifier.ratio=args.ratio;modifier.use_collapse_triangulate=True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        mesh=obj.data;mesh.calc_loop_triangles();after+=len(mesh.loop_triangles)
        new_bvh=BVHTree.FromPolygons([v.co for v in mesh.vertices],[tuple(t.vertices) for t in mesh.loop_triangles],all_triangles=True)
        for point in old_samples:
            hit=new_bvh.find_nearest(point)
            if hit[0] is not None:forward.append(float(hit[3]))
        for point in samples(mesh):
            hit=old_bvh.find_nearest(point)
            if hit[0] is not None:backward.append(float(hit[3]))
        uv=mesh.uv_layers.active
        if uv is None:raise ValueError('UVs lost during simplification')
        path=target/record['uri'];path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('w') as stream:
            stream.write(f'# Visual simplification only; analytical MVS cloud retained separately\nmtllib {path.stem}.mtl\nusemtl photograph\no surface\n')
            for vertex in mesh.vertices:
                point=obj.matrix_world@vertex.co
                stream.write('v '+' '.join(f'{v:.9g}' for v in point)+'\n')
            for loop in uv.data:stream.write(f'vt {loop.uv.x:.9g} {loop.uv.y:.9g}\n')
            normal_matrix=obj.matrix_world.to_3x3().inverted().transposed()
            for vertex in mesh.vertices:
                normal=(normal_matrix@vertex.normal).normalized()
                stream.write('vn '+' '.join(f'{v:.9g}' for v in normal)+'\n')
            for triangle in mesh.loop_triangles:
                stream.write('f '+' '.join(f'{v+1}/{l+1}/{v+1}' for v,l in zip(triangle.vertices,triangle.loops))+'\n')
        record['faces']=len(mesh.loop_triangles)
        per_mesh.append(dict(uri=record['uri'],before=original_count,after=len(mesh.loop_triangles)))
        bpy.data.objects.remove(obj,do_unlink=True)
        print(f'Simplified {path.name}: {original_count} -> {record["faces"]}',flush=True)
    def quantiles(values):
        return dict(zip(['p50','p95','p99','max'],np.quantile(values,[.5,.95,.99,1]).tolist()))
    evidence=dict(script_version='reconstruction-pilot/0.2',seed=20261001,parameter_preset='visual_simplification',
        source_package=str(source),ratio=args.ratio,before_triangles=before,after_triangles=after,
        sampling='Up to 1200 evenly indexed vertices per camera mesh, deterministic; nearest triangle via BVH',
        original_samples_to_simplified=quantiles(forward),simplified_samples_to_original=quantiles(backward),
        sample_counts=[len(forward),len(backward)],units='arbitrary',
        deviation_is_global_bound=False,physical_accuracy=False,analytical_cloud_modified=False,
        meshes=per_mesh,seconds=time.time()-started)
    manifest['visual_representation']='simplified_depth_checked_photo_textured_supported_Poisson_surface'
    manifest['textured_triangles']=after;manifest['simplification']=evidence
    (target/'simplification_report.json').write_text(json.dumps(evidence,indent=2))
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in evidence.items() if k!='meshes'}))


if __name__=='__main__':main()
