"""Render small crop rows from untouched V142 morphology, with per-view contact evidence."""
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
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.root.resolve();protocol=json.loads((root/'protocol.json').read_text());config=next(s for s in protocol['scenes'] if s['name']==a.scene);out=root/a.scene;out.mkdir(exist_ok=True)
 helper=load_module('field_environment',ROOT/'scripts/render_sparse_pilot.py');matmod=load_module('approved_v142_materials',root/'source_snapshot/v142_materials.py')
 cleanup_scene();materials=matmod.create_v142_materials(config['seed']);mapping={};plants=[]
 for entry in config['plants']:
  path=Path(entry['path']);assert sha(path)==entry['sha256'];plant=Plant.from_dict(json.loads(path.read_text(encoding='utf-8')));plants.append(plant)
  write(out/f'{entry["sample"]}_morphology_validation.json',validate_morphology_tree(plant))
  for axis in axes(plant):
   for node in axis.nodes:
    u=node.reproductive_unit
    if u and u.calyx:
     cl=class_for_grade(u.synthetic_reference_grade);assert cl==u.provenance['synthetic_reference']['class_id']
     mapping[entry['instance_id']+':'+u.id]=dict(class_id=cl,plant_id=entry['instance_id'],unit_id=u.id,grade=u.synthetic_reference_grade)
  build_geometry_from_morphology(plant,materials,instance_id=entry['instance_id'],position=tuple(entry['position']),add_ground=False,defer_scene_update=True)
 bpy.context.view_layer.update();scene=bpy.context.scene
 repairs=[]
 target_path=root/f'{a.scene}_repair_targets.json'
 if target_path.exists():
  sys.path.insert(0,str(ROOT/'scripts'))
  from v142_visible_contact_repair import repair_visible_targets
  original=[plant.to_dict() for plant in plants]
  repairs=repair_visible_targets(plants,config['plants'],materials,json.loads(target_path.read_text())['target_object_names'])
  for entry,plant,before in zip(config['plants'],plants,original):
   after=plant.to_dict();restored=json.loads(json.dumps(after))
   def nodes(payload):
    result={};todo=list(payload['axes'])
    while todo:
     axis=todo.pop();todo.extend(axis['child_axes']);result.update({n['id']:n for n in axis['nodes']})
    return result
   old=nodes(before)
   for key,node in nodes(restored).items():
    if node.get('reproductive_unit'):node['reproductive_unit']['pedicel']=old[key]['reproductive_unit']['pedicel']
   assert restored==before,'Repair changed non-pedicel morphology'
   write(out/f'{entry["sample"]}_used_morphology.json',after)
 write(out/'geometry_changes.json',repairs)
 # Preserve complete audit, but do not require zero soft occupancy or hidden contacts.
 audit=audit_scene_mesh_collisions(near_contact_distance=0,limit_clearance_search=True,max_bvh_cache_objects=64)
 write(out/'mesh_audit.json',audit);assert audit['physical_collision_count']==len(audit['physical_collisions']), 'Truncated rigid-contact evidence'
 print('AUDIT',a.scene,audit['physical_collision_count'],flush=True)
 dg=bpy.context.evaluated_depsgraph_get();cache={}
 def mesh(name):
  if name not in cache:
   obj=bpy.data.objects[name];ev=obj.evaluated_get(dg);m=ev.to_mesh();m.calc_loop_triangles();vs=[ev.matrix_world@v.co for v in m.vertices];fs=[tuple(f.vertices) for f in m.loop_triangles];ev.to_mesh_clear();cache[name]=(vs,fs,BVHTree.FromPolygons(vs,fs,all_triangles=True,epsilon=0))
  return cache[name]
 contact_samples=[]
 for pair in audit['physical_collisions']:
  av,af,at=mesh(pair['object_a']);bv,bf,bt=mesh(pair['object_b']);hits=at.overlap(bt);points=[]
  # Deterministic bounded sampling, explicitly not a penetration-depth proof.
  for ia,ib in hits[::max(1,len(hits)//64)]:
   ta=[av[i] for i in af[ia]];tb=[bv[i] for i in bf[ib]]
   for tri,other in ((ta,tb),(tb,ta)):
    for k in range(3):
     start=tri[k];delta=tri[(k+1)%3]-start
     if delta.length<1e-9:continue
     point=intersect_ray_tri(*other,delta,start,True)
     if point is not None and (point-start).length<=delta.length+1e-7:points.append(point)
  points=points[::max(1,len(points)//64)][:64]
  contact_samples.append(dict(pair=pair,points=[list(x) for x in points],zero_epsilon_triangle_pairs=len(hits)))
  if len(cache)>48:cache.clear()
 write(out/'contact_samples.json',contact_samples);cache.clear()
 # Existing Gazebo-style soil, low vegetation and overhead support geometry.
 from types import SimpleNamespace
 helper.environment(config['seed'],[])
 post=create_material('row_support',(.12,.08,.04,1),.9);wire=create_material('row_wire',(.32,.34,.30,1),.9)
 for x in (-15,15):_create_cylinder_between(f'row_post_{x}',(x,0,0),(x,0,13),.13,post)
 _create_cylinder_between('row_overhead',(-15,0,13),(15,0,13),.025,wire)
 # Strings are scene context only; no deformation or force simulation.
 from uchuva_lsystem.blender_pose_repair import _rendered_node_frames
 for entry,plant in zip(config['plants'],plants):
  frames=_rendered_node_frames(plant)
  branch=next(axis for axis in axes(plant) if axis.order==1 and axis.nodes)
  attachment=Vector(frames[branch.nodes[-1].id][0])+Vector(entry['position'])
  _create_cylinder_between('row_string_'+entry['instance_id'],attachment,(attachment.x,0,13),.012,wire)
 bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera;camera.data.type='PERSP';camera.data.lens=35;camera.data.sensor_width=36;camera.data.sensor_fit='HORIZONTAL'
 scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.cycles.device='GPU'
 pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
 for device in pref.devices:device.use=device.type=='OPTIX'
 scene.render.resolution_x=1280;scene.render.resolution_y=720;scene.render.resolution_percentage=100
 scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.view_settings.view_transform='AgX';scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.125
 write(out/'class_mapping_private.json',mapping)
 completed=0
 for view in range(config['views']):
  folder=out/f'view_{view:03d}'
  if (folder/'capture.json').exists():continue
  folder.mkdir(exist_ok=True);focus=config['plants'][view%2]['position'][0];sign=-1 if (view//2)%2==0 else 1;angle=math.radians((-24,-8,8,24)[(view//4)%4]);distance=(20,24)[(view//8)%2]
  target=Vector((focus,0,4.0));camera.location=target+Vector((distance*math.sin(angle),sign*distance*math.cos(angle),3+(view%3)*.7));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
  scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=(.6,.85)[view%2];bpy.data.objects['sun'].data.energy=(1.6,2.2,1.9)[view%3]
  scene.render.engine='CYCLES';scene.render.image_settings.color_mode='RGB';scene.render.filepath=str(folder/'rgb.png');bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
  visible=[];hidden=0;indeterminate=0
  for contact in contact_samples:
   exposed=[]
   for coords in contact['points']:
    pt=Vector(coords);uv=world_to_camera_view(scene,camera,pt)
    if not (uv.z>0 and 0<=uv.x<=1 and 0<=uv.y<=1):continue
    delta=pt-camera.location;hit,loc,normal,index,obj,matrix=scene.ray_cast(dg,camera.location,delta.normalized(),distance=delta.length+.001)
    if hit and (loc-pt).length<.001:exposed.append([float(uv.x*1280),float((1-uv.y)*720)])
   if exposed:
    xs=[x[0] for x in exposed];ys=[x[1] for x in exposed];visible.append(dict(pair=contact['pair'],points_px=exposed,bounds_px=[min(xs),min(ys),max(xs),max(ys)]))
   elif contact['points']:hidden+=1
   elif contact['zero_epsilon_triangle_pairs']:indeterminate+=1
  write(folder/'contact_visibility_private.json',dict(exposed=visible,sampled_hidden_or_out_of_frame=hidden,indeterminate=indeterminate,method='Zero-epsilon triangle edge intersections, <=64 samples per pair, perspective first-hit rays. Sampling cannot prove absence; manual RGB review required.'))
  bpy.ops.render.render(write_still=True)
  annotation=render_crisp_calyx_annotations(camera,folder,width=1280,height=720);write(folder/'annotations_private.json',annotation)
  write(folder/'camera_private.json',camera_metadata(camera,1280,720))
  write(folder/'capture.json',dict(version='field-capture/181',scene=config['name'],split=config['split'],view=view,seeds=[e['seed'] for e in config['plants']],rgb_sha256=sha(folder/'rgb.png'),mask_sha256=sha(folder/'mask_calyx_crisp_v2.png'),visible_contact_pairs=len(visible),indeterminate_contacts=indeterminate,geometry_edits=[r for r in repairs if r.get('changed')],training_eligible=False,pending='Review externally visible contacts and labels; hidden contacts are not blocking under user policy.'))
  print('CAPTURE',a.scene,view,'exposed',len(visible),'unknown',indeterminate,flush=True);completed+=1
  if a.limit and completed>=a.limit:break
 write(out/'progress.json',dict(completed=len(list(out.glob('view_*/capture.json'))),planned=config['views'],geometry_unchanged=True))
if __name__=='__main__':main()
