"""Archived project-authored v142 shader behavior for paired controls.
Source SHA256: 312985e61e31080a2ba040438880441a87aeec5887b19576736e41bcf9531c3d.
Kept separate from candidate materials; this does not define plant architecture.
"""
from pathlib import Path
from types import SimpleNamespace
import bpy
from uchuva_lsystem.blender_scene import create_project_materials
from uchuva_lsystem.matte_organ_review import apply_matte_organ_review
def create_v142_materials(seed):
    a=SimpleNamespace(leaf_cell_relief=True,dark_calyx_veins=True,graded_leaf_color=True)
    materials=create_project_materials(seed);apply_matte_organ_review(materials)
    for key,mat in materials.items():
     if not key.startswith(('leaf','calyx')):continue
     for node in mat.node_tree.nodes:
      if node.type=='NORMAL_MAP':
       node.inputs['Strength'].default_value=.40;mat['review_normal_strength']=.40
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
      bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.003
      if bsdf.inputs['Normal'].links:links.new(bsdf.inputs['Normal'].links[0].from_socket,bump.inputs['Normal'])
      links.new(uv.outputs['UV'],cells.inputs['Vector']);links.new(cells.outputs['Distance'],bump.inputs['Height']);links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
      mat['review_cell_relief']='UV cellular bump, scale22 strength0.18 distance0.003; uncalibrated appearance only, not anatomical venation'
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
      bsdf=nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=.94
      dry='dry' in key;source=albedo.outputs['Color']
      if dry:
       noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=5.5;noise.inputs['Detail'].default_value=3
       if albedo.inputs['Vector'].links:links.new(albedo.inputs['Vector'].links[0].from_socket,noise.inputs['Vector'])
       ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.35;ramp.color_ramp.elements[0].color=(0,0,0,1);ramp.color_ramp.elements[1].position=.7;ramp.color_ramp.elements[1].color=(.8,.8,.8,1)
       links.new(noise.outputs['Fac'],ramp.inputs[0]);patch=nodes.new('ShaderNodeMixRGB');patch.inputs[2].default_value=(.19,.065,.022,1)
       links.new(ramp.outputs[0],patch.inputs[0]);links.new(source,patch.inputs[1]);source=patch.outputs[0]
      power=nodes.new('ShaderNodeMath');power.operation='POWER';power.inputs[1].default_value=.48 if dry else .62
      links.new(mask.outputs['Color'],power.inputs[0]);mix=nodes.new('ShaderNodeMixRGB');mix.inputs[2].default_value=(.055,.024,.025,1) if dry else (.075,.055,.065,1)
      links.new(power.outputs[0],mix.inputs[0]);links.new(source,mix.inputs[1]);links.new(mix.outputs[0],bsdf.inputs['Base Color'])
      mat['review_v139']='Existing UV veins dark and matte, ochre/brown patches in dry appearance only; user references 1 and 2; no fruit maturity inference'
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
    # V103: texture-only leaf detail, including graded materials.
    seen_leaf_detail=set()
    for key,mat in materials.items():
     if not key.startswith('leaf') or mat.name in seen_leaf_detail:continue
     seen_leaf_detail.add(mat.name)
     nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
     albedo=next((n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo')),None)
     if albedo is None:continue
     mask_path=Path(bpy.path.abspath(albedo.image.filepath)).with_name(Path(albedo.image.filepath).name.replace('_albedo','_vein_mask'))
     if not mask_path.exists():raise FileNotFoundError(mask_path)
     mask=nodes.new('ShaderNodeTexImage');mask.name='review_v103_leaf_veins';mask.image=bpy.data.images.load(str(mask_path),check_existing=True);mask.image.colorspace_settings.name='Non-Color'
     if albedo.inputs['Vector'].links:links.new(albedo.inputs['Vector'].links[0].from_socket,mask.inputs['Vector'])
     source=bsdf.inputs['Base Color'].links[0].from_socket
     strength=nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=.55
     # Lift faint mask signals; intensity is only a proxy, not anatomical order.
     fine=nodes.new('ShaderNodeMath');fine.operation='POWER';fine.inputs[1].default_value=.35
     links.new(mask.outputs['Color'],fine.inputs[0])
     links.new(fine.outputs[0],strength.inputs[0])
     vein_color=nodes.new('ShaderNodeMixRGB');vein_color.inputs[2].default_value=(.11,.115,.055,1) if mat.get('review_color_blend',0)>.5 else (.19,.28,.10,1)
     bsdf.inputs['Roughness'].default_value=.92
     links.new(strength.outputs[0],vein_color.inputs[0]);links.new(source,vein_color.inputs[1]);links.new(vein_color.outputs[0],bsdf.inputs['Base Color'])
     relief=nodes.new('ShaderNodeBump');relief.inputs['Strength'].default_value=.30;relief.inputs['Distance'].default_value=.004
     if bsdf.inputs['Normal'].links:links.new(bsdf.inputs['Normal'].links[0].from_socket,relief.inputs['Normal'])
     links.new(fine.outputs[0],relief.inputs['Height']);links.new(relief.outputs['Normal'],bsdf.inputs['Normal'])
     mat['review_v103']='V106 existing UV mask power .35, color factor .55; bump .30/.004; faint signal proxy, not anatomical order; no mesh displacement; engineering heuristic'

    return materials
