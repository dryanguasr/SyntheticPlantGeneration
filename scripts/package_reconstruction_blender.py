"""Run in Blender: package the observed textured surface for direct inspection.

Example: blender --background --python this_script.py -- --package ... --output ...
The scene preserves the arbitrary display scale declared by the Gazebo package.
"""
import argparse
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    package=args.package.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((package/'manifest.json').read_text())
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for record in manifest['textures']:
        # OBJ vertices already use the Gazebo display frame: +Z up, +Y forward.
        bpy.ops.wm.obj_import(filepath=str(package/record['uri']),forward_axis='Y',up_axis='Z')
    for obj in list(bpy.context.scene.objects):
        if obj.type=='MESH':
            obj['geometry_status']='partial_supported_Poisson_surface_from_MVS'
            obj['scale_status']='arbitrary_uncalibrated_not_metres'
    bpy.ops.object.camera_add(location=(0,-9,3))
    camera=bpy.context.object
    camera.rotation_euler=(Vector((0,0,2))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.lens=35
    bpy.context.scene.camera=camera
    bpy.ops.object.light_add(type='SUN',location=(0,-5,8))
    bpy.context.object.data.energy=2
    bpy.context.object.rotation_euler=(.5,-.3,-.4)
    bpy.context.scene.world.color=(.6,.6,.6)
    bpy.context.scene['source_manifest']=json.dumps(manifest)
    bpy.context.scene['measurement_warning']='Uncalibrated; interpolated visual mesh. Use retained analytical MVS cloud for geometry diagnostics.'
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'uchuva_observed_surface.blend'))
    bpy.ops.export_scene.gltf(filepath=str(args.output/'uchuva_observed_surface.glb'),export_format='GLB')
    result=dict(script_version='reconstruction-pilot/0.2',seed=20261001,
        parameter_preset='review_package',source_package=str(package),
        meshes=sum(o.type=='MESH' for o in bpy.context.scene.objects),
        vertices=sum(len(o.data.vertices) for o in bpy.context.scene.objects if o.type=='MESH'),
        polygons=sum(len(o.data.polygons) for o in bpy.context.scene.objects if o.type=='MESH'),
        image_count=len(bpy.data.images),physical_scale=False)
    (args.output/'package_report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':main()
