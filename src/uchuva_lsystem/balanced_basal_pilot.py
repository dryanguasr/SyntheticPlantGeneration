"""Organ-conserving structural redistribution assay, not a growth simulation."""
from copy import deepcopy
import math
import random
from .morphology import Axis,Node,Internode,AxillaryBud


def balanced_basal_pilot(plant,count):
    if count not in range(2,6) or len(plant.axes)!=1:raise ValueError('Expected one root and 2..5 scaffolds')
    result=deepcopy(plant);old=result.axes[0];rng=random.Random(plant.seed+count*71)
    def size(a):return len(a.nodes)+sum(size(c) for c in a.child_axes)
    children={n.id:[] for n in old.nodes}
    for c in old.child_axes:children[c.parent_node_id].append(c)
    packets=[(n,s,children[n.id]) for n,s in zip(old.nodes,old.internodes)]
    groups=[[] for _ in range(count)];loads=[0]*count
    for packet in sorted(packets,key=lambda p:1+sum(size(c) for c in p[2]),reverse=True):
        k=min(range(count),key=lambda i:(loads[i],i));groups[k].append(packet)
        loads[k]+=1+sum(size(c) for c in packet[2])
    if any(not g for g in groups):raise ValueError('Too few root nodes')
    root=Axis(id='balanced_common_base',order=0,resolved_direction=(0,0,1))
    radius=max(s.radius_cm for s in old.internodes)*1.2
    total_length=sum(s.length_cm for s in old.internodes)
    weights=[rng.uniform(.9,1.1) for _ in groups]
    def rotate(a,angle):
        a.order+=1
        for n in a.nodes:
            n.order+=1
            if n.axillary_bud:n.axillary_bud.order+=1
        for s in a.internodes:s.order+=1
        if a.resolved_direction:
            x,y,z=a.resolved_direction;a.resolved_direction=(x*math.cos(angle)-y*math.sin(angle),x*math.sin(angle)+y*math.cos(angle),z)
        for c in a.child_axes:rotate(c,angle)
    original_az=math.atan2(old.resolved_direction[1],old.resolved_direction[0]) if old.resolved_direction else math.radians(old.azimuth_deg)
    for k,pack in enumerate(groups):
        node_id=f'balanced_base_node_{k}';axis_id=f'balanced_scaffold_{k}'
        root.internodes.append(Internode(f'balanced_base_segment_{k}',0,1.2/count,radius*(1-.03*k)))
        root.nodes.append(Node(node_id,0,0,k,axillary_bud=AxillaryBud(f'balanced_base_bud_{k}',node_id,0,state='branch',branch_id=axis_id)))
        az=2*math.pi*k/count+rng.uniform(-.12,.12);polar=math.radians(rng.uniform(30,40))
        a=Axis(axis_id,1,parent_node_id=node_id,resolved_direction=(math.sin(polar)*math.cos(az),math.sin(polar)*math.sin(az),math.cos(polar)))
        pack.sort(key=lambda p:p[0].position_index)
        factor=(total_length*weights[k]/sum(weights))/sum(p[1].length_cm for p in pack)
        for i,(n,s,subtrees) in enumerate(pack):
            n.order=1;n.position_index=i
            if n.axillary_bud:n.axillary_bud.order=1
            s.order=1;s.length_cm*=factor;s.radius_cm=min(s.radius_cm,radius*.8)
            a.nodes.append(n);a.internodes.append(s)
            for c in subtrees:rotate(c,az-original_az);a.child_axes.append(c)
        a.max_internodes=len(a.nodes);a.growth_budget_length_cm=sum(s.length_cm for s in a.internodes)
        root.child_axes.append(a)
    result.axes=[root];result.parameter_preset='balanced-basal-redistribution/0.1'
    result.metadata['balanced_basal_pilot']=dict(version='0.1',count=count,seed=plant.seed,
        descendant_nodes=loads,source_nodes_preserved=True,added_common_base_nodes=count,
        parameter_status='engineering_heuristic',growth_simulation=False,
        limitations=['Redistributed nodal packages, not developmental growth','Light competition and support fit not implemented','Intersections and real apparent density require review'])
    return result
