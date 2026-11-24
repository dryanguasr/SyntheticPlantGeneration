"""Interpret new baked albedo with the campaign's frozen class color gains."""
import json
from pathlib import Path
from .blender_calyx_diffusion_texture import make_review_material as create_material


def make_review_material(base,plan,bump_scale=1.,*,map_manifest):
    mat=create_material(base,plan,bump_scale,map_manifest=map_manifest)
    if plan.name=='historical':return mat
    manifest=json.loads(Path(map_manifest).read_text(encoding='utf-8'))
    gain=manifest['class_albedo_multiplier_linear'][str(plan.class_id)]
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
    original=bsdf.inputs['Base Color'].links[0].from_socket
    multiply=nodes.new('ShaderNodeMixRGB');multiply.name='frozen_profile_albedo_gain'
    multiply.blend_type='MULTIPLY';multiply.inputs[0].default_value=1;multiply.inputs[2].default_value=(*gain,1)
    links.new(original,multiply.inputs[1]);links.new(multiply.outputs[0],bsdf.inputs['Base Color'])
    for node in nodes:
        if node.type=='BSDF_TRANSLUCENT':links.new(multiply.outputs[0],node.inputs['Color'])
    mat['review_profile_albedo_gain']=json.dumps(gain)
    return mat
