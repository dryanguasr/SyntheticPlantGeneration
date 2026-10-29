"""Photo-guided nodal foliage refill on the approved P4/P5 architecture family."""
import math
import random
from copy import deepcopy
from .canopy_preference_pilot import canopy_preference_pilot,node_positions


def foliage_reference_pilot(source, density=1.25, preserve_leaf_senescence=False):
    plant=canopy_preference_pilot(source)
    rng=random.Random(source.seed+8191)
    templates=[]
    def collect(axis):
        templates.extend(deepcopy(n.leaf) for n in axis.nodes if n.leaf)
        for child in axis.child_axes:collect(child)
    for axis in source.axes:collect(axis)
    if not templates:raise ValueError('Source has no leaf templates')
    positions,axes=node_positions(plant)
    height=max(p[2] for p in positions.values());radii={}
    for p in positions.values():
        band=min(5,int(p[2]/height*6));radii[band]=max(radii.get(band,0),math.hypot(p[0],p[1]))
    before=sum(n.leaf is not None for a in axes.values() for n in a.nodes)
    added=0
    for a in axes.values():
        if a.order<1:continue
        for i,n in enumerate(a.nodes):
            x,y,z=positions[n.id];band=min(5,int(z/height*6))
            exterior=min(1,math.hypot(x,y)/max(radii[band],1e-9))
            tip=not a.child_axes and i>=8
            terminal_endpoint=not a.child_axes and i==len(a.nodes)-1
            eligible=i in (2,4,6,8,10,11) or tip
            probability=min(.98,density*(.22+.70*exterior**1.5+(.38 if tip else 0)))
            if a.order==1:probability*=.65  # Variable basal foliage; exposed bases are not universal.
            if n.leaf is None and (terminal_endpoint or (eligible and rng.random()<probability)):
                n.leaf=deepcopy(rng.choice(templates));n.leaf.id=n.id+'_refill_leaf';n.leaf.node_id=n.id;added+=1
            if n.leaf:
                leaf=n.leaf;leaf.shape='ovate_cordate_acuminate'
                leaf.width_cm=max(leaf.width_cm,leaf.length_cm*rng.uniform(.69,.83))
                if tip:
                    scale=rng.uniform(.80,1.00);leaf.length_cm*=scale;leaf.width_cm*=scale
                leaf.azimuth_deg=(math.degrees(math.atan2(y,x))+rng.uniform(-85,85))%360
                leaf.insertion_angle_deg=rng.uniform(110,165) if not tip else rng.uniform(65,145)
                if not preserve_leaf_senescence:leaf.senescence=min(leaf.senescence,.18)
                leaf.curl=rng.uniform(.10,.24);leaf.twist_deg=rng.uniform(-38,38)
                leaf.provenance['surface_relief_ratio']=rng.uniform(.055,.095)
                leaf.provenance.update(reference_refill=True,exterior_proxy=exterior,terminal_leaf=tip,terminal_endpoint=terminal_endpoint,parameter_status='engineering_heuristic')
    plant.parameter_preset='foliage-reference-review/0.6'
    plant.metadata['foliage_reference_pilot']=dict(version='0.6',seed=source.seed,density=density,leaves_before=before,leaves_added=added,leaves_after=before+added,reference='user_foliage_reference_20261014.jpg',accepted_for_dataset=False,limitations=['Visual fit without physical scale','Leaf shape and density changed together','No quantitative light competition or collision correction'])
    plant.metadata['foliage_reference_pilot']['preserve_leaf_senescence']=preserve_leaf_senescence
    return plant


def scale_petiole_lengths(plant, factor):
    """Paired proportion trial; factor is an uncalibrated visual hypothesis."""
    if not 0 < factor <= 2:
        raise ValueError('Petiole factor must be in (0, 2]')
    result = deepcopy(plant)
    for axis in node_positions(result)[1].values():
        for node in axis.nodes:
            if node.leaf:
                node.leaf.provenance['petiole_length_before_review_cm'] = node.leaf.petiole_length_cm
                node.leaf.petiole_length_cm *= factor
    result.metadata['petiole_length_review'] = dict(
        factor=factor, parameter_status='engineering_heuristic', accepted_for_dataset=False)
    return result


def space_secondary_leaves(plant, ratio):
    """Opt-in arclength spacing experiment, not a calibrated light model.

    Keep distal leaves first, including every terminal leaf. Basal axes and
    reproductive structures are untouched. Compare on the same morphology.
    """
    if not 0 < ratio <= 1:
        raise ValueError('Spacing ratio must be in (0, 1]')
    result = deepcopy(plant)
    removed = []
    for axis in node_positions(result)[1].values():
        if axis.order < 2:
            continue
        distances = []
        distance = 0.0
        for segment in axis.internodes:
            distance += segment.length_cm
            distances.append(distance)
        retained = None
        for node, distance in reversed(list(zip(axis.nodes, distances))):
            if node.leaf is None:
                continue
            length = node.leaf.length_cm
            if retained and retained[0] - distance < ratio * (length + retained[1]) / 2:
                removed.append(node.leaf.id)
                node.leaf = None
            else:
                retained = (distance, length)
    result.metadata['leaf_spacing_review'] = dict(
        ratio=ratio, removed_leaf_ids=removed, version='1.0',
        parameter_status='engineering_heuristic', accepted_for_dataset=False,
        limitation='Within-axis spacing only; does not solve inter-axis collisions or light competition')
    return result


def stagger_secondary_branches(plant):
    """Paired geometry-only review: distribute secondary forks along parent axes.

    Preserve all organs, lengths and directions. This is an engineering
    alternative to the terminal-fork heuristic, not a calibrated growth law.
    """
    result=deepcopy(plant)
    rng=random.Random(plant.seed+7601)
    changes=[]
    def walk(axis):
        if axis.order>=2 and len(axis.child_axes)>=2:
            child=axis.child_axes[0]
            old=child.parent_node_id
            new=axis.nodes[rng.randint(4,9)]
            child.parent_node_id=new.id
            for node in axis.nodes:
                if node.axillary_bud and node.axillary_bud.branch_id==child.id:
                    node.axillary_bud=None
            from .morphology import AxillaryBud
            new.axillary_bud=AxillaryBud(child.id+'_emergence',new.id,axis.order,state='branch',branch_id=child.id)
            changes.append(dict(child=child.id,old_node=old,new_node=new.id))
        for child in axis.child_axes:walk(child)
    for axis in result.axes:walk(axis)
    result.metadata['staggered_secondary_review']={'version':'1.0','changes':changes,'parameter_status':'engineering_heuristic','organs_preserved':True,'accepted_for_dataset':False}
    from .hierarchical_basal_pilot import refresh_branch_junction_contract
    refresh_branch_junction_contract(result)
    return result


def spread_leaf_azimuths(plant, half_range_deg):
    """Paired orientation-only hypothesis; not a calibrated light response."""
    if not 0 < half_range_deg <= 180:
        raise ValueError('Azimuth half range must be in (0, 180]')
    result = deepcopy(plant)
    rng = random.Random(plant.seed + 19403)
    positions, axes = node_positions(result)
    for axis in axes.values():
        for node in axis.nodes:
            if node.leaf:
                x, y, _ = positions[node.id]
                node.leaf.provenance['azimuth_before_spread_deg'] = node.leaf.azimuth_deg
                node.leaf.azimuth_deg = (math.degrees(math.atan2(y, x)) + rng.uniform(-half_range_deg, half_range_deg)) % 360
    result.metadata['leaf_azimuth_review'] = dict(half_range_deg=half_range_deg,
        parameter_status='engineering_heuristic', accepted_for_dataset=False)
    return result


def splay_branch_junctions(plant, minimum_angle_deg=25):
    """Opt-in junction angle floor; preserve topology and organ dimensions."""
    from .collisions import _bend_direction, _load_deflection, _normalise
    if not 0 < minimum_angle_deg < 90:
        raise ValueError('Branch angle floor must be between zero and 90 degrees')
    result = deepcopy(plant)
    changes = []
    frames = {}
    def visit(axis):
        direction = _normalise(tuple(axis.resolved_direction))
        if axis.parent_node_id:
            parent = frames[axis.parent_node_id]
            dot = max(-1., min(1., sum(a*b for a,b in zip(direction,parent))))
            angle = math.acos(dot)
            if angle < math.radians(minimum_angle_deg):
                radial = tuple(a-dot*b for a,b in zip(direction,parent))
                if sum(x*x for x in radial) < 1e-12:
                    index = min(range(3),key=lambda i:abs(parent[i]))
                    radial = tuple(float(i==index)-parent[index]*parent[i] for i in range(3))
                radial = _normalise(radial)
                theta = math.radians(minimum_angle_deg)
                new = tuple(a*math.cos(theta)+b*math.sin(theta) for a,b in zip(parent,radial))
                changes.append(dict(axis_id=axis.id,before=list(direction),after=list(new),original_angle_deg=math.degrees(angle)))
                axis.resolved_direction = new
                direction = new
        for index,segment in enumerate(axis.internodes):
            direction = _bend_direction(direction,segment.bend_azimuth_deg,segment.bend_angle_deg)
            direction = _load_deflection(direction,axis,index,len(axis.internodes))
            if index < len(axis.nodes):frames[axis.nodes[index].id] = direction
        for child in axis.child_axes:visit(child)
    for axis in result.axes:visit(axis)
    result.metadata['junction_splay_review'] = dict(minimum_angle_deg=minimum_angle_deg,changes=changes,
        parameter_status='engineering_heuristic',accepted_for_dataset=False)
    return result
