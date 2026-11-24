"""Preserve frozen profile gains and install the matching dry normal per stage."""
from pathlib import Path
import json
from .blender_calyx_diffusion_profile import make_review_material as create_material


def make_review_material(base,plan,bump_scale=1.,*,map_manifest):
    import bpy
    from .nodal_automation import sha
    mat=create_material(base,plan,bump_scale,map_manifest=map_manifest)
    if plan.name=='historical':return mat
    data=json.loads(Path(map_manifest).read_text(encoding='utf-8'))
    albedo=next(n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
    preset=Path(bpy.path.abspath(albedo.image.filepath)).name.removesuffix('_albedo.png')
    stage=data['presets'][preset]['stages'][plan.name]
    assert sha(stage['normal'])==stage['normal_sha256']
    for node in mat.node_tree.nodes:
        if node.type=='TEX_IMAGE' and node.name.endswith('_normal'):
            node.image=bpy.data.images.load(stage['normal'],check_existing=True);node.image.colorspace_settings.name='Non-Color'
    mat['dry_texture_revision']=data['version']
    return mat
