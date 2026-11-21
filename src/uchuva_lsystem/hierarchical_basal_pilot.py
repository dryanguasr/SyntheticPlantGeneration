"""Hierarchical basal architecture for visual development, not calibrated growth."""
import math
import random
from copy import deepcopy
from .morphology import Axis, Node, Internode, AxillaryBud


def refresh_branch_junction_contract(plant):
    """Index all outgoing axes without redefining a fork as multiple buds.

    child_axes and parent_node_id remain authoritative. The legacy singular
    bud.branch_id is retained, but must not be used to enumerate a junction.
    Call again after changing parent links.
    """
    junctions = []
    def walk(axis):
        nodes = {node.id: node for node in axis.nodes}
        children = {}
        for child in axis.child_axes:
            if child.parent_node_id not in nodes:
                raise ValueError(f'Unknown parent node for {child.id}')
            children.setdefault(child.parent_node_id, []).append(child.id)
        for node_id, child_ids in children.items():
            bud = nodes[node_id].axillary_bud
            junctions.append(dict(parent_axis_id=axis.id, node_id=node_id,
                                  child_axis_ids=child_ids,
                                  legacy_bud_branch_id=bud.branch_id if bud else None))
        for child in axis.child_axes:
            walk(child)
    for axis in plant.axes:
        walk(axis)
    plant.metadata['branch_junction_contract'] = dict(
        version='1.0', source='child_axes + parent_node_id', junctions=junctions,
        legacy_branch_id_role='single reference, not complete outgoing topology',
        botanical_interpretation='engineering topology; bud origin unvalidated')


def hierarchical_basal_pilot(plant, count, levels=3):
    if count not in range(2,6) or levels not in (3,4):
        raise ValueError('Expected 2..5 basal axes and 3..4 successive branching levels')
    result=deepcopy(plant);rng=random.Random(plant.seed+971)
    templates=[]
    def collect(axis):
        templates.extend(n for n in axis.nodes if n.leaf or n.reproductive_unit)
        for child in axis.child_axes:collect(child)
    for axis in plant.axes:collect(axis)
    rng.shuffle(templates)
    serial=0;forks=[]
    def build(depth, parent, az, polar, length, radius):
        nonlocal serial
        serial+=1;aid=f'hierarchy_axis_{serial}'
        axis=Axis(aid,depth,parent_node_id=parent,resolved_direction=(math.sin(polar)*math.cos(az),math.sin(polar)*math.sin(az),math.cos(polar)))
        # Smooth A2-like inward curvature; retain a positive upward tip tangent.
        terminal=max(math.radians(8),polar-math.radians(24))
        steps=12
        for i in range(steps):
            nid=f'{aid}_node_{i}'
            axis.internodes.append(Internode(f'{aid}_segment_{i}',depth,length/steps,radius*(1-.28*i/(steps-1)),bend_angle_deg=math.degrees(terminal-polar)/steps,bend_azimuth_deg=math.degrees(az)))
            node=Node(nid,depth,0,i)
            # Expose the lower framework; organs remain nodal, never scattered.
            if depth>=2 and i in (3,6,9,11) and templates:
                template=templates.pop();node.leaf=deepcopy(template.leaf);node.reproductive_unit=deepcopy(template.reproductive_unit)
                if node.leaf:node.leaf.node_id=nid
                if node.reproductive_unit:
                    node.reproductive_unit.node_id=nid
                    if node.reproductive_unit.pedicel:node.reproductive_unit.pedicel.node_id=nid
            axis.nodes.append(node)
        if depth<=levels:
            # One lateral at an earlier node and a fork at the tip: multiple
            # emergence positions, continuation plus opposite outgoing axes.
            indices=(7,11,11) if depth==1 else (11,11)
            phase=az+rng.uniform(-.65,.65)
            for j,index in enumerate(indices):
                child_az=phase+(j-(1 if depth==1 else 0))*math.pi+rng.uniform(-.24,.24)
                child_polar=math.radians(rng.uniform(23,48))
                child_radius=axis.internodes[index].radius_cm*rng.uniform(.64,.76)
                child=build(depth+1,axis.nodes[index].id,child_az,child_polar,length*rng.uniform(.61,.72),child_radius)
                axis.child_axes.append(child)
                axis.nodes[index].axillary_bud=AxillaryBud(f'{aid}_bud_{index}',axis.nodes[index].id,depth,state='branch',branch_id=child.id)
            forks.append(dict(axis_id=aid,child_axes=[c.id for c in axis.child_axes],node_indices=list(indices)))
        axis.max_internodes=steps;axis.growth_budget_length_cm=length
        return axis
    root=Axis('hierarchy_common_base',0,resolved_direction=(0,0,1))
    for i in range(count):
        nid=f'hierarchy_base_{i}'
        root.internodes.append(Internode(f'hierarchy_base_segment_{i}',0,7/count,1.05*(1-.025*i)))
        root.nodes.append(Node(nid,0,0,i))
        axis=build(1,nid,2*math.pi*i/count+rng.uniform(-.2,.2),math.radians(rng.uniform(33,42)),rng.uniform(40,48),rng.uniform(.65,.72))
        root.child_axes.append(axis)
        root.nodes[-1].axillary_bud=AxillaryBud(f'base_bud_{i}',nid,0,state='branch',branch_id=axis.id)
    root.max_internodes=count;root.growth_budget_length_cm=7
    result.axes=[root];result.parameter_preset='hierarchical-basal-review/0.1'
    result.metadata['hierarchical_basal_pilot']=dict(version='0.1',count=count,successive_branching_levels=levels,seed=plant.seed,axis_count=serial,forks=forks,parameter_status='engineering_heuristic',accepted_for_dataset=False,limitations=['Architecture and organ density changed together for human review, not controlled efficacy comparison','Opposed azimuths with jitter, not strict botanical phyllotaxis','No calibrated mechanical support or light competition'])
    refresh_branch_junction_contract(result)
    return result
