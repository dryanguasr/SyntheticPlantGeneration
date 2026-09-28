"""Blender-only visual LOD for an existing morphology-derived Gazebo package."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import bpy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ratio',type=float,default=.12)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not 0 < args.ratio <= 1: raise ValueError('ratio must be in (0,1]')
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'meshes').mkdir()
    manifest=json.loads((args.source/'manifest.json').read_text(encoding='utf-8'))
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    for index,entry in enumerate(manifest['meshes']):
        source=args.source/entry['uri']; target=args.output/entry['uri']
        vertices=[]; faces=[]
        with source.open() as stream:
            for line in stream:
                if line.startswith('v '): vertices.append(tuple(map(float,line.split()[1:4])))
                elif line.startswith('f '): faces.append(tuple(int(v.split('/')[0])-1 for v in line.split()[1:]))
        data=bpy.data.meshes.new('source'); data.from_pydata(vertices,[],faces); data.update()
        obj=bpy.data.objects.new('lod',data); bpy.context.collection.objects.link(obj)
        modifier=obj.modifiers.new('navigation_lod','DECIMATE'); modifier.ratio=args.ratio
        modifier.use_collapse_triangulate=True
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh=evaluated.to_mesh()
        mesh.calc_loop_triangles()
        with target.open('w') as stream:
            stream.write(f'mtllib surface.mtl\nusemtl {target.stem}\no merged\n')
            for vertex in mesh.vertices:
                stream.write('v '+' '.join(f'{v:.8f}' for v in vertex.co)+'\n')
            for i,tri in enumerate(mesh.loop_triangles,1):
                stream.write('vn '+' '.join(f'{v:.7g}' for v in tri.normal)+'\n')
                stream.write('f '+' '.join(f'{v+1}//{i}' for v in tri.vertices)+'\n')
        entry['source_triangles']=entry['triangles']; entry['triangles']=len(mesh.loop_triangles)
        evaluated.to_mesh_clear(); bpy.data.objects.remove(obj,do_unlink=True); bpy.data.meshes.remove(data)
        if index%30==0: print(f'LOD {index+1}/{len(manifest["meshes"])}',flush=True)
    shutil.copy2(args.source/'meshes/surface.mtl',args.output/'meshes/surface.mtl')
    shutil.copy2(args.source/'field.sdf',args.output/'field.sdf')
    manifest['visual_lod']={'method':'Blender collapse decimation','ratio':args.ratio,
        'source_package':str(args.source.resolve()),'status':'engineering_heuristic',
        'markers_and_colliders':'unchanged','organ_mapping':'source_identity_only_after_decimation'}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'triangles':sum(m['triangles'] for m in manifest['meshes'])}),flush=True)


if __name__=='__main__': main()
