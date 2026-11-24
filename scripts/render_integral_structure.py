"""Six fixed-camera structural review frames; not a photometric material test."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials


def main():
    root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
    skeleton='--skeleton' in sys.argv
    out=root/('structure_skeleton' if skeleton else 'structure_preview');out.mkdir(exist_ok=False)
    records=[]
    for label in ('baseline_814140','basal_814140_3'):
        cleanup_scene()
        path=root/'fixtures'/f'{label}.json';plant=Plant.from_dict(json.loads(path.read_text()))
        materials=create_project_materials(seed=plant.seed)
        report=build_geometry_from_morphology(plant,materials,add_ground=False,defer_scene_update=True)
        bpy.context.view_layer.update()
        points=[o.matrix_world@Vector(v) for o in bpy.context.scene.objects if o.type=='MESH' for v in o.bound_box]
        bounds=[[min(v[i] for v in points),max(v[i] for v in points)] for i in range(3)]
        scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
        scene.display.shading.color_type='OBJECT';scene.display.shading.light='STUDIO'
        scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
        for obj in scene.objects:
            kind=obj.get('uchuva_semantic_class','')
            obj.color=(.1,.38,.12,1) if kind=='leaf' else (.65,.47,.12,1) if kind=='calyx' else (.2,.12,.06,1)
            if skeleton:
                obj.hide_render=kind!='stem'
                obj.color=(.95,.72,.32,1)
        scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG'
        bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera
        camera.data.type='ORTHO';camera.data.ortho_scale=28
        for name,position in [('front',(0,-35,12)),('side',(35,0,12)),('oblique',(26,-26,20))]:
            camera.location=position;camera.rotation_euler=(Vector((0,0,7))-camera.location).to_track_quat('-Z','Y').to_euler()
            scene.render.filepath=str(out/f'{label}_{name}.png');bpy.ops.render.render(write_still=True)
        if skeleton:
            camera.location=(0,-10,3);camera.data.ortho_scale=8
            camera.rotation_euler=(Vector((0,0,1))-camera.location).to_track_quat('-Z','Y').to_euler()
            scene.render.filepath=str(out/f'{label}_base.png');bpy.ops.render.render(write_still=True)
        records.append(dict(label=label,seed=plant.seed,parameter_preset=plant.parameter_preset,
            bounds_model_units=bounds,units_per_metre=8,geometry_report=report))
    (out/'manifest.json').write_text(json.dumps(dict(version='structure-review/1.0',records=records,
        purpose='Same cameras and diagnostic colors; visual review pending; not Gazebo or texture fidelity',
        views=4 if skeleton else 3,images=8 if skeleton else 6,skeleton=skeleton),indent=2))


if __name__=='__main__':main()
