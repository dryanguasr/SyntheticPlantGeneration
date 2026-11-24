"""V187 consecutive diagnostic route; unchanged V181 plants, no repeated collision sweep."""
import argparse, hashlib, importlib.util, json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.validation import validate_morphology_tree
from uchuva_lsystem.blender_scene import cleanup_scene,create_material
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology,audit_scene_mesh_collisions,_create_cylinder_between
from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations,camera_metadata
from uchuva_lsystem.segmentation_cycles import class_for_grade

def load_module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def write(path,data):path.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def axes(plant):
 todo=list(plant.axes)
 while todo:
  a=todo.pop();todo.extend(a.child_axes);yield a

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--scene',required=True);p.add_argument('--limit',type=int,default=0)
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.root.resolve();protocol=json.loads((root/'protocol.json').read_text());config=next(s for s in protocol['scenes'] if s['name']==a.scene);out=root.parent/'field_geometry_evaluation_v189'/'evaluator_private';out.mkdir(exist_ok=True)
 helper=load_module('field_environment',ROOT/'scripts/render_sparse_pilot.py');matmod=load_module('approved_v142_materials',root/'source_snapshot/v142_materials.py')
 cleanup_scene();materials=matmod.create_v142_materials(config['seed']);mapping={};plants=[]
 for entry in config['plants']:
  path=Path(entry['path']);assert sha(path)==entry['sha256'];plant=Plant.from_dict(json.loads(path.read_text(encoding='utf-8')));plants.append(plant)
  # Prior morphology validation preserved; no repeated audit.
  for axis in axes(plant):
   for node in axis.nodes:
    u=node.reproductive_unit
    if u and u.calyx:
     cl=class_for_grade(u.synthetic_reference_grade);assert cl==u.provenance['synthetic_reference']['class_id']
     mapping[entry['instance_id']+':'+u.id]=dict(class_id=cl,plant_id=entry['instance_id'],unit_id=u.id,grade=u.synthetic_reference_grade)
  build_geometry_from_morphology(plant,materials,instance_id=entry['instance_id'],position=tuple(entry['position']),add_ground=False,defer_scene_update=True)
 bpy.context.view_layer.update();scene=bpy.context.scene

 from uchuva_lsystem.blender_annotations import _object_reproductive_instance_id
 groups={};dg=bpy.context.evaluated_depsgraph_get()
 for obj in scene.objects:
  if obj.get('uchuva_semantic_class')!='calyx' or obj.type!='MESH':continue
  key=_object_reproductive_instance_id(obj);ev=obj.evaluated_get(dg);mesh=ev.to_mesh()
  points=[ev.matrix_world@v.co for v in mesh.vertices];ev.to_mesh_clear()
  groups.setdefault(key,[]).extend(points)
 records={}
 for key,points in groups.items():
  low=[min(v[i] for v in points) for i in range(3)];high=[max(v[i] for v in points) for i in range(3)]
  records[key]=dict(center_world_bu=[(low[i]+high[i])/2 for i in range(3)],bounds_world_bu=[low,high],vertices=len(points))
 assert set(records)==set(mapping),(len(records),len(mapping))
 write(out/'calyx_centers.json',dict(definition='Center of evaluated calyx world-axis-aligned mesh bounds; not internal fruit center or visible-mask centroid',meters_per_bu=.125,items=records,source_hashes=[dict(path=e['path'],sha256=sha(Path(e['path']))) for e in config['plants']],estimator_access=False))
 print('EXPORTED',len(records),'evaluated calyx bounds; no rendering',flush=True)
if __name__=='__main__':main()
