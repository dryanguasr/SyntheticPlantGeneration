"""Fifteen matched morphology samples requested for human visual selection."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.ascending_basal_pilot import ascending_basal_pilot,VARIANTS
from uchuva_lsystem.curved_basal_pilot import curved_basal_pilot
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.validation import validate_morphology_tree

inward='--inward' in sys.argv
curved='--curved' in sys.argv or inward
out=ROOT/'outputs/integral_diagnosis_20261014'/('curved_basal_review_v5_inward' if inward else 'curved_basal_review_v4' if curved else 'ascending_basal_review_v1')
out.mkdir(exist_ok=True)
records=[]
for variant in VARIANTS:
    for index,count in enumerate((2,3,4,5,3),1):
        seed=814139+index
        name=f'{variant}_{index:02}_ramas{count}'
        base=prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))
        plant=curved_basal_pilot(base,count,variant,inward=inward) if curved else ascending_basal_pilot(base,count,variant)
        (out/f'{name}.json').write_text(json.dumps(plant.to_dict(),indent=2))
        (out/f'{name}_validation.json').write_text(json.dumps(validate_morphology_tree(plant),indent=2))
        records.append(dict(name=name,seed=seed,variant=variant,branches=count,
                            reproductive_units=plant.reproductive_unit_count()))
        if (out/f'{name}.png').exists():continue
        cleanup_scene()
        build_geometry_from_morphology(plant,create_project_materials(seed),add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
        scene.display.shading.color_type='MATERIAL';scene.display.shading.light='STUDIO'
        scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
        scene.display.shading.background_type='WORLD';scene.world.color=(.32,.32,.32)
        scene.render.resolution_x=1000;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG'
        bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
        camera.location=(15,-30,11);target=Vector((0,0,5.5))
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.type='ORTHO';camera.data.ortho_scale=22 if curved else 16
        scene.render.filepath=str(out/f'{name}.png');bpy.ops.render.render(write_still=True)
        print('SAMPLE_COMPLETE',name,flush=True)
(out/'manifest.json').write_text(json.dumps(dict(version='curved-basal-review/0.3' if inward else 'curved-basal-review/0.2' if curved else 'ascending-basal-review/0.1',
    records=records,camera='fixed across all 15 samples',materials='Workbench diagnostic colors; no photometric claim',
    accepted_for_dataset=False),indent=2))
