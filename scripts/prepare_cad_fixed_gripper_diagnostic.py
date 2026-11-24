#!/usr/bin/env python3
"""Freeze only the CAD gripper at q0 for a base/arm/suspension diagnostic.

This is an explicit topology derivative, never a repaired operating gripper or
a harvest-capable model. Every source link, CAD asset, inertia and collision
policy is retained. All preparation checks are pure Python; no Gazebo launch.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_kinematics import forward_kinematics
from uchuva_gazebo.robot_sdf import resolved_robot_model, resolved_robot_contract
from uchuva_gazebo.robot_collision_filters import collision_masks


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def derive_fixed_gripper(source, evidence):
    """Remove exactly the gripper's moving coordinates, retaining its tree."""
    old = source.to_dict()
    new = copy.deepcopy(old)
    selected = {j['name'] for j in old['joints'] if j['child'].startswith('gripper_')}
    if not selected:
        raise ValueError('Source has no explicit CAD gripper subtree')
    for joint in old['joints']:
        in_subtree = joint['name'] in selected
        if in_subtree and (not joint['name'].startswith('gripper_') or joint['group'] not in ('passive','gripper')):
            raise ValueError('Ambiguous gripper joint assignment')
        if joint['parent'].startswith('gripper_') and not in_subtree:
            raise ValueError('Gripper subtree has an unclassified descendant')
        if in_subtree and (joint['type'] == 'fixed' or joint['zero_offset'] != 0):
            raise ValueError('Expected moving gripper with zero CAD offsets; do not silently change its pose')
    changed_indices = []
    for index, joint in enumerate(new['joints']):
        if joint['name'] in selected:
            joint['type'], joint['group'] = 'fixed', 'fixed'
            changed_indices.append(index)
    # No parent, child, origin or child_pose changes: auxiliary half-masses
    # remain in the fixed tree, rather than being discarded or duplicated.
    maps, removed = {}, {}
    selectors = {
        'actuators': lambda r: r['joint'] in selected,
        'closures': lambda r: r['moving_joint'] in selected,
        'gear_couplings': lambda r: r['driver'] in selected or r['follower'] in selected,
    }
    for key, should_remove in selectors.items():
        rows, mapping, discarded = [], {}, []
        for index, row in enumerate(old.get(key, [])):
            if should_remove(row):
                if key == 'closures' and not all(row[k].startswith('gripper_') for k in ('body','auxiliary')):
                    raise ValueError('Gripper closure crosses into another mechanism')
                if key == 'gear_couplings' and not {row['driver'], row['follower']} <= selected:
                    raise ValueError('Gear coupling crosses the gripper boundary')
                discarded.append(copy.deepcopy(row))
            else:
                mapping[index] = len(rows)
                rows.append(copy.deepcopy(row))
        if key in old:
            new[key] = rows
        maps[key], removed[key] = mapping, discarded
    removed_control = {name:settings for name,settings in new['control'].get('gripper',{}).items() if name in selected}
    unexpected = set(new['control'].get('gripper',{}))-selected
    if unexpected:
        raise ValueError('Gripper control names cross the selected subtree')
    new['control'].pop('gripper', None)

    def remap(path):
        tokens = path.split('/')
        if path == '/control/gripper' or path.startswith('/control/gripper/'):
            return None
        if len(tokens) > 2 and tokens[1] in maps and tokens[2].isdigit():
            replacement = maps[tokens[1]].get(int(tokens[2]))
            if replacement is None:
                return None
            tokens[2] = str(replacement)
        return '/'.join(tokens)

    new['parameter_metadata'] = {target:metadata for path,metadata in old['parameter_metadata'].items()
                                 if (target := remap(path)) is not None}
    new['derived_values'] = [{**row,'path':target} for row in old['derived_values']
                             if (target := remap(row['path'])) is not None]
    # A recipe must never restore an active joint type/group or alter its q0.
    for row in new['derived_values']:
        if any(row['path'].startswith('/joints/'+str(i)+'/') for i in changed_indices):
            raise ValueError('Selected gripper joint has an unresolved parameter recipe')
    new['capabilities'] = [value for value in old['capabilities'] if value != 'native_harvest']
    new['profile_id'] = old['profile_id']+'_fixed_gripper_q0_diagnostic'
    new['provenance'] = copy.deepcopy(evidence)
    for index in changed_indices:
        for field in ('type','group'):
            new['parameter_metadata'][f'/joints/{index}/{field}'] = {**evidence,'update_class':'model_regeneration'}
    robot = resolve_robot_profile(new)
    actual = robot.to_dict()
    # Reconstitute the exact source document to reject unrelated mutations,
    # including recipes that could otherwise recompute dimensions on resolve.
    reverse = copy.deepcopy(actual)
    for key in ('profile_id','provenance','capabilities','parameter_metadata','derived_values','actuators'):
        reverse[key] = copy.deepcopy(old[key])
    for key in ('closures','gear_couplings'):
        if key in old: reverse[key] = copy.deepcopy(old[key])
        else: reverse.pop(key,None)
    if 'gripper' in old['control']: reverse['control']['gripper'] = copy.deepcopy(old['control']['gripper'])
    for index in changed_indices: reverse['joints'][index] = copy.deepcopy(old['joints'][index])
    if reverse != old:
        raise ValueError('Unrelated source properties changed during derivation')
    masks_before, masks_after = collision_masks(old), collision_masks(actual)
    if masks_before != masks_after or actual['collision_policy'] != old['collision_policy']:
        raise ValueError('Collision masks or declared exclusions changed')
    q_old = {j['name']:0 for j in old['joints'] if j['type'] != 'fixed'}
    q_new = {j['name']:0 for j in actual['joints'] if j['type'] != 'fixed'}
    before, after = forward_kinematics(source,q_old), forward_kinematics(robot,q_new)
    positions = max(math.dist(before[n]['xyz_m'],after[n]['xyz_m']) for n in before)
    rotations = max(1-abs(sum(a*b for a,b in zip(before[n]['quaternion_xyzw'],after[n]['quaternion_xyzw']))) for n in before)
    if positions > 1e-12 or rotations > 1e-12:
        raise ValueError('Reference link/frame poses changed')
    return robot, {
        'fixed_joint_names':sorted(selected), 'removed_gripper_records':{**removed,'control':removed_control},
        'all_links_inertias_visuals_colliders_identical':actual['links']==old['links'],
        'collision_policy_identical':True,'collision_masks_identical':True,'link_masks':masks_after,
        'source_property_reconstruction_identical':True,
        'maximum_q0_position_difference_m':positions,'maximum_q0_quaternion_dot_difference':rotations,
        'link_count':len(actual['links']), 'visual_count':sum(len(l['visuals']) for l in actual['links']),
        'collision_count':sum(len(l['collisions']) for l in actual['links']),
        'total_mass_kg':sum(l['inertial']['mass_kg'] for l in actual['links']),
        'remaining_closures':len(actual.get('closures',[])), 'remaining_gear_couplings':len(actual.get('gear_couplings',[])),
    }


def xml_value(element):
    return [element.tag,sorted(element.attrib.items()),(element.text or '').strip(),[xml_value(c) for c in element]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--asset-root',type=Path,required=True)
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Use a fresh output directory')
    source_hash = sha(args.profile)
    source = resolve_robot_profile(args.profile)
    if source.sha256 != args.expected_source_sha256:
        raise ValueError('Source canonical identity differs')
    sources = [Path(__file__), ROOT/'src/uchuva_gazebo/robot_spec.py',ROOT/'src/uchuva_gazebo/robot_kinematics.py',
               ROOT/'src/uchuva_gazebo/robot_sdf.py',ROOT/'src/uchuva_gazebo/robot_collision_filters.py',ROOT/'configs/robots/robot_spec.schema.json']
    frozen_sources = {p:p.read_bytes() for p in sources}
    verified_assets = verify_robot_assets(source,args.asset_root)
    evidence = {'status':'estimado', 'source':'Explicit fixed-gripper diagnostic derivative of RobotSpec '+source.sha256,
        'revision':source_hash, 'method':'Replace only the eight gripper moving joints by fixed q0 joints. Retain all physical links, mass partitions and source collision policy; remove gripper motors, elastic gear and redundant gripper weld closures.',
        'uncertainty':'Deliberate diagnostic topology, not an operating gripper, hardware redesign, contact repair or harvest validation. Inherited collision reasons retain their source context; fixed subassembly constraint semantics require new native observations.'}
    robot, report = derive_fixed_gripper(source,evidence)
    old_sdf, new_sdf = resolved_robot_model(source), resolved_robot_model(robot)
    old_links = {l.get('name'):xml_value(l) for l in old_sdf.findall('link')}
    new_links = {l.get('name'):xml_value(l) for l in new_sdf.findall('link')}
    if old_links != new_links:
        raise ValueError('Canonical SDF changed physical link content or poses')
    changed = set(report['fixed_joint_names'])
    for joint in old_sdf.findall('joint'):
        if joint.get('name') not in changed:
            other = new_sdf.find("joint[@name='"+joint.get('name')+"']")
            if other is None or xml_value(other) != xml_value(joint):
                raise ValueError('Non-gripper SDF joint changed')
    contract = resolved_robot_contract(robot)
    if contract.get('native_harvest_eligible') or 'native_harvest' in robot.to_dict()['capabilities']:
        raise ValueError('Diagnostic cannot authorize native harvest')
    args.output.mkdir(parents=True)
    shutil.copytree(args.asset_root,args.output/'assets')
    if verify_robot_assets(robot,args.output/'assets') != verified_assets:
        raise ValueError('Copied assets differ')
    write(args.output/'profile.json',robot.to_dict())
    sdf = ET.Element('sdf',version='1.10');sdf.append(new_sdf);ET.indent(sdf,space='  ')
    (args.output/'model.sdf').write_text(ET.tostring(sdf,encoding='unicode')+'\n',encoding='utf-8')
    write(args.output/'robot_contract.json',contract)
    (args.output/'source_profile.json').write_bytes(args.profile.read_bytes())
    snapshots = args.output/'source_snapshot';snapshots.mkdir()
    for path, content in frozen_sources.items():
        if path.read_bytes() != content: raise ValueError('Source code changed during preparation')
        (snapshots/path.name).write_bytes(content)
    if sha(args.profile) != source_hash: raise ValueError('Source profile changed')
    write(args.output/'derivation.json',{
        'status':'PREPARED_NOT_NATIVE_VALIDATED','scope':'Base, arm and suspension diagnostics with rigid q0 gripper',
        'source_robot_spec_sha256':source.sha256,'robot_spec_sha256':robot.sha256,'source_profile_sha256':source_hash,
        'profile_file_sha256':sha(args.output/'profile.json'),'model_sdf_sha256':sha(args.output/'model.sdf'),
        'asset_root':'assets','native_validation':'NO EJECUTADO','native_harvest_eligible':False,
        'physical_SDF_links_identical':True,'non_gripper_SDF_joints_identical':True,
        'auxiliary_mass_note':'Gripper auxiliary half-masses remain as fixed tree links without duplicated collision geometry; suspension auxiliary closures are unchanged.',
        'collision_note':'Numeric SDF masks and the full explicit exclusion list are identical. Fixed-body contact/constraint behavior is a deliberate diagnostic change, not proof that the moving CAD gripper is repaired.',
        'source_files_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(b).hexdigest() for p,b in frozen_sources.items()},
        **report})
    print(json.dumps({'status':'PREPARED_NOT_NATIVE_VALIDATED','robot_spec_sha256':robot.sha256,
                      'output':str(args.output),'fixed_joints':len(changed),'links':report['link_count']},indent=2))


if __name__ == '__main__': main()
