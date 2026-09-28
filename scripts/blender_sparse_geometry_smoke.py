"""Prove deferred transforms match evaluated historical visible geometry, vertex by vertex."""
import json
from pathlib import Path
import re
import sys

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_morphology_parameters

cleanup_scene()
plant=generate_morphology_tree(23092600,get_morphology_parameters("trained_trellis"))
materials=create_project_materials(seed=plant.seed)
snapshots=[]
for deferred in (False,True):
    before=set(bpy.data.objects.keys())
    build_geometry_from_morphology(plant,materials,instance_id="test",position=(3,-2,.4),
                                  rotation_deg=37,plant_scale=1.04,add_ground=False,defer_scene_update=deferred)
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get()
    snapshot={}
    for obj in bpy.data.objects:
        if obj.name in before or obj.hide_render or obj.type not in {"MESH","CURVE"}:continue
        evaluated=obj.evaluated_get(deps)
        data=evaluated.to_mesh()
        snapshot[re.sub(r"\.\d{3}$","",obj.name)]=[tuple(obj.matrix_world@v.co) for v in data.vertices]
        evaluated.to_mesh_clear()
    snapshots.append(snapshot)
assert snapshots[0].keys()==snapshots[1].keys()
errors=[]
for name,left in snapshots[0].items():
    right=snapshots[1][name]
    assert len(left)==len(right)
    local_errors=[abs(a-b) for p,q in zip(left,right) for a,b in zip(p,q)]
    errors.extend(local_errors)
maximum=max(errors)
assert maximum<1e-5,maximum
print(json.dumps({"status":"passed","objects":len(snapshots[0]),"maximum_coordinate_error_BU":maximum}),flush=True)

# The bounded cache must change memory retention, not physical classifications.
from uchuva_lsystem.blender_geometry import _create_uv_sphere,audit_scene_mesh_collisions
from uchuva_lsystem.blender_annotations import tag_annotation_object
cleanup_scene()
material=bpy.data.materials.new("audit_test")
for index in range(5):
    obj=_create_uv_sphere(f"audit_{index}",(index*.15,0,0),.1,material,(1,1,1))
    tag_annotation_object(obj,"calyx",plant_id=f"p{index}",organ_id=f"o{index}",reproductive_id=f"r{index}")
for index,x in enumerate((3,3.221,5,5.23)):
    obj=_create_uv_sphere(f"clearance_{index}",(x,0,0),.1,material,(1,1,1))
    tag_annotation_object(obj,"calyx",plant_id=f"clearance_p{index}",organ_id=f"clearance_o{index}",reproductive_id=f"clearance_r{index}")
for index,x in enumerate((7,7.15)):
    obj=_create_uv_sphere(f"leaf_overlap_{index}",(x,0,0),.1,material,(1,1,1))
    tag_annotation_object(obj,"leaf",plant_id=f"leaf_p{index}",organ_id=f"leaf_o{index}")
bpy.context.view_layer.update()
full=audit_scene_mesh_collisions()
bounded=audit_scene_mesh_collisions(max_bvh_cache_objects=2,limit_clearance_search=True)
full.pop("max_bvh_cache_objects");bounded.pop("max_bvh_cache_objects")
assert full==bounded
assert full["clearance_violation_count"]>=1
assert full["near_contact_count"]>=1
assert full["soft_occupancy_intersection_count"]==1
assert full["visual_occlusion_count"]==0
print(json.dumps({"bounded_audit":"identical","physical_collisions":full["physical_collision_count"]}),flush=True)

# Joining evaluated geometry preserves visible vertices, UVs and material slots.
import importlib.util
spec=importlib.util.spec_from_file_location("saved_capture",ROOT/"scripts/capture_saved_sparse.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
cleanup_scene()
for index in range(3):
    bpy.ops.mesh.primitive_cube_add(size=.2, location=(index*.5,.3,.2))
    obj=bpy.context.object
    obj.rotation_euler=(.1*index,.2,.3)
    obj.scale=(1,1.3,.7)
    obj.data.materials.append(bpy.data.materials.new(f"surface_{index}"))
    obj["uchuva_semantic_class"]="leaf"
    obj["uchuva_plant_id"]="join_test"
    if index==1:
        modifier=obj.modifiers.new("thickness","SOLIDIFY");modifier.thickness=.01

def surface_snapshot():
    bpy.context.view_layer.update()
    deps=bpy.context.evaluated_depsgraph_get();result=[]
    for obj in bpy.context.scene.objects:
        if obj.type!="MESH":continue
        evaluated=obj.evaluated_get(deps);mesh=evaluated.to_mesh()
        uv=mesh.uv_layers.active
        for poly in mesh.polygons:
            corners=[]
            for loop in poly.loop_indices:
                position=evaluated.matrix_world@mesh.vertices[mesh.loops[loop].vertex_index].co
                tex=uv.data[loop].uv if uv else (0,0)
                corners.append(tuple(round(float(v),4) for v in (*position,*tex)))
            result.append((mesh.materials[poly.material_index].name,tuple(sorted(corners))))
        evaluated.to_mesh_clear()
    return sorted(result)
before=surface_snapshot()
compaction=module.compact_render_geometry()
after=surface_snapshot()
assert before==after
print(json.dumps({"render_compaction":"vertices_uv_materials_preserved","polygons":len(after),**compaction}),flush=True)

# Optional full-scene regression against an already recorded unbounded search.
if "--scene-dir" in sys.argv:
    import hashlib
    folder=Path(sys.argv[sys.argv.index("--scene-dir")+1]).resolve()
    reference_path=folder/"mesh_audit.json"
    expected=json.loads(reference_path.read_text(encoding="utf-8"))
    expected.pop("seconds",None)
    bpy.ops.wm.open_mainfile(filepath=str(folder/"cultivation.blend"))
    bpy.context.view_layer.update()
    actual=audit_scene_mesh_collisions(max_bvh_cache_objects=128,limit_clearance_search=True)
    changed=[key for key in sorted(set(expected)|set(actual)) if expected.get(key)!=actual.get(key)]
    result={"status":"passed" if not changed else "failed","changed_keys":changed,
            "reference_sha256":hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            "physical_collision_count":actual["physical_collision_count"],
            "clearance_violation_count":actual["clearance_violation_count"]}
    (folder/"bounded_audit_equivalence.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result),flush=True)
    assert not changed,changed
