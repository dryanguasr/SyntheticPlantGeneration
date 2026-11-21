"""Reproducible appearance diversity independent of architecture and camera.

These are engineering sampling choices, not measurements of senescence or
agronomic maturity. Every visual bank receives the same plant/leaf decisions.
"""
from __future__ import annotations

import random
from .appearance_profiles import component_seed

VERSION = "plant-appearance-diversity/1"


def plant_appearance(seed, plant_id, scene_index, slot, real_class_counts):
    rng = random.Random(component_seed(seed, "foliage", plant_id))
    stratum = (2 * scene_index + slot) % 3
    foliage = ("green", "mixed", "yellowing")[stratum]
    fraction = (.06, .24, .48)[stratum] + rng.uniform(-.035, .035)
    # A separate stream prevents foliage colour from predicting capacho class.
    classes = random.Random(component_seed(seed, "class_mixture", plant_id))
    total = sum(real_class_counts)
    if total <= 0 or len(real_class_counts) != 3:
        raise ValueError("Three nonempty training class counts required")
    draws = [classes.gammavariate(max(.5, 18 * n / total), 1.) for n in real_class_counts]
    weights = [max(.12, v / sum(draws)) for v in draws]
    weights = [v / sum(weights) for v in weights]
    return dict(version=VERSION, plant_id=plant_id, foliage=foliage,
        senescent_leaf_fraction=fraction,
        hue_shift=(-.005, -.025, -.045)[stratum] + rng.uniform(-.004, .004),
        saturation=1.12, value=(1., 1.02, 1.04)[stratum],
        class_probabilities=weights, seed=component_seed(seed,"foliage",plant_id),
        basis="engineering_heuristic; foliage and capacho class independent")


def appearance_assignments(seed, plant_id, unit_ids, probabilities):
    ordered = sorted(unit_ids, key=lambda k: (component_seed(seed,"class_order",plant_id+":"+k), k))
    result = {}
    for index, unit_id in enumerate(ordered):
        q = component_seed(seed,"class_draw",plant_id+":"+unit_id) / 2**32
        # Assign states to existing units; never create organs for coverage.
        cls = index if index < 3 else (0 if q < probabilities[0] else 1 if q < sum(probabilities[:2]) else 2)
        result[unit_id] = cls
    return result


def leaf_appearance(seed, plant_id, leaf_id, profile):
    q = component_seed(seed,"leaf_colour",plant_id+":"+leaf_id) / 2**32
    return "leaf_senescent" if q < profile["senescent_leaf_fraction"] else "leaf"
