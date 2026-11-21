"""Gravity-prioritized nodal growth poses (engineering heuristic, not forces).

Topology and organ dimensions are immutable. A pose is expressed in the plant
frame, before camera/light/material choices. Conservative proxy clearance guides
the search; only an independently rebuilt evaluated-mesh audit admits a scene.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import time

KEY = "nodal_growth_repulsion_v1"
VERSION = "bottom-up-lower-first/1"


def require_legacy_pose_inputs(plants,consumer):
    """Never silently prune or ignore a tree with explicit nodal directions."""
    for plant in plants:
        if plant.metadata.get('nodal_repulsion_requested') or plant.metadata.get('nodal_repulsion') or any(
                KEY in p.provenance for a in axes(plant.axes) for p in a.internodes):
            raise ValueError(f'{consumer} uses the historical pose contract; use the nodal growth/mesh-feedback path for this tree')


def unit(v):
    length=math.sqrt(sum(float(x)**2 for x in v))
    if not math.isfinite(length) or length<1e-12:raise ValueError('Invalid growth direction')
    return tuple(float(x)/length for x in v)


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def point_segment_distance(point,a,b):
    direction=sub(b,a);denominator=dot(direction,direction)
    t=max(0.,min(1.,dot(sub(point,a),direction)/denominator)) if denominator else 0.
    delta=sub(point,add(a,mul(direction,t)))
    return math.sqrt(dot(delta,delta))


def rotate_between(vector,old,new):
    old,new=unit(old),unit(new);axis=cross(old,new);cosine=max(-1.,min(1.,dot(old,new)))
    if cosine < -.999999:raise ValueError('Growth joint cannot reverse through 180 degrees')
    if dot(axis,axis)<1e-20:return tuple(vector)
    return add(add(vector,cross(axis,vector)),mul(cross(axis,cross(axis,vector)),1/(1+cosine)))


def pose_direction(organ,fallback):
    record=organ.provenance.get(KEY)
    return unit(record['direction']) if record else tuple(fallback)


def segment_directions(part,previous=None):
    record=part.provenance[KEY];direction=unit(record['direction'])
    driver=previous.provenance[KEY] if previous is not None else record
    incoming=unit(rotate_between(record['input_incoming_direction'],driver['input_direction'],driver['direction']))
    return incoming,direction


def pitched(direction,degrees,azimuth_degrees=0.):
    x,y,z=unit(direction);az=math.atan2(y,x)+math.radians(azimuth_degrees)
    elevation=max(math.radians(-85),min(math.radians(85),math.atan2(z,math.hypot(x,y))+math.radians(degrees)))
    return (math.cos(az)*math.cos(elevation),math.sin(az)*math.cos(elevation),math.sin(elevation))


def joint_angles(direction):
    x,y,z=unit(direction)
    return math.degrees(math.atan2(y,x))%360,math.degrees(math.atan2(z,math.hypot(x,y)))


def joint_direction(azimuth,elevation):
    az,el=math.radians(azimuth),math.radians(elevation)
    return math.cos(az)*math.cos(el),math.sin(az)*math.cos(el),math.sin(el)


def joint_candidates(before,input_direction,*,kind,limit,excursion_limit_deg=None):
    """Nodal mesh feedback: exhaust descending leaf moves before ascending.

    Reproductive endpoints try rising first; the separate capacho gravity axis
    remains immutable. Bounds are explicitly unmeasured engineering priors.
    """
    seen={tuple(before)};result=[]
    shifts=(-6,-12,-24,-36,-60,-90,6,12,24,36,60,90) if kind=='leaf' else (6,12,24,36,60,90,120,150,-6,-12,-24,-36,-60,-90,-120,-150)
    for shift in shifts:
        for yaw in (0,-15,15,-30,30,-60,60,-90,90,180):
            pose=((before[0]+yaw)%360,max(-85,min(85,before[1]+shift)))
            direction=joint_direction(*pose)
            if pose in seen:continue
            seen.add(pose)
            if math.degrees(math.acos(max(-1,min(1,dot(direction,input_direction)))))>(excursion_limit_deg or (120 if kind=='leaf' else 75)):continue
            result.append(pose)
            if len(result)>=limit:return result
    return result


def cooperative_joint_candidates(before,input_direction,*,lower_first,excursion_limit_deg=75):
    """Cover both elevation hemispheres; preference must not become exclusion."""
    original_azimuth,_=joint_angles(input_direction)
    candidates=joint_candidates(before,input_direction,kind='reproductive',limit=400,excursion_limit_deg=excursion_limit_deg)
    seen=set(candidates)|{tuple(before)}
    for elevation in range(-80,81,10):
        for step in range(24):
            pose=((original_azimuth+step*15)%360,float(elevation))
            direction=joint_direction(*pose)
            if pose not in seen and math.degrees(math.acos(max(-1,min(1,dot(direction,input_direction)))))<=excursion_limit_deg:
                candidates.append(pose);seen.add(pose)
    candidates.insert(0,tuple(before))
    candidates.sort(key=lambda pose:((pose[1]>before[1]) if lower_first else (pose[1]<before[1]),abs(pose[1]-before[1])))
    return candidates


def revise_pedicel_mobility(plant,limit_deg,*,reason):
    """Explicit, hashed engineering search revision; calyx axes stay immutable."""
    if not math.isfinite(limit_deg) or not 75<=limit_deg<=180 or not reason:
        raise ValueError('Explicit reason and bounded pedicel mobility required')
    initialize_growth_poses(plant)
    policy=dict(version='pedicel-mobility-review/1',excursion_from_input_deg=float(limit_deg),
        status='engineering_heuristic',reason=reason,calyx_gravity_axis='unchanged',
        interpretation='Search freedom, not a measured botanical pose distribution')
    digest=hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    plant.metadata.setdefault('nodal_mobility_revisions',[]).append(dict(policy=policy,sha256=digest))
    for axis in axes(plant.axes):
        for node in axis.nodes:
            if node.reproductive_unit:
                node.reproductive_unit.pedicel.provenance[KEY].update(excursion_limit_deg=float(limit_deg),mobility_revision_sha256=digest)
    return policy


def restore_calyx_toward_gravity(plant,unit_ids,*,fraction=1.):
    """Explicit pendulous relaxation: never tilt farther from down or sideways."""
    from .reproductive_orientation import organ_direction
    if not math.isfinite(fraction) or not 0<=fraction<=1:raise ValueError('Gravity restoration fraction must be in [0,1]')
    requested=set(unit_ids)
    available={n.reproductive_unit.id:n.reproductive_unit for a in axes(plant.axes) for n in a.nodes if n.reproductive_unit}
    if requested-set(available):raise ValueError('Unknown requested calyx units')
    planned=[]
    for identity in sorted(requested):
        u=available[identity]
        if u.calyx is None or 'reproductive_orientation' not in u.provenance:raise ValueError('Gravity restoration requires a pendulous calyx')
        initial=u.provenance.get(KEY,{}).get('calyx_input_direction',organ_direction(u))
        direction=unit(add(mul(initial,1-fraction),(0.,0.,-fraction)))
        planned.append((u,initial,direction))
    before=protected_anatomy(plant);initialize_growth_poses(plant)
    for u,initial,direction in planned:
        u.provenance.setdefault(KEY,{}).update(calyx_direction=list(direction),calyx_input_direction=list(initial),
            frame='plant_gravity_down',method='gravity_restoring_only',fraction=fraction,status='engineering_heuristic')
    assert protected_anatomy(plant)==before
    plant.metadata.setdefault('calyx_gravity_restoration',[]).append(dict(units=sorted(requested),fraction=fraction,
        status='engineering_heuristic',scope='more downward only; no lateral escape or dimension change'))
    from .grammar import record_reproductive_counts
    record_reproductive_counts(plant,'adapted')


def protected_anatomy(plant):
    axes=deepcopy(plant.to_dict()['axes']);counts=dict(axes=0,nodes=0,leaves=0,flowers=0,fruits=0,calyces=0)
    def visit(items):
        for axis in items:
            counts['axes']+=1;counts['nodes']+=len(axis['nodes'])
            for part in axis['internodes']:part['provenance'].pop(KEY,None)
            for node in axis['nodes']:
                leaf=node.get('leaf')
                if leaf:counts['leaves']+=1;leaf['provenance'].pop(KEY,None)
                u=node.get('reproductive_unit')
                if u:
                    u['provenance'].pop(KEY,None)
                    u['pedicel']['provenance'].pop(KEY,None)
                    counts['flowers']+=u['stage']=='flower';counts['fruits']+=u['fruit'] is not None;counts['calyces']+=u['calyx'] is not None
            visit(axis['child_axes'])
    visit(axes)
    return dict(sha256=hashlib.sha256(json.dumps(axes,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),counts=counts)


def axes(items):
    for axis in items:yield axis;yield from axes(axis.child_axes)


def coarsen_stem_guides(proxies):
    """One conservative curve envelope per bone, never change rendered stems."""
    from .collisions import _frame_from_long
    groups={};other=[]
    for p in proxies:
        if p.kind=='stem' and p.axis_id:groups.setdefault(p.group_id,[]).append(p)
        else:other.append(p)
    for group in groups.values():
        group.sort(key=lambda p:int(p.proxy_id.rsplit('_',1)[1]))
        a,b=group[0].start,group[-1].end
        radius=max(p.radius+max(point_segment_distance(p.start,a,b),point_segment_distance(p.end,a,b)) for p in group)
        other.append(replace(group[0],start=a,end=b,center=mul(add(a,b),.5),radius=radius,axes=_frame_from_long(unit(sub(b,a)))))
    return other


class ProxyIndex:
    def __init__(self,proxies,cell=.6):
        self.cell=cell;self.proxies={p.proxy_id:p for p in proxies};self.grid={};self.members={}
        for p in proxies:self.put(p)
    def cells(self,p):
        lo,hi=p.aabb(.012);a=[math.floor(v/self.cell) for v in lo];b=[math.floor(v/self.cell) for v in hi]
        return {(x,y,z) for x in range(a[0],b[0]+1) for y in range(a[1],b[1]+1) for z in range(a[2],b[2]+1)}
    def put(self,p):
        old=self.members.pop(p.proxy_id,set())
        for c in old:
            self.grid[c].discard(p.proxy_id)
        cells=self.cells(p);self.members[p.proxy_id]=cells;self.proxies[p.proxy_id]=p
        for c in cells:self.grid.setdefault(c,set()).add(p.proxy_id)
    def near(self,p):
        found=set()
        for c in self.cells(p):found.update(self.grid.get(c,()))
        return found


def repulsion_score(index,updates,*,margin=.003,rigid_ids=frozenset()):
    from .collisions import _is_exempt,_proxy_clearance,_aabb_overlap
    changed={p.proxy_id:p for p in updates};seen=set();energy=0.;contacts=[]
    unchanged_view=len(changed)==len(index.proxies) and all(p is index.proxies[k] for k,p in changed.items())
    temporary=ProxyIndex(updates,index.cell) if len(changed)>8 and not unchanged_view else None
    for left in updates:
        candidates=index.near(left) | (temporary.near(left) if temporary else set() if unchanged_view else set(changed))
        for identity in candidates:
            if identity==left.proxy_id:continue
            if identity in rigid_ids and left.proxy_id in rigid_ids:continue
            key=tuple(sorted((identity,left.proxy_id)))
            if key in seen:continue
            seen.add(key);right=changed.get(identity,index.proxies.get(identity))
            if right is None or left.kind==right.kind=='leaf' or _is_exempt(left,right):continue
            if not _aabb_overlap(left.aabb(margin),right.aabb(margin)):continue
            gap=_proxy_clearance(left,right)
            if gap<margin:
                depth=margin-gap;energy+=depth*depth
                contacts.append((left.proxy_id,right.proxy_id,gap))
    return energy,contacts


def downstream_module(axis,index):
    """Actual descendants of an insertion, including every attached organ."""
    nodes=list(axis.nodes[index:]);parts=list(axis.internodes[index+1:])
    attached={n.id for n in nodes}
    for child in axis.child_axes:
        if child.parent_node_id in attached:
            for branch in axes([child]):nodes.extend(branch.nodes);parts.extend(branch.internodes)
    return nodes,parts


def local_joint_candidates(axis,index,bone_frames,*,excursion_limit_deg=35):
    """Two-bone inverse kinematics: move one insertion, hold both ends fixed.

    The joint follows the intersection circle of the two length spheres.
    Every distal insertion beyond the following bone stays in place. This is
    an engineering posture search, not tissue elasticity or a force law.
    """
    if not 0<=index<len(axis.internodes)-1:return []
    first,second=axis.internodes[index:index+2]
    a=bone_frames[first.id]['start'];b=bone_frames[second.id]['end']
    current=bone_frames[first.id]['end'];delta=sub(b,a);distance=math.sqrt(dot(delta,delta))
    l1,l2=first.length_cm*.08,second.length_cm*.08
    if distance<1e-10:return []
    longitudinal=unit(delta);height=(l1*l1-l2*l2+distance*distance)/(2*distance)
    radius2=l1*l1-height*height
    if radius2<=1e-16:return []
    center=add(a,mul(longitudinal,height));radius=math.sqrt(radius2)
    v=unit(sub(current,center));w=unit(cross(longitudinal,v));result=[]
    for degrees in (-5,5,-10,10,-20,20,-40,40,-60,60,-90,90,-120,120,180):
        angle=math.radians(degrees)
        point=add(center,mul(add(mul(v,math.cos(angle)),mul(w,math.sin(angle))),radius))
        directions=(unit(sub(point,a)),unit(sub(b,point)))
        if any(math.degrees(math.acos(max(-1,min(1,dot(d,p.provenance[KEY]['input_direction'])))))>excursion_limit_deg+1e-8
               for p,d in zip((first,second),directions)):continue
        result.append(dict(degrees=degrees,point=point,first_direction=directions[0],second_direction=directions[1],
            delta_z=point[2]-current[2],fixed_start=a,fixed_end=b,nominal_lengths_preserved=True))
    return sorted(result,key=lambda row:(row['delta_z']>1e-10,abs(row['degrees']),row['degrees']))


def counterbend_candidates(axis,index,bone_frames,*,bearing,excursion_limit_deg=35):
    """Fold two existing bones while keeping their end on the growth ray.

    Both lengths are immutable. The distal anchor may move toward the basal
    anchor along their original growth direction; it cannot drift sideways.
    This introduces local nodal room without translating the upper crown
    laterally or making a camera-conditioned change.
    """
    if not 0<=index<len(axis.internodes)-1:return []
    first,second=axis.internodes[index:index+2];a=bone_frames[first.id]['start'];b=bone_frames[second.id]['end']
    current=bone_frames[first.id]['end'];growth=unit(sub(b,a));l1,l2=first.length_cm*.08,second.length_cm*.08
    radial=sub(bearing,mul(growth,dot(bearing,growth)))
    if dot(radial,radial)<1e-12:radial=cross(growth,(1.,0.,0.))
    if dot(radial,radial)<1e-12:radial=cross(growth,(0.,1.,0.))
    v=unit(radial);w=unit(cross(growth,v));distance=math.sqrt(dot(sub(b,a),sub(b,a)));result=[]
    for degrees in (5,10,15,20,25,30):
        angle=math.radians(degrees);transverse2=l1/l2*math.sin(angle)
        if transverse2>=1:continue
        for azimuth in (0,-30,30,-60,60,90,-90,180):
            yaw=math.radians(azimuth);transverse=add(mul(v,math.cos(yaw)),mul(w,math.sin(yaw)))
            d1=add(mul(growth,math.cos(angle)),mul(transverse,math.sin(angle)))
            d2=sub(mul(growth,math.sqrt(1-transverse2*transverse2)),mul(transverse,transverse2))
            if any(math.degrees(math.acos(max(-1,min(1,dot(d,p.provenance[KEY]['input_direction'])))))>excursion_limit_deg+1e-8 for p,d in ((first,d1),(second,d2))):continue
            point=add(a,mul(d1,l1));end=add(point,mul(d2,l2));shortening=distance-dot(sub(end,a),growth)
            if shortening<-1e-8:continue
            result.append(dict(degrees=degrees,azimuth=azimuth,first_direction=d1,second_direction=d2,point=point,
                delta_z=point[2]-current[2],fixed_growth_ray=True,axial_shortening_bu=shortening,
                end_anchor=end,nominal_lengths_preserved=True))
    return sorted(result,key=lambda row:(row['delta_z']>1e-10,row['degrees'],abs(row['azimuth']),row['azimuth']))


def shifted(proxy,delta):
    return replace(proxy,center=add(proxy.center,delta),
        start=add(proxy.start,delta) if proxy.start is not None else None,
        end=add(proxy.end,delta) if proxy.end is not None else None)


def branch_candidate(axis,index,new_direction,node_frames,bone_frames,proxy_index):
    """Rotate one nodal bone; translate its complete distal module rigidly."""
    from .geometry_contracts import stem_centerline_points,axis_sag_factor
    from .collisions import _frame_from_long
    part=axis.internodes[index];old=bone_frames[part.id]
    new_end=add(old['start'],mul(new_direction,part.length_cm*.08));delta=sub(new_end,old['end'])
    nodes,parts=downstream_module(axis,index)
    groups={f'growth:{p.id}' for p in parts}
    for node in nodes:
        if node.leaf:groups.add(f'growth:{node.leaf.id}')
        if node.reproductive_unit:groups.add(f'growth:{node.reproductive_unit.id}')
    changed=[shifted(p,delta) for p in proxy_index.proxies.values() if p.group_id in groups]
    reframe=[part]+([axis.internodes[index+1]] if index+1<len(axis.internodes) else [])
    for segment in reframe:
        segment_index=axis.internodes.index(segment);state=bone_frames[segment.id]
        start=state['start'] if segment is part else add(state['start'],delta)
        end=new_end if segment is part else add(state['end'],delta)
        incoming,direction=segment_directions(segment,axis.internodes[segment_index-1] if segment_index else None)
        points=stem_centerline_points(start,end,axis_sag_factor(axis),points_count=13 if axis.provenance.get('continuous_tangent_v140') else 6,
            endpoint_tangents=(incoming,direction) if axis.provenance.get('continuous_tangent_v140') else None)
        group=f'growth:{segment.id}';changed=[p for p in changed if p.group_id!=group]
        templates=sorted((p for p in proxy_index.proxies.values() if p.group_id==group),key=lambda p:int(p.proxy_id.rsplit('_',1)[1]))
        if len(templates)==1 and len(points)>2:
            template=templates[0];a,b=points[0],points[-1]
            radius=max(segment.radius_cm*.08,.008)+max(point_segment_distance(p,a,b) for p in points)
            changed.append(replace(template,start=a,end=b,center=mul(add(a,b),.5),radius=radius,axes=_frame_from_long(unit(sub(b,a)))))
            continue
        for template,a,b in zip(templates,points,points[1:]):
            changed.append(replace(template,start=a,end=b,center=mul(add(a,b),.5),axes=_frame_from_long(unit(sub(b,a)))))
    reframed_groups={f'growth:{p.id}' for p in reframe}
    rigid={p.proxy_id for p in changed if p.group_id not in reframed_groups}
    return changed,rigid,delta,nodes,parts,reframe


def initialize_growth_poses(plant):
    from .collisions import build_scene_proxies,_append_leaf_proxies,_leaf_direction_with_clearance_lift
    from .scene import CultivationScene,PlantInstance
    from .organ_frames import local_cone_leaf_direction
    from .reproductive_orientation import pedicel_direction
    if any(n.leaf and n.leaf.provenance.get('insertion_frame')!='local_cone_v2' for a in axes(plant.axes) for n in a.nodes):
        raise ValueError('Nodal growth poses require the explicit local_cone_v2 leaf frame')
    scene=CultivationScene('growth','growth',plant.seed,plant_instances=[PlantInstance('growth',plant.seed)])
    frames={};bones={};proxies=build_scene_proxies(scene,{'growth':plant},frame_output=frames,bone_output=bones)
    for axis in axes(plant.axes):
        for part in axis.internodes:
            if KEY not in part.provenance:
                b=bones['growth'][part.id]
                part.provenance[KEY]=dict(version=VERSION,frame='plant',direction=list(b['direction']),
                    input_direction=list(b['direction']),input_incoming_direction=list(b['incoming']),
                    status='engineering_heuristic',includes_generated_bend_and_load=True)
        for node in axis.nodes:
            if node.leaf and KEY not in node.leaf.provenance:
                leaf=node.leaf;direction=local_cone_leaf_direction(frames['growth'][node.id][1],leaf.azimuth_deg,leaf.insertion_angle_deg)
                direction=_leaf_direction_with_clearance_lift(direction,leaf.petiole_length_cm*.08,leaf.clearance_lift_cm*.08)
                leaf.provenance[KEY]=dict(version=VERSION,frame='plant',direction=list(direction),input_direction=list(direction),status='engineering_heuristic')
            if node.reproductive_unit:
                p=node.reproductive_unit.pedicel
                if KEY not in p.provenance:
                    direction=pedicel_direction(node.reproductive_unit)
                    p.provenance[KEY]=dict(version=VERSION,frame='plant',direction=list(direction),input_direction=list(direction),status='engineering_heuristic')
    return scene


def resolve_nodal_repulsion(plant,*,sweeps=6,step_deg=6.,max_seconds=120.,margin=.003,checkpoint=None):
    """Transactional public entry point; restore the tree on a failed search."""
    if isinstance(sweeps,bool) or not isinstance(sweeps,int) or sweeps<1:
        raise ValueError('Positive integer sweeps required')
    if not all(math.isfinite(x) for x in (step_deg,max_seconds,margin)) or not 0<step_deg<=15 or max_seconds<=0 or margin<0:
        raise ValueError('Invalid nodal search limits')
    saved=deepcopy(plant.__dict__)
    try:
        return _resolve_nodal_repulsion(plant,sweeps=sweeps,step_deg=step_deg,max_seconds=max_seconds,margin=margin,checkpoint=checkpoint)
    except Exception:
        plant.__dict__.clear();plant.__dict__.update(saved)
        raise


def _resolve_nodal_repulsion(plant,*,sweeps,step_deg,max_seconds,margin,checkpoint):
    """Bottom-to-top sweep; try lower actions before any raising action.

    The iterative proxy phase is deliberately separate from physical admission.
    Leaf and reproductive articulations belong to their actual axillary nodes.
    Internode changes translate the complete distal module, never remove it.
    """
    from .collisions import build_scene_proxies,_append_leaf_proxies,_append_reproductive_proxies
    from .execution_budget import awake_seconds
    before=protected_anatomy(plant);scene=initialize_growth_poses(plant);instance=scene.plant_instances[0]
    changes=[];history=[];started=awake_seconds()
    for sweep in range(sweeps):
        frames={};bones={};proxies=build_scene_proxies(scene,{'growth':plant},frame_output=frames,bone_output=bones)
        proxies=coarsen_stem_guides(proxies)
        index=ProxyIndex(proxies);node_frames=frames['growth'];node_owner={n.id:(a,n) for a in axes(plant.axes) for n in a.nodes}
        ordered=sorted(node_owner,key=lambda n:(node_frames[n][0][2],node_owner[n][0].order,node_owner[n][1].position_index,n))
        initial,_=repulsion_score(index,proxies,margin=margin);pass_changes=0
        for mode in ('lower','raise','lateral'):
            for node_id in ordered:
                if awake_seconds()-started>=max_seconds:break
                axis,node=node_owner[node_id];point,tangent=node_frames[node_id]
                controls=[]
                if node.leaf:controls.append(('leaf',node.leaf,f'growth:{node.leaf.id}'))
                if node.reproductive_unit:controls.append(('reproductive',node.reproductive_unit,f'growth:{node.reproductive_unit.id}'))
                for kind,organ,group in controls:
                    old=[p for p in index.proxies.values() if p.group_id==group]
                    energy,contacts=repulsion_score(index,old,margin=margin)
                    if not contacts:continue
                    target=organ if kind=='leaf' else organ.pedicel;record=target.provenance[KEY];current=tuple(record['direction'])
                    moves=((-step_deg,0.),(-step_deg*.5,0.)) if mode=='lower' else ((step_deg,0.),(step_deg*.5,0.)) if mode=='raise' else ((0.,-step_deg),(0.,step_deg))
                    # Calyx priority is to rise only after lower-phase attempts;
                    # calyx gravity orientation itself is never a search DOF.
                    if kind=='reproductive' and mode=='lower':continue
                    best=None
                    for pitch,yaw in moves:
                        direction=pitched(current,pitch,yaw)
                        if pitch<0 and direction[2]>=current[2]-1e-10:continue
                        if pitch>0 and direction[2]<=current[2]+1e-10:continue
                        limit=120 if kind=='leaf' else record.get('excursion_limit_deg',75)
                        if math.degrees(math.acos(max(-1.,min(1.,dot(direction,record['input_direction'])))))>limit:continue
                        record['direction']=list(direction);trial=[]
                        if kind=='leaf':_append_leaf_proxies(trial,organ,point,tangent,instance)
                        else:_append_reproductive_proxies(trial,organ,point,instance)
                        if any(p.aabb()[0][2]<.010 for p in trial):continue
                        score,_=repulsion_score(index,trial,margin=margin)
                        if score<energy-1e-12 and (best is None or score<best[0]):best=(score,direction,trial,pitch,yaw)
                    record['direction']=list(current)
                    if best:
                        record['direction']=list(best[1]);record['last_phase']=mode
                        for p in best[2]:index.put(p)
                        changes.append(dict(sweep=sweep,node=node_id,kind=kind,phase=mode,pitch=best[3],yaw=best[4],energy_before=energy,energy_after=best[0]))
                        pass_changes+=1
                if axis.order==0 or awake_seconds()-started>=max_seconds:continue
                position=axis.nodes.index(node)
                if position>=len(axis.internodes):continue
                part=axis.internodes[position];record=part.provenance[KEY];current=tuple(record['direction'])
                moves=((-step_deg,0.),) if mode=='lower' else ((step_deg,0.),) if mode=='raise' else ((0.,-step_deg),(0.,step_deg))
                best=None
                for pitch,yaw in moves:
                    direction=pitched(current,pitch,yaw)
                    if pitch<0 and direction[2]>=current[2]-1e-10:continue
                    if pitch>0 and direction[2]<=current[2]+1e-10:continue
                    if math.degrees(math.acos(max(-1.,min(1.,dot(direction,record['input_direction'])))))>35:continue
                    record['direction']=list(direction)
                    trial,rigid,delta,moved_nodes,moved_parts,reframe=branch_candidate(axis,position,direction,node_frames,bones['growth'],index)
                    if any(p.aabb()[0][2]<.010 for p in trial):continue
                    old=[index.proxies[p.proxy_id] for p in trial]
                    energy,contacts=repulsion_score(index,old,margin=margin,rigid_ids=rigid)
                    if not contacts:continue
                    score,_=repulsion_score(index,trial,margin=margin,rigid_ids=rigid)
                    if score<energy-1e-12 and (best is None or score<best[0]):
                        best=(score,direction,trial,delta,moved_nodes,moved_parts,reframe,energy,pitch,yaw)
                record['direction']=list(current)
                if best:
                    score,direction,trial,delta,moved_nodes,moved_parts,reframe,energy,pitch,yaw=best
                    record['direction']=list(direction);record['last_phase']=mode
                    for p in trial:index.put(p)
                    for moved in moved_nodes:
                        point,tangent=node_frames[moved.id];node_frames[moved.id]=(add(point,delta),direction if moved.id==node_id else tangent)
                    for moved in moved_parts:
                        state=bones['growth'][moved.id];state['start']=add(state['start'],delta);state['end']=add(state['end'],delta)
                    bones['growth'][part.id]['end']=add(bones['growth'][part.id]['end'],delta)
                    for segment in reframe:
                        i=axis.internodes.index(segment);incoming,d=segment_directions(segment,axis.internodes[i-1] if i else None)
                        bones['growth'][segment.id].update(incoming=incoming,direction=d)
                    changes.append(dict(sweep=sweep,node=node_id,kind='nodal_branch',phase=mode,pitch=pitch,yaw=yaw,
                        energy_before=energy,energy_after=score,distal_nodes=len(moved_nodes),subtree_preserved=True))
                    pass_changes+=1
            if awake_seconds()-started>=max_seconds:break
        final,remaining=repulsion_score(index,list(index.proxies.values()),margin=margin)
        history.append(dict(sweep=sweep,energy_before=initial,energy_after=final,proxy_contacts=len(remaining),changes=pass_changes))
        if checkpoint:checkpoint(plant,history[-1])
        if not pass_changes or awake_seconds()-started>=max_seconds:break
    assert protected_anatomy(plant)==before,'Growth repulsion changed topology or organ dimensions'
    report=dict(version=VERSION,status='proxy_search_requires_mesh_audit',direction_priority=['lower','raise','lateral'],
        traversal='ascending node height, then order/index/ID',history=history,changes=changes,
        elapsed_active_seconds=awake_seconds()-started,anatomy_before=before,anatomy_after=protected_anatomy(plant),
        interpretation='Engineering repulsion metaphor; no magnetic or biomechanical force calibrated',physical_validity='not established')
    plant.metadata.setdefault('nodal_repulsion_history',[]).append(report)
    plant.metadata['nodal_repulsion']=report;plant.metadata['model_stage']='adapted'
    plant.metadata.pop('nodal_repulsion_pending',None)
    from .grammar import record_reproductive_counts
    record_reproductive_counts(plant,'adapted')
    return report
