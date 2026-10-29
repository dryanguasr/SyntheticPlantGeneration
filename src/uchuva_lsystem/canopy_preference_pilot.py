"""Opt-in photo-guided canopy heuristics; not a light or mechanics solver."""
import math
import random
from .hierarchical_basal_pilot import hierarchical_basal_pilot


def _unit(v):
    length=math.sqrt(sum(x*x for x in v))
    return tuple(x/length for x in v)


def node_positions(plant):
    positions={};axes={}
    def walk(axis,start):
        axes[axis.id]=axis;point=start;direction=axis.resolved_direction
        for segment,node in zip(axis.internodes,axis.nodes):
            az=math.radians(segment.bend_azimuth_deg);radial=(math.cos(az),math.sin(az),0)
            dot=sum(a*b for a,b in zip(direction,radial))
            radial=_unit(tuple(a-dot*b for a,b in zip(radial,direction)))
            angle=math.radians(segment.bend_angle_deg)
            direction=_unit(tuple(a*math.cos(angle)+b*math.sin(angle) for a,b in zip(direction,radial)))
            point=tuple(a+segment.length_cm*b for a,b in zip(point,direction));positions[node.id]=point
        for child in axis.child_axes:walk(child,positions[child.parent_node_id])
    for axis in plant.axes:walk(axis,(0,0,0))
    return positions,axes


def canopy_preference_pilot(plant, four_level_probability=.2):
    if not 0<=four_level_probability<=1:raise ValueError('Invalid probability')
    rng=random.Random(plant.seed+2173)
    count=rng.choice((3,4,5));levels=4 if rng.random()<four_level_probability else 3
    result=hierarchical_basal_pilot(plant,count,levels)
    positions,axes=node_positions(result);height=max(p[2] for p in positions.values())
    trained=[]
    # Use original height to choose eligible axes; keep this reference explicit.
    for axis in axes.values():
        heights=[positions[n.id][2]/height for n in axis.nodes]
        if axis.order==0 or min(heights)>.60 or max(heights)<.45 or rng.random()>.45:continue
        transition=rng.uniform(.45,.60)
        for segment,node in zip(axis.internodes,axis.nodes):
            z=positions[node.id][2]/height
            # Smooth change of sign over 12% of reference plant height.
            weight=max(0.,min(1.,(z-transition+.06)/.12))
            weight=weight*weight*(3-2*weight)
            segment.bend_angle_deg=(1-weight)*segment.bend_angle_deg+weight*2.0
            x,y,_=positions[node.id]
            segment.bend_azimuth_deg=math.degrees(math.atan2(y,x))
            segment.provenance.update(tutoring_shape='inward_to_outward',status='engineering_heuristic')
        trained.append(axis.id)
    positions,axes=node_positions(result)
    # Compare radial position within broad height bands, not a global radius
    # that would penalize all leaves in a naturally narrower upper canopy.
    radii={};height=max(p[2] for p in positions.values())
    for node,p in positions.items():
        band=min(5,int(p[2]/height*6));radii[band]=max(radii.get(band,0),math.hypot(p[0],p[1]))
    kept=removed=0
    for axis in axes.values():
        for node in axis.nodes:
            if not node.leaf:continue
            x,y,z=positions[node.id];band=min(5,int(z/height*6))
            exposure=min(1,math.hypot(x,y)/max(radii[band],1e-9))
            probability=.25+.70*exposure**2
            node.leaf.provenance.update(exterior_exposure_proxy=exposure,retention_probability=probability,status='engineering_heuristic_not_light_simulation')
            if rng.random()>probability:node.leaf=None;removed+=1
            else:kept+=1
    result.parameter_preset='canopy-preference-review/0.1'
    result.metadata['canopy_preference_pilot']=dict(version='0.1',seed=plant.seed,basal_axes=count,levels=levels,four_level_probability=four_level_probability,basal_count_distribution='uniform_3_4_5',trained_axes=trained,leaf_count_kept=kept,leaf_count_removed=removed,parameter_status='engineering_heuristic_user_guided',accepted_for_dataset=False,limitations=['Radial exposure proxy, not irradiance or competition','Prescribed curvature, not tension equilibrium','No collision correction'])
    return result
