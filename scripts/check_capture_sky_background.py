"""Small Blender regression: upper sky changes, lower landscape stays fixed."""
from pathlib import Path
from types import SimpleNamespace
import sys,math,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import bpy
from mathutils import Vector
from uchuva_lsystem.blender_capture_skies import CaptureSkyBackground
from uchuva_lsystem.capture_skies import sky_condition_for_view
from uchuva_lsystem.blender_capture_optimized import binary_geometry_digest


def run(out,assets_manifest):
    out.mkdir(parents=True,exist_ok=False)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=4
    scene.render.resolution_x=256;scene.render.resolution_y=128;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='Standard'
    world=bpy.data.worlds.new('SkyRegression');world.use_nodes=True;scene.world=world
    nodes=world.node_tree.nodes;links=world.node_tree.links;nodes.clear()
    sky=nodes.new('ShaderNodeTexSky');sky.sky_type='MULTIPLE_SCATTERING'
    sky.sun_elevation=math.radians(45);sky.sun_rotation=math.radians(125)
    bg=nodes.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.15
    links.new(sky.outputs[0],bg.inputs['Color'])
    assets=json.loads(assets_manifest.read_text(encoding='utf-8'))
    environment=nodes.new('ShaderNodeTexEnvironment')
    environment.image=bpy.data.images.load(assets['source_hdr'],check_existing=False)
    panorama=nodes.new('ShaderNodeBackground');panorama.inputs['Strength'].default_value=.55
    links.new(environment.outputs['Color'],panorama.inputs['Color'])
    path=nodes.new('ShaderNodeLightPath');mix=nodes.new('ShaderNodeMixShader');output=nodes.new('ShaderNodeOutputWorld')
    links.new(path.outputs['Is Camera Ray'],mix.inputs[0]);links.new(bg.outputs[0],mix.inputs[1])
    links.new(panorama.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
    bpy.ops.object.light_add(type='SUN');sun=bpy.context.object
    bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera;camera.data.lens=18
    camera.rotation_euler=Vector((0,1,.05)).to_track_quat('-Z','Y').to_euler()
    session=SimpleNamespace(scene=scene,sky=sky,background=bg,sun=sun,
        panorama={'asset':environment.image.name},config={'horizon_assets_manifest':str(assets_manifest)})
    guard=binary_geometry_digest(scene);background=CaptureSkyBackground(session);results={}
    for name in ('overcast','clear_blue','hazy_clear'):
        condition=next(sky_condition_for_view(15,i) for i in range(9) if sky_condition_for_view(15,i)['sky_type']==name)
        metadata=background.apply(condition,dict(lighting={}))
        target=out/(name+'.png');scene.render.filepath=str(target);bpy.ops.render.render(write_still=True)
        image=bpy.data.images.load(str(target),check_existing=False);pixels=list(image.pixels)
        def sample(x,y):
            index=(y*256+x)*4;return pixels[index:index+3]
        results[name]=dict(top=sample(128,115),bottom=sample(128,5),metadata=metadata)
        bpy.data.images.remove(image)
        if binary_geometry_digest(scene)!=guard:raise ValueError('Sky changed geometry')
    for name in ('clear_blue','hazy_clear'):
        if max(abs(a-b) for a,b in zip(results[name]['bottom'],results['overcast']['bottom']))>1/255:
            raise ValueError('Lower landscape changed: '+name)
    top=results['clear_blue']['top']
    if not top[2]>top[0]+.02:raise ValueError('Upper hemisphere is not blue; check ray direction')
    if results['clear_blue']['top']==results['overcast']['top']:raise ValueError('Sky did not change')
    (out/'result.json').write_text(json.dumps(dict(status='pass',geometry_unchanged=True,results=results),indent=2),encoding='utf-8')


if __name__=='__main__':run(*[Path(p).resolve() for p in sys.argv[sys.argv.index('--')+1:]])
