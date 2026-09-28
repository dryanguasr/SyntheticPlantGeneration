"""Blender diagnostic: matched isolated crowns and outward-only marker faces."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.sparse_pilot import *
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.blender_scene import cleanup_scene, create_project_materials, create_material, setup_render_settings
from uchuva_lsystem.blender_annotations import _set_render_engine

spec = importlib.util.spec_from_file_location("pilot_renderer",ROOT/"scripts/render_sparse_pilot.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plant",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    out=args.output.resolve(); out.mkdir(exist_ok=False)
    old=json.loads((ROOT/"outputs/sparse_overhead_pilot_v4/scene_00/input.json").read_text())["plants"]["plant_00"]
    counts={}
    for revision,plant_dict in (("old",old),("dense",json.loads(args.plant.read_text()))):
        cleanup_scene()
        plant=Plant.from_dict(plant_dict)
        axes=list(walk_axes(plant.axes))
        counts[revision]={"axes":len(axes),"leaves":sum(bool(n.leaf) for a in axes for n in a.nodes),
                          "calyxes":sum(bool(n.reproductive_unit and n.reproductive_unit.calyx) for a in axes for n in a.nodes)}
        materials=create_project_materials(seed=plant.seed)
        for grade,color in enumerate(CALYX_COLORS):
            materials[f"calyx_ntc_{grade}"]=create_material(f"calyx_ntc_{grade}",color)
        build_geometry_from_morphology(plant,materials,instance_id="plant_00",add_ground=False)
        cultivation=create_sparse_scene(230926)
        cultivation.plant_instances=cultivation.plant_instances[:1]
        cultivation.plant_instances[0].position=(0,0,0)
        renderer.environment(230926,cultivation.plant_instances)
        white=create_material("marker_white",(.9,.9,.9,1));black=create_material("marker_black",(.002,.002,.002,1))
        for marker in marker_specs(cultivation):
            cells=json.loads((ROOT/"outputs/sparse_overhead_pilot_v4/markers"/f"{marker['id']}.json").read_text())
            renderer.plate(marker,cells,white,black)
        scene=bpy.context.scene
        scene.unit_settings.system="METRIC";scene.unit_settings.scale_length=1/UNITS_PER_METRE
        setup_render_settings(640,960);_set_render_engine(scene,"BLENDER_EEVEE_NEXT")
        scene.render.resolution_percentage=100
        scene.render.image_settings.file_format="PNG"
        scene.render.threads_mode="FIXED";scene.render.threads=4
        camera=bpy.data.objects.new("review_camera",bpy.data.cameras.new("review_camera"))
        scene.collection.objects.link(camera);scene.camera=camera
        camera.data.lens=35;camera.data.sensor_width=36;camera.data.sensor_fit="HORIZONTAL"
        for face,sign in (("front",-1),("back",1)):
            if revision=="old" and face=="back":continue
            camera.location=(0,sign*2.3*UNITS_PER_METRE,.85*UNITS_PER_METRE)
            target=Vector((0,0,.80*UNITS_PER_METRE))
            camera.rotation_euler=(target-camera.location).to_track_quat("-Z","Y").to_euler()
            scene.render.filepath=str(out/f"{revision}_{face}.png")
            bpy.ops.render.render(write_still=True)
        if revision=="dense":bpy.ops.wm.save_as_mainfile(filepath=str(out/"dense_bush.blend"))
    (out/"counts.json").write_text(json.dumps(counts,indent=2))


if __name__=="__main__":main()
