"""Explicit nodal sampling of outward ascending parabolic scaffold paths."""
import math
from copy import deepcopy
from .morphology import Node
from .ascending_basal_pilot import ascending_basal_pilot

CURVATURES={'A_vertical':38,'B_intermedia':52,'C_abierta':64}


def curved_basal_pilot(plant,count,variant,*,inward=False):
    result=ascending_basal_pilot(plant,count,variant)
    added=0
    for axis in result.axes[0].child_axes:
        x,y,_=axis.resolved_direction
        az=math.atan2(y,x)
        start=math.radians(CURVATURES[variant] if inward else 8)
        end=math.radians(8 if inward else CURVATURES[variant])
        slope=math.tan(start);curvature=(math.tan(end)-slope)/2
        segments=axis.internodes;nodes=axis.nodes
        total=sum(s.length_cm for s in segments)
        # Normalize height so the sampled curve retains the earlier path length.
        sample=[i/200 for i in range(201)]
        arc=sum(math.hypot(b-a,slope*(b-a)+curvature*(b*b-a*a))
                for a,b in zip(sample,sample[1:]))
        height=total/arc
        new_segments=[];new_nodes=[];t=0.;previous_angle=start
        axis.resolved_direction=(math.sin(start)*math.cos(az),math.sin(start)*math.sin(az),math.cos(start))
        axis.mechanical_deflection_deg=0
        for segment,node in zip(segments,nodes):
            divisions=max(4,math.ceil(segment.length_cm/total*80))
            for part in range(divisions):
                next_t=t+segment.length_cm/total/divisions
                dz=height*(next_t-t)
                dr=height*(slope*(next_t-t)+curvature*(next_t**2-t**2))
                angle=math.atan2(dr,dz)
                piece=deepcopy(segment)
                piece.id=segment.id if part==divisions-1 else segment.id+f'_curve_{part}'
                piece.length_cm=math.hypot(dr,dz)
                piece.bend_azimuth_deg=math.degrees(az)
                piece.bend_angle_deg=math.degrees(angle-previous_angle)
                if abs(piece.bend_angle_deg)>12:raise ValueError('Curve exceeds interpreter bend limit')
                piece.provenance.update(curve='inward_concave_parabola' if inward else 'outward_parabola',parameter_status='engineering_heuristic',t0=t,t1=next_t)
                new_segments.append(piece)
                if part==divisions-1:
                    node.position_index=len(new_nodes);new_nodes.append(node)
                else:
                    new_nodes.append(Node(id=node.id+f'_curve_{part}',order=axis.order,age=0,position_index=len(new_nodes)))
                    added+=1
                previous_angle=angle;t=next_t
        axis.internodes=new_segments;axis.nodes=new_nodes
        axis.max_internodes=len(new_nodes)
        axis.growth_budget_length_cm=sum(s.length_cm for s in new_segments)
    version='0.3' if inward else '0.2'
    result.parameter_preset='curved-basal-review/'+version+'/'+variant
    result.metadata['curved_basal_pilot']=dict(version=version,variant=variant,inward_concavity=inward,
        seed=plant.seed,count=count,added_curve_support_nodes=added,
        curve='radial displacement = height * (initial_slope*t + curvature*t^2)',
        interpretation='Visual approximation requested by user; not fitted botanical law',
        initial_tangent_deg=CURVATURES[variant] if inward else 8,
        terminal_tangent_deg=8 if inward else CURVATURES[variant],
        parameter_status='engineering_heuristic',accepted_for_dataset=False)
    return result
