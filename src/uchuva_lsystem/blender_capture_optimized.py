"""Capture-only acceleration; morphology, materials and raster policy stay intact.

Geometry is still checked before and after every capture. Bulk RNA reads avoid
building Python tuples and their decimal repr for every vertex at every view.
The historical geometry hash remains the boundary/lineage proof.
"""
from array import array
import hashlib
import math
from pathlib import Path

from .appearance_profiles import resolved_profile
from .blender_appearance import apply_profile
from . import blender_annotations as annotations


def refresh_hidden_fruit_transforms(scene):
    """Match the ground auditor's depsgraph warmup after loading a .blend.

Viewport-hidden fruit interiors have valid stored transform channels, but
their cached matrix_world need not be evaluated on load. The physical ground
auditor already uses this exact visibility cycle. Never change hide_render.
"""
    import bpy
    fruits=[o for o in scene.objects if o.get('uchuva_organ_kind')=='fruit'
            or o.get('uchuva_hidden_inside_closed_calyx')]
    state=[(o,bool(o.hide_viewport),bool(o.hide_get()),bool(o.hide_render)) for o in fruits]
    try:
        for obj,global_hidden,local_hidden,render_hidden in state:
            if global_hidden:obj.hide_viewport=False
            if local_hidden:obj.hide_set(False)
        bpy.context.view_layer.update()
    finally:
        for obj,global_hidden,local_hidden,render_hidden in state:
            obj.hide_set(local_hidden);obj.hide_viewport=global_hidden
            if bool(obj.hide_render)!=render_hidden:raise ValueError('Fruit render visibility changed')
        bpy.context.view_layer.update()
    return dict(fruit_objects=len(state),viewport_flags_restored=True,render_flags_unchanged=True)


def reads_object_color(node_tree,seen=None):
    """Include nested node groups; only call for materials actually in scene."""
    seen=set() if seen is None else seen
    if id(node_tree) in seen:return False
    seen.add(id(node_tree))
    for node in node_tree.nodes:
        if node.type=='OBJECT_INFO' and node.outputs['Color'].is_linked:return True
        if node.type=='GROUP' and node.node_tree and reads_object_color(node.node_tree,seen):return True
    return False


def binary_geometry_digest(scene):
    """Hash complete coordinates/topology/transforms, not a sampled geometry.

This is a separate versioned fingerprint, not equal to the historical repr hash.
No geometry memoization: in-place edits must be detected on every check.
"""
    digest = hashlib.sha256(b'uchuva.bulk_geometry/1')
    for obj in sorted((o for o in scene.objects if o.type in {'MESH','CURVE','SURFACE'}), key=lambda o:o.name):
        digest.update(repr((obj.name,obj.type,[list(r) for r in obj.matrix_world])).encode())
        data = obj.data
        if obj.type == 'MESH':
            digest.update(repr((len(data.vertices),len(data.polygons),len(data.loops))).encode())
            for collection, attribute, size, code in (
                (data.vertices,'co',len(data.vertices)*3,'f'),
                (data.loops,'vertex_index',len(data.loops),'i'),
                (data.polygons,'loop_start',len(data.polygons),'i'),
                (data.polygons,'loop_total',len(data.polygons),'i')):
                buffer = array(code,[0])*size
                collection.foreach_get(attribute,buffer)
                digest.update(buffer.tobytes())
        else:
            digest.update(repr((data.bevel_depth,data.bevel_resolution,data.resolution_u,
                [(s.type,s.use_cyclic_u,[(tuple(p.co),p.radius) for p in s.points],
                  [(tuple(p.co),tuple(p.handle_left),tuple(p.handle_right),p.radius) for p in s.bezier_points])
                 for s in data.splines])).encode())
    return digest.hexdigest()


def camera_panorama(config,index):
    """Same camera-only background as the historical renderer; created once."""
    if not config.get('asset_dir'):return None
    import bpy
    image=bpy.data.images.get('UchuvaAsset_farmland_overcast_2k')
    if image is None:raise ValueError('Configured panorama was not loaded')
    world=bpy.context.scene.world;nodes=world.node_tree.nodes;links=world.node_tree.links
    output=next(n for n in nodes if n.type=='OUTPUT_WORLD')
    old=output.inputs['Surface'].links[0].from_socket
    env=nodes.new('ShaderNodeTexEnvironment');env.image=image
    tex=nodes.new('ShaderNodeTexCoord');mapping=nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value[2]=index*.47
    links.new(tex.outputs['Generated'],mapping.inputs['Vector']);links.new(mapping.outputs['Vector'],env.inputs['Vector'])
    bg=nodes.new('ShaderNodeBackground');bg.inputs['Strength'].default_value=.55
    links.new(env.outputs['Color'],bg.inputs['Color'])
    path=nodes.new('ShaderNodeLightPath');mix=nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'],mix.inputs[0]);links.new(old,mix.inputs[1])
    links.new(bg.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
    return dict(asset=image.name,camera_only=True,strength=.55,rotation_rad=index*.47)


class CaptureSession:
    """One admitted scene, reusable lighting and immutable annotation registry.

ID colors can remain installed between masks because RGB uses materials. Fail
closed if an RGB material reads Object Info Color. All other objects remain
black depth occluders. Colors/render state are restored on close/failure.
"""
    def __init__(self,scene,profiles,config,scene_index,camera):
        import bpy
        self.scene=scene;self.profiles=profiles;self.config=config;self.scene_index=scene_index
        self.camera=camera;self.configured=False;self.colors={};self.closed=False
        self.registry=annotations.annotation_registry()
        self.spec=annotations._annotation_pass_definitions(self.registry)['reproductive_instance']
        materials={slot.material for obj in scene.objects for slot in obj.material_slots if slot.material}
        for material in materials:
            if material.use_nodes and reads_object_color(material.node_tree):
                raise ValueError('Persistent ID colors unsafe: material reads Object Info Color')
        self.expected=binary_geometry_digest(scene)
        self.colors={obj.name:tuple(obj.color) for obj in scene.objects}
        for obj in scene.objects:obj.color=(0,0,0,1)
        for obj in self.registry['objects']:
            if obj.get('uchuva_semantic_class')=='calyx':
                obj.color=annotations._linear_rgba(self.spec['object_color'](obj))

    def verify_geometry(self):
        if binary_geometry_digest(self.scene)!=self.expected:
            raise ValueError('Capture changed complete geometry/topology/transform fingerprint')

    def lighting(self,camera,target,diagnostic_light=None,condition=None):
        import bpy
        from mathutils import Vector
        profiles=self.profiles
        if condition is not None:
            from .capture_plan import profiles_for_condition
            profiles,diagnostic_light=profiles_for_condition(profiles,condition)
        config=resolved_profile(profiles,'LT',diagnostic_light);p=config['lighting']
        if not self.configured:
            apply_profile(profiles,'LT',camera,target,diagnostic_light)
            self.sky=next(n for n in self.scene.world.node_tree.nodes if n.type=='TEX_SKY')
            self.background=next(n for n in self.scene.world.node_tree.nodes if n.type=='BACKGROUND')
            self.panorama=camera_panorama(self.config,self.scene_index)
            self.sun=next(o for o in self.scene.objects if o.type=='LIGHT' and o.data.type=='SUN')
            self.fill=next((o for o in self.scene.objects if o.type=='LIGHT' and o.data.type=='AREA'),None)
            self.configured=True
        self.sky.sky_type=p['sky'];self.sky.sun_disc=False
        self.sky.sun_elevation=math.radians(p['sun_elevation_deg'])
        self.sky.sun_rotation=math.radians(p['sun_azimuth_deg'])
        self.background.inputs['Strength'].default_value=p['world_strength']
        self.sun.data.energy=p['sun_energy'];self.sun.data.angle=math.radians(p['sun_angle_deg'])
        self.sun.rotation_euler=(math.radians(90-p['sun_elevation_deg']),0,math.radians(p['sun_azimuth_deg']))
        if self.fill is None and p['fill_energy']:
            data=bpy.data.lights.new('appearance_fill','AREA');data.size=3
            self.fill=bpy.data.objects.new(data.name,data);self.scene.collection.objects.link(self.fill)
        if self.fill:
            self.fill.data.energy=p['fill_energy'];self.fill.hide_render=not bool(p['fill_energy'])
            self.fill.location=camera.location+Vector((-1,0,1))
            self.fill.rotation_euler=(Vector(target)-self.fill.location).to_track_quat('-Z','Y').to_euler()
        self.scene.view_settings.view_transform=config['color_management']['view_transform']
        self.scene.view_settings.look=config['color_management']['look']
        self.scene.view_settings.gamma=config['color_management']['gamma']
        self.scene.view_settings.exposure=p['exposure_ev']
        config['effective_exposure_ev']=self.scene.view_settings.exposure
        config['camera_background']=self.panorama
        if condition is not None:config['capture_condition']=condition
        bpy.context.view_layer.update()
        return config

    def mask(self,camera,output_dir,*,width,height):
        import bpy
        scene=self.scene;previous=annotations._capture_render_state(scene)
        shading=scene.display.shading
        keys=('light','color_type','show_shadows','show_cavity','show_specular_highlight',
              'background_type','background_color','show_object_outline','show_xray','show_backface_culling')
        old={k:tuple(getattr(shading,k)) if k=='background_color' else getattr(shading,k) for k in keys}
        old_aa=scene.display.render_aa
        folder=Path(output_dir).resolve();raw=folder/'.crisp_raw.png';final=folder/'mask_calyx_crisp_v2.png'
        try:
            scene.camera=camera;scene.render.engine='BLENDER_WORKBENCH';scene.display.render_aa='OFF'
            shading.light='FLAT';shading.color_type='OBJECT'
            shading.show_shadows=shading.show_cavity=shading.show_specular_highlight=False
            shading.show_object_outline=shading.show_xray=shading.show_backface_culling=False
            shading.background_type='VIEWPORT';shading.background_color=(0,0,0)
            scene.render.resolution_x,scene.render.resolution_y=width,height
            scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
            scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='8'
            scene.render.film_transparent=True;scene.render.dither_intensity=0
            scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
            scene.view_settings.exposure=0;scene.view_settings.gamma=1
            scene.render.filepath=str(raw);bpy.ops.render.render(write_still=True)
            from .mask_arrays import snap_and_save_image
            stats=snap_and_save_image(raw,final,self.spec['palette'],width,height)
            raw.unlink()
            return dict(path=str(final),engine='BLENDER_WORKBENCH',anti_aliasing='OFF',
                palette_version='rgb_lattice_4095_v1',palette={str(k):list(v) for k,v in self.spec['palette'].items()},
                items=annotations._enrich_mask_stats('reproductive_instance',stats,self.registry))
        finally:
            for key,value in old.items():setattr(shading,key,value)
            scene.display.render_aa=old_aa;annotations._restore_render_state(scene,previous)

    def close(self):
        if self.closed:return
        for obj in self.scene.objects:
            if obj.name in self.colors:obj.color=self.colors[obj.name]
        self.closed=True

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
