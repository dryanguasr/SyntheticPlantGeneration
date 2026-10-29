"""Explicit light/material interpretation; never changes morphological geometry."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path

from .appearance_profiles import resolved_profile


def geometry_digest(scene):
    digest=hashlib.sha256()
    for obj in sorted((o for o in scene.objects if o.type in {'MESH','CURVE','SURFACE'}),key=lambda o:o.name):
        if obj.type=='MESH':
            shape=([tuple(v.co) for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons])
        else:
            shape=(obj.data.bevel_depth,obj.data.bevel_resolution,obj.data.resolution_u,
                   [(s.type, s.use_cyclic_u, [(tuple(p.co),p.radius) for p in s.points],
                     [(tuple(p.co),tuple(p.handle_left),tuple(p.handle_right),p.radius) for p in s.bezier_points])
                    for s in obj.data.splines])
        digest.update(repr((obj.name,obj.type,[list(r) for r in obj.matrix_world],shape)).encode())
    return digest.hexdigest()


def create_material_sets(seed, profiles):
    import bpy
    from .appearance_legacy_materials import create_v142_materials
    from .blender_scene import create_project_materials
    previous=create_v142_materials(seed)
    candidate=create_project_materials(seed)
    options=profiles['materials']['candidate']
    seen=set()
    for key,mat in candidate.items():
        if not key.startswith(('leaf','calyx')) or mat.name in seen:continue
        seen.add(mat.name)
        nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
        for node in nodes:
            if node.type=='NORMAL_MAP':node.inputs['Strength'].default_value=options['normal_strength']
            if node.type=='BUMP' and 'micro' in node.name:
                node.inputs['Strength'].default_value=options['micro_strength']
                node.inputs['Distance'].default_value=options['micro_distance']
        for link in list(bsdf.inputs['Roughness'].links):
            remap=nodes.new('ShaderNodeMapRange')
            remap.inputs['To Min'].default_value=options['roughness_min'];remap.inputs['To Max'].default_value=options['roughness_max']
            links.new(link.from_socket,remap.inputs['Value']);links.new(remap.outputs['Result'],bsdf.inputs['Roughness'])
        mat['appearance_status']='manual_initial_guess_pending_human_review'
    # Three independent surface hypotheses: no geometry or latent fruit maturity edits.
    class_materials=[]
    for class_id,preset in enumerate(options['class_presets']):
        mat=candidate[preset].copy();mat.name=f'appearance_candidate_class_{class_id}'
        nodes=mat.node_tree.nodes;links=mat.node_tree.links;bsdf=nodes.get('Principled BSDF')
        albedo=next(n for n in nodes if n.type=='TEX_IMAGE' and n.name.endswith('_albedo'))
        multiplier=nodes.new('ShaderNodeMixRGB');multiplier.blend_type='MULTIPLY';multiplier.inputs[0].default_value=1
        multiplier.inputs[2].default_value=(*options['albedo_multiplier_linear'][class_id],1)
        links.new(albedo.outputs['Color'],multiplier.inputs[1])
        mask_path=Path(bpy.path.abspath(albedo.image.filepath)).with_name(Path(albedo.image.filepath).name.replace('_albedo','_vein_mask'))
        if not mask_path.is_file():raise FileNotFoundError(mask_path)
        vein=nodes.new('ShaderNodeTexImage');vein.image=bpy.data.images.load(str(mask_path),check_existing=True);vein.image.colorspace_settings.name='Non-Color'
        links.new(albedo.inputs['Vector'].links[0].from_socket,vein.inputs['Vector'])
        power=nodes.new('ShaderNodeMath');power.operation='POWER';power.inputs[1].default_value=options['vein_power'];links.new(vein.outputs['Color'],power.inputs[0])
        strength=nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=options['vein_factor'];links.new(power.outputs[0],strength.inputs[0])
        mix=nodes.new('ShaderNodeMixRGB');mix.inputs[2].default_value=options['vein_colors_linear'][class_id]
        links.new(strength.outputs[0],mix.inputs[0]);links.new(multiplier.outputs[0],mix.inputs[1]);links.new(mix.outputs[0],bsdf.inputs['Base Color'])
        if 'Emission Strength' in bsdf.inputs:bsdf.inputs['Emission Strength'].default_value=0
        mat['appearance_class_id']=class_id;mat['wear_fraction']=options['wear_fraction']
        class_materials.append(mat)
    return {'previous':previous,'candidate':candidate,
            'class_previous':[previous[k] for k in profiles['materials']['previous']['class_presets']],
            'class_candidate':class_materials}


def apply_materials(objects, sets, material_mode, assignments, *, focal=None, focal_class=None,
                    foliage_profiles=None, seed=0):
    for obj in objects:
        semantic=obj.get('uchuva_semantic_class')
        if semantic=='calyx':
            key=str(obj.get('uchuva_reproductive_instance_id'))
            if key not in assignments:raise ValueError(f'Missing class for {key}')
            cl=focal_class if focal is obj and focal_class is not None else assignments[key]['class_id']
            mat=sets['class_'+material_mode][cl]
        elif semantic=='leaf':
            profile=(foliage_profiles or {}).get(str(obj.get('uchuva_plant_id')))
            if profile is not None:
                from .appearance_diversity import leaf_appearance
                from .appearance_profiles import canonical_hash
                plant_id=str(obj.get('uchuva_plant_id'))
                leaf_id=str(obj.get('uchuva_organ_id',obj.name))
                key=leaf_appearance(seed,plant_id,leaf_id,profile)
                cache=sets.setdefault('_foliage_materials',{})
                signature=(material_mode,plant_id,key,canonical_hash(profile))
                if signature not in cache:
                    mat=sets[material_mode][key].copy()
                    mat.name=f'appearance_foliage_{plant_id}_{material_mode}_{key}'
                    nodes=mat.node_tree.nodes;links=mat.node_tree.links
                    bsdf=nodes.get('Principled BSDF')
                    hue=nodes.new('ShaderNodeHueSaturation')
                    hue.inputs['Hue'].default_value=.5+profile['hue_shift']
                    hue.inputs['Saturation'].default_value=profile['saturation']
                    hue.inputs['Value'].default_value=profile['value']
                    if bsdf.inputs['Base Color'].links:
                        links.new(bsdf.inputs['Base Color'].links[0].from_socket,hue.inputs['Color'])
                    else:hue.inputs['Color'].default_value=bsdf.inputs['Base Color'].default_value
                    links.new(hue.outputs['Color'],bsdf.inputs['Base Color'])
                    if 'Emission Strength' in bsdf.inputs:bsdf.inputs['Emission Strength'].default_value=0
                    mat['foliage_profile_sha256']=canonical_hash(profile)
                    cache[signature]=mat
                mat=cache[signature]
                obj['appearance_foliage_state']=profile['foliage']
                obj['appearance_leaf_material']=key
                obj.data.materials.clear();obj.data.materials.append(mat)
                continue
            # Preserve the morphology's original healthy/senescent choice across switches.
            key=obj.get('appearance_original_leaf_material')
            if key is None:
                original=obj.data.materials[0] if obj.data.materials else None
                key='leaf_senescent' if original == sets['previous'].get('leaf_senescent') else 'leaf'
                obj['appearance_original_leaf_material']=key
            mat=sets[material_mode][key]
        else:continue
        obj.data.materials.clear();obj.data.materials.append(mat)


def apply_profile(profiles,bank,camera,target,diagnostic_light=None):
    import bpy
    from mathutils import Vector
    config=resolved_profile(profiles,bank,diagnostic_light);p=config['lighting'];scene=bpy.context.scene
    for obj in list(scene.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    world=scene.world or bpy.data.worlds.new('appearance_world');scene.world=world;world.use_nodes=True
    nodes=world.node_tree.nodes;links=world.node_tree.links;nodes.clear()
    output=nodes.new('ShaderNodeOutputWorld');background=nodes.new('ShaderNodeBackground');sky=nodes.new('ShaderNodeTexSky')
    sky.sky_type=p['sky'];sky.sun_disc=False;sky.sun_elevation=math.radians(p['sun_elevation_deg']);sky.sun_rotation=math.radians(p['sun_azimuth_deg'])
    background.inputs['Strength'].default_value=p['world_strength'];links.new(sky.outputs['Color'],background.inputs['Color']);links.new(background.outputs[0],output.inputs['Surface'])
    data=bpy.data.lights.new('appearance_sun','SUN');data.energy=p['sun_energy'];data.angle=math.radians(p['sun_angle_deg'])
    sun=bpy.data.objects.new(data.name,data);scene.collection.objects.link(sun)
    sun.rotation_euler=(math.radians(90-p['sun_elevation_deg']),0,math.radians(p['sun_azimuth_deg']))
    if p['fill_energy']:
        data=bpy.data.lights.new('appearance_fill','AREA');data.energy=p['fill_energy'];data.size=3
        fill=bpy.data.objects.new(data.name,data);scene.collection.objects.link(fill)
        fill.location=camera.location+Vector((-1,0,1));fill.rotation_euler=(Vector(target)-fill.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.view_transform=config['color_management']['view_transform']
    scene.view_settings.look=config['color_management']['look'];scene.view_settings.gamma=config['color_management']['gamma']
    scene.view_settings.exposure=p['exposure_ev']
    config['effective_exposure_ev']=scene.view_settings.exposure
    return config
