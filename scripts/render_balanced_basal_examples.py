"""Three small, explicitly experimental morphology-first visual examples."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.balanced_basal_pilot import balanced_basal_pilot
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.validation import validate_morphology_tree

root=ROOT/'outputs/integral_diagnosis_20261014'
out=root/'balanced_examples_v1';out.mkdir(exist_ok='--resume' in sys.argv)
records=[]
for count in (2,3,5):
    plant=Plant.from_dict(json.loads((root/'fixtures/baseline_814140.json').read_text()))
    pilot=balanced_basal_pilot(plant,count)
    assert pilot.node_count()==plant.node_count()+count
    assert pilot.reproductive_unit_count()==plant.reproductive_unit_count()
    (out/f'plant_{count}.json').write_text(json.dumps(pilot.to_dict(),indent=2))
    (out/f'validation_{count}.json').write_text(json.dumps(validate_morphology_tree(pilot),indent=2))
    record=dict(source_seed=pilot.seed,nodes=pilot.node_count(),reproductive_units=pilot.reproductive_unit_count(),**pilot.metadata['balanced_basal_pilot'])
    records.append(record)
    if (out/f'arbusto_{count}_ramas.png').exists() and (out/f'estructura_{count}_ramas.png').exists():continue
    cleanup_scene();build_geometry_from_morphology(pilot,create_project_materials(pilot.seed),add_ground=False,defer_scene_update=True)
    bpy.context.view_layer.update()
    scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.color_type='MATERIAL';scene.display.shading.light='STUDIO'
    scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
    scene.display.shading.background_type='WORLD';scene.world.color=(.13,.13,.13)
    scene.render.resolution_x=1100;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
    camera.location=(18,-28,14);target=Vector((0,0,3.5))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=16
    scene.render.filepath=str(out/f'arbusto_{count}_ramas.png');bpy.ops.render.render(write_still=True)
    for obj in scene.objects:
        if obj.type in ('CURVE','MESH'):
            obj.hide_render=obj.get('uchuva_semantic_class')!='stem';obj.color=(.95,.7,.28,1)
    scene.display.shading.color_type='OBJECT'
    scene.render.filepath=str(out/f'estructura_{count}_ramas.png');bpy.ops.render.render(write_still=True)
(out/'manifest.json').write_text(json.dumps(dict(version='balanced-examples/0.1',records=records,
    purpose='Structural pilot, diagnostic material colors; not photometric validation',accepted_for_dataset=False),indent=2))
