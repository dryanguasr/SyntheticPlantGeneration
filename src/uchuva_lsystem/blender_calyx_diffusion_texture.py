"""Load the newly baked, internally consistent texture maps on copied materials."""
from pathlib import Path
import json


def make_review_material(base,plan,bump_scale=1.,*,map_manifest):
    import bpy
    from .nodal_automation import sha
    mat=base.copy();mat.name=f'diffusion_{plan.class_id}_{plan.name}_{plan.seed}'
    if plan.name=='historical':return mat
    manifest=json.loads(Path(map_manifest).read_text(encoding='utf-8'))
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
    albedo=next(n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
    preset=Path(bpy.path.abspath(albedo.image.filepath)).name.removesuffix('_albedo.png')
    entry=manifest['presets'][preset];maps=entry['stages'][plan.name]
    if maps['step']!=plan.snapshot_step:raise ValueError('Texture stage does not match the frozen diffusion plan')
    uv=albedo.inputs['Vector'].links[0].from_socket
    for kind,socket in (('albedo','Base Color'),('roughness','Roughness')):
        path=Path(maps[kind]);assert sha(path)==maps[kind+'_sha256']
        node=nodes.new('ShaderNodeTexImage');node.name=f'diffused_{kind}';node.image=bpy.data.images.load(str(path),check_existing=True)
        if kind!='albedo':node.image.colorspace_settings.name='Non-Color'
        node.extension='REPEAT';links.new(uv,node.inputs['Vector']);links.new(node.outputs['Color'],bsdf.inputs[socket])
        if kind=='albedo':color=node.outputs['Color']
    assert sha(entry['normal'])==entry['normal_sha256']
    for node in nodes:
        if node.type=='TEX_IMAGE' and node.name.endswith('_normal'):
            node.image=bpy.data.images.load(entry['normal'],check_existing=True);node.image.colorspace_settings.name='Non-Color'
    translucent=nodes.new('ShaderNodeBsdfTranslucent');links.new(color,translucent.inputs['Color'])
    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    old=output.inputs['Surface'].links[0].from_socket
    sheet=nodes.new('ShaderNodeMixShader');sheet.inputs[0].default_value=plan.transmitted_diffuse_mix
    links.new(old,sheet.inputs[1]);links.new(translucent.outputs[0],sheet.inputs[2]);links.new(sheet.outputs[0],output.inputs['Surface'])
    if 'Alpha' in bsdf.inputs:bsdf.inputs['Alpha'].default_value=1
    mat['diffusion_texture_plan']=json.dumps(plan.to_dict(),sort_keys=True)
    return mat
