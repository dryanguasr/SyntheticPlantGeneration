"""CPU-only 100-pose comparison of main and isolated evaluated depsgraphs.

The crowded scene is a timing fixture, not a claim about full-plant throughput.
No renders, files from frozen attempts, or production morphology are changed.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
import time

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.blender_geometry import _create_leaf_at_node, _new_collision_context
from uchuva_lsystem.blender_pose_repair import _remove_pose_objects
from uchuva_lsystem.morphology import Leaf


def run():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    main=bpy.context.scene
    material=bpy.data.materials.new("trial_profile")
    materials={key:material for key in ("leaf","leaf_vein","petiole","petiole_green")}
    crowd_mesh=bpy.data.meshes.new("shared_fixture_mesh")
    crowd_mesh.from_pydata([(0,0,0),(.1,0,0),(0,.1,0)],[],[(0,1,2)])
    for i in range(1500):
        obj=bpy.data.objects.new("static_fixture",crowd_mesh)
        main.collection.objects.link(obj)
        obj.location=(i%30*.15,i//30*.15,0)
    bpy.context.view_layer.update()
    scratch=bpy.data.scenes.new("isolated_profile")
    obstacle=BVHTree.FromPolygons([(-1,0,0),(1,0,0),(1,0,3),(-1,0,3)],[(0,1,2,3)],all_triangles=False)
    leaf=Leaf("profile_leaf","node",8,5,2,insertion_angle_deg=60,azimuth_deg=0,
              provenance={"insertion_frame":"local_cone_v2"})
    before=(len(bpy.data.objects),len(bpy.data.meshes))

    def measure(scene):
        totals={k:0.0 for k in ("create","update","evaluate","bvh","score","cleanup")}
        geometry=[]
        with bpy.context.temp_override(scene=scene,view_layer=scene.view_layers[0],collection=scene.collection):
            for index in range(100):
                leaf.azimuth_deg=(index*29)%360
                leaf.insertion_angle_deg=30+(index%11)*10
                t=time.perf_counter()
                objects=_create_leaf_at_node(Vector((0,0,2)),Vector((.5,.2,1)).normalized(),leaf,
                    materials,_new_collision_context(),{"plant_id":"fixture","plant_role":"target"},.08,"petiole_green","node",0)
                totals["create"]+=time.perf_counter()-t
                t=time.perf_counter();bpy.context.view_layer.update();totals["update"]+=time.perf_counter()-t
                signatures=[]
                for obj in objects:
                    t=time.perf_counter()
                    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=ev.to_mesh()
                    vertices=[ev.matrix_world@v.co for v in mesh.vertices]
                    polygons=[tuple(p.vertices) for p in mesh.polygons]
                    ev.to_mesh_clear()
                    totals["evaluate"]+=time.perf_counter()-t
                    signatures.append(([(float(v.x),float(v.y),float(v.z)) for v in vertices],polygons))
                    t=time.perf_counter();tree=BVHTree.FromPolygons(vertices,polygons,all_triangles=False,epsilon=.0005);totals["bvh"]+=time.perf_counter()-t
                    t=time.perf_counter();tree.overlap(obstacle);totals["score"]+=time.perf_counter()-t
                geometry.append(signatures)
                t=time.perf_counter();_remove_pose_objects(objects);totals["cleanup"]+=time.perf_counter()-t
        return totals,geometry

    try:
        main_times,main_geometry=measure(main)
        isolated_times,isolated_geometry=measure(scratch)
        assert main_geometry==isolated_geometry,"Evaluated trial geometry differs between scenes"
        assert (len(bpy.data.objects),len(bpy.data.meshes))==before,"Trial geometry leaked"
    finally:
        _remove_pose_objects(list(scratch.objects));bpy.data.scenes.remove(scratch)
    result={"version":"isolated-exact-leaf-trials/1","trials_per_context":100,"static_fixture_objects":1500,
            "main_scene_seconds":main_times,"isolated_scene_seconds":isolated_times,
            "speedup":sum(main_times.values())/sum(isolated_times.values()),
            "evaluated_world_vertices_and_polygons_exactly_equal":True,"datablock_count_preserved":True,
            "limitation":"CPU timing fixture; not measured full-plant repair throughput.",
            "solver_sha256":hashlib.sha256((ROOT/"src/uchuva_lsystem/blender_pose_repair_v2.py").read_bytes()).hexdigest()}
    path=ROOT/"outputs/appearance_factorial_20261026/revisions/lower_crown_contacts_20261026/leaf_trial_isolation_profile.json"
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    run()
