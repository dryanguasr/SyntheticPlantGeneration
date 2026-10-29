"""Blender interpretation of a portable earth/litter plan, without crop edits."""
import math


def apply_cultivation_floor(plan, terrain_name):
    import bpy
    from .blender_annotations import tag_annotation_object
    seed=plan['seed'];material=bpy.data.materials.new('cultivation_earthen_floor_'+str(seed));material.use_nodes=True
    nodes=material.node_tree.nodes;links=material.node_tree.links;nodes.clear()
    out=nodes.new('ShaderNodeOutputMaterial');bsdf=nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value=.93;links.new(bsdf.outputs[0],out.inputs['Surface'])
    coord=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Location'].default_value=(seed%83,seed%37,0)
    mapping.inputs['Rotation'].default_value[2]=(seed%17)*.37
    links.new(coord.outputs['Object'],mapping.inputs['Vector'])
    broad=nodes.new('ShaderNodeTexNoise');broad.inputs['Scale'].default_value=.19
    broad.inputs['Detail'].default_value=3.5;broad.inputs['Distortion'].default_value=.7
    links.new(mapping.outputs[0],broad.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.23
    ramp.color_ramp.elements[0].color=(.032,.012,.0035,1)
    ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=(.22,.105,.031,1)
    ramp.color_ramp.elements.new(.5).color=(.105,.043,.012,1)
    links.new(broad.outputs['Fac'],ramp.inputs[0]);color=ramp.outputs['Color']
    image=bpy.data.images.get('UchuvaAsset_brown_mud_diff_2k')
    if image is not None:
        tex=nodes.new('ShaderNodeTexImage');tex.image=image
        links.new(mapping.outputs[0],tex.inputs['Vector'])
        bw=nodes.new('ShaderNodeRGBToBW');links.new(tex.outputs['Color'],bw.inputs[0])
        scale=nodes.new('ShaderNodeMapRange');scale.inputs['From Min'].default_value=.03
        scale.inputs['From Max'].default_value=.5;scale.inputs['To Min'].default_value=.65;scale.inputs['To Max'].default_value=1.3
        links.new(bw.outputs[0],scale.inputs['Value'])
        mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.65
        links.new(color,mix.inputs[1]);links.new(scale.outputs[0],mix.inputs[2]);color=mix.outputs[0]
    links.new(color,bsdf.inputs['Base Color'])
    fine=nodes.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=18.;fine.inputs['Detail'].default_value=4.
    links.new(mapping.outputs[0],fine.inputs['Vector']);bump=nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value=.35;bump.inputs['Distance'].default_value=.035
    links.new(fine.outputs['Fac'],bump.inputs['Height']);links.new(bump.outputs[0],bsdf.inputs['Normal'])
    terrain=bpy.data.objects[terrain_name];terrain.data.materials.clear();terrain.data.materials.append(material)
    tones=[(.065,.026,.006,1),(.17,.073,.017,1),(.31,.16,.043,1),(.095,.057,.018,1)]
    materials=[]
    for index,tone in enumerate(tones):
        m=bpy.data.materials.new(f'cultivation_litter_{seed}_{index}');m.use_nodes=True
        b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=tone;b.inputs['Roughness'].default_value=.95
        materials.append(m)
    vertices=[];faces=[];indices=[]
    for item in plan['litter']+plan['twigs']:
        # Low curled fragments: every vertex is below 0.01 BU.
        x,y,z=item['x'],item['y'],item['z'];length,width=item['length'],item['width'];angle=item['angle']
        shape=([(0,0,0),(.25,.7,.002),(.65,1.,.004),(1.,0,.001),(.65,-1.,.003),(.25,-.6,.001)]
               if item['kind']=='leaf' else [(0,-1,0),(1,-.5,.001),(1,1,.002),(0,.7,.001)])
        face=[]
        for u,v,dz in shape:
            along=(u-.5)*length;side=v*width/2
            face.append(len(vertices));vertices.append((x+along*math.cos(angle)-side*math.sin(angle),y+along*math.sin(angle)+side*math.cos(angle),z+dz))
        faces.append(tuple(face));indices.append(item['tone'])
    mesh=bpy.data.meshes.new('cultivation_litter_mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new('cultivation_ground_litter',mesh);bpy.context.scene.collection.objects.link(obj)
    for m in materials:mesh.materials.append(m)
    for polygon,index in zip(mesh.polygons,indices):polygon.material_index=index
    tag_annotation_object(obj,'soil',organ_id=obj.name)
    return dict(version=plan['version'],seed=seed,ground_material=material.name,litter_leaves=len(plan['litter']),
                twigs=len(plan['twigs']),vegetation_clusters=len(plan['vegetation_centres']),
                organ_emission=False,crop_geometry_modified=False,context_contacts='not exhaustively certified')
