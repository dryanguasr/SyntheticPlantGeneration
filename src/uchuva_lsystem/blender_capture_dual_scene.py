"""Keep Cycles geometry resident while an independent scene rasterizes IDs.

Scenes share every collection/object/datablock. No copies, LODs, subdivision
changes or missing occluders. Only engine/color-management state is separated.
"""
from pathlib import Path
from .blender_capture_optimized import CaptureSession
from . import blender_annotations as annotations
from .mask_arrays import snap_and_save_image


class DualSceneCaptureSession(CaptureSession):
    def __init__(self,*args,**kwargs):
        import bpy
        super().__init__(*args,**kwargs)
        self.old_persistent=self.scene.render.use_persistent_data
        self.scene.render.use_persistent_data=True
        self.mask_scene=bpy.data.scenes.new('UchuvaExactMaskCapture')
        mask=self.mask_scene
        for collection in self.scene.collection.children:mask.collection.children.link(collection)
        for obj in self.scene.collection.objects:mask.collection.objects.link(obj)
        if {o.as_pointer() for o in mask.objects}!={o.as_pointer() for o in self.scene.objects}:
            raise ValueError('Mask scene must share every RGB object, including occluders')
        mask.camera=self.camera;mask.world=self.scene.world
        mask.unit_settings.system=self.scene.unit_settings.system
        mask.unit_settings.scale_length=self.scene.unit_settings.scale_length
        mask.frame_set(self.scene.frame_current)
        mask.render.engine='BLENDER_WORKBENCH';mask.display.render_aa='OFF'
        shading=mask.display.shading;shading.light='FLAT';shading.color_type='OBJECT'
        shading.show_shadows=shading.show_cavity=shading.show_specular_highlight=False
        shading.show_object_outline=shading.show_xray=shading.show_backface_culling=False
        shading.background_type='VIEWPORT';shading.background_color=(0,0,0)
        mask.render.resolution_percentage=100
        mask.render.pixel_aspect_x=self.scene.render.pixel_aspect_x
        mask.render.pixel_aspect_y=self.scene.render.pixel_aspect_y
        mask.render.image_settings.file_format='PNG';mask.render.image_settings.color_mode='RGBA'
        mask.render.image_settings.color_depth='8';mask.render.film_transparent=True
        mask.render.dither_intensity=0;mask.render.filter_size=self.scene.render.filter_size
        mask.view_settings.view_transform='Standard';mask.view_settings.look='None'
        mask.view_settings.exposure=0;mask.view_settings.gamma=1
        for key in ('use_white_balance','white_balance_temperature','white_balance_tint'):
            if hasattr(self.scene.view_settings,key):setattr(mask.view_settings,key,getattr(self.scene.view_settings,key))
        mask['uchuva_preserve_mask_components']=bool(self.scene.get('uchuva_preserve_mask_components',False))

    def mask(self,camera,output_dir,*,width,height):
        import bpy
        mask=self.mask_scene;mask.camera=camera
        mask.render.resolution_x=width;mask.render.resolution_y=height
        folder=Path(output_dir).resolve();raw=folder/'.crisp_raw.png';final=folder/'mask_calyx_crisp_v2.png'
        mask.render.filepath=str(raw)
        with bpy.context.temp_override(scene=mask,view_layer=mask.view_layers[0]):
            bpy.ops.render.render(write_still=True,scene=mask.name)
            stats=snap_and_save_image(raw,final,self.spec['palette'],width,height)
        raw.unlink()
        return dict(path=str(final),engine='BLENDER_WORKBENCH',anti_aliasing='OFF',
            palette_version='rgb_lattice_4095_v1',palette={str(k):list(v) for k,v in self.spec['palette'].items()},
            items=annotations._enrich_mask_stats('reproductive_instance',stats,self.registry))

    def close(self):
        if self.closed:return
        import bpy
        self.scene.render.use_persistent_data=self.old_persistent
        bpy.data.scenes.remove(self.mask_scene)
        super().close()
