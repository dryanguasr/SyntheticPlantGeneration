"""Cloud-free analytic skies over the existing distant landscape.

Only world/light nodes change. Geometry, materials and the exact Workbench
mask pass are untouched. Atmospheric parameters are engineering heuristics.
"""
import math


class CaptureSkyBackground:
    def __init__(self,session):
        self.session=session;scene=session.scene
        nodes=scene.world.node_tree.nodes;links=scene.world.node_tree.links
        output=next(n for n in nodes if n.type=='OUTPUT_WORLD')
        camera_mix=output.inputs['Surface'].links[0].from_node
        if camera_mix.type!='MIX_SHADER' or not session.panorama:
            raise ValueError('Expected the original camera-only landscape panorama')
        panorama=camera_mix.inputs[2].links[0].from_socket
        import bpy
        from .nodal_automation import read,sha
        self.assets=read(session.config['horizon_assets_manifest'])
        for key in ('source_hdr','landscape_clean','sky_matte'):
            if sha(self.assets[key])!=self.assets[key+'_sha256']:raise ValueError('Horizon asset changed: '+key)
        original_env=panorama.node.inputs['Color'].links[0].from_node
        if original_env.type!='TEX_ENVIRONMENT':raise ValueError('Expected original panorama environment texture')
        size=(self.assets['metadata']['width'],self.assets['metadata']['height'])
        if tuple(original_env.image.size)!=size:raise ValueError('Panorama/matte dimensions differ')
        environments={}
        for key in ('landscape_clean','sky_matte'):
            image=bpy.data.images.load(self.assets[key],check_existing=True)
            if key=='sky_matte':image.colorspace_settings.name='Non-Color'
            env=nodes.new('ShaderNodeTexEnvironment');env.image=image
            env.projection=original_env.projection;env.interpolation='Linear'
            # Identical mapping is essential: an angular/luminance mask can
            # retain the old bright cloud fringe at a different horizon.
            if original_env.inputs['Vector'].is_linked:
                links.new(original_env.inputs['Vector'].links[0].from_socket,env.inputs['Vector'])
            environments[key]=env
        landscape=nodes.new('ShaderNodeBackground')
        landscape.inputs['Strength'].default_value=panorama.node.inputs['Strength'].default_value
        links.new(environments['landscape_clean'].outputs['Color'],landscape.inputs['Color'])
        self.mix=nodes.new('ShaderNodeMixShader')
        links.new(environments['sky_matte'].outputs['Color'],self.mix.inputs[0])
        links.new(landscape.outputs[0],self.mix.inputs[1])
        links.new(session.background.outputs[0],self.mix.inputs[2])
        self.selector=nodes.new('ShaderNodeMixShader')
        links.new(panorama,self.selector.inputs[1]);links.new(self.mix.outputs[0],self.selector.inputs[2])
        links.new(self.selector.outputs[0],camera_mix.inputs[2])

    def apply(self,condition,lighting):
        session=self.session;sky=session.sky
        aerosol_attribute='aerosol_density' if hasattr(sky,'aerosol_density') else 'dust_density'
        if not hasattr(sky,aerosol_attribute):raise ValueError('No supported sky aerosol control')
        setattr(sky,aerosol_attribute,condition['aerosol_density'])
        sky.air_density=condition['sky_air_density'];sky.ozone_density=condition['sky_ozone_density']
        # No extra solar disk or light is introduced. The existing Sun and
        # analytic sky keep the same elevation/azimuth set by the session.
        sky.sun_disc=False;session.sun.data.angle=math.radians(condition['sun_angle_deg'])
        self.selector.inputs[0].default_value=float(condition['sky_type']!='overcast')
        lighting['lighting'].update(sun_angle_deg=condition['sun_angle_deg'],
            aerosol_density=condition['aerosol_density'],air_density=sky.air_density,
            ozone_density=sky.ozone_density)
        lighting['camera_background']=dict(sky_type=condition['sky_type'],
            procedural_cloud_free=condition['sky_type']!='overcast',
            implementation=sky.sky_type,landscape=session.panorama,
            landscape_below_horizon_preserved=True,
            sky_replacement_version='aligned_horizon_matte/3',
            horizon_assets={key:self.assets[key+'_sha256'] for key in ('source_hdr','landscape_clean','sky_matte')},
            edge_cleanup_rows=self.assets['metadata']['edge_cleanup_rows'],
            silhouette_mask_provenance=self.assets['metadata']['provenance'],
            same_sky_for_illumination=condition['sky_type']!='overcast',
            overcast_lighting_approximation=condition['sky_type']=='overcast',sun_disc=False,
            provenance=condition['sky_provenance'])
        return lighting
