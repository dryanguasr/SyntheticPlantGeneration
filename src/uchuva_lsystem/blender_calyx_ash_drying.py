"""Papery optical roughness over preserved meshes and transmitted diffuse."""
from .blender_calyx_dry_refinement import make_review_material as prior_material


def make_review_material(base, plan, bump_scale=1., *, map_manifest):
    import json
    from pathlib import Path
    mat = prior_material(base, plan, bump_scale, map_manifest=map_manifest)
    if plan.class_id != 2 or plan.name == 'historical':
        return mat
    manifest = json.loads(Path(map_manifest).read_text(encoding='utf-8'))
    stage = next(iter(manifest['presets'].values()))['stages'][plan.name]
    severity = stage['severity']
    if not severity:
        return mat
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes.get('Principled BSDF')
    original = bsdf.inputs['Normal'].links[0].from_socket if bsdf.inputs['Normal'].is_linked else None
    tex = nodes.new('ShaderNodeTexCoord')
    noise = nodes.new('ShaderNodeTexNoise'); noise.name = 'dry_paper_grain'
    noise.inputs['Scale'].default_value = 115
    noise.inputs['Detail'].default_value = 3
    noise.inputs['Roughness'].default_value = .72
    links.new(tex.outputs['Generated'], noise.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump'); bump.name = 'dry_paper_optical_relief'
    bump.inputs['Strength'].default_value = .46 * severity
    bump.inputs['Distance'].default_value = .045 * severity * bump_scale
    links.new(noise.outputs['Fac'], bump.inputs['Height'])
    if original is not None:
        links.new(original, bump.inputs['Normal'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    for node in nodes:
        if node.type == 'BSDF_TRANSLUCENT':
            links.new(bump.outputs['Normal'], node.inputs['Normal'])
    mat['ash_drying_revision'] = manifest['version']
    mat['dry_relief_scope'] = 'optical bump only; unchanged mesh and alpha'
    return mat
