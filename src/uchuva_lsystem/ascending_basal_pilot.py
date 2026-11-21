"""Photo-guided morphological alternatives for human review, not calibrated growth."""
import math
import random
from .balanced_basal_pilot import balanced_basal_pilot

VARIANTS = {'A_vertical': 16, 'B_intermedia': 27, 'C_abierta': 38}


def ascending_basal_pilot(plant, count, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown architecture variant')
    result = balanced_basal_pilot(plant, count)
    rng = random.Random(plant.seed + 183)
    root = result.axes[0]
    source_length = sum(s.length_cm for s in plant.axes[0].internodes)
    for i, segment in enumerate(root.internodes):
        segment.length_cm = 12 / count
        segment.radius_cm = .65 * (1 - .03 * i)
    def direct(axis, azimuth, polar, depth):
        axis.resolved_direction = (math.sin(polar)*math.cos(azimuth),
                                   math.sin(polar)*math.sin(azimuth), math.cos(polar))
        for segment in axis.internodes:
            segment.bend_angle_deg *= .25
            if depth > 1:
                segment.length_cm *= .75
        for node in axis.nodes:
            for leaf in ([node.leaf] if node.leaf else []):
                leaf.azimuth_deg = (leaf.azimuth_deg + rng.uniform(-35,35)) % 360
                leaf.insertion_angle_deg = rng.uniform(35,80)
                leaf.twist_deg = rng.uniform(-25,25)
        for child in axis.child_axes:
            child_az = azimuth + rng.uniform(-1.5,1.5)
            child_polar = math.radians(rng.uniform(20,55))
            direct(child, child_az, child_polar, depth+1)
    lengths=[]
    for i, axis in enumerate(root.child_axes):
        # Each structural axis keeps substantial height instead of dividing one
        # trunk's length among all axes, which caused the former flattened crown.
        target = source_length * rng.uniform(.78,.92)
        factor = target / sum(s.length_cm for s in axis.internodes)
        for j, segment in enumerate(axis.internodes):
            segment.length_cm *= factor
            segment.radius_cm = .48 * (1 - .55*j/max(1,len(axis.internodes)-1))
        azimuth = 2*math.pi*i/count + rng.uniform(-.22,.22)
        polar = math.radians(VARIANTS[variant] + rng.uniform(-5,5))
        direct(axis,azimuth,polar,1)
        axis.growth_budget_length_cm=target
        lengths.append(target)
    result.parameter_preset='ascending-basal-review/0.1/'+variant
    result.metadata['ascending_basal_pilot']=dict(version='0.1',variant=variant,
        seed=plant.seed,structural_branches=count,scaffold_lengths_cm=lengths,
        parameter_status='engineering_heuristic_not_measured_from_photos',
        reference='user_basal_references/reference_01.jpg and reference_05.jpg',
        accepted_for_dataset=False,limitations=['Nodal redistribution assay, not developmental growth',
        'No light-competition solver or mechanical tutoring calibration',
        'Collisions and real density still require validation'])
    return result
