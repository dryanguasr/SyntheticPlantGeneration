"""Render a small review only after a fresh serialized-tree physical audit.

No training or camera-conditioned repair. Positive interorgan clearance remains
a reported warning under the previously authorized policy; actual audited
crossings and terrain clearance below one millimetre block every final image.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys
import shutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import bpy
from mathutils import Vector
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.scene import CultivationScene,PlantInstance
from uchuva_lsystem.nodal_repulsion import protected_anatomy,axes
from uchuva_lsystem.collisions import build_scene_proxies
from uchuva_lsystem.blender_scene import cleanup_scene,create_material
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions
from uchuva_lsystem.blender_environment import audit_plant_ground_clearance
from uchuva_lsystem.blender_reproductive_orientation import audit_calyx_orientation
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.blender_appearance import create_material_sets,apply_materials,apply_profile
from uchuva_lsystem.appearance_diversity import plant_appearance,appearance_assignments

def write(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plant',type=Path,required=True)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--foliage',type=int,choices=(0,1,2),default=0)
    parser.add_argument('--before',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    args.output.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'src/uchuva_lsystem').glob('*.py'))}
    sources[str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    write(args.output/'source_lock.json',sources)
    for relative in sources:
        target_file=args.output/'source_snapshot'/relative;target_file.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target_file)
    plant=Plant.from_dict(json.loads(args.plant.read_text(encoding='utf-8')))
    raw=Plant.from_dict(json.loads(args.raw.read_text(encoding='utf-8')))
    assert protected_anatomy(plant)==protected_anatomy(raw),'Organs, dimensions, classes or topology changed'
    profiles=json.loads((ROOT/'outputs/appearance_factorial_20261026/profiles.json').read_text(encoding='utf-8'))
    write(args.output/'profiles.json',profiles)
    layout=CultivationScene('nodal_review','fixed_growth_review',plant.seed,plant_instances=[PlantInstance('growth',plant.seed)])
    # Camera is declared from the ORIGINAL crown before interpreting the final
    # tree. The same camera is retained for the before/after comparison.
    proxies=build_scene_proxies(layout,{'growth':raw})
    lo=[min(p.aabb()[0][i] for p in proxies) for i in range(3)]
    hi=[max(p.aabb()[1][i] for p in proxies) for i in range(3)]
    target=Vector(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,(lo[2]+hi[2])/2))
    span=max(hi[i]-lo[i] for i in range(3))
    camera_position=target+Vector((.32,-1,.24)).normalized()*span*2.5
    view=dict(position=list(camera_position),target=list(target),lens_mm=48,original_bounds=[lo,hi],
              policy='fixed before/after from raw crown; never an input to growth or collision repair')
    write(args.output/'camera.json',view)
    units=[n.reproductive_unit.id for a in axes(plant.axes) for n in a.nodes if n.reproductive_unit and n.reproductive_unit.calyx]
    profile=plant_appearance(20261027,'growth',0,args.foliage,[1,1,1])
    classes=appearance_assignments(20261027,'growth',units,profile['class_probabilities'])
    assignments={'growth:'+k:dict(class_id=v,basis='synthetic appearance hypothesis; independent of fruit maturity') for k,v in classes.items()}
    write(args.output/'appearance_assignments.json',dict(foliage=profile,capachos=assignments))
    audit_rows=[]
    for name,current in ([('before',raw),('after',plant)] if args.before else [('after',plant)]):
        cleanup_scene(include_hidden=True)
        bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=.1
        sets=create_material_sets(plant.seed,profiles)
        bpy.ops.mesh.primitive_plane_add(size=max(64,span*8),location=(0,0,0))
        terrain=bpy.context.object;terrain.name='uchuva_terrain_agricultural'
        terrain.data.materials.append(create_material('review_soil',(.14,.105,.055,1),roughness=.95))
        build_geometry_from_morphology(current,sets['previous'],instance_id='growth',add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        mesh=audit_scene_mesh_collisions(tolerate_only_leaf_leaf=True,max_reported_pairs=None,limit_clearance_search=True)
        ground=audit_plant_ground_clearance(seed=plant.seed,terrain_object=terrain,required_clearance_m=.001)
        orientation=audit_calyx_orientation([current],layout,list(bpy.context.scene.objects))
        validation=validate_morphology_tree(current,stage='generated' if name=='before' else 'adapted')
        for suffix,value in [('mesh',mesh),('ground',ground),('orientation',orientation),('morphology',validation)]:
            write(args.output/f'{name}_{suffix}.json',value)
        accepted=mesh['physical_collision_count']==0 and ground['status']=='valid' and orientation['status']=='valid' and not validation['errors']
        audit_rows.append(dict(stage=name,physical_crossings=mesh['physical_collision_count'],
            positive_clearance_warnings=mesh['clearance_violation_count'],ground_status=ground['status'],orientation=orientation['status'],admitted=accepted))
        print('INDEPENDENT_AUDIT',audit_rows[-1],flush=True)
        if name=='after' and not accepted:
            write(args.output/'rejected.json',dict(audits=audit_rows,images_admitted=False));return
        bpy.ops.object.camera_add(location=camera_position)
        camera=bpy.context.object;camera.data.lens=view['lens_mm'];camera.data.clip_end=500
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        bpy.context.scene.camera=camera
        apply_materials(list(bpy.context.scene.objects),sets,'candidate',assignments,foliage_profiles={'growth':profile},seed=20261027)
        effective=apply_profile(profiles,'LT',camera,tuple(target))
        write(args.output/f'{name}_effective_appearance.json',effective)
        scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24
        scene.cycles.use_denoising=True;scene.cycles.device='GPU'
        preferences=bpy.context.preferences.addons['cycles'].preferences
        preferences.compute_device_type='OPTIX';preferences.get_devices()
        for device in preferences.devices:device.use=device.type=='OPTIX'
        scene.render.resolution_x=1200;scene.render.resolution_y=1050;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';scene.render.filepath=str((args.output/f'{name}.png').resolve())
        bpy.ops.render.render(write_still=True)
        if name=='after':bpy.ops.wm.save_as_mainfile(filepath=str((args.output/'scene.blend').resolve()))
    assert all(sha(ROOT/p)==digest for p,digest in sources.items()),'Sources changed during independent admission'
    assets={str(Path(bpy.path.abspath(img.filepath)).resolve()):sha(Path(bpy.path.abspath(img.filepath)))
        for img in bpy.data.images if img.filepath and Path(bpy.path.abspath(img.filepath)).is_file()}
    write(args.output/'admission.json',dict(status='admitted_under_existing_audited_scope',audits=audit_rows,
        anatomy_before=protected_anatomy(raw),anatomy_after=protected_anatomy(plant),
        input=str(args.plant.resolve()),input_sha256=sha(args.plant),raw_sha256=sha(args.raw),sources=sources,assets=assets,
        terrain='flat diagnostic plane; does not establish performance on irregular field terrain',
        scope='evaluated stem/leaf/calyx meshes; only leaf-leaf soft overlaps tolerated; intentional attachments retained; flowers and contextual objects not exhaustively collision certified',
        no_training=True,calyx_angular_prior='0–25 degrees from down, unmeasured engineering heuristic',
        review='pending human review; physical admission is not human visual approval'))

if __name__=='__main__':main()
