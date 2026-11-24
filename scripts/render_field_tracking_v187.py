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
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.root.resolve();protocol=json.loads((root/'protocol.json').read_text());config=next(s for s in protocol['scenes'] if s['name']==a.scene);out=root.parent/'field_tracking_v187'/'evaluator_private';out.mkdir(exist_ok=True)
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
 # V181 validation geometry already admitted; no geometry repair or collision sweep.
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
 # A physical matte board composed of square faces, no image compositing.
 cells=[[0, 0, 0, 0, 0, 0], [0, 255, 255, 255, 255, 0], [0, 255, 255, 255, 0, 0], [0, 255, 255, 0, 255, 0], [0, 255, 0, 255, 0, 0], [0, 0, 0, 0, 0, 0]];side=1.6;step=side/6;cx,cy,cz=-7.2,-5.,1.0;
 white=bpy.data.materials.new('marker_white');white.diffuse_color=(.9,.9,.9,1);white.use_nodes=True;white.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.9,.9,.9,1);white.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.9
 black=bpy.data.materials.new('marker_black');black.diffuse_color=(.005,.005,.005,1);black.use_nodes=True;black.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.005,.005,.005,1);black.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.9
 vertices=[];faces=[];colors=[]
 for row in range(-1,7):
  for col in range(-1,7):
   x=cx-side/2+col*step;z=cz+side/2-row*step;k=len(vertices)
   vertices.extend([(x,cy,z-step),(x+step,cy,z-step),(x+step,cy,z),(x,cy,z)]);faces.append((k,k+1,k+2,k+3));colors.append(0 if row in (-1,6) or col in (-1,6) or cells[row][col]>0 else 1)
 mesh=bpy.data.meshes.new('marker_board');mesh.from_pydata(vertices,[],faces);mesh.materials.append(white);mesh.materials.append(black)
 board=bpy.data.objects.new('visual_aruco_8',mesh);bpy.context.collection.objects.link(board)
 for poly,index in zip(mesh.polygons,colors):poly.material_index=index
 (out/'board_private.json').write_text(json.dumps(dict(center_world_bu=[cx,cy,cz],R_world_from_marker=[[1,0,0],[0,0,-1],[0,1,0]],side_bu=side,meters_per_bu=.125),indent=2))
 write(out/'class_mapping_private.json',mapping)
 completed=0
 for view in range(config['views']):
  folder=out/f'view_{view:03d}'
  if (folder/'capture.json').exists():continue
  folder.mkdir(exist_ok=True)
  # Fixed target and illumination: eight consecutive 0.5 s observations, no alternating views.
  angle=math.radians(-7+2*view);distance=24
  target=Vector((-7.2,0,4.0));camera.location=target+Vector((distance*math.sin(angle),-distance*math.cos(angle),3.7))
  camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
  scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.85;bpy.data.objects['sun'].data.energy=1.9
  scene.render.engine='CYCLES';scene.render.image_settings.color_mode='RGB';scene.render.filepath=str(folder/'rgb.png');bpy.context.view_layer.update()
  visible=[];indeterminate=0
  bpy.ops.render.render(write_still=True)
  annotation=render_crisp_calyx_annotations(camera,folder,width=1280,height=720);write(folder/'annotations_private.json',annotation)
  write(folder/'camera_private.json',camera_metadata(camera,1280,720))
  write(folder/'capture.json',dict(version='field-consecutive-route/187',stamp_ns=1000000000+view*500000000,scene=config['name'],split=config['split'],view=view,seeds=[e['seed'] for e in config['plants']],rgb_sha256=sha(folder/'rgb.png'),mask_sha256=sha(folder/'mask_calyx_crisp_v2.png'),visible_contact_pairs=len(visible),indeterminate_contacts=indeterminate,geometry_edits=[r for r in repairs if r.get('changed')],training_eligible=False,pending='Diagnostic tracking only; verify native masks and public isolation before inference.'))
  print('CAPTURE',a.scene,view,'exposed',len(visible),'unknown',indeterminate,flush=True);completed+=1
  if a.limit and completed>=a.limit:break
 write(out/'progress.json',dict(completed=len(list(out.glob('view_*/capture.json'))),planned=config['views'],geometry_unchanged=True))
if __name__=='__main__':main()
