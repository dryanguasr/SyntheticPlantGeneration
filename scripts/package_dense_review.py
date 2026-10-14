"""Blender: collect the three editable review crowns into one presentation file."""
import argparse
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('review',type=Path)
    p.add_argument('--reuse',action='store_true',help='Refresh presentation of an existing generated package')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=a.review.resolve()
    if a.reuse:
        bpy.ops.wm.open_mainfile(filepath=str(folder/'arbustos_frondosos.blend'))
        for obj in list(bpy.data.objects):
            if obj.type in {'CAMERA','LIGHT'}:bpy.data.objects.remove(obj,do_unlink=True)
    else:
        bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
    for index,identifier in enumerate(() if a.reuse else ('plant_13','plant_03','plant_27')):
        with bpy.data.libraries.load(str(folder/f'{identifier}_dense.blend'),link=False) as (source,target):
            target.collections=[f'uchuva_{identifier}']
        collection=target.collections[0];bpy.context.scene.collection.children.link(collection)
        root=next(o for o in collection.objects if o.name.startswith(f'uchuva_{identifier}_root'))
        root.location.x=index*12
    for index,identifier in enumerate(('plant_13','plant_03','plant_27')):
        collection=bpy.data.collections[f'uchuva_{identifier}']
        if not collection.get('presentation_offset_applied'):
            # Morphology geometry is baked in world space; the organizational
            # root empty does not parent every organ.
            for obj in collection.all_objects:
                if obj.type != 'EMPTY' and obj.parent is None:obj.location.x+=index*12
            collection['presentation_offset_applied']=True
    scene=bpy.context.scene;scene['script_version']='dense-review-package/1.0';scene['seed']=230926
    scene['parameter_preset']=json.loads((folder/'metrics.json').read_text())[-1]['parameter_preset'] if (folder/'metrics.json').exists() else 'individual_dense_crown_v3'
    scene['purpose']='Three representative editable crowns; presentation offsets are NOT field positions'
    scene['contact_validation']='invalid_pending_correction'
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1/8
    camera=bpy.data.objects.new('review_camera',bpy.data.cameras.new('review_camera'))
    scene.collection.objects.link(camera);scene.camera=camera
    camera.location=(12,-32,10);camera.rotation_euler=(Vector((12,0,6))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=36
    scene.render.resolution_x=1600;scene.render.resolution_y=800
    light=bpy.data.lights.new('review_light','AREA');light.energy=40000;light.size=24
    obj=bpy.data.objects.new('review_light',light);scene.collection.objects.link(obj);obj.location=(12,-18,28)
    obj.rotation_euler=(Vector((12,0,6))-obj.location).to_track_quat('-Z','Y').to_euler()
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.color_type='MATERIAL'
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'arbustos_frondosos.blend'),compress=True)

if __name__=='__main__':main()
