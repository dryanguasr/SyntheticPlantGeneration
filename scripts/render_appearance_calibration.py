"""Render paired diagnostic views from new corrected morphology; no training admission."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'src'))
import bpy
from mathutils import Vector,Matrix
from uchuva_lsystem.appearance_profiles import CLASSES,calibration_schedule,canonical_hash,component_seed
from uchuva_lsystem.blender_appearance import create_material_sets,apply_materials,apply_profile,geometry_digest
from uchuva_lsystem.blender_scene import cleanup_scene
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions,audit_scene_geometry_envelopes
from uchuva_lsystem.blender_environment import create_outdoor_environment, audit_calyx_ground_clearance, audit_plant_ground_clearance
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations,camera_metadata
from uchuva_lsystem.morphology import Plant


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(path)


def center(obj):return sum((obj.matrix_world@Vector(v) for v in obj.bound_box),Vector())/8


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=0)
    p.add_argument('--structure-only',action='store_true',help='Four fixed-camera structural checks, not a factorial calibration round')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.root.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    profiles=read(out/'profiles.json');plants=read(out/'plants.json')['plants'];assets=read(root/'texture_assets.json')
    for path,h in assets['files'].items():assert sha(path)==h,path
    signature={'profiles':sha(out/'profiles.json'),'runner':sha(__file__),
               'sources':{str(path.relative_to(REPO)):sha(path) for path in sorted((REPO/'src/uchuva_lsystem').glob('*.py'))},
               'plants':{str(r['index']):r['sha256'] for r in plants},'assets':sha(root/'texture_assets.json'),
               'structure_only':a.structure_only}
    if (out/'source_lock.json').exists():assert read(out/'source_lock.json')==signature,'Changed sources; use a new attempt directory'
    else:write(out/'source_lock.json',signature)
    schedule=calibration_schedule();completed=0
    if a.structure_only:schedule=[r for r in schedule if r['kind']=='context' and r['view']==0 and r['bank']=='LT']
    for entry in plants:
        tasks=[r for r in schedule if r['plant_index']==entry['index'] and not (out/r['view_id']/'capture.json').exists()]
        if not tasks:continue
        cleanup_scene(include_hidden=True);assert sha(entry['path'])==entry['sha256'];plant=Plant.from_dict(read(entry['path']))
        sets=create_material_sets(component_seed(20261026,'material',entry['index']),profiles)
        plant_id=f"calibration_{entry['index']:02d}"
        build=build_geometry_from_morphology(plant,sets['previous'],instance_id=plant_id,add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update();scene=bpy.context.scene
        # Disable historical component cleanup while preserving every visible calyx.
        scene['uchuva_preserve_mask_components']=True
        # Establish physical unit metadata before measuring evaluated geometry.
        scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.125
        objects=[o for o in scene.objects if o.type in {'MESH','CURVE','SURFACE'} and o.get('uchuva_semantic_class')]
        original_hidden={o.name:bool(o.hide_render) for o in objects}
        calyces=[o for o in objects if o.get('uchuva_semantic_class')=='calyx'];assert calyces
        assignments={plant_id+':'+r['unit_id']:r for r in entry['assignments']}
        env=create_outdoor_environment(seed=component_seed(20261026,'context',entry['index']),scene_radius=5,terrain_size=12,
            terrain_subdivisions=18,background_cluster_count=0,mode=profiles['context']['modes'][entry['index']%2])
        write(out/f'plant_{entry["index"]:02d}_environment.json',env)
        # Report physical mesh intersections separately; calibration does not silently admit them.
        strict_leaf_only=profiles.get('geometry_review',{}).get('strict_leaf_only',False)
        mesh_audit=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=strict_leaf_only,max_reported_pairs=None)
        write(out/f'plant_{entry["index"]:02d}_mesh_audit.json',mesh_audit)
        if profiles.get('geometry_review',{}).get('ground_audit'):
            write(out/f'plant_{entry["index"]:02d}_ground_audit.json',
                audit_plant_ground_clearance(seed=component_seed(20261026,'context',entry['index'])))
        write(out/f'plant_{entry["index"]:02d}_envelopes.json',audit_scene_geometry_envelopes())
        bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
        camera.data.lens=55;camera.data.sensor_width=36;camera.data.clip_start=.01;camera.data.clip_end=150
        scene.render.engine='CYCLES';scene.cycles.samples=profiles['render']['samples'];scene.cycles.use_denoising=True;scene.cycles.device='GPU'
        pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
        for device in pref.devices:device.use=device.type=='OPTIX'
        scene.render.resolution_x=profiles['render']['width'];scene.render.resolution_y=profiles['render']['height'];scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.film_transparent=False
        target_obj=min(calyces,key=lambda o:(center(o).y,o.name));focus=center(target_obj)
        corners=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
        lo=Vector(tuple(min(c[i] for c in corners) for i in range(3)));hi=Vector(tuple(max(c[i] for c in corners) for i in range(3)))
        body=(lo+hi)/2;extent=max(hi.x-lo.x,hi.y-lo.y,hi.z-lo.z)
        base_geometry=geometry_digest(scene)
        for task in tasks:
            folder=out/task['view_id'];folder.mkdir(exist_ok=True)
            for o in objects:o.hide_render=original_hidden[o.name]
            if task['kind']=='focal':
                # Isolated material specimen on the original mesh; not a training view.
                for o in objects:o.hide_render=o is not target_obj
                target=focus;span=max(target_obj.dimensions);distance=max(.6,span*5)
                camera.location=target+Vector((0,-distance,distance*.12))
            elif task['view']==0:
                target=body;distance=max(3.,extent*2.2);camera.location=target+Vector((0,-distance,distance*.20))
            else:
                target=focus;distance=max(1.,max(target_obj.dimensions)*15);camera.location=target+Vector((distance*.25,-distance,distance*.15))
            camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update()
            if a.structure_only:
                source=root/profiles['diagnostic_camera_source']/task['view_id']/'camera.json'
                original_camera=read(source)
                camera.matrix_world=Matrix(original_camera['matrix_world'])
                camera.data.lens=original_camera['lens_mm']
                camera.data.sensor_width=original_camera['sensor_width_mm']
                bpy.context.view_layer.update()
            light_target_source=None
            if a.structure_only and profiles.get('diagnostic_light_target_source'):
                # Freeze the fill light aim across architecture changes, too. The
                # reference envelope is a lighting anchor, never a growth target.
                light_target_source=root/profiles['diagnostic_light_target_source']/f'plant_{entry["index"]:02d}_envelopes.json'
                bounds=[row['bounds'] for row in read(light_target_source)['objects'] if row['plant_id']==plant_id]
                if not bounds:raise ValueError('Missing plant envelope for fixed light target')
                target=Vector(tuple((min(b['minimum'][i] for b in bounds)+max(b['maximum'][i] for b in bounds))/2 for i in range(3)))
            config=apply_profile(profiles,task['bank'],camera,target,task['light'])
            bpy.context.view_layer.update()
            lighting_geometry={o.name:{'type':o.data.type,'matrix_world':[list(row) for row in o.matrix_world],
                'energy':o.data.energy} for o in scene.objects if o.type=='LIGHT'}
            apply_materials(objects,sets,config['material_mode'],assignments,focal=target_obj if task['kind']=='focal' else None,focal_class=task['class_id'])
            assert geometry_digest(scene)==base_geometry,'Visual change altered mesh geometry'
            started=time.perf_counter();scene.render.filepath=str(folder/'rgb.png');bpy.ops.render.render(write_still=True)
            annotation=render_crisp_calyx_annotations(camera,folder,width=scene.render.resolution_x,height=scene.render.resolution_y)
            write(folder/'annotations.json',annotation);write(folder/'camera.json',camera_metadata(camera,scene.render.resolution_x,scene.render.resolution_y))
            focal_override=None
            if task['kind']=='focal':
                focal_id=str(target_obj.get('uchuva_reproductive_instance_id'))
                focal_override=dict(instance_id=focal_id,class_id=task['class_id'],class_name=CLASSES[task['class_id']],
                    original_appearance_assignment=assignments[focal_id],
                    basis='diagnostic material-only override; not a morphology or training label change',
                    latent_phenology=dict(calyx_state=target_obj.get('uchuva_calyx_state'),
                        maturity=target_obj.get('uchuva_maturity'),reproductive_stage=target_obj.get('uchuva_reproductive_stage')),
                    agronomic_maturity='unknown',human_review='pending')
            write(folder/'capture.json',dict(task,profiles_sha256=signature['profiles'],geometry_sha256=base_geometry,
                morphology_sha256=entry['sha256'],rgb_sha256=sha(folder/'rgb.png'),mask_sha256=sha(folder/'mask_calyx_crisp_v2.png'),
                effective_profile=config,assignments=assignments,focal_instance=target_obj.get('uchuva_reproductive_instance_id'),
                focal_appearance_override=focal_override,
                diagnostic_camera_source=profiles.get('diagnostic_camera_source') if a.structure_only else None,
                light_target_source=str(light_target_source) if light_target_source else None,
                light_target_source_sha256=sha(light_target_source) if light_target_source else None,
                lighting_geometry=lighting_geometry,
                visibility_contract='context restores original organ hide_render; focal isolates one diagnostic calyx',
                render_wall_seconds=time.perf_counter()-started,training_eligible=False,human_review='pending',
                annotation_contract='all visible valid calyces; mask fill is not physical occlusion'))
            completed+=1;print('APPEARANCE_CAPTURE',task['view_id'],flush=True)
            if a.limit and completed>=a.limit:return
    write(out/'completion.json',{'complete':True,'captures':len(list(out.glob('*/capture.json'))),'expected':len(schedule),'human_review':'pending','training_eligible':False,
        'purpose':'four fixed-camera structural checks' if a.structure_only else 'full visual factorial calibration'})


if __name__=='__main__':main()
