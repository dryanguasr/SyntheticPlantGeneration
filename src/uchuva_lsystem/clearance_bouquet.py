"""Deterministic axis pose search preserving nodes, organs, lengths and radii."""
import math
from .collisions import _bend_direction, _segment_segment_distance


def clear_branch_axes(plant, fine_search=False):
    """Choose upward directions with conservative stem-capsule clearance.

    This is an engineering training-pose heuristic, not a growth law. Only
    axis directions change; no organ is deleted, scaled or detached.
    """
    fixed=[];frames={};changes=[];unresolved=[]

    def segments(axis,start,direction):
        result=[];point=start
        for i,internode in enumerate(axis.internodes):
            direction=_bend_direction(direction,internode.bend_azimuth_deg,internode.bend_angle_deg)
            end=tuple(point[d]+direction[d]*internode.length_cm*.08 for d in range(3))
            radius=max(internode.radius_cm*.08,.008)
            result.append({'axis':axis.id,'index':i,'start':point,'end':end,'radius':radius,
                'kind':'segment',
                'box':([min(point[d],end[d])-radius for d in range(3)],
                       [max(point[d],end[d])+radius for d in range(3)])})
            point=end
        radius=max(.018*(1-.18*axis.order),.008)
        result.append({'axis':axis.id,'index':len(axis.internodes),'start':point,'end':point,
                       'radius':radius,'kind':'apex',
                       'box':([point[d]-radius for d in range(3)],
                              [point[d]+radius for d in range(3)])})
        return result

    def score(axis,candidates):
        count=0;penetration=0
        parent_axis,parent_index=(axis.parent_node_id.rsplit('_node_',1) if axis.parent_node_id else ('',-9))
        parent_index=int(parent_index)
        for s in candidates:
            for other in fixed:
                if s['index']==0 and other['axis']==parent_axis:
                    if other['kind']=='segment' and other['index'] in (parent_index,parent_index+1):continue
                    if other['kind']=='apex' and other['index']==parent_index+1:continue
                a,b=s['box'],other['box']
                if not all(a[0][d]<=b[1][d]+.024 and b[0][d]<=a[1][d]+.024 for d in range(3)):continue
                distance=_segment_segment_distance(s['start'],s['end'],other['start'],other['end'])
                overlap=s['radius']+other['radius']+.024-distance
                if overlap>0:count+=1;penetration+=overlap
        return count,round(penetration,7)

    def visit(axis,start):
        initial=tuple(axis.resolved_direction or (0,0,1));best=segments(axis,start,initial)
        before=score(axis,best);best_score=before;chosen=initial
        az=math.degrees(math.atan2(initial[1],initial[0]));polar=math.degrees(math.acos(max(-1,min(1,initial[2]))))
        if axis.order and before[0]:
            offsets=(15,-15,30,-30,45,-45,60,-60,90,-90,120,-120,150,-150,180)
            if fine_search:
                offsets=tuple(v for step in range(1,15) for v in (step,-step))+offsets
            for offset in offsets:
                if not best_score[0]:break
                inclinations=(polar,30,45,60,75,85,15,5)
                if fine_search:
                    inclinations=(polar,)+tuple(max(1,min(89,polar+v)) for v in (-5,5,-10,10))+inclinations[1:]
                for inclination in inclinations:
                    a,b=math.radians(az+offset),math.radians(inclination)
                    direction=(math.cos(a)*math.sin(b),math.sin(a)*math.sin(b),math.cos(b))
                    candidate=segments(axis,start,direction);value=score(axis,candidate)
                    if value<best_score:best,best_score,chosen=candidate,value,direction
                    if not best_score[0]:break
        axis.resolved_direction=chosen;axis.training_target_direction=chosen
        if chosen!=initial:changes.append({'axis':axis.id,'before':initial,'after':chosen,'pairs_before':before,'pairs_after':best_score})
        if best_score[0]:unresolved.append({'axis':axis.id,'score':best_score})
        fixed.extend(best)
        for node,segment in zip(axis.nodes,best):frames[node.id]=segment['end']
        for child in axis.child_axes:visit(child,frames[child.parent_node_id])

    for axis in plant.axes:visit(axis,(0,0,0))
    plant.metadata['axis_clearance_pose']={'version':'bouquet-axis-clearance/1.0',
        'parameter_status':'engineering_heuristic','changes':changes,'unresolved':unresolved}
    return plant.metadata['axis_clearance_pose']
