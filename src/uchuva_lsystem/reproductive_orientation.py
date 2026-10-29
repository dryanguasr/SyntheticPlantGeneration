"""Serialized reproductive posture, independent of architecture and camera.

The numerical cone is an engineering prior informed by local visual review;
botanical descriptions do not provide measured angular distributions. Missing
policy preserves the historical straight, collinear pedicel/calyx interpreter.
"""
from __future__ import annotations

import hashlib
import math
import random

POLICY = "gravity_pendulous_v1"
KEY = "reproductive_orientation"


def pedicel_direction(unit, azimuth_offset_deg=0., angle_offset_deg=0.):
    """Angle is depression below horizontal, not inclination from vertical."""
    if 'nodal_growth_repulsion_v1' in unit.pedicel.provenance:
        from .nodal_repulsion import pose_direction,pitched
        direction=pose_direction(unit.pedicel,(0,0,-1))
        return pitched(direction,-angle_offset_deg,azimuth_offset_deg) if angle_offset_deg or azimuth_offset_deg else direction
    azimuth = math.radians(unit.pedicel.azimuth_deg + azimuth_offset_deg)
    if unit.stage == "flower" and KEY not in unit.provenance:
        length = math.hypot(.9, .18)
        return (.9*math.cos(azimuth)/length, .9*math.sin(azimuth)/length, .18/length)
    angle = math.radians(max(5., min(72., unit.pedicel.angle_deg + angle_offset_deg)))
    return (math.cos(azimuth)*math.cos(angle), math.sin(azimuth)*math.cos(angle), -math.sin(angle))


def organ_direction(unit, fallback=None):
    """Direction from pedicel insertion toward distal calyx/flower tip."""
    pose = unit.provenance.get(KEY)
    if pose is None:
        return fallback if fallback is not None else pedicel_direction(unit)
    if pose.get("policy") != POLICY or pose.get("frame") != "plant_gravity_down":
        raise ValueError("Unknown reproductive orientation policy/frame")
    tilt, azimuth = float(pose["inclination_from_down_deg"]), float(pose["azimuth_deg"])
    bounds = pose["inclination_bounds_deg"]
    if not (all(math.isfinite(x) for x in (tilt, azimuth, *bounds))
            and 0 <= bounds[0] <= tilt <= bounds[1] < 90 and 0 <= azimuth < 360):
        raise ValueError("Invalid pendulous reproductive orientation")
    adapted=unit.provenance.get('nodal_growth_repulsion_v1',{}).get('calyx_direction')
    if adapted is not None:
        record=unit.provenance['nodal_growth_repulsion_v1']
        if (record.get('frame')!='plant_gravity_down' or record.get('method')!='gravity_restoring_only'
                or record.get('status')!='engineering_heuristic'):
            raise ValueError('Missing explicit gravity-restoration provenance')
        if len(adapted)!=3 or not all(math.isfinite(v) for v in adapted) or abs(sum(v*v for v in adapted)-1)>1e-5:
            raise ValueError('Invalid adapted calyx direction')
        inclination=math.degrees(math.acos(max(-1.,min(1.,-adapted[2]))))
        bearing=math.radians(azimuth)
        side_error=abs(adapted[0]*math.sin(bearing)-adapted[1]*math.cos(bearing))
        forward=adapted[0]*math.cos(bearing)+adapted[1]*math.sin(bearing)
        if inclination>tilt+1e-5 or side_error>1e-5 or forward<-1e-5:
            raise ValueError('Gravity restoration may only reduce the original tilt, without lateral rotation')
        fraction=record.get('fraction');initial=record.get('calyx_input_direction',[])
        original=(math.sin(math.radians(tilt))*math.cos(bearing),math.sin(math.radians(tilt))*math.sin(bearing),-math.cos(math.radians(tilt)))
        if (not isinstance(fraction,(int,float)) or not math.isfinite(fraction) or not 0<=fraction<=1 or len(initial)!=3
                or any(abs(a-b)>1e-5 for a,b in zip(initial,original))):
            raise ValueError('Gravity-restoration input or fraction does not match original pose')
        target=[(1-fraction)*v for v in original];target[2]-=fraction;length=math.sqrt(sum(v*v for v in target))
        if any(abs(a-b/length)>1e-5 for a,b in zip(adapted,target)):
            raise ValueError('Gravity-restoration direction does not match its recorded fraction')
        return tuple(adapted)
    tilt, azimuth = math.radians(tilt), math.radians(azimuth)
    return (math.sin(tilt)*math.cos(azimuth), math.sin(tilt)*math.sin(azimuth), -math.cos(tilt))


def assign_reproductive_orientation(plant, parameters):
    """Assign post-generation poses using separate per-organ random streams."""
    config = parameters.get("reproduction", {}).get("organ_orientation")
    if config is None:
        return
    if config.get("value") != POLICY:
        raise ValueError("Unknown reproductive organ orientation policy")
    low, high = map(float, config["inclination_from_down_deg_range"])
    mode = float(config["mode_deg"])
    if not (all(math.isfinite(x) for x in (low, mode, high)) and 0 <= low <= mode <= high < 90):
        raise ValueError("Invalid reproductive orientation sampling cone")
    def visit(axes):
        for axis in axes:
            for node in axis.nodes:
                unit = node.reproductive_unit
                if unit is None:
                    continue
                seed = int(hashlib.sha256(f"{plant.seed}:{POLICY}:{unit.id}".encode()).hexdigest()[:16], 16)
                rng = random.Random(seed)
                unit.provenance[KEY] = dict(policy=POLICY, frame="plant_gravity_down",
                    inclination_from_down_deg=round(rng.triangular(low, high, mode), 6),
                    azimuth_deg=round(rng.uniform(0, 359.999999), 6),
                    inclination_bounds_deg=[low, high], seed=seed, status="engineering_heuristic",
                    anatomical_attachment="organ proximal pole at pedicel distal endpoint",
                    evidence="local human review; Kew Flora Zambesiaca / World Agroforestry qualitative descriptions",
                    numeric_uncertainty="angular cone is not a measured botanical distribution")
            visit(axis.child_axes)
    visit(plant.axes)
    plant.metadata[KEY] = dict(policy=POLICY, frame="plant_gravity_down",
        inclination_bounds_deg=[low, high], status="engineering_heuristic",
        independent_of="camera, lighting, materials, reproductive counts and contact-search pedicel angles")
