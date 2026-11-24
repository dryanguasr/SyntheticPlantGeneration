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

from copy import deepcopy
from uchuva_lsystem.hierarchical_basal_pilot import hierarchical_basal_pilot
from uchuva_lsystem.canopy_preference_pilot import canopy_preference_pilot
from uchuva_lsystem.matte_organ_review import apply_matte_organ_review
preferences='--preferences' in sys.argv
out=ROOT/'outputs/integral_diagnosis_20261014'/('canopy_preference_review_v1' if preferences else 'hierarchical_basal_review_v1')
out.mkdir(exist_ok=True)
records=[]
for index,(count,levels) in enumerate(((2,3),(3,3),(4,3),(5,3),(3,4)),1):
    seed=814140+index
    base=prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))
    plant=canopy_preference_pilot(base) if preferences else hierarchical_basal_pilot(base,count,levels)
    if preferences:
        count=plant.metadata['canopy_preference_pilot']['basal_axes'];levels=plant.metadata['canopy_preference_pilot']['levels']
    name=f'H{index}_bases{count}_niveles{levels}'
    (out/f'{name}.json').write_text(json.dumps(plant.to_dict(),indent=2))
    (out/f'{name}_validation.json').write_text(json.dumps(validate_morphology_tree(plant),indent=2))
    for mode in ('foliage','structure'):
        specimen=deepcopy(plant)
        if mode=='structure':
            def strip(axis):
                for node in axis.nodes:node.leaf=None;node.reproductive_unit=None
                for child in axis.child_axes:strip(child)
            strip(specimen.axes[0])
        cleanup_scene()
        materials=create_project_materials(seed)
        if preferences:apply_matte_organ_review(materials)
        build_geometry_from_morphology(specimen,materials,add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
        scene.display.shading.color_type='MATERIAL';scene.display.shading.light='STUDIO'
        if preferences:scene.display.shading.show_specular_highlight=False
        scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
        scene.display.shading.background_type='WORLD';scene.world.color=(.45,.45,.45)
        scene.render.resolution_x=1000;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG'
        bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
        camera.location=(15,-30,11);target=Vector((0,0,5.5))
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.type='ORTHO';camera.data.ortho_scale=18
        scene.render.filepath=str(out/f'{name}_{mode}.png');bpy.ops.render.render(write_still=True)
        print('SAMPLE_COMPLETE',name,mode,flush=True)
    records.append(dict(name=name,seed=seed,basal_axes=count,branching_levels=levels))
(out/'manifest.json').write_text(json.dumps(dict(version='hierarchical-review/0.1',records=records,accepted_for_dataset=False),indent=2))
