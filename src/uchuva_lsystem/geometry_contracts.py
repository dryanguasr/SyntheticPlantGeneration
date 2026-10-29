"""Pure geometry interpretations shared by Blender and collision diagnostics.

These helpers report geometric evidence, never botanical validity or image
occlusion. Lengths retain the coordinate system of their input points.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

Vec3 = tuple[float, float, float]


def axis_sag_factor(axis: Any) -> float:
    """Use the same declared training-phase interpretation in every consumer."""
    if axis.training_phase in {
        "overhead_strings_manual_initial_guess", "bouquet_open_and_lift_v4"
    }:
        return 0.0
    return (0.012 + axis.reproductive_load * 0.025 if axis.order == 0
            else 0.045 + axis.reproductive_load * 0.115)


def stem_centerline_points(
    start: Iterable[float], end: Iterable[float], sag_factor: float,
    *, points_count: int = 6,
    endpoint_tangents: tuple[Iterable[float], Iterable[float]] | None = None,
) -> list[Vec3]:
    """Sample the existing polyline or cubic Bezier interpretation in world units.

Bezier points approximate a curve for proxies; they are not a mesh collision
certificate. Like the Blender interpreter, tangent-constrained curves do not
also receive an additional gravity sag.
"""
    if points_count < 2:
        raise ValueError("At least two centerline points are required")
    a, b = tuple(start), tuple(end)
    vector = tuple(y - x for x, y in zip(a, b))
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-12:
        return [a] * points_count
    sag = length * sag_factor * (math.hypot(vector[0], vector[1]) / length) ** 1.35
    controls = None
    if endpoint_tangents is not None:
        tangents = []
        for tangent in endpoint_tangents:
            values = tuple(tangent)
            norm = math.sqrt(sum(value * value for value in values))
            if norm <= 0:
                raise ValueError("A Bezier endpoint tangent cannot be zero")
            tangents.append(tuple(value / norm for value in values))
        controls = (
            tuple(a[i] + tangents[0][i] * length / 3 for i in range(3)),
            tuple(b[i] - tangents[1][i] * length / 3 for i in range(3)),
        )
    result = []
    for index in range(points_count):
        t = index / (points_count - 1)
        if controls is None:
            p = tuple(a[i] + vector[i] * t for i in range(3))
            result.append((p[0], p[1], p[2] - sag * math.sin(math.pi * t)))
        else:
            c, d = controls
            result.append(tuple(
                (1 - t) ** 3 * a[i] + 3 * (1 - t) ** 2 * t * c[i]
                + 3 * (1 - t) * t ** 2 * d[i] + t ** 3 * b[i]
                for i in range(3)))
    return result


def bounds_from_points(points: Iterable[Iterable[float]]) -> dict[str, Any]:
    """Return the axis-aligned envelope of actual transformed geometry points."""
    minimum, maximum = [math.inf] * 3, [-math.inf] * 3
    count = 0
    for point in points:
        values = tuple(point)
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError("Geometry points must have three finite coordinates")
        count += 1
        for i, value in enumerate(values):
            minimum[i] = min(minimum[i], value)
            maximum[i] = max(maximum[i], value)
    if not count:
        raise ValueError("Cannot measure an empty geometry envelope")
    return {"minimum": minimum, "maximum": maximum,
            "extent": [b - a for a, b in zip(minimum, maximum)],
            "point_count": count}


def compare_fruit_calyx_bounds(fruit: dict, calyx: dict, *, epsilon: float = 1e-7) -> dict:
    """A fruit outside the calyx AABB cannot be fully enclosed; the converse is unknown."""
    excess = [max(0.0, calyx['minimum'][i] - fruit['minimum'][i],
                  fruit['maximum'][i] - calyx['maximum'][i]) for i in range(3)]
    outside = any(value > epsilon for value in excess)
    return {"fruit_outside_calyx_aabb": outside, "axis_excess": excess,
            "solid_containment": "not_possible_within_envelope" if outside else "not_established",
            "surface_intersection": "not_measured", "visual_occlusion": "not_measured"}


def summarize_geometry_envelopes(objects: list[dict]) -> dict:
    """Aggregate evaluated-mesh envelopes, including hidden internal fruit geometry."""
    plants: dict[str, list[dict]] = {}
    units: dict[tuple[str, str], dict[str, dict]] = {}
    for item in objects:
        plants.setdefault(item['plant_id'], []).append(item)
        if item.get('reproductive_instance_id') and item['semantic'] in {'calyx', 'fruit'}:
            key = (item['plant_id'], item['reproductive_instance_id'])
            unit = units.setdefault(key, {})
            if item['semantic'] in unit:
                raise ValueError(f"Duplicate {item['semantic']} geometry for reproductive instance {key}")
            unit[item['semantic']] = item
    by_plant = {}
    for plant_id, rows in plants.items():
        envelope = bounds_from_points(p for row in rows for p in
                                      (row['bounds']['minimum'], row['bounds']['maximum']))
        extent = envelope['extent']
        by_plant[plant_id] = dict(envelope, object_count=len(rows),
            width_to_height=max(extent[:2]) / extent[2] if extent[2] > 0 else None,
            interpretation='evaluated_world_aabb_not_sum_of_branch_projections')
    pairs = []
    for (plant_id, unit_id), entries in sorted(units.items()):
        if set(entries) == {'calyx', 'fruit'}:
            pairs.append(dict(plant_id=plant_id, reproductive_instance_id=unit_id,
                fruit_object=entries['fruit']['name'], calyx_object=entries['calyx']['name'],
                **compare_fruit_calyx_bounds(entries['fruit']['bounds'], entries['calyx']['bounds'])))
    return {'version': 'evaluated-geometry-envelopes/1', 'objects': objects,
            'plants': by_plant, 'fruit_calyx_pairs': pairs,
            'fruit_outside_calyx_envelope_count': sum(p['fruit_outside_calyx_aabb'] for p in pairs),
            'physical_collision': 'requires_separate_mesh_audit',
            'visual_occlusion': 'not_measured',
            'inside_aabb_is_not_solid_containment': True}
