"""Opt-in basal architecture assay with conserved organs and nodal identity.

This rearranges existing nodal segments, not arbitrary organ coordinates.
It is an engineering intervention, not a developmental growth simulation.
"""
from copy import deepcopy
import math

VERSION = 'basal-scaffolds/1.0'


def basal_scaffolds(plant, count=3, base_height_m=.15, units_per_metre=8.):
    """Return a new plant: root continuation plus count-1 low scaffold axes.

    Existing attached subtrees and organs are preserved. Nodal segments bearing
    the selected branches move to the base together, retaining their identity.
    Descendant directions rotate with their scaffold. Radius is not inflated.
    """
    if count not in range(2,6) or not 0 < base_height_m <= .3 or units_per_metre <= 0:
        raise ValueError('Invalid engineering basal configuration')
    if len(plant.axes)!=1 or 'basal_architecture' in plant.metadata:
        raise ValueError('Expected one unmodified root')
    result=deepcopy(plant);root=result.axes[0]
    if len(root.child_axes)<count-1:
        raise ValueError('Not enough existing root branches for organ-conserving assay')
    node_lookup={n.id:i for i,n in enumerate(root.nodes)}
    selected=sorted(root.child_axes,key=lambda a:node_lookup[a.parent_node_id])[:count-1]
    chosen=[node_lookup[a.parent_node_id] for a in selected]
    order=chosen+[i for i in range(len(root.nodes)) if i not in chosen]
    root.nodes=[root.nodes[i] for i in order];root.internodes=[root.internodes[i] for i in order]
    for i,node in enumerate(root.nodes):node.position_index=i
    old_base=sum(i.length_cm for i in root.internodes[:count-1])
    factor=base_height_m*units_per_metre/old_base
    for segment in root.internodes[:count-1]:
        segment.length_cm*=factor
        segment.provenance['basal_length_factor']=factor
        segment.bend_angle_deg=0
    def point(azimuth,polar):
        a,p=map(math.radians,(azimuth,polar))
        return math.sin(p)*math.cos(a),math.sin(p)*math.sin(a),math.cos(p)
    # Main continuation is one scaffold. Other scaffold directions are evenly
    # spread; later support fitting must validate actual anchor geometry.
    root.resolved_direction=point(0,28)
    for index,axis in enumerate(selected,1):
        desired=360*index/count
        prior=math.degrees(math.atan2(axis.resolved_direction[1],axis.resolved_direction[0])) if axis.resolved_direction else axis.azimuth_deg
        angle=math.radians(desired-prior)
        def rotate(child):
            if child.resolved_direction:
                x,y,z=child.resolved_direction
                child.resolved_direction=(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle),z)
            child.azimuth_deg=(child.azimuth_deg+desired-prior)%360
            for branch in child.child_axes:rotate(branch)
        rotate(axis)
        axis.resolved_direction=point(desired,48)
        axis.training_target_direction=axis.resolved_direction
        axis.training_phase=VERSION
    # The quoted base height is arc length, not falsely a measured vertical height.
    result.metadata['basal_architecture']=dict(version=VERSION,source_preset=plant.parameter_preset,
        scaffold_count=count,includes_root_continuation=True,base_path_length_m=base_height_m,
        parameter_status='engineering_heuristic',count_source='user_observation_2_to_5_not_validated_distribution',
        organ_count_preserved=True,attachment_ids_preserved=True,developmental_simulation=False,
        anchor_fit='pending_scene_support_validation',selected_axes=[a.id for a in selected])
    result.parameter_preset=VERSION
    return result
