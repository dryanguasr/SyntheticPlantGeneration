"""Blender interpreter for an explicit calyx shell deformation/material plan."""
import json
from .calyx_deterioration import deform_calyx_point


def apply_shell_state(obj,state,reference_length,reference_radius,base_material):
    """A new mesh/material copy only; never modify an admitted plant or asset."""
    obj.data=obj.data.copy()
    for vertex in obj.data.vertices:
        vertex.co=deform_calyx_point(vertex.co,length=reference_length,radius=reference_radius,state=state)
    obj.data.update();obj['calyx_deterioration_plan']=json.dumps(state.to_dict(),sort_keys=True)
    obj['full_plant_admission']='not_assessed_organ_fixture_only'
    if state.severity==0:return
    mat=base_material.copy();mat.name=f'deterioration_{state.seed}_{state.severity:.2f}'
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
    original=bsdf.inputs['Base Color'].links[0].from_socket
    coord=nodes.new('ShaderNodeTexCoord');split=nodes.new('ShaderNodeSeparateXYZ');links.new(coord.outputs['Generated'],split.inputs[0])
    shifted=nodes.new('ShaderNodeVectorMath');shifted.operation='ADD'
    shifted.inputs[1].default_value=(state.phase,state.phase*.73,state.phase*.31);links.new(coord.outputs['Generated'],shifted.inputs[0])
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=7
    noise.inputs['Detail'].default_value=5;noise.inputs['Roughness'].default_value=.72;links.new(shifted.outputs['Vector'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.28;ramp.color_ramp.elements[1].position=.72
    ramp.color_ramp.elements[0].color=(.095,.037,.012,1);ramp.color_ramp.elements[1].color=(.39,.245,.105,1)
    links.new(noise.outputs['Fac'],ramp.inputs[0])
    brown=nodes.new('ShaderNodeMixRGB');brown.inputs[0].default_value=state.brown_coverage
    links.new(original,brown.inputs[1]);links.new(ramp.outputs[0],brown.inputs[2])
    bleach=nodes.new('ShaderNodeMixRGB');bleach.inputs[0].default_value=state.bleaching
    links.new(brown.outputs[0],bleach.inputs[1]);bleach.inputs[2].default_value=(.36,.29,.205,1)
    # Local +Z is proximal. Noise breaks up the boundary rather than a hard band.
    jagged=nodes.new('ShaderNodeMath');jagged.operation='MULTIPLY_ADD'
    links.new(noise.outputs['Fac'],jagged.inputs[0]);jagged.inputs[1].default_value=.18;jagged.inputs[2].default_value=-.09
    add=nodes.new('ShaderNodeMath');add.operation='ADD';links.new(split.outputs['Z'],add.inputs[0]);links.new(jagged.outputs[0],add.inputs[1])
    neck=nodes.new('ShaderNodeMapRange');neck.clamp=True
    neck.inputs['From Min'].default_value=.94-.33*state.severity;neck.inputs['From Max'].default_value=.99-.18*state.severity
    links.new(add.outputs[0],neck.inputs['Value'])
    amount=nodes.new('ShaderNodeMath');amount.operation='MULTIPLY';amount.inputs[1].default_value=state.proximal_darkening;links.new(neck.outputs['Result'],amount.inputs[0])
    dark=nodes.new('ShaderNodeMixRGB');links.new(amount.outputs[0],dark.inputs[0]);links.new(bleach.outputs[0],dark.inputs[1]);dark.inputs[2].default_value=(.006,.004,.003,1)
    links.new(dark.outputs[0],bsdf.inputs['Base Color'])
    fine=nodes.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=32;fine.inputs['Detail'].default_value=4
    links.new(shifted.outputs['Vector'],fine.inputs['Vector'])
    bump=nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12+.5*state.severity
    bump.inputs['Distance'].default_value=.007+.065*state.severity;links.new(fine.outputs['Fac'],bump.inputs['Height'])
    for link in list(bsdf.inputs['Normal'].links):links.new(link.from_socket,bump.inputs['Normal'])
    links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    for link in list(bsdf.inputs['Roughness'].links):links.remove(link)
    bsdf.inputs['Roughness'].default_value=.84+.13*state.severity
    obj.data.materials.clear();obj.data.materials.append(mat)
