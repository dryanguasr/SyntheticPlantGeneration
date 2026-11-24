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
 a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);root=a.root.resolve();protocol=json.loads((root/'protocol.json').read_text());config=next(s for s in protocol['scenes'] if s['name']==a.scene);out=root.parent/'field_environment_v193'/'evaluator_private';out.mkdir(exist_ok=True)
 import copy
 config=copy.deepcopy(config);originals=copy.deepcopy(config['plants'])
 for index,position in enumerate([(-15,14,0),(1,17,0),(-25,30,0),(18,31,0)]):
  entry=copy.deepcopy(originals[index%2]);entry.update(instance_id='neighbor_'+str(index),sample='neighbor_'+str(index),position=list(position));config['plants'].append(entry)
 config['views']=2
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
 # Procedural environment only: no edits to plant geometry or appearance materials.
 ground=bpy.data.objects['ground'];mat=ground.data.materials[0];nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
 tex=nodes.new('ShaderNodeTexCoord')
 macro=nodes.new('ShaderNodeTexNoise');macro.inputs['Scale'].default_value=.24;macro.inputs['Detail'].default_value=4;macro.inputs['Roughness'].default_value=.7;links.new(tex.outputs['Object'],macro.inputs['Vector'])
 ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.25;ramp.color_ramp.elements[0].color=(.025,.014,.006,1);ramp.color_ramp.elements[1].position=.72;ramp.color_ramp.elements[1].color=(.11,.18,.035,1)
 e=ramp.color_ramp.elements.new(.45);e.color=(.16,.085,.033,1)
 e=ramp.color_ramp.elements.new(.56);e.color=(.06,.09,.017,1)
 links.new(macro.outputs['Fac'],ramp.inputs['Fac'])
 fine=nodes.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=16;fine.inputs['Detail'].default_value=3;links.new(tex.outputs['Object'],fine.inputs['Vector'])
 mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.55;links.new(ramp.outputs['Color'],mix.inputs[1]);links.new(fine.outputs['Fac'],mix.inputs[2]);links.new(mix.outputs[0],bsdf.inputs['Base Color']);bsdf.inputs['Roughness'].default_value=.98
 bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.45;bump.inputs['Distance'].default_value=.045;links.new(fine.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
 world=scene.world;wn=world.node_tree.nodes;wl=world.node_tree.links;sky=wn.new('ShaderNodeTexSky');sky.sky_type='MULTIPLE_SCATTERING';sky.sun_elevation=math.radians(32);sky.sun_rotation=math.radians(125);sky.sun_disc=False;sky.air_density=1.0
 wl.new(sky.outputs['Color'],wn['Background'].inputs['Color'])
 write(out/'environment_protocol.json',dict(version='193',plants=[dict(instance_id=e['instance_id'],source=e['path'],source_sha256=e['sha256'],position=e['position']) for e in config['plants']],neighbors_annotated=True,environment='Procedural soil/grass-colored cover with multiscale bump and atmospheric sky; not calibrated real photography, no geometric seedlings',plant_geometry_or_material_changes=False,training_eligible=False))
 write(out/'class_mapping_private.json',mapping)
 completed=0
 for view in range(config['views']):
  folder=out/f'view_{view:03d}'
  if (folder/'capture.json').exists():continue
  folder.mkdir(exist_ok=True)
  # Fixed target and illumination: eight consecutive 0.5 s observations, no alternating views.
  angle=math.radians(-1 if view==0 else 19);distance=24 if view==0 else 32
  target=Vector((-7.2,0,4.0) if view==0 else (-3,4,4.0));camera.location=target+Vector((distance*math.sin(angle),-distance*math.cos(angle),3.7))
  camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
  scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3;bpy.data.objects['sun'].data.energy=1.5
  scene.render.engine='CYCLES';scene.render.image_settings.color_mode='RGB';scene.render.filepath=str(folder/'rgb.png');bpy.context.view_layer.update()
  visible=[];indeterminate=0
  bpy.ops.render.render(write_still=True)
  annotation=render_crisp_calyx_annotations(camera,folder,width=1280,height=720);write(folder/'annotations_private.json',annotation)
  write(folder/'camera_private.json',camera_metadata(camera,1280,720))
  write(folder/'capture.json',dict(version='environment-review/193',stamp_ns=1000000000+view*500000000,scene=config['name'],split=config['split'],view=view,seeds=[e['seed'] for e in config['plants']],rgb_sha256=sha(folder/'rgb.png'),mask_sha256=sha(folder/'mask_calyx_crisp_v2.png'),visible_contact_pairs=len(visible),indeterminate_contacts=indeterminate,geometry_edits=[r for r in repairs if r.get('changed')],training_eligible=False,pending='Diagnostic tracking only; verify native masks and public isolation before inference.'))
  print('CAPTURE',a.scene,view,'exposed',len(visible),'unknown',indeterminate,flush=True);completed+=1
  if a.limit and completed>=a.limit:break
 write(out/'progress.json',dict(completed=len(list(out.glob('view_*/capture.json'))),planned=config['views'],geometry_unchanged=True))
if __name__=='__main__':main()
