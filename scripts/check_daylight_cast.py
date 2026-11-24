"""Controlled optical probe, not a plant admission or dataset capture.

Preserve calyx/floor albedos while comparing atmosphere, camera white balance
and ambient-radiance chroma. The diagnostic fixtures are isolated hollow shells.
"""
from pathlib import Path
import sys,math,json
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO/'src'))
import bpy
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
from uchuva_lsystem.nodal_automation import read,write,sha
from uchuva_lsystem.blender_appearance import apply_profile
from uchuva_lsystem.capture_plan import profiles_for_condition


def run(out, neutral_mix=None):
    prior=REPO/'outputs/blue_sky_sparse_samples_20261111'
    for p,h in read(prior/'source_lock.json')['files'].items():assert sha(p)==h,p
    source=Path(read(prior/'plan.json')['source'])
    assert read(source/'pause_requested.json')['active']
    fixture=REPO/'outputs/calyx_ash_drying_20261111/organ_fixtures.blend'
    bpy.ops.wm.open_mainfile(filepath=str(fixture));scene=bpy.context.scene
    original_geometry={o.name:[tuple(v.co) for v in o.data.vertices] for o in scene.objects if o.type=='MESH'}
    for o in scene.objects:
        if o.get('approval_fixture'):
            o.hide_render=o.name not in {'approval_1_4','approval_1_5','approval_1_6','ped_1_4','ped_1_5','ped_1_6'}
    # Append the actual floor shader; do not recreate or recolor its albedo.
    checkpoint=source/'dataset/scenes/scene_027/scene.blend'
    with bpy.data.libraries.load(str(checkpoint),link=False) as (a,b):
        names=[n for n in a.materials if n.startswith('cultivation_earthen_floor_')]
        assert len(names)==1,names
        b.materials=names
    floor_mat=b.materials[0]
    bpy.ops.mesh.primitive_plane_add(size=120,location=(28,0,-1.5));floor=bpy.context.object;floor.name='probe_floor';floor.data.materials.append(floor_mat)
    grey=bpy.data.materials.new('probe_neutral_diffuse');grey.use_nodes=True
    n=grey.node_tree.nodes;n.clear();d=n.new('ShaderNodeBsdfDiffuse');d.inputs['Color'].default_value=(.18,.18,.18,1)
    output=n.new('ShaderNodeOutputMaterial');grey.node_tree.links.new(d.outputs[0],output.inputs[0])
    bpy.ops.mesh.primitive_plane_add(size=2.6,location=(20.5,0,2),rotation=(math.pi/2,0,0))
    card=bpy.context.object;card.name='probe_grey_card';card.data.materials.append(grey)
    camera=scene.camera;camera.location=(28,-30,5)
    camera.rotation_euler=(Vector((28,0,1.5))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO';camera.data.ortho_scale=23
    scene.render.resolution_x=960;scene.render.resolution_y=540;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.cycles.samples=16;scene.cycles.use_denoising=True
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
    for device in prefs.devices:device.use=device.type=='OPTIX'
    scene.cycles.device='GPU'
    profiles=read(source/'profiles.json');c=read(prior/'scene_027_view_010/view.json')['lighting']['capture_condition']
    records=[]
    variants=[('baseline',0.,None,False),('atmosphere_defaults',0.,None,True),
              ('white_balance_9000',0.,9000,False),('white_balance_12000',0.,12000,False),
              ('ambient_chroma_070',.70,None,False)]
    if neutral_mix is not None:
        variants=[('confirmed_ambient',neutral_mix,None,False)]
    for name,mix,temperature,defaults in variants:
        p,light=profiles_for_condition(profiles,c);config=apply_profile(p,'LT',camera,(28,0,1.5),light)
        nodes=scene.world.node_tree.nodes;links=scene.world.node_tree.links
        sky=next(n for n in nodes if n.type=='TEX_SKY');background=next(n for n in nodes if n.type=='BACKGROUND')
        setattr(sky,'aerosol_density' if hasattr(sky,'aerosol_density') else 'dust_density',.15 if defaults else c['aerosol_density'])
        sky.air_density=1. if defaults else c['sky_air_density'];sky.ozone_density=1. if defaults else c['sky_ozone_density']
        adjust=nodes.new('ShaderNodeHueSaturation')
        adjust.inputs['Saturation'].default_value=1. if defaults else c['analytic_sky_saturation']
        adjust.inputs['Value'].default_value=1. if defaults else c['analytic_sky_value']
        links.new(sky.outputs['Color'],adjust.inputs['Color']);links.new(adjust.outputs[0],background.inputs['Color'])
        if mix:
            bw=nodes.new('ShaderNodeRGBToBW');links.new(adjust.outputs[0],bw.inputs[0])
            color=nodes.new('ShaderNodeMixRGB');color.inputs[0].default_value=mix
            links.new(adjust.outputs[0],color.inputs[1]);links.new(bw.outputs[0],color.inputs[2])
            ambient=nodes.new('ShaderNodeBackground');ambient.inputs['Strength'].default_value=background.inputs['Strength'].default_value
            links.new(color.outputs[0],ambient.inputs['Color'])
            rays=nodes.new('ShaderNodeLightPath');switch=nodes.new('ShaderNodeMixShader')
            links.new(rays.outputs['Is Camera Ray'],switch.inputs[0]);links.new(ambient.outputs[0],switch.inputs[1]);links.new(background.outputs[0],switch.inputs[2])
            out_node=next(n for n in nodes if n.type=='OUTPUT_WORLD');links.new(switch.outputs[0],out_node.inputs['Surface'])
        scene.view_settings.use_white_balance=temperature is not None
        if temperature:scene.view_settings.white_balance_temperature=temperature;scene.view_settings.white_balance_tint=0
        bpy.context.view_layer.update()
        uv=world_to_camera_view(scene,camera,card.location)
        path=out/f'probe_{name}.png';scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
        records.append(dict(name=name,image=str(path),image_sha256=sha(path),neutral_mix=mix,white_balance_temperature=temperature,
            grey_card_center_pixel=[int(uv.x*960),int((1-uv.y)*540)],condition=c,light=config['lighting']))
        print('DAYLIGHT_PROBE_COMPLETE',name,flush=True)
    for name,coords in original_geometry.items():assert [tuple(v.co) for v in bpy.data.objects[name].data.vertices]==coords
    write(out/'probe_result.json',dict(records=records,original_fixture_meshes_unchanged=True,
        actual_floor_material=floor_mat.name,scope='optical probe only; no bank views or whole-plant admission',
        source_checkpoint_sha256=sha(checkpoint),fixture_sha256=sha(fixture),training_started=False))


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    run(Path(args[0]).resolve(),float(args[1]) if len(args)>1 else None)
