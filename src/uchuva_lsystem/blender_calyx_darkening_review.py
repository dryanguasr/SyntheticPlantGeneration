"""Surface-only interpreter; preserves complete morphology and mask geometry."""


def make_review_material(base,plan,bump_scale=1.):
    mat=base.copy();mat.name=f'approval_{plan.class_id}_{plan.name}_{plan.seed}'
    if plan.intensity==0 and plan.browning==0:return mat
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
    old=bsdf.inputs['Base Color'].links[0].from_socket
    coord=nodes.new('ShaderNodeTexCoord');split=nodes.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Generated'],split.inputs[0])
    shifted=nodes.new('ShaderNodeVectorMath');shifted.operation='ADD';shifted.inputs[1].default_value=(plan.phase,.4*plan.phase,.7*plan.phase)
    links.new(coord.outputs['Generated'],shifted.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=8;noise.inputs['Detail'].default_value=4;noise.inputs['Roughness'].default_value=.72
    links.new(shifted.outputs[0],noise.inputs['Vector'])
    brown=nodes.new('ShaderNodeMixRGB');brown.inputs[0].default_value=plan.browning;brown.inputs[2].default_value=(.22,.105,.035,1);links.new(old,brown.inputs[1])
    inverse=nodes.new('ShaderNodeMath');inverse.operation='SUBTRACT';inverse.inputs[0].default_value=1;links.new(split.outputs['Z'],inverse.inputs[1])
    jitter=nodes.new('ShaderNodeMath');jitter.operation='MULTIPLY_ADD';jitter.inputs[1].default_value=.18;jitter.inputs[2].default_value=-.09;links.new(noise.outputs['Fac'],jitter.inputs[0])
    rank=nodes.new('ShaderNodeMath');rank.operation='ADD';links.new(inverse.outputs[0],rank.inputs[0]);links.new(jitter.outputs[0],rank.inputs[1])
    ramp=nodes.new('ShaderNodeMapRange');ramp.clamp=True;ramp.inputs['From Min'].default_value=plan.proximal_extent-.04;ramp.inputs['From Max'].default_value=plan.proximal_extent+.04
    ramp.inputs['To Min'].default_value=1;ramp.inputs['To Max'].default_value=0;links.new(rank.outputs[0],ramp.inputs['Value'])
    amount=nodes.new('ShaderNodeMath');amount.operation='MULTIPLY';amount.inputs[1].default_value=plan.intensity;links.new(ramp.outputs['Result'],amount.inputs[0])
    dark_palette=nodes.new('ShaderNodeValToRGB');dark_palette.color_ramp.elements[0].color=(.002,.0015,.001,1)
    dark_palette.color_ramp.elements[1].color=(.035,.018,.009,1);links.new(noise.outputs['Fac'],dark_palette.inputs[0])
    mix=nodes.new('ShaderNodeMixRGB');links.new(amount.outputs[0],mix.inputs[0]);links.new(brown.outputs[0],mix.inputs[1]);links.new(dark_palette.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],bsdf.inputs['Base Color'])
    if plan.class_id==2 and plan.contraction>0:
        bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.2+.45*plan.contraction
        bump.inputs['Distance'].default_value=.03*bump_scale*plan.contraction;links.new(noise.outputs['Fac'],bump.inputs['Height'])
        for link in list(bsdf.inputs['Normal'].links):links.new(link.from_socket,bump.inputs['Normal'])
        links.new(bump.outputs[0],bsdf.inputs['Normal'])
    mat['approval_darkening_plan']=__import__('json').dumps(plan.to_dict(),sort_keys=True)
    return mat
