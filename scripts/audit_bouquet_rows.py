"""Blender: screen all row faces against full, undecimated plant meshes."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, create_cultivation_supports
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials
from uchuva_gazebo.neo import LENGTH,WIDTH,HEIGHT


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reuse-distances',type=Path,help='Select from previously audited full-mesh distances, without rerendering')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.reuse_distances:
        result=json.loads(a.reuse_distances.read_text())
        if Path(result['source']).resolve()!=a.input.resolve():raise ValueError('Cached audit source differs')
        select_routes(result)
        a.output.write_text(json.dumps(result));return
    source=json.loads(a.input.read_text())
    scene=CultivationScene.from_dict(source['scene']);cleanup_scene();mats=create_project_materials(seed=scene.seed)
    radius=math.sqrt(LENGTH**2+WIDTH**2+HEIGHT**2)/2
    candidates=[]
    # Shared internal aisles; outer faces at the same stand-off. End turns at +/-4.8.
    for row in range(6):
        for side in (-1,1):
            for z in (.65,.80,.95,1.10):
                y=(row-2.5)*1.8+side*.9
                samples=[{'p':[round(-4.8+j*.04,5),y,z],'distance':z,'obstacle':'ground'} for j in range(241)]
                candidates.append({'row':row,'side':side,'height':z,'samples':samples})
    # Cross-row transfers and yaw changes stay outside both row ends.
    transfers=[{'p':[x,round(-5.4+j*.04,5),z],'distance':z,'obstacle':'ground'}
               for x in (-4.8,4.8) for z in (.65,.8,.95,1.1) for j in range(271)]
    points=[s for c in candidates for s in c['samples']]+transfers
    reports=[]
    for instance in [*scene.plant_instances,None]:
        before=set(bpy.data.objects)
        if instance:
            report=build_geometry_from_morphology(Plant.from_dict(source['plants'][instance.plant_id]),mats,
                instance_id=instance.plant_id,position=instance.position,rotation_deg=instance.rotation_deg,
                plant_scale=instance.scale,add_ground=False,defer_scene_update=True)
            reports.append({'plant_id':instance.plant_id,**report});name=instance.plant_id
        else:create_cultivation_supports(scene,mats,reports);name='supports'
        bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get();objects=set(bpy.data.objects)-before
        vertices=[];faces=[]
        for ob in objects:
            if ob.type not in {'MESH','CURVE'} or ob.hide_render:continue
            ev=ob.evaluated_get(deps);mesh=ev.to_mesh();mesh.calc_loop_triangles();offset=len(vertices)
            vertices.extend((ev.matrix_world@v.co)/8 for v in mesh.vertices)
            faces.extend(tuple(offset+i for i in t.vertices) for t in mesh.loop_triangles);ev.to_mesh_clear()
        if vertices:
            lo=[min(v[i] for v in vertices) for i in range(3)];hi=[max(v[i] for v in vertices) for i in range(3)]
            bvh=BVHTree.FromPolygons(vertices,faces,all_triangles=True)
            for s in points:
                boxdistance=math.sqrt(sum(max(lo[i]-s['p'][i],0,s['p'][i]-hi[i])**2 for i in range(3)))
                if boxdistance>=s['distance']:continue
                nearest=bvh.find_nearest(Vector(s['p']))
                if nearest[3]<s['distance']:s.update(distance=nearest[3],obstacle=name)
            del bvh
        del vertices,faces
        for ob in objects:bpy.data.objects.remove(ob,do_unlink=True)
        for blocks in (bpy.data.meshes,bpy.data.curves):
            for b in list(blocks):
                if not b.users:blocks.remove(b)
        print('Full-mesh clearance '+name,flush=True)
    for c in candidates:
        c['minimum_margin_m']=min(s['distance'] for s in c['samples'])-radius-.02
    result={'source':str(a.input),'radius_m':radius,'sampling_correction_m':.02,'required_margin_m':.15,
            'candidates':candidates,'transfers':transfers,
            'scope':'Full plant/support meshes and ground; marker boxes require package audit; no executed trajectory yet'}
    select_routes(result)
    a.output.write_text(json.dumps(result));print('Selected faces '+str(len(result['selected'])),flush=True)


def select_routes(result):
    selected=[]
    for row in range(6):
        for side in (-1,1):
            options=[c for c in result['candidates'] if c['row']==row and c['side']==side and c['minimum_margin_m']>=.18]
            if options:selected.append(min(options,key=lambda c:abs(c['height']-.80)))
    result.update(selected=selected,planned_reserve_m=.18,
        passed=len(selected)==12 and min(s['distance'] for s in result['transfers'])-result['radius_m']-.02>=.18)

if __name__=='__main__':main()
