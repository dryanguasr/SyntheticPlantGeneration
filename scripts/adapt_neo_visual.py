"""Blender: adapt a locally licensed Neo mesh to Gazebo, independently of dynamics.

Supported source meshes: OBJ, STL, FBX, GLB/glTF. STEP requires a mesh exported
by the CAD author/tool first. No external converter is installed automatically.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys


def main():
    import bpy
    from mathutils import Euler, Vector
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--author',required=True)
    parser.add_argument('--license',required=True,help='License identifier or URL; preserved verbatim')
    parser.add_argument('--source-url',required=True)
    parser.add_argument('--source-kind',choices=('external_mesh','original_photo_reference'),default='external_mesh')
    parser.add_argument('--reference-url',help='Photographic reference, distinct from mesh authorship and license')
    parser.add_argument('--rotation-deg',type=float,nargs=3,default=(0,0,0),metavar=('X','Y','Z'))
    parser.add_argument('--objects',default='.*',help='Regex selecting airframe objects; excludes scan surroundings')
    parser.add_argument('--triangle-budget',type=int,default=50000)
    parser.add_argument('--animated-rotors',action='store_true',help='Objects named rotor_0_* through rotor_3_* become rotating visuals')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.triangle_budget<100:raise ValueError('Triangle budget must be at least 100')
    if args.output.exists():raise FileExistsError(args.output)
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    source=args.input.resolve(); suffix=source.suffix.lower()
    if suffix=='.obj':bpy.ops.wm.obj_import(filepath=str(source))
    elif suffix=='.stl':bpy.ops.wm.stl_import(filepath=str(source))
    elif suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(source),use_anim=False)
    elif suffix in ('.glb','.gltf'):bpy.ops.import_scene.gltf(filepath=str(source))
    else:raise ValueError('Export CAD to OBJ, STL, FBX or GLB first')
    meshes=[obj for obj in bpy.context.scene.objects if obj.type=='MESH' and re.search(args.objects,obj.name)]
    if not meshes:raise ValueError('No selected mesh objects')
    rotation=Euler(tuple(math.radians(v) for v in args.rotation_deg),'XYZ').to_matrix()
    points=[rotation @ (obj.matrix_world @ v.co) for obj in meshes for v in obj.data.vertices]
    low=Vector(tuple(min(v[i] for v in points) for i in range(3)))
    high=Vector(tuple(max(v[i] for v in points) for i in range(3)))
    size=high-low; center=(low+high)/2
    if min(size)<=1e-10:raise ValueError('Degenerate mesh envelope')
    envelope=(.130,.157,.0485)
    scale=min(a/b for a,b in zip(envelope,size))
    occupancy=[scale*b/a for a,b in zip(envelope,size)]
    if min(occupancy)<.65:
        raise ValueError(f'Envelope proportions inconsistent with Neo: {occupancy}; check orientation and object selection')
    before=sum(sum(len(p.vertices)-2 for p in obj.data.polygons) for obj in meshes)
    ratio=min(1,args.triangle_budget/max(1,before))
    groups={}
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in meshes:
        rotor=re.match(r'^rotor_([0-3])_',obj.name) if args.animated_rotors else None
        link=f'rotor_{rotor[1]}' if rotor else 'base_link'
        centers=((.0315,.045,.01),(-.0315,-.045,.01),(.0315,-.045,.01),(-.0315,.045,.01))
        offset=Vector(centers[int(rotor[1])]) if rotor else Vector((0,0,0))
        if ratio<1:
            modifier=obj.modifiers.new('simulation_lod','DECIMATE'); modifier.ratio=ratio
        evaluated=obj.evaluated_get(depsgraph); mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
        for triangle in mesh.loop_triangles:
            mat=mesh.materials[triangle.material_index] if mesh.materials else None
            color=tuple(mat.diffuse_color) if mat else (.62,.65,.66,1)
            if mat and mat.use_nodes:
                principled=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
                if principled:color=tuple(principled.inputs['Base Color'].default_value)
            vertices=[(rotation @ (obj.matrix_world @ mesh.vertices[i].co)-center)*scale-offset for i in triangle.vertices]
            groups.setdefault((link,color),[]).append(vertices)
        evaluated.to_mesh_clear()
    args.output.mkdir(parents=True)
    assets=[]
    for index,((link,color),triangles) in enumerate(groups.items()):
        name=f'neo_{index}'
        with (args.output/f'{name}.obj').open('w',encoding='utf-8') as stream:
            stream.write(f'mtllib {name}.mtl\no {name}\nusemtl surface\n')
            for j,vertices in enumerate(triangles):
                for v in vertices:stream.write('v '+' '.join(f'{a:.9g}' for a in v)+'\n')
                normal=(vertices[1]-vertices[0]).cross(vertices[2]-vertices[0]).normalized()
                stream.write('vn '+' '.join(f'{a:.9g}' for a in normal)+'\n')
                stream.write('f '+' '.join(f'{3*j+k+1}//{j+1}' for k in range(3))+'\n')
        (args.output/f'{name}.mtl').write_text('newmtl surface\nKd '+' '.join(str(v) for v in color[:3])+'\n',encoding='utf-8')
        assets.append({'uri':f'{name}.obj','link':link,'color':color,'triangles':len(triangles)})
    metadata={'script_version':'neo-visual-adapter/0.1','seed':0,'parameter_preset':'uniform_envelope_fit',
        'source':{'url':args.source_url,'author':args.author,'license':args.license,
                  'kind':args.source_kind,'reference_url':args.reference_url,
                  'file':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
        'selected_objects':[obj.name for obj in meshes],'rotation_deg':args.rotation_deg,
        'source_extent':list(size),'uniform_scale':scale,'extent_m':[v*scale for v in size],
        'triangles_before':before,'triangles_after':sum(a['triangles'] for a in assets),'meshes':assets,
        'adaptations':['Selected mesh objects','Centered bounding box; uniform scale to manufacturer envelope',
            'Optional decimation; flat triangle normals; material base colors only, no textures',
            'Named rotor visuals separated' if args.animated_rotors else 'Complete static visual including propellers',
            'Physics remains separate'],
        'status':'visual_approximation_not_measured_mass_or_inertia'}
    (args.output/'visual_manifest.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')
    (args.output/'ATTRIBUTION.txt').write_text(f"{args.author}\n{args.source_url}\nLicense: {args.license}\nAdapted for Gazebo; see visual_manifest.json. Original terms remain applicable.\n",encoding='utf-8')
    print(json.dumps(metadata,indent=2))


if __name__=='__main__':main()
