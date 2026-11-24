#!/usr/bin/env python3
"""Bind a nominal CAD operating-envelope result to one experimental part.

This is neither native-physics acceptance nor a four-millimetre self-clearance
PASS. The two pre-existing planar cover interfaces remain explicitly tangent.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from summarize_gripper_brep_envelope import summarize

EXPECTED_PAIRS = [
    ['Eslabon L:1', 'Eslabon L:2'],
    ['Eslabon 1:1', 'Engranaje recto2:1'], ['Eslabon 1:2', 'Engranaje recto1:1'],
    ['Gripper y engranaje:1', 'Eslabon L:1'], ['Gripper y engranaje:1', 'Eslabon L:2'],
    ['Gripper 1:1', 'Eslabon L:1'], ['Gripper 1:1', 'Eslabon L:2'],
    ['gomas:1', 'gomas:2'], ['Mordaza blanda:1', 'Mordaza blanda:2'], ['Cuchilla:1', 'Cuchilla:2']]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kinematic_visual_fingerprint(data):
    """Bind CAD shapes and their full kinematic placement, independent of PID.

    Mesh identity uses bytes/SI scale, not a movable package's URI. This is
    deliberately not a substitute for the runtime collider/physics manifest.
    """
    joint_keys=('name','type','parent','child','origin','child_pose','axis','zero_offset')
    links=[]
    for link in data['links']:
        visuals=[]
        for visual in link['visuals']:
            geometry={k:v for k,v in visual['geometry'].items() if k!='uri'}
            visuals.append({'name':visual['name'],'pose':visual['pose'],'geometry':geometry})
        links.append({'name':link['name'],'visuals':sorted(visuals,key=lambda v:v['name'])})
    payload={'links':sorted(links,key=lambda r:r['name']),
             'joints':sorted(({k:j[k] for k in joint_keys if k in j} for j in data['joints']),key=lambda r:r['name']),
             'frames':sorted(data.get('frames',[]),key=lambda r:r['name'])}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def prove_cover_tangencies(geometry, motion):
    """Verify disjoint Y half-spaces invariant along the ideal four-bar path.

    The 0.1-nm tolerance concerns transformed floating point coordinates only;
    it cannot admit a physical penetration or relax any motion clearance.
    Native BRep must independently report zero overlapping volume.
    """
    if geometry.get('status') != 'COMPLETED' or geometry.get('source_files_unchanged') is not True:
        raise ValueError('Complete source-intact native body bounds are required')
    if geometry['assembly_sha256'].lower() != motion['assembly_sha256'].lower():
        raise ValueError('Tangency proof and operational path have different assemblies')
    tolerance = 1e-10
    rows = []
    for name in ('Eslabon L:1', 'Eslabon L:2'):
        records = [r for r in geometry['pairs'] if r['occurrences'] == ['Gripper 1:1', name] and r['driver_rad'] == 0]
        if len(records) != 1:
            raise ValueError('Need one native reference-pose cover pair for ' + name)
        row = records[0]
        if row['interference_count'] or row['interference_volumes_m3'] or row['minimum_distance_m'] != 0:
            raise ValueError('Cover pair must be an exact native zero-volume tangency')
        parts = {p['occurrence']: p for p in row['visualization_parts']}
        cover_min = parts['Gripper 1:1']['native_body_range_bounds_m']['min'][1]
        jaw_max = parts[name]['native_body_range_bounds_m']['max'][1]
        if not all(math.isfinite(v) for v in (cover_min,jaw_max)) or abs(cover_min - jaw_max) > tolerance:
            raise ValueError('Native body bounds do not establish the shared contact plane')
        for part_name in ('Gripper 1:1', name):
            reference = motion['samples'][0]['occurrence_transforms_m'][part_name]
            if len(reference)!=16 or not all(math.isfinite(v) for v in reference):
                raise ValueError('Invalid native reference transform')
            if abs(reference[4]) > 1e-12 or abs(reference[6]) > 1e-12 or abs(abs(reference[5])-1) > 1e-12:
                raise ValueError('The reference transform does not preserve the assembly Y direction')
            for sample in motion['samples']:
                transform = sample['occurrence_transforms_m'][part_name]
                if len(transform)!=16 or not all(math.isfinite(v) for v in transform):
                    raise ValueError('Invalid native motion transform')
                if any(abs(transform[k] - reference[k]) > 1e-12 for k in (4, 5, 6, 7)):
                    raise ValueError('The nominal path does not preserve the contact half-spaces')
        rows.append({'occurrences': row['occurrences'], 'cover_min_y_m': cover_min,
                     'jaw_max_y_m': jaw_max, 'native_volumetric_intersection': False})
    return {'status': 'IDEAL_COPLANAR_CONTACT_WITHOUT_VOLUME_PROVED',
            'coordinate_rounding_tolerance_m': tolerance, 'pairs': rows,
            'proof': 'Native body range boxes occupy opposite Y half-spaces. All ideal revolute axes are parallel to Y and every motion transform preserves its Y row, so neither solid can enter the other open half-space. The plane itself remains a zero-clearance contact.',
            'positive_clearance_claimed': False, 'collision_exclusion_authorized': False}


def evaluate(revision, motion, observed, summary):
    """Evaluate the unchanged CAD criteria; callers also verify source bytes."""
    checks = {}
    checks['native_sources_unchanged'] = observed.get('source_files_unchanged') is True
    checks['original_sources_unchanged'] = revision.get('original_sources_unchanged') is True
    checks['private_arm_chain_verified'] = revision.get('full_arm_reference', {}).get('status') == 'PRIVATE_CHAIN_VERIFIED'
    checks['assembly_placements_unchanged'] = revision.get('maximum_saved_assembly_transform_change', float('inf')) <= 1e-10
    checks['pin_hole_preserved'] = revision.get('feature', {}).get('pin_hole_preserved') is True
    checks['same_L2_source'] = revision.get('final_L2_copy_sha256') == revision['plan']['original_part_sha256']
    checks['native_plane_guard_rechecked'] = len(revision.get('native_matching_planes', [])) >= 1
    planes = revision.get('actual_cut_planes', [])
    ligament = min((row['offset_local_m'] - revision['plan']['pin_hole_radius_m'] for row in planes), default=-1)
    checks['unchanged_minimum_ligament_1p900mm'] = ligament >= .0019
    pairs = summary['pairs']
    checks['zero_native_volumetric_interference'] = all(not row['interference_count'] and not row['interference_volumes_m3'] for row in observed['pairs'])
    critical = [row for row in pairs if row['occurrences'] == ['Gripper y engranaje:1', 'Eslabon L:1']]
    checks['continuous_housing_L1_reserve_0p200mm'] = len(critical) == 1 and critical[0]['continuous_lower_gap_m'] >= .0002
    tangencies = [['Gripper 1:1', 'Eslabon L:1'], ['Gripper 1:1', 'Eslabon L:2']]
    checks['all_other_noncontact_pairs_continuously_separated'] = all(
        row['continuous_lower_gap_m'] > 0 for row in pairs if row['occurrences'] not in tangencies)
    checks['ten_diagnostic_pairs_present'] = sorted(row['occurrences'] for row in pairs) == sorted(EXPECTED_PAIRS)
    checks['full_functional_interval'] = summary['driver_interval_rad'] == [0, revision['plan']['target_driver_rad']]
    # This does not certify positive clearance at a deliberately tangent face.
    # The separate geometric plane evidence is required by main before PASS.
    return {'checks': checks, 'minimum_geometric_ligament_m': ligament,
            'continuous_critical_gap_m': critical[0]['continuous_lower_gap_m'] if len(critical) == 1 else None,
            'intentional_cover_tangencies': tangencies,
            'status': 'PASS' if all(checks.values()) else 'FAIL'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('revision-root', 'motion', 'observation', 'contact-geometry', 'profile', 'reference-profile', 'curve', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    revision_path = args.revision_root / 'revision_report.json'
    revision, motion, observed = read(revision_path), read(args.motion), read(args.observation)
    if observed.get('motion_file_sha256', '').lower() != sha(args.motion):
        raise ValueError('Native observation did not measure these exact motion inputs')
    if revision['artifact_sha256']['source/' + revision['plan']['gripper_assembly']] != observed['assembly_sha256'].lower():
        raise ValueError('Observation uses a different revised CAD assembly')
    visual = args.revision_root / 'L1_clearance_document_local.obj'
    part = args.revision_root / 'source' / revision['plan']['private_part']
    for path in (visual, part):
        key = path.relative_to(args.revision_root).as_posix()
        if sha(path) != revision['artifact_sha256'][key]:
            raise ValueError('Revised source or visual changed after the native export')
    contact_geometry = read(args.contact_geometry)
    matching_sources = [value.lower() for key, value in contact_geometry['source_sha256'].items()
                        if key.replace('\\', '/').endswith('/' + revision['plan']['private_part'])]
    if matching_sources != [sha(part)]:
        raise ValueError('Native contact geometry must reference this exact dedicated L1 CAD part')
    tangent = prove_cover_tangencies(contact_geometry, motion)
    profile=read(args.profile)
    matching_visuals=[v for link in profile['links'] for v in link['visuals'] if v['name']=='part_104']
    if len(matching_visuals)!=1 or matching_visuals[0]['geometry'].get('sha256')!=sha(visual):
        raise ValueError('Profile does not contain the exact revised L1 visual')
    reference=read(args.reference_profile);curve=read(args.curve)
    if sha(args.reference_profile) not in curve['source_files_sha256'].values():
        raise ValueError('The ideal CAD trajectory did not use this reference profile')
    comparison=copy.deepcopy(profile)
    old=[v for link in reference['links'] for v in link['visuals'] if v['name']=='part_104']
    if len(old)!=1:raise ValueError('Reference profile must contain exactly one L1 visual')
    for link in comparison['links']:
        for item in link['visuals']:
            if item['name']=='part_104':item['geometry']=copy.deepcopy(old[0]['geometry'])
    if kinematic_visual_fingerprint(comparison)!=kinematic_visual_fingerprint(reference):
        raise ValueError('Kinematics or other CAD shapes changed outside the validated L1 revision')
    summary = summarize(motion, observed)
    result = evaluate(revision, motion, observed, summary)
    result.update({'schema_version': 'cad-gripper-operating-envelope-admission/1.0',
                   'scope': 'nominal_CAD_operating_geometry_only',
                   'interval_rad': summary['driver_interval_rad'],
                   'visual_obj_sha256': sha(visual), 'cad_part_sha256': sha(part),
                   'kinematic_visual_fingerprint':kinematic_visual_fingerprint(profile),
                   'source_sha256': {str(p): sha(p) for p in (revision_path, args.motion, args.observation, args.contact_geometry, args.profile, args.reference_profile, args.curve, Path(__file__), Path(__file__).with_name('summarize_gripper_brep_envelope.py'))},
                   'intentional_cover_tangency_proof': tangent,
                   'native_samples': len(motion['samples']), 'native_pair_evaluations': len(observed['pairs']),
                   'continuous_envelope': summary,
                   'external_clearance_m_unchanged': .004,
                   'collision_exclusions_authorized': False,
                   'native_dynamics_acceptance': 'NOT_EXECUTED_BY_THIS_GEOMETRIC_AUDIT',
                   'hardware_or_structural_validation': 'NOT_VALIDATED',
                   'limitations': ['Approximate user-reported openings do not calibrate the hardware.',
                                   'Native closure/gear drift and mesh discretization need their separate unchanged acceptance criteria.',
                                   'Coplanar cover contact is retained explicitly; it is not positive clearance or a four-millimetre margin PASS.']})
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write('\n')
    print(json.dumps({'status': result['status'], 'checks': result['checks']}))


if __name__ == '__main__':
    main()
