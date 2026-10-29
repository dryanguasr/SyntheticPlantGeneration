"""Length-preserving alternating nodal poses; an engineering search family."""
import math
from .nodal_repulsion import KEY, unit, dot, add, sub, mul, cross


def four_node_candidates(axis, index, bone_frames, *, bearing, excursion_limit_deg=35):
    """Move a whole four-bone module before judging its mutual contacts.

    The first and third insertions move to opposite sides of the growth ray;
    the fourth anchor stays on that ray and may move basally. No bone length,
    radius, organ, calyx gravity axis or attachment identity is changed.
    """
    parts=axis.internodes[index:index+4]
    if len(parts)!=4:
        return []
    start=bone_frames[parts[0].id]['start'];end=bone_frames[parts[-1].id]['end']
    growth=unit(sub(end,start));lengths=[p.length_cm*.08 for p in parts]
    radial=sub(bearing,mul(growth,dot(bearing,growth)))
    if dot(radial,radial)<1e-12:radial=cross(growth,(1.,0.,0.))
    if dot(radial,radial)<1e-12:radial=cross(growth,(0.,1.,0.))
    v=unit(radial);w=unit(cross(growth,v));old_span=dot(sub(end,start),growth)
    original_first=bone_frames[parts[0].id]['end'];result=[]
    for degrees in (5,10,15,20,25,30):
        height=min(lengths)*math.sin(math.radians(degrees))
        for azimuth in (0,-30,30,-60,60,-90,90,180):
            yaw=math.radians(azimuth);lateral=add(mul(v,math.cos(yaw)),mul(w,math.sin(yaw)))
            directions=[];point=start;anchors=[]
            for part,length,sign in zip(parts,lengths,(1,-1,-1,1)):
                transverse=height/length
                direction=add(mul(growth,math.sqrt(max(0.,1-transverse*transverse))),mul(lateral,sign*transverse))
                directions.append(direction);point=add(point,mul(direction,length));anchors.append(point)
            if any(math.degrees(math.acos(max(-1.,min(1.,dot(d,p.provenance[KEY]['input_direction'])))))>excursion_limit_deg+1e-8 for p,d in zip(parts,directions)):
                continue
            shortening=old_span-dot(sub(point,start),growth)
            if shortening<-1e-8:
                continue
            result.append(dict(mode='alternating_four_nodes',degrees=degrees,azimuth=azimuth,
                               directions=directions,anchors=anchors,delta_z=anchors[0][2]-original_first[2],
                               end_anchor=point,fixed_growth_ray=True,axial_shortening_bu=shortening,
                               nominal_lengths_preserved=True,status='engineering_heuristic'))
    return sorted(result,key=lambda c:(c['delta_z']>1e-10,c['degrees'],abs(c['azimuth']),c['azimuth']))


def balanced_proposals(families, limit):
    """Cover each mode and its angular span; prefer lowering with a 3:1 share."""
    if limit<=0:return []
    buckets=[]
    for family in families:
        buckets.append([[p for p in family if (p['delta_z']>1e-10)==up] for up in (False,True)])
    output=[];seen=set()
    for phase,total in ((0,math.ceil(limit*.75)),(1,limit-math.ceil(limit*.75))):
        nonempty=[b[phase] for b in buckets if b[phase]]
        if not nonempty:continue
        quota=max(1,total//len(nonempty))
        selected=[]
        for bucket in nonempty:
            n=min(quota,len(bucket))
            indices=[round(i*(len(bucket)-1)/(n-1)) for i in range(n)] if n>1 else [0]
            selected.extend(bucket[i] for i in indices)
        selected.sort(key=lambda c:(abs(c['degrees']),abs(c.get('azimuth',0)),c.get('mode','')))
        for row in selected[:total]:
            if id(row) not in seen:output.append(row);seen.add(id(row))
    # Fill unused slots deterministically, keeping remaining lowering moves first.
    rest=[p for family in families for p in family if id(p) not in seen]
    rest.sort(key=lambda c:(c['delta_z']>1e-10,abs(c['degrees']),abs(c.get('azimuth',0))))
    return sorted((output+rest)[:limit],key=lambda c:c['delta_z']>1e-10)
