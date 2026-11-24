"""Apply the same directional sky with calibrated ambient chroma only.

Camera rays preserve the original sky/landscape. Irradiance is an explicitly
documented engineering approximation, not unmodified atmospheric radiometry.
No mesh, material, lamp, exposure or white-balance edits are made here.
"""
from .daylight_balance import balance_for_condition


class DaylightRadianceBalance:
    def __init__(self,session):
        self.session=session
        nodes=session.scene.world.node_tree.nodes;links=session.scene.world.node_tree.links
        out=next(n for n in nodes if n.type=='OUTPUT_WORLD')
        switch=out.inputs['Surface'].links[0].from_node
        if switch.type!='MIX_SHADER':raise ValueError('Expected camera-ray world selector')
        if switch.inputs[1].links[0].from_node != session.background:
            raise ValueError('Unexpected original illumination branch')
        original=session.background.inputs['Color'].links[0].from_socket
        grey=nodes.new('ShaderNodeRGBToBW');grey.name='daylight_ambient_luminance'
        links.new(original,grey.inputs[0])
        self.color=nodes.new('ShaderNodeMixRGB');self.color.name='daylight_ambient_chroma_balance'
        self.color.use_clamp=False
        links.new(original,self.color.inputs[1]);links.new(grey.outputs[0],self.color.inputs[2])
        self.background=nodes.new('ShaderNodeBackground');self.background.name='daylight_balanced_irradiance'
        links.new(self.color.outputs[0],self.background.inputs['Color'])
        links.new(self.background.outputs[0],switch.inputs[1])

    def apply(self,condition,lighting):
        plan=balance_for_condition(condition)
        self.color.inputs[0].default_value=plan.neutral_mix
        self.background.inputs['Strength'].default_value=self.session.background.inputs['Strength'].default_value
        lighting['ambient_color_balance']=plan.to_dict()
        lighting['camera_background']['analytic_camera_sky_unchanged']=True
        lighting['camera_background']['illumination_is_unmodified_atmospheric_radiance']=False
        lighting['camera_background']['same_analytic_atmosphere']=True
        return lighting
