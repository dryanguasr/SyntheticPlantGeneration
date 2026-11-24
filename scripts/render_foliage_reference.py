import argparse,json,sys,random
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.sparse_pilot import prepare_plant,sparse_morphology_parameters
from uchuva_lsystem.foliage_reference_pilot import foliage_reference_pilot,stagger_secondary_branches,space_secondary_leaves,scale_petiole_lengths,spread_leaf_azimuths
from uchuva_lsystem.blender_scene import cleanup_scene,create_project_materials
from uchuva_lsystem.blender_geometry import build_geometry_from_morphology
from uchuva_lsystem.matte_organ_review import apply_matte_organ_review
from uchuva_lsystem.validation import validate_morphology_tree
p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--seeds',nargs='+',type=int,required=True);p.add_argument('--density',type=float,default=1.25)
p.add_argument('--saved-morphology',help='Render one exact saved morphology; generation transforms are ignored')
p.add_argument('--annotation-smoke',action='store_true',help='Diagnostic calyx instance masks; not an accepted training dataset')
p.add_argument('--field-appearance',action='store_true')
p.add_argument('--dark-calyx-veins',action='store_true')
p.add_argument('--stagger-secondary',action='store_true')
p.add_argument('--side-view',action='store_true')
p.add_argument('--leaf-relief-scale',type=float,default=1.0)
p.add_argument('--leaf-spacing-ratio',type=float,default=0.0)
p.add_argument('--petiole-length-scale',type=float,default=1.0)
p.add_argument('--leaf-cell-relief',action='store_true')
p.add_argument('--lighting-preset',choices=['studio','side_daylight'],default='studio')
p.add_argument('--preserve-leaf-senescence',action='store_true')
p.add_argument('--graded-leaf-color',action='store_true')
p.add_argument('--orthogonal-leaf-frame',action='store_true')
p.add_argument('--leaf-azimuth-half-range',type=float,default=0)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);out=ROOT/'outputs/integral_diagnosis_20261014'/a.name;out.mkdir(exist_ok=False)
records=[]
if a.annotation_smoke and not a.saved_morphology:
 raise ValueError('Annotation smoke requires an exact saved morphology')
for seed in a.seeds:
 base=prepare_plant(generate_morphology_tree(seed,sparse_morphology_parameters('individual_dense_crown_v3')))
 plant=foliage_reference_pilot(base,a.density,preserve_leaf_senescence=a.preserve_leaf_senescence)
 if a.stagger_secondary:plant=stagger_secondary_branches(plant)
 if a.leaf_spacing_ratio:plant=space_secondary_leaves(plant,a.leaf_spacing_ratio)
 if a.leaf_azimuth_half_range:plant=spread_leaf_azimuths(plant,a.leaf_azimuth_half_range)
 if a.petiole_length_scale!=1:plant=scale_petiole_lengths(plant,a.petiole_length_scale)
 if not 0<a.leaf_relief_scale<=3:raise ValueError('Leaf relief scale outside review range')
 def scale_leaf_relief(axis):
  for node in axis.nodes:
   if node.leaf:
    node.leaf.provenance['surface_relief_ratio']*=a.leaf_relief_scale
    if a.orthogonal_leaf_frame:node.leaf.provenance['insertion_frame']='orthogonal_local_v1'
  for child in axis.child_axes:scale_leaf_relief(child)
 for axis in plant.axes:scale_leaf_relief(axis)
 plant.metadata['leaf_relief_review']={'scale':a.leaf_relief_scale,'parameter_status':'engineering_heuristic'}
 plant.metadata['lighting_review']={'preset':a.lighting_preset,'parameter_status':'engineering_heuristic','calibrated_to_real_capture':False}
 plant.metadata['leaf_color_review']={'graded':a.graded_leaf_color,'bins':11,'parameter_status':'engineering_heuristic','senescence_unchanged':True}
 if a.field_appearance:
  rng=random.Random(seed+6026)
  def apply_field_appearance(axis):
   for node in axis.nodes:
    for unit in ([node.reproductive_unit] if node.reproductive_unit else []):
     if unit.calyx and rng.random()<.85:
      calyx=unit.calyx
      calyx.provenance.update(visual_material_override='field_reference_green',original_material_key=calyx.material_key,fruit_maturity_unchanged=True)
      calyx.material_key='calyx_inflated_green'
   for child in axis.child_axes:apply_field_appearance(child)
  for axis in plant.axes:apply_field_appearance(axis)
  plant.metadata['field_appearance_review']={'green_material_probability':.85,'parameter_status':'engineering_heuristic','not_a_maturity_label':True}

 if a.saved_morphology:
  from uchuva_lsystem.morphology import Plant
  if len(a.seeds)!=1:raise ValueError('Saved morphology requires exactly one seed')
  plant=Plant.from_dict(json.loads(Path(a.saved_morphology).read_text(encoding='utf-8')))
  if plant.seed!=seed:raise ValueError('Saved seed mismatch')

 (out/f'{seed}.json').write_text(json.dumps(plant.to_dict(),indent=2))
 (out/f'{seed}_validation.json').write_text(json.dumps(validate_morphology_tree(plant),indent=2))
 cleanup_scene();materials=create_project_materials(seed);apply_matte_organ_review(materials)
 for key,mat in materials.items():
  if not key.startswith(('leaf','calyx')):continue
  for node in mat.node_tree.nodes:
   if node.type=='NORMAL_MAP':
    node.inputs['Strength'].default_value=.75;mat['review_normal_strength']=.75
   if node.type=='TEX_NOISE' and 'pubescent' in node.name:node.inputs['Scale'].default_value=38
   if node.type=='BUMP' and 'micro' in node.name:node.inputs['Strength'].default_value=.22;node.inputs['Distance'].default_value=.018
 if a.leaf_cell_relief:
  seen_leaves=set()
  for key,mat in materials.items():
   if not key.startswith('leaf') or mat.name in seen_leaves:continue
   seen_leaves.add(mat.name)
   nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
   uv=nodes.new('ShaderNodeUVMap');uv.uv_map='leaf_uv'
   cells=nodes.new('ShaderNodeTexVoronoi');cells.voronoi_dimensions='2D';cells.feature='DISTANCE_TO_EDGE';cells.inputs['Scale'].default_value=22
   bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.45;bump.inputs['Distance'].default_value=.015
   if bsdf.inputs['Normal'].links:links.new(bsdf.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
   links.new(uv.outputs['UV'],cells.inputs['Vector']);links.new(cells.outputs['Distance'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
   mat['review_cell_relief']='UV cellular bump, scale22 strength0.45 distance0.015; uncalibrated appearance only, not anatomical venation'
 if a.dark_calyx_veins:
  seen=set()
  for key,mat in materials.items():
   if not key.startswith('calyx') or mat.name in seen:continue
   seen.add(mat.name)
   nodes=mat.node_tree.nodes;links=mat.node_tree.links
   albedo=next((n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo')),None)
   if albedo is None:continue
   mask_path=Path(bpy.path.abspath(albedo.image.filepath)).with_name(Path(albedo.image.filepath).name.replace('_albedo','_vein_mask'))
   if not mask_path.exists():raise FileNotFoundError(mask_path)
   mask=nodes.new('ShaderNodeTexImage');mask.image=bpy.data.images.load(str(mask_path),check_existing=True);mask.image.colorspace_settings.name='Non-Color'
   if albedo.inputs['Vector'].links:links.new(albedo.inputs['Vector'].links[0].from_socket,mask.inputs['Vector'])
   mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[2].default_value=(.025,.012,.022,1)
   links.new(mask.outputs['Color'],mix.inputs[0]);links.new(albedo.outputs['Color'],mix.inputs[1]);links.new(mix.outputs[0],nodes.get('Principled BSDF').inputs['Base Color'])
   mat['review_veins']='dark_purple_brown_from_existing_vein_mask; engineering_heuristic'
 if a.graded_leaf_color:
  yellow=next(n.image for n in materials['leaf_senescent'].node_tree.nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
  for index in range(11):
   mat=materials['leaf'].copy();mat.name=f'review_leaf_senescence_{index}'
   nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
   green=next(n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
   other=nodes.new('ShaderNodeTexImage');other.image=yellow;other.extension=green.extension
   links.new(green.inputs['Vector'].links[0].from_socket,other.inputs['Vector'])
   mix=nodes.new('ShaderNodeMixRGB');mix.inputs[0].default_value=index/10
   links.new(green.outputs['Color'],mix.inputs[1]);links.new(other.outputs['Color'],mix.inputs[2]);links.new(mix.outputs[0],bsdf.inputs['Base Color'])
   mat['review_color_blend']=index/10;materials[f'leaf_senescence_{index}']=mat
 build_geometry_from_morphology(plant,materials,add_ground=False,defer_scene_update=True);bpy.context.view_layer.update()
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
 scene.cycles.device='GPU'
 pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
 for device in pref.devices:device.use=device.type=='OPTIX'
 scene.render.resolution_x=900;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
 scene.world.use_nodes=True;scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.55,.62,.70,1);scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.65
 lights=[((5,-10,15),2400,9),((-8,-3,8),1100,8)] if a.lighting_preset=='studio' else []
 if a.lighting_preset=='side_daylight':
  scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.35
  bpy.ops.object.light_add(type='SUN',location=(-8,-6,14));sun=bpy.context.object;sun.data.energy=2.5;sun.data.angle=.15
  sun.rotation_euler=(Vector((0,0,6))-sun.location).to_track_quat('-Z','Y').to_euler()
 for location,power,size in lights:
  bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(Vector((0,0,6))-light.location).to_track_quat('-Z','Y').to_euler()
 bpy.ops.object.camera_add(location=(15,-30,11));camera=bpy.context.object;scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=15
 camera.rotation_euler=(Vector((0,0,5.5))-camera.location).to_track_quat('-Z','Y').to_euler()
 scene.render.image_settings.file_format='PNG'
 for view in (('whole','detail','side') if a.side_view else ('whole','detail')):
  if view=='detail':camera.data.ortho_scale=6;camera.rotation_euler=(Vector((0,0,6.5 if a.field_appearance else 8))-camera.location).to_track_quat('-Z','Y').to_euler()
  if view=='side':
   camera.location=(30,15,11);camera.data.ortho_scale=15;camera.rotation_euler=(Vector((0,0,5.5))-camera.location).to_track_quat('-Z','Y').to_euler()
  scene.render.filepath=str(out/f'{seed}_{view}.png');bpy.ops.render.render(write_still=True)
  print('RENDER_COMPLETE',seed,view,flush=True)
  if a.annotation_smoke:
   from uchuva_lsystem.blender_annotations import render_crisp_calyx_annotations
   mask_dir=out/f'{seed}_{view}_annotations';mask_dir.mkdir(exist_ok=False)
   annotation=render_crisp_calyx_annotations(camera,mask_dir,width=900,height=1000)
   annotation.update(purpose='diagnostic_instance_contract_only',accepted_for_training=False,
    appearance_is_not_fruit_maturity=True,camera_projection='orthographic',
    orthographic_scale=float(camera.data.ortho_scale),rgb_path=str(out/f'{seed}_{view}.png'))
   (mask_dir/'annotations.json').write_text(json.dumps(annotation,indent=2))
   print('ANNOTATION_COMPLETE',seed,view,flush=True)
 records.append(dict(seed=seed,foliage=plant.metadata['foliage_reference_pilot'],architecture=plant.metadata['canopy_preference_pilot'],textures={k:dict(v.items()) for k,v in materials.items() if k.startswith(('leaf','calyx'))}))
(out/'manifest.json').write_text(json.dumps(dict(engine='Cycles OptiX',samples=24,records=records,accepted_for_dataset=False),indent=2,default=str))
