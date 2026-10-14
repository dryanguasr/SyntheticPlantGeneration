"""Blender: matched individual-crown renders, leaf coverage and editable plants."""
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology, audit_scene_mesh_collisions
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material
from uchuva_lsystem.sparse_pilot import CALYX_COLORS, walk_axes
from uchuva_lsystem.blender_annotations import _set_render_engine

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--new',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--plants',nargs='+')
    p.add_argument('--audit-saved',action='store_true',help='Re-audit existing editable review plants without rendering')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    a.output=a.output.resolve()
    if a.audit_saved:
        for path in sorted(a.output.glob('*_dense.blend')):
            bpy.ops.wm.open_mainfile(filepath=str(path))
            audit=audit_scene_mesh_collisions(near_contact_distance=0,limit_clearance_search=True,max_bvh_cache_objects=128,tolerate_only_leaf_leaf=True)
            original=json.loads((a.new/'plants'/(path.stem.replace('_dense','')+'.json')).read_text())
            audit.update(script_version='dense-crown-review/1.0',seed=original['seed'],parameter_preset=original['parameter_preset'])
            (a.output/(path.stem.replace('_dense','')+'_mesh_contacts.json')).write_text(json.dumps(audit,indent=2))
        return
    a.output.mkdir(parents=True,exist_ok=False)
    old=json.loads(a.source.read_text())
    ids=a.plants or json.loads((a.new/'comparison.json').read_text())['review_plants']
    new={'plants':{identifier:json.loads((a.new/'plants'/f'{identifier}.json').read_text()) for identifier in ids}}
    metrics=[]
    for identifier in ids:
        for version,payload in [('before',old),('after',new)]:
            cleanup_scene()
            plant=Plant.from_dict(payload['plants'][identifier])
            mats=create_project_materials(seed=plant.seed)
            for i,c in enumerate(CALYX_COLORS): mats[f'calyx_ntc_{i}']=create_material(f'calyx_ntc_{i}',c)
            build_geometry_from_morphology(plant,mats,instance_id=identifier,add_ground=False,defer_scene_update=True)
            bpy.context.view_layer.update()
            objects=[o for o in bpy.context.scene.objects if o.type in {'MESH','CURVE'}]
            leaves=[o for o in objects if o.get('uchuva_semantic_class')=='leaf' and not str(o.get('uchuva_organ_id','')).endswith('_midrib')]
            deps=bpy.context.evaluated_depsgraph_get(); area=0; triangles=0; points=[]
            for o in objects:
                ev=o.evaluated_get(deps); mesh=ev.to_mesh();mesh.calc_loop_triangles()
                triangles+=len(mesh.loop_triangles)
                points.extend(o.matrix_world@Vector(v) for v in o.bound_box)
                if o in leaves:
                    for t in mesh.loop_triangles:
                        v=[ev.matrix_world@mesh.vertices[i].co for i in t.vertices]
                        area+=(v[1]-v[0]).cross(v[2]-v[0]).length/2/64
                ev.to_mesh_clear()
            bounds=[[min(v[i] for v in points)/8,max(v[i] for v in points)/8] for i in range(3)]
            row={'plant_id':identifier,'version':version,'script_version':'dense-crown-review/1.0',
                 'seed':plant.seed,'parameter_preset':plant.parameter_preset,
                 'leaf_mesh_area_m2':area,'triangles':triangles,'bounds_m':bounds,'coverage':{}}
            if version=='after':
                audit=audit_scene_mesh_collisions(near_contact_distance=0,limit_clearance_search=True,max_bvh_cache_objects=128,tolerate_only_leaf_leaf=True)
                audit.update(script_version='dense-crown-review/1.0',seed=plant.seed,parameter_preset=plant.parameter_preset)
                soft=audit['soft_occupancy_intersections']
                audit['dense_policy']='Only leaf/leaf intersections tolerated; other soft-category pairs require correction'
                audit['leaf_leaf_examples']=[r for r in soft if r['semantic_a']==r['semantic_b']=='leaf']
                audit['nonfoliar_conflict_examples']=[r for r in soft if not r['semantic_a']==r['semantic_b']=='leaf']
                audit['examples_may_be_truncated']=audit['soft_occupancy_intersection_count']>len(soft)
                (a.output/f'{identifier}_mesh_contacts.json').write_text(json.dumps(audit,indent=2))
            scene=bpy.context.scene
            scene.unit_settings.system='METRIC'
            scene.unit_settings.scale_length=1/8
            _set_render_engine(scene,'BLENDER_EEVEE_NEXT')
            scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
            scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
            scene.render.film_transparent=True
            scene.world.color=(.25,.25,.25)
            for name,pos,energy,size in [('key',(-12,-15,24),22000,12),('fill',(10,12,18),17000,10)]:
                light=bpy.data.lights.new(name,'AREA');light.energy=energy;light.shape='DISK';light.size=size
                ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob);ob.location=pos
                ob.rotation_euler=(Vector((0,0,7))-ob.location).to_track_quat('-Z','Y').to_euler()
            camera=bpy.data.objects.new('comparison_camera',bpy.data.cameras.new('comparison_camera'))
            scene.collection.objects.link(camera);scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=20
            for face,sign in [('front',-1),('back',1)]:
                camera.location=(0,sign*28,8);camera.rotation_euler=(Vector((0,0,8))-camera.location).to_track_quat('-Z','Y').to_euler()
                scene.render.filepath=str(a.output/f'{identifier}_{version}_{face}.png');bpy.ops.render.render(write_still=True)
                for o in objects:o.hide_render=o not in leaves
                scene.render.filepath=str(a.output/f'{identifier}_{version}_{face}_leafmask.png');bpy.ops.render.render(write_still=True)
                image=bpy.data.images.load(scene.render.filepath,check_existing=False)
                import numpy as np
                pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels)
                row['coverage'][face]=float((pixels.reshape(-1,4)[:,3]>.5).mean())
                bpy.data.images.remove(image)
                for o in objects:o.hide_render=False
            if version=='after':
                bpy.ops.wm.save_as_mainfile(filepath=str(a.output/f'{identifier}_dense.blend'))
            metrics.append(row)
            (a.output/'metrics.json').write_text(json.dumps(metrics,indent=2))
            print(json.dumps(row),flush=True)

if __name__=='__main__':main()
