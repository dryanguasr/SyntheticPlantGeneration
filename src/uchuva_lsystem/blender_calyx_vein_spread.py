"""Read registered vein arrival maps using the exact original calyx UVs."""
import json
from pathlib import Path


def make_review_material(base,plan,bump_scale=1.,*,map_manifest):
    import bpy
    manifest=json.loads(Path(map_manifest).read_text(encoding='utf-8'))
    mat=base.copy();mat.name=f'vein_spread_{plan.class_id}_{plan.name}_{plan.seed}'
    if plan.progress==0:return mat
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
    albedo=next(n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
    preset=Path(bpy.path.abspath(albedo.image.filepath)).name.removesuffix('_albedo.png')
    item=manifest['presets'][preset];path=Path(item['map'])
    from .nodal_automation import sha
    if sha(path)!=item['map_sha256']:raise ValueError('Arrival map changed')
    old=bsdf.inputs['Base Color'].links[0].from_socket

    def math_node(operation,a,b=None,c=None):
        n=nodes.new('ShaderNodeMath');n.operation=operation
        for i,value in enumerate((a,b,c)):
            if value is None:continue
            if isinstance(value,(float,int)):n.inputs[i].default_value=value
            else:links.new(value,n.inputs[i])
        return n.outputs[0]

    def mix(a,b,factor,blend='MIX'):
        n=nodes.new('ShaderNodeMixRGB');n.blend_type=blend
        if isinstance(factor,(float,int)):n.inputs[0].default_value=factor
        else:links.new(factor,n.inputs[0])
        for slot,value in ((1,a),(2,b)):
            if isinstance(value,tuple):n.inputs[slot].default_value=value
            else:links.new(value,n.inputs[slot])
        return n.outputs[0]

    source_uv=albedo.inputs['Vector'].links[0].from_socket
    uv=nodes.new('ShaderNodeSeparateXYZ');links.new(source_uv,uv.inputs[0])
    # U is periodic. Keep V within half a texel so distal v=1 never wraps to
    # proximal v=0 on an image node with REPEAT extension.
    eps=.5/manifest['resolution'];bounded_v=math_node('MULTIPLY_ADD',uv.outputs['Y'],1-2*eps,eps)
    coords=nodes.new('ShaderNodeCombineXYZ');links.new(uv.outputs['X'],coords.inputs['X']);links.new(bounded_v,coords.inputs['Y'])
    image=nodes.new('ShaderNodeTexImage');image.name='registered_vein_arrival_rgb'
    image.image=bpy.data.images.load(str(path),check_existing=True);image.image.colorspace_settings.name='Non-Color'
    image.extension='REPEAT';image.interpolation='Linear';links.new(coords.outputs[0],image.inputs['Vector'])
    split=nodes.new('ShaderNodeSeparateColor');split.mode='RGB';links.new(image.outputs['Color'],split.inputs[0])
    arrival=math_node('MULTIPLY',split.outputs['Red'],manifest['arrival_scale'])
    reached=nodes.new('ShaderNodeMapRange');reached.interpolation_type='SMOOTHSTEP';reached.clamp=True
    reached.inputs['From Min'].default_value=plan.progress-.045;reached.inputs['From Max'].default_value=plan.progress+.045
    reached.inputs['To Min'].default_value=1;reached.inputs['To Max'].default_value=0
    links.new(arrival,reached.inputs['Value'])
    proximal=math_node('MULTIPLY_ADD',uv.outputs['Y'],-.28,1.)
    windows=math_node('MULTIPLY_ADD',split.outputs['Blue'],.35,.65)
    halo=math_node('MULTIPLY',math_node('MULTIPLY',reached.outputs['Result'],proximal),math_node('MULTIPLY',windows,plan.halo_strength))
    vein=math_node('POWER',split.outputs['Green'],.5)
    vascular=nodes.new('ShaderNodeMapRange');vascular.interpolation_type='SMOOTHSTEP';vascular.clamp=True
    vascular.inputs['From Min'].default_value=plan.progress-.035;vascular.inputs['From Max'].default_value=plan.progress+.035
    vascular.inputs['To Min'].default_value=1;vascular.inputs['To Max'].default_value=0
    links.new(math_node('MULTIPLY',arrival,.62),vascular.inputs['Value'])
    core=math_node('MULTIPLY',math_node('MULTIPLY',vein,vascular.outputs['Result']),
        math_node('MULTIPLY',math_node('MULTIPLY_ADD',uv.outputs['Y'],-.12,1.),plan.vein_strength))
    brown=mix(old,(.46,.25,.12,1),halo,'MULTIPLY')
    dark=mix(brown,(.065,.035,.022,1),1.,'MULTIPLY')
    amount=math_node('MAXIMUM',core,math_node('MULTIPLY',halo,.84))
    colored=mix(brown,dark,amount);links.new(colored,bsdf.inputs['Base Color'])
    # Keep the previous surface relief and papery transmitted response.
    if plan.class_id==2 and plan.contraction:
        noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=28;noise.inputs['Detail'].default_value=4
        links.new(source_uv,noise.inputs['Vector'])
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.2+.45*plan.contraction
        bump.inputs['Distance'].default_value=.03*bump_scale*plan.contraction;links.new(noise.outputs['Fac'],bump.inputs['Height'])
        for link in list(bsdf.inputs['Normal'].links):links.new(link.from_socket,bump.inputs['Normal'])
        links.new(bump.outputs[0],bsdf.inputs['Normal'])
    translucent=nodes.new('ShaderNodeBsdfTranslucent');links.new(colored,translucent.inputs['Color'])
    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    previous=output.inputs['Surface'].links[0].from_socket
    sheet=nodes.new('ShaderNodeMixShader');sheet.inputs[0].default_value=plan.transmitted_diffuse_mix
    links.new(previous,sheet.inputs[1]);links.new(translucent.outputs[0],sheet.inputs[2]);links.new(sheet.outputs[0],output.inputs['Surface'])
    if 'Alpha' in bsdf.inputs:bsdf.inputs['Alpha'].default_value=1
    mat['approval_vein_spread_plan']=json.dumps(plan.to_dict(),sort_keys=True)
    mat['vein_spread_source_mask_sha256']=item['source_mask_sha256']
    return mat
