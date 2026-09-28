"""Run one memory-isolated audit or capture from a complete saved 6x6 scene."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
from collections import defaultdict

import bpy
from mathutils import Matrix,Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations,_set_render_engine
from uchuva_lsystem.blender_geometry import audit_scene_mesh_collisions
from uchuva_lsystem.sparse_pilot import UNITS_PER_METRE as U
spec=importlib.util.spec_from_file_location("pilot_renderer",ROOT/"scripts/render_sparse_pilot.py")
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)


def read(path):return json.loads(path.read_text(encoding="utf-8"))


def compact_render_geometry():
    """Bake evaluated leaves/stems and join per plant, preserving UVs/materials.

    Calyces, plates and cameras stay individual. The authoritative saved scene
    and its collision audit are unchanged; this is only a render interpreter.
    """
    groups=defaultdict(list)
    for obj in bpy.context.scene.objects:
        if not obj.hide_render and obj.get("uchuva_semantic_class") in {"leaf","stem"}:
            groups[(obj.get("uchuva_plant_id",""),obj.get("uchuva_semantic_class"))].append(obj)
    before=len(bpy.context.scene.objects)
    started=time.perf_counter()
    depsgraph=bpy.context.evaluated_depsgraph_get()
    originals=[]
    for group_index,((plant,semantic),objects) in enumerate(groups.items(),1):
        vertices=[];faces=[];materials=[];material_indices=[];smooth=[];uvs={};normals=[]
        loop_count=0
        for obj in objects:
            evaluated=obj.evaluated_get(depsgraph);source=evaluated.to_mesh()
            matrix=evaluated.matrix_world;normal_matrix=matrix.to_3x3().inverted().transposed()
            offset=len(vertices)
            vertices.extend(tuple(matrix@v.co) for v in source.vertices)
            slots=[]
            for evaluated_material in source.materials:
                material=bpy.data.materials[evaluated_material.name]
                if material not in materials:materials.append(material)
                slots.append(materials.index(material))
            for poly in source.polygons:
                faces.append(tuple(offset+i for i in poly.vertices))
                material_indices.append(slots[poly.material_index] if slots else 0)
                smooth.append(poly.use_smooth)
            for layer in source.uv_layers:
                if layer.name not in uvs:uvs[layer.name]=[0.0]*(loop_count*2)
            for name,values in uvs.items():
                layer=source.uv_layers.get(name)
                if layer:
                    values.extend(c for item in layer.data for c in item.uv)
                else:values.extend([0.0]*(len(source.loops)*2))
            normals.extend(tuple((normal_matrix@n.vector).normalized()) for n in source.corner_normals)
            loop_count+=len(source.loops)
            evaluated.to_mesh_clear()
        data=bpy.data.meshes.new(f"render_batch_{plant}_{semantic}")
        data.from_pydata(vertices,[],faces)
        for material in materials:data.materials.append(material)
        data.polygons.foreach_set("material_index",material_indices)
        data.polygons.foreach_set("use_smooth",smooth)
        for name,values in uvs.items():data.uv_layers.new(name=name).data.foreach_set("uv",values)
        data.normals_split_custom_set(normals)
        data.update()
        joined=bpy.data.objects.new(data.name,data)
        for key,value in objects[0].items():joined[key]=value
        bpy.context.scene.collection.objects.link(joined)
        originals.extend(objects)
        print("COMPACT",group_index,len(groups),plant,semantic,flush=True)
    bpy.data.batch_remove(ids=originals)
    bpy.context.view_layer.update()
    bpy.data.orphans_purge(do_recursive=True)
    return {"objects_before":before,"objects_after":len(bpy.context.scene.objects),
            "method":"evaluated_world_mesh_batch_per_plant_semantic", "groups":len(groups),
            "seconds":time.perf_counter()-started}


def recover_plan(folder,payload):
    """Recover the known v1.1 camera plan after a saved build stopped in its audit."""
    geometry=read(folder/"geometry.json")
    centers={}
    for obj in bpy.context.scene.objects:
        identity=obj.get("uchuva_reproductive_instance_id","")
        if obj.get("uchuva_semantic_class")=="calyx" and identity in geometry["grades"]:
            center=sum((obj.matrix_world@Vector(v) for v in obj.bound_box),Vector())/8/U
            centers[identity]={"center_world_m":list(center),"plant_id":obj["uchuva_plant_id"],
                "synthetic_reference_grade":geometry["grades"][identity],
                "center_definition":"mesh_local_bounds_midpoint_transformed"}
    markers=payload["markers"]
    for marker in markers:
        center=Vector(marker["center_world_m"]);normal=Vector(marker["normal_world"])
        up=Vector((0,0,1));right=up.cross(normal);half=marker["side_m"]/2
        transform=Matrix(((*right,0),(*up,0),(*normal,0),(0,0,0,1))).transposed()
        transform.translation=center
        marker["T_world_marker_m"]=renderer.matrix_list(transform)
        marker["corners_world_m"]=[list(center+right*x+up*y) for x,y in ((-half,half),(half,half),(half,-half),(-half,-half))]
    target=payload["scene"]["plant_instances"][14]
    views=[]
    for obj in bpy.context.scene.objects:
        if obj.type!="CAMERA":continue
        face,distance,height=obj.name.split("_")
        delta=obj.location-Vector(target["position"])
        views.append({"name":obj.name,"capture":{"face":face,"distance_band":distance,
            "height_band":height,"height_m":delta.z/U,"horizontal_distance_m":(delta.x**2+delta.y**2)**.5/U,
            "target_plant_id":target["plant_id"]}})
    plan={"markers":markers,"centers":centers,"views":views,"provenance":"recovered_from_saved_scene_v1.1"}
    renderer.write(folder/"capture_plan.json",plan)
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-dir",type=Path,required=True)
    parser.add_argument("--mode",choices=("audit","capture"),required=True)
    parser.add_argument("--camera")
    parser.add_argument("--all-missing",action="store_true",help="Reuse one loaded scene for all remaining views")
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    folder=args.scene_dir.resolve();started=time.perf_counter()
    payload=read(folder/"input.json")
    compact=folder/"capture_geometry.blend"
    source=compact if args.mode=="capture" and compact.exists() else folder/"cultivation.blend"
    bpy.ops.wm.open_mainfile(filepath=str(source))
    bpy.context.view_layer.update()
    plan=read(folder/"capture_plan.json") if (folder/"capture_plan.json").exists() else recover_plan(folder,payload)
    if args.mode=="audit":
        if (folder/"mesh_audit.json").exists():raise FileExistsError("Preserve existing audit")
        report=audit_scene_mesh_collisions(max_bvh_cache_objects=128,limit_clearance_search=True)
        report["seconds"]=time.perf_counter()-started
        renderer.write(folder/"mesh_audit.json",report)
        print("AUDIT",report["status"],report["physical_collision_count"],flush=True)
        return
    if not compact.exists():
        renderer.write(folder/"render_compaction.json",compact_render_geometry())
        bpy.ops.wm.save_as_mainfile(filepath=str(compact))
    views=[v for v in plan["views"] if not (folder/v["name"]/"capture.json").exists()] if args.all_missing else [
        next(v for v in plan["views"] if v["name"]==args.camera)]
    scene=bpy.context.scene
    timings={}
    # Keep EEVEE resident for RGB, then run the identical crisp-mask pass.
    for view in views:
        tick=time.perf_counter();name=view["name"]
        scene.camera=bpy.data.objects[name]
        output=folder/name;output.mkdir(exist_ok=False)
        _set_render_engine(scene,"BLENDER_EEVEE_NEXT")
        scene.render.filepath=str(output/"rgb.png")
        bpy.ops.render.render(write_still=True)
        timings[name]=time.perf_counter()-tick
        print("RGB",name,flush=True)
    for view in views:
        tick=time.perf_counter();name=view["name"];output=folder/name
        camera=bpy.data.objects[name];scene.camera=camera
        mask=render_crisp_calyx_annotations(camera,output,width=1280,height=960)
        metadata=renderer.camera_metadata(camera,plan["markers"],plan["centers"],1280,960)
        renderer.write(output/"capture.json",{"script_version":payload["script_version"],"seed":payload["seed"],
            "preset":payload["preset"],"scene_id":payload["scene"]["scene_id"],"capture":view["capture"],
            "mask":mask,"geometry":metadata,"seconds":timings[name]+time.perf_counter()-tick,
            "timing_scope":"view_RGB_mask_and_metadata_excludes_shared_load_and_compaction"})
        print("CAPTURE",name,flush=True)


if __name__=="__main__":main()
