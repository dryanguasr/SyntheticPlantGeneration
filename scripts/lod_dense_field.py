"""Blender per-organ visual LOD: keep all organ IDs, materials and collision geometry."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import bpy

def chunks(path):
    name=None;vertices=[];faces=[];uvs=[];face_uvs=[];offset=0;uv_offset=0
    with path.open() as stream:
        for line in stream:
            if line.startswith('# source '):
                if name is not None:
                    yield name,vertices,faces,face_uvs
                    offset+=len(vertices)
                    uv_offset+=len(uvs)
                name=line.strip()[9:];vertices=[];faces=[];uvs=[];face_uvs=[]
            elif line.startswith('v '):vertices.append(tuple(map(float,line.split()[1:4])))
            elif line.startswith('vt '):uvs.append(tuple(map(float,line.split()[1:3])))
            elif line.startswith('f '):
                tokens=[v.split('/') for v in line.split()[1:]]
                faces.append(tuple(int(v[0])-1-offset for v in tokens))
                face_uvs.append([uvs[int(v[1])-1-uv_offset] for v in tokens] if all(len(v)>1 and v[1] for v in tokens) else None)
    if name is not None:yield name,vertices,faces,face_uvs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ratio',type=float,default=.2)
    p.add_argument('--minimum',type=int,default=128)
    p.add_argument('--preserve-calyces',action='store_true',help='Keep target calyx triangles unchanged')
    p.add_argument('--fit-bounds',action='store_true',help='Restore context AABBs after bounded visual decimation; requires silhouette review')
    p.add_argument('--background-roles',type=Path,help='Explicit instance_roles contract: simplify only background; copy target assets byte-for-byte')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.output.mkdir(parents=True,exist_ok=False);(a.output/'meshes').mkdir()
    manifest=json.loads((a.source/'manifest.json').read_text());bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
    eligible=None
    if a.background_roles:
        roles=json.loads(a.background_roles.read_text(encoding='utf-8'))['instance_roles']
        mesh_roles={}
        for organ in manifest['organs']:
            role='support' if organ['plant_id']=='support' else roles[organ['plant_id']]['role']
            if role not in ('target','background','support'):raise ValueError('Unknown plant role')
            for uri in organ['meshes']:mesh_roles.setdefault(uri,set()).add(role)
        # Shared support/tie meshes can reference several roles. Copy them
        # unchanged; only exclusively background assets are eligible.
        eligible={uri for uri,roleset in mesh_roles.items() if roleset=={'background'}}
    from mathutils import Vector
    diagnostics=[]
    for index,entry in enumerate(manifest['meshes']):
        target=a.output/entry['uri'];offset=normal=total=uv_index=0
        if eligible is not None and entry['uri'] not in eligible:
            shutil.copy2(a.source/entry['uri'],target)
            shutil.copy2((a.source/entry['uri']).with_suffix('.mtl'),target.with_suffix('.mtl'))
            for name,vertices,faces,face_uvs in chunks(a.source/entry['uri']):
                diagnostics.append({'mesh':entry['uri'],'object':name,'source_triangles':len(faces),
                    'triangles':len(faces),'decimated':False,'target_copied_exactly':True})
            continue
        with target.open('w') as out:
            out.write(f'mtllib {target.stem}.mtl\nusemtl {target.stem}\no merged\n')
            for name,vertices,faces,face_uvs in chunks(a.source/entry['uri']):
                original=len(faces);drift=0;accepted=False;fitted=False;unfitted_drift=0
                if original>2*a.minimum and not (a.preserve_calyces and 'calyx' in name):
                    data=bpy.data.meshes.new('organ');data.from_pydata(vertices,[],faces);data.update()
                    if all(v is not None for v in face_uvs):
                        layer=data.uv_layers.new(name='organ_uv')
                        for polygon,coords in zip(data.polygons,face_uvs):
                            for loop,uv in zip(polygon.loop_indices,coords):layer.data[loop].uv=uv
                    obj=bpy.data.objects.new('organ',data);bpy.context.collection.objects.link(obj)
                    dec=obj.modifiers.new('visual_lod','DECIMATE');dec.ratio=max(a.ratio,a.minimum/original);dec.use_collapse_triangulate=True
                    bpy.context.view_layer.update();ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh();mesh.calc_loop_triangles()
                    candidate=[tuple(v.co) for v in mesh.vertices];triangles=[tuple(t.vertices) for t in mesh.loop_triangles]
                    if candidate and triangles:
                        drift=max(abs(fn(v[i] for v in vertices)-fn(v[i] for v in candidate)) for i in range(3) for fn in (min,max))
                        unfitted_drift=drift
                        if a.fit_bounds and 'calyx' not in name and drift>.002:
                            old_bounds=[(min(v[i] for v in vertices),max(v[i] for v in vertices)) for i in range(3)]
                            new_bounds=[(min(v[i] for v in candidate),max(v[i] for v in candidate)) for i in range(3)]
                            factors=[(oh-ol)/(nh-nl) if nh-nl>1e-10 else 1 for (ol,oh),(nl,nh) in zip(old_bounds,new_bounds)]
                            if all(.8<=factor<=1.25 for factor in factors):
                                candidate=[tuple(old_bounds[i][0]+(v[i]-new_bounds[i][0])*factors[i] for i in range(3)) for v in candidate]
                                drift=max(abs(fn(v[i] for v in vertices)-fn(v[i] for v in candidate)) for i in range(3) for fn in (min,max))
                                fitted=True
                        if drift<=.002 and len(triangles)>=8:
                            vertices,faces=candidate,triangles;accepted=True
                            face_uvs=[[tuple(mesh.uv_layers.active.data[i].uv) for i in t.loops] for t in mesh.loop_triangles] if mesh.uv_layers.active else [None]*len(faces)
                    ev.to_mesh_clear();bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(data)
                assert vertices and faces, f'Lost organ {name}'
                out.write(f'# source {name}\n')
                for v in vertices:out.write('v '+' '.join(f'{q:.8f}' for q in v)+'\n')
                for f,coords in zip(faces,face_uvs):
                    v0,v1,v2=[Vector(vertices[i]) for i in f];n=(v1-v0).cross(v2-v0)
                    if n.length:n.normalize()
                    normal+=1;out.write('vn '+' '.join(f'{q:.8g}' for q in n)+'\n')
                    if coords:
                        for uv in coords:out.write('vt '+' '.join(map(str,uv))+'\n')
                        out.write('f '+' '.join(f'{i+1+offset}/{uv_index+j+1}/{normal}' for j,i in enumerate(f))+'\n');uv_index+=3
                    else:out.write('f '+' '.join(f'{i+1+offset}//{normal}' for i in f)+'\n')
                offset+=len(vertices);total+=len(faces)
                diagnostics.append({'mesh':entry['uri'],'object':name,'source_triangles':original,'triangles':len(faces),'decimated':accepted,'candidate_bbox_drift_m':drift,'pre_fit_bbox_drift_m':unfitted_drift,'bounded_aabb_fit':fitted})
        entry['source_triangles']=entry['triangles'];entry['triangles']=total
        shutil.copy2(a.source/'meshes'/f'{target.stem}.mtl',target.with_suffix('.mtl'))
        if index%60==0:print(f'Organ-preserving LOD {index}/{len(manifest["meshes"])}',flush=True)
    for name in ('field.sdf','inventory.json'):shutil.copy2(a.source/name,a.output/name)
    if (a.source/'textures').is_dir():shutil.copytree(a.source/'textures',a.output/'textures')
    expected={(uri,o['object']) for o in manifest['organs'] for uri in o['meshes']}
    actual={(d['mesh'],d['object']) for d in diagnostics};assert expected==actual
    manifest['visual_lod']={'source':str(a.source.resolve()),'ratio':a.ratio,'minimum_target_triangles_per_decimated_organ':a.minimum,
        'preserve_calyces':a.preserve_calyces,
        'background_roles':str(a.background_roles) if a.background_roles else None,
        'target_assets':'byte-for-byte copy' if eligible is not None else 'standard LOD policy',
        'fit_bounds':a.fit_bounds,'fit_scale_limits':[.8,1.25],'silhouette_review_required':a.fit_bounds,
        'bbox_drift_limit_m':.002,'organs_preserved':len(actual),'status':'engineering_heuristic','colliders_markers_materials':'unchanged',
        'source_triangles':sum(d['source_triangles'] for d in diagnostics),'triangles':sum(d['triangles'] for d in diagnostics)}
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (a.output/'lod_diagnostics.json').write_text(json.dumps({'script_version':'dense-organ-lod/1.0','seed':manifest['seed'],
        'parameter_preset':manifest['crown_preset'],'organs':diagnostics},indent=2))
    print(json.dumps(manifest['visual_lod']),flush=True)

if __name__=='__main__':main()
