"""Opt-in matte organ material adjustment, preserving texture links."""
def apply_matte_organ_review(materials):
    for key,material in materials.items():
        if not key.startswith(('leaf','calyx')):continue
        if hasattr(material,'roughness'):material.roughness=.94
        if hasattr(material,'specular_intensity'):material.specular_intensity=.15
        if not material.use_nodes:continue
        for node in material.node_tree.nodes:
            if node.type!='BSDF_PRINCIPLED':continue
            roughness=node.inputs.get('Roughness')
            if roughness is not None:
                if roughness.is_linked:
                    # Remap existing texture variation into a matte interval.
                    source=roughness.links[0].from_socket
                    ramp=material.node_tree.nodes.new('ShaderNodeMapRange')
                    ramp.label='Review matte roughness: preserve mapped variation'
                    ramp.inputs['To Min'].default_value=.85
                    ramp.inputs['To Max'].default_value=.98
                    material.node_tree.links.new(source,ramp.inputs['Value'])
                    material.node_tree.links.new(ramp.outputs['Result'],roughness)
                else:roughness.default_value=.94
            for name,value in [('Specular IOR Level',.15),('Coat Weight',0.),('Metallic',0.)]:
                socket=node.inputs.get(name)
                if socket is not None and not socket.is_linked:socket.default_value=value
