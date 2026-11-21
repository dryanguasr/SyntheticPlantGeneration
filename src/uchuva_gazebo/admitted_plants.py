"""Portable, evidence-linked plant hand-off; no Blender or Gazebo runtime."""
from __future__ import annotations
from copy import deepcopy
import math
from uchuva_lsystem.morphology import Plant
from uchuva_lsystem.nodal_repulsion import protected_anatomy
from uchuva_lsystem.spatial_admission import validate_plan
from uchuva_lsystem.validation import validate_morphology_tree
from .interfaces import build_gazebo_export_plan, GazeboExportConfig


def build_admitted_plant_bundle(plant, admission, audits, *, metres_per_scene_unit, lod=1):
    """Preserve the complete tree/poses and check supplied static evidence.

    Evidence is caller-supplied, not a fresh mesh audit of a simulator. The
    consumer must honour the embedded pose metadata and explicit scene units.
    """
    if not math.isfinite(metres_per_scene_unit) or metres_per_scene_unit<=0:
        raise ValueError('Explicit positive scene-unit conversion required')
    anatomy=protected_anatomy(plant)
    if admission.get('status')!='admitted' or admission.get('seed')!=plant.seed:
        raise ValueError('Plant has no matching admission')
    if admission.get('counts')!=anatomy['counts'] or admission.get('anatomy_sha256')!=anatomy['sha256']:
        raise ValueError('Admission does not match retained anatomy')
    mesh,ground,orientation=audits['mesh'],audits['ground'],audits['orientation']
    if mesh.get('physical_collision_count')!=0 or mesh.get('truncated'):
        raise ValueError('Complete zero-hard-crossing evidence required')
    if ground.get('status')!='valid' or orientation.get('status')!='valid':
        raise ValueError('Ground/orientation evidence is not valid')
    validation=validate_morphology_tree(plant,stage='adapted')
    if validation['errors']:raise ValueError('Invalid morphology')
    proof=validate_plan(plant);original=admission['original_counts'];kept=anatomy['counts']
    if proof.get('applied') and proof['original_counts']!=original:
        raise ValueError('Admission original differs from reversible spatial plan')
    for name in ['fruits','leaves']:
        if not 0<=original[name]-kept[name] or (original[name] and 20*(original[name]-kept[name])>=original[name]):
            raise ValueError('Strict per-organ loss threshold violated')
    if proof.get('leaf_nominal_area_loss_fraction',0)>=.05:
        raise ValueError('Nominal leaf envelope loss threshold violated')
    return dict(schema_version='uchuva.admitted_gazebo_bundle/1',plant=deepcopy(plant.to_dict()),
        source_seed=plant.seed,parameter_preset=plant.parameter_preset,
        scene_units=dict(metres_per_scene_unit=metres_per_scene_unit,status='explicit_engineering_input'),
        admission=deepcopy(admission),spatial_admission_verification=proof,
        gazebo_plan=build_gazebo_export_plan(plant,GazeboExportConfig(lod=lod)).to_dict(),
        static_evidence=dict(origin='caller_supplied_audits',hard_crossings=0,ground='valid',orientation='valid'),
        limitations=['This is not a new simulator collision audit or SDF export.',
            'Retain plant metadata and nodal poses when interpreting geometry.',
            'Leaf-leaf soft occupancy and proximity warnings retain the source policy.',
            'No exhaustive flowers/context contacts, dynamics, masses or stiffness certification.'])
