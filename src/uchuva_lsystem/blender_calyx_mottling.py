"""Blender material interpreter for a soft, irregular patch field."""
import json


def make_review_material(base,plan,bump_scale=1.):
    mat=base.copy();mat.name=f'mottling_{plan.class_id}_{plan.name}_{plan.seed}'
    if not plan.patches:return mat
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
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

    coord=nodes.new('ShaderNodeTexCoord');shift=nodes.new('ShaderNodeVectorMath');shift.operation='ADD'
    shift.inputs[1].default_value=(plan.phase,.4*plan.phase,.7*plan.phase)
    links.new(coord.outputs['Generated'],shift.inputs[0])
    noises=[]
    for scale,detail in ((3.3,2),(28,4)):
        n=nodes.new('ShaderNodeTexNoise');n.inputs['Scale'].default_value=scale
        n.inputs['Detail'].default_value=detail;n.inputs['Roughness'].default_value=.7
        links.new(shift.outputs[0],n.inputs['Vector']);noises.append(n)
    macro,fine=noises
    warp=nodes.new('ShaderNodeVectorMath');warp.operation='SCALE';warp.inputs['Scale'].default_value=.20
    links.new(macro.outputs['Color'],warp.inputs[0])
    offset=nodes.new('ShaderNodeVectorMath');offset.operation='ADD';offset.inputs[1].default_value=(-.1,-.1,-.1)
    links.new(warp.outputs[0],offset.inputs[0])
    warped=nodes.new('ShaderNodeVectorMath');warped.operation='ADD'
    links.new(coord.outputs['Generated'],warped.inputs[0]);links.new(offset.outputs[0],warped.inputs[1])
    field=0.
    for patch in plan.patches:
        delta=nodes.new('ShaderNodeVectorMath');delta.operation='SUBTRACT';delta.inputs[1].default_value=patch.center
        links.new(warped.outputs[0],delta.inputs[0])
        scaled=nodes.new('ShaderNodeVectorMath');scaled.operation='DIVIDE';scaled.inputs[1].default_value=patch.radii
        links.new(delta.outputs[0],scaled.inputs[0])
        length=nodes.new('ShaderNodeVectorMath');length.operation='LENGTH';links.new(scaled.outputs[0],length.inputs[0])
        ramp=nodes.new('ShaderNodeMapRange');ramp.interpolation_type='SMOOTHSTEP';ramp.clamp=True
        ramp.inputs['From Min'].default_value=.25;ramp.inputs['From Max'].default_value=1.3
        ramp.inputs['To Min'].default_value=1;ramp.inputs['To Max'].default_value=0
        links.new(length.outputs['Value'],ramp.inputs['Value'])
        field=math_node('MAXIMUM',field,math_node('MULTIPLY',ramp.outputs['Result'],patch.strength))
    windows=nodes.new('ShaderNodeMapRange');windows.interpolation_type='SMOOTHSTEP';windows.clamp=True
    windows.inputs['From Min'].default_value=.18;windows.inputs['From Max'].default_value=.54
    windows.inputs['To Min'].default_value=.24;windows.inputs['To Max'].default_value=1
    links.new(macro.outputs['Fac'],windows.inputs['Value'])
    grain=math_node('MULTIPLY_ADD',fine.outputs['Fac'],.28,.72)
    amount=math_node('MULTIPLY',math_node('MULTIPLY',field,windows.outputs['Result']),math_node('MULTIPLY',grain,plan.max_dark_mix))
    brown_strength=math_node('MULTIPLY_ADD',macro.outputs['Fac'],plan.browning*.6,plan.browning*.4)
    brown=mix(old,(.65,.42,.24,1),brown_strength,'MULTIPLY')
    # Multiply the existing substrate rather than paint a featureless black.
    dark=mix(brown,(.08,.055,.035,1),1.,'MULTIPLY')
    colored=mix(brown,dark,amount);links.new(colored,bsdf.inputs['Base Color'])
    if plan.class_id==2 and plan.contraction:
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.2+.45*plan.contraction
        bump.inputs['Distance'].default_value=.03*bump_scale*plan.contraction;links.new(fine.outputs['Fac'],bump.inputs['Height'])
        for link in list(bsdf.inputs['Normal'].links):links.new(link.from_socket,bump.inputs['Normal'])
        links.new(bump.outputs[0],bsdf.inputs['Normal'])
    # A diffuse transmitted lobe represents papery backlighting. Alpha remains
    # one: there are no transparent holes, missing organs or changed ID masks.
    translucent=nodes.new('ShaderNodeBsdfTranslucent');links.new(colored,translucent.inputs['Color'])
    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
    previous=output.inputs['Surface'].links[0].from_socket
    sheet=nodes.new('ShaderNodeMixShader');sheet.inputs[0].default_value=plan.transmitted_diffuse_mix
    links.new(previous,sheet.inputs[1]);links.new(translucent.outputs[0],sheet.inputs[2]);links.new(sheet.outputs[0],output.inputs['Surface'])
    if 'Alpha' in bsdf.inputs:bsdf.inputs['Alpha'].default_value=1
    mat['approval_mottling_plan']=json.dumps(plan.to_dict(),sort_keys=True)
    return mat
