#!/usr/bin/env python3
"""Apply one traced CAD leaf revision without changing the robot mechanism.

Original assets remain immutable. The new visual uses the native OBJ bytes;
its collision derivative may change only triangle winding and normals. This
prepares an experimental model, never certifies its operational CAD envelope
or native dynamics.
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

ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = [Path(__file__).resolve(), ROOT / 'scripts/prepare_cad_robot.py',
              ROOT / 'src/uchuva_gazebo/robot_mesh_geometry.py',
              ROOT / 'src/uchuva_gazebo/robot_kinematics.py',
              ROOT / 'src/uchuva_gazebo/robot_spec.py']
# Capture execution sources before importing them, including concurrent-work
# protection when another task is changing the common model implementation.
CODE_BYTES = {path: path.read_bytes() for path in CODE_PATHS}
sys.path.insert(0, str(ROOT / 'src'))
from prepare_cad_robot import aggregate_inertia
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_mesh_geometry import MeshRepository, repair_collision_obj


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False,
                                    allow_nan=False) + '\n', encoding='utf-8')


def apply_revision(data, imported, replacement, visual_asset, collision_asset,
                   evidence):
    """Pure, narrowly scoped replacement with a byte-equivalent reverse diff."""
    index = replacement['full_robot_part_index']
    if type(index) is not int or not 0 <= index < len(imported['parts']):
        raise ValueError('Invalid CAD leaf index')
    old, new = replacement['original_import_record'], replacement['replacement_import_record']
    if imported['parts'][index] != old:
        raise ValueError('Original CAD import record differs from the revision input')
    for key in ('occurrence_id', 'occurrence_name_path', 'link', 'link_T_document'):
        if old[key] != new[key]:
            raise ValueError('CAD revision cannot change occurrence identity or placement: ' + key)
    if visual_asset['sha256'] != new['mesh_sha256']:
        raise ValueError('Replacement visual does not match the native export hash')
    owners = [(i, link) for i, link in enumerate(data['links'])
              if any(v['name'] == f'part_{index}' for v in link['visuals'])]
    if len(owners) != 1:
        raise ValueError('Revised leaf must occur in exactly one rigid link')
    link_index, link = owners[0]
    if any(link['name'] in (c['body'], c['auxiliary']) for c in data.get('closures', [])):
        raise ValueError('A mass-partitioned closure body requires its own revision adapter')
    visuals = [v for v in link['visuals'] if v['name'] == f'part_{index}']
    collisions = [v for v in link['collisions'] if v['name'] == f'part_{index}_bounds']
    if len(visuals) != 1 or len(collisions) != 1:
        raise ValueError('Revised leaf needs one identified visual and collision')
    visual, collision = visuals[0], collisions[0]
    if (visual['geometry']['type'] != 'mesh' or collision['geometry']['type'] != 'mesh'
            or visual['geometry']['sha256'] != old['mesh_sha256']
            or visual['pose'] != collision['pose']):
        raise ValueError('Old visual, collider and document placement are inconsistent')
    parts = []
    for item in link['visuals']:
        name = item['name']
        if not name.startswith('part_') or not name[5:].isdigit():
            raise ValueError('Every rigid-link visual must identify its CAD mass leaf')
        part_index = int(name[5:])
        row = imported['parts'][part_index]
        if item['geometry']['sha256'] != row['mesh_sha256']:
            raise ValueError('Rigid-link leaf visual differs from the mass inventory')
        parts.append((part_index, row['mass_properties'], item['pose']))
    if len({i for i, _, _ in parts}) != len(parts):
        raise ValueError('Duplicate mass leaf in the revised rigid link')
    reconstructed = aggregate_inertia([(mass, pose) for _, mass, pose in parts])
    if reconstructed != link['inertial']:
        raise ValueError('Original rigid-link inertia is not exactly reproduced from all CAD leaves')
    revised_inertia = aggregate_inertia([
        (new['mass_properties'] if i == index else mass, pose) for i, mass, pose in parts])
    delta = new['mass_properties']['mass_kg'] - old['mass_properties']['mass_kg']
    if not math.isclose(revised_inertia['mass_kg'] - reconstructed['mass_kg'], delta,
                        rel_tol=1e-12, abs_tol=1e-18):
        raise ValueError('Rigid-link mass change differs from the native CAD leaf change')
    updated = copy.deepcopy(data)
    target = updated['links'][link_index]
    target['inertial'] = revised_inertia
    parameter = f'cad_part_{index}_revision'
    if parameter in updated['parameters']:
        raise ValueError('This adapter requires an unmodified source leaf revision')
    updated['parameters'][parameter] = 1
    parameter_path = '/parameters/' + parameter
    updated['parameter_metadata'][parameter_path] = {**evidence, 'update_class': 'cad_reexport'}
    inertia_path = f'/links/{link_index}/inertial'
    updated['parameter_metadata'][inertia_path] = {**evidence, 'update_class': 'model_regeneration'}
    for key, shape_name, asset in (('visuals', f'part_{index}', visual_asset),
                                  ('collisions', f'part_{index}_bounds', collision_asset)):
        shape = next(v for v in target[key] if v['name'] == shape_name)
        shape['geometry'].update(asset)
        shape['geometry']['bound_parameters'][parameter_path] = 1
    updated['provenance']['source'] += '; ' + evidence['source']
    updated['provenance']['method'] += '; One experimental CAD leaf revised; operational envelope and dynamics remain pending.'
    # Restoring only the admitted fields must reproduce the entire input.
    reverse = copy.deepcopy(updated)
    reverse_link = reverse['links'][link_index]
    reverse_link['inertial'] = copy.deepcopy(link['inertial'])
    for kind, name in (('visuals', f'part_{index}'), ('collisions', f'part_{index}_bounds')):
        before = next(s for s in link[kind] if s['name'] == name)
        after = next(s for s in reverse_link[kind] if s['name'] == name)
        after['geometry'] = copy.deepcopy(before['geometry'])
    for key in ('parameters', 'parameter_metadata', 'provenance'):
        reverse[key] = copy.deepcopy(data[key])
    if reverse != data:
        raise ValueError('CAD part revision changed unrelated model fields')
    retained = replacement.get('unchanged_L2_part_index')
    if retained == index:
        raise ValueError('The explicitly preserved leaf cannot be the revised one')
    if retained is not None:
        for old_link, new_link in zip(data['links'], updated['links']):
            for kind in ('visuals', 'collisions'):
                names = {f'part_{retained}', f'part_{retained}_bounds'}
                if [s for s in old_link[kind] if s['name'] in names] != [s for s in new_link[kind] if s['name'] in names]:
                    raise ValueError('Explicitly preserved leaf changed')
    old_total = math.fsum(l['inertial']['mass_kg'] for l in data['links'])
    new_total = math.fsum(l['inertial']['mass_kg'] for l in updated['links'])
    if not math.isclose(new_total - old_total, delta, rel_tol=1e-9, abs_tol=1e-14):
        raise ValueError('Whole-robot mass change differs from the native CAD leaf change')
    return updated, {'part_index': index, 'link': link['name'], 'link_index': link_index,
        'all_link_leaf_indices': [i for i, _, _ in parts],
        'old_inertia_reconstructed_exactly': True, 'old_inertial': reconstructed,
        'new_inertial': revised_inertia, 'native_leaf_mass_delta_kg': delta,
        'old_total_mass_kg': old_total, 'new_total_mass_kg': new_total,
        'total_mass_delta_roundoff_kg': (new_total - old_total) - delta,
        'unrelated_links_joints_frames_controls_masks_closures_physics_unchanged': True,
        'all_visual_and_collision_poses_unchanged': True,
        'explicitly_preserved_part_index': retained}


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a fresh output directory; previous evidence is immutable')
    inputs = {name: Path(getattr(args, name)).resolve() for name in
              ('profile', 'import_report', 'replacement', 'native_mesh', 'native_part')}
    hashes = {name: sha(path) for name, path in inputs.items()}
    replacement = read(args.replacement)
    revised = replacement['replacement_import_record']
    if hashes['native_mesh'] != revised['mesh_sha256'] or hashes['native_part'] != revised['source_sha256']:
        raise ValueError('Native revised part or tessellation differs from its recorded hash')
    source = resolve_robot_profile(args.profile)
    verify_robot_assets(source, args.asset_root)
    args.output.mkdir(parents=True)
    assets = args.output / 'assets'
    shutil.copytree(args.asset_root, assets)
    raw_uri = 'meshes/' + hashes['native_mesh'] + '.obj'
    shutil.copyfile(args.native_mesh, assets / raw_uri)
    temporary = assets / 'collision_meshes' / ('revision_' + hashes['native_mesh'] + '.obj')
    orientation = repair_collision_obj(args.native_mesh, temporary)
    collision_uri = 'collision_meshes/' + orientation['collision_sha256'] + '.obj'
    temporary.rename(assets / collision_uri)
    entry = {'collision_uri': collision_uri, 'collision_sha256': orientation['collision_sha256'],
             'positions_unchanged': True, 'unoriented_triangles_unchanged': True,
             'report': orientation}
    manifest = {'schema_version': 'cad-collision-derivatives/1', 'asset_root': '.',
                'source_native_part_sha256': hashes['native_part'],
                'entries': {hashes['native_mesh']: entry}}
    write(assets / 'part_collision_derivatives.json', manifest)
    evidence = {'status': 'derivado_de_CAD',
        'source': f'Private CAD leaf revision SHA256 {hashes["replacement"]}; native part {hashes["native_part"]}',
        'revision': hashes['replacement'],
        'method': 'Native leaf mass/tensor; exact unchanged rigid-link placements; full link inertia recomputed.',
        'uncertainty': 'Experimental CAD revision, not measured hardware; native validation and CAD motion certificate pending.'}
    updated, report = apply_revision(source.to_dict(), read(args.import_report), replacement,
        {'uri': raw_uri, 'sha256': hashes['native_mesh']},
        {'uri': collision_uri, 'sha256': orientation['collision_sha256']}, evidence)
    robot = resolve_robot_profile(updated)
    if robot.to_dict() != updated:
        raise ValueError('Resolving the revised profile changed fields outside this explicit revision')
    verify_robot_assets(robot, assets)
    geometries = [c['geometry'] for l in robot.links for c in l['collisions']
                  if c['geometry']['type'] == 'mesh']
    repository = MeshRepository(assets, geometries)
    write(args.output / 'profile.json', robot.to_dict())
    old_import = read(args.import_report)
    records = copy.deepcopy(old_import['parts'])
    records[replacement['full_robot_part_index']] = revised
    write(args.output / 'revised_import_report.json', {
        'schema_version': 'cad-part-import-revision/1.0', 'status': 'EXPERIMENTAL_CAD_PENDING_VALIDATION',
        'source_import_report_sha256': hashes['import_report'],
        'source_profile_sha256': source.sha256, 'robot_spec_sha256': robot.sha256,
        'parts': records, 'total_cad_mass_kg': sum(p['mass_properties']['mass_kg'] for p in records),
        'part_assignment_scope': 'Historical import frames retained; current rigid-link placement is profile.visuals[].pose.',
        'native_harvest_eligible': False, 'native_validation': 'NO EJECUTADO'})
    snapshots = args.output / 'source_snapshot'
    snapshots.mkdir()
    for path, content in CODE_BYTES.items():
        if path.read_bytes() != content:
            raise ValueError('An execution source changed during preparation: ' + path.name)
        (snapshots / path.name).write_bytes(content)
    if any(sha(path) != hashes[name] for name, path in inputs.items()):
        raise ValueError('An immutable revision input changed during preparation')
    report.update(schema_version='cad-part-revision/1.0',
        status='PREPARED_CAD_AND_NATIVE_VALIDATION_PENDING',
        source_profile_sha256=source.sha256, robot_spec_sha256=robot.sha256,
        source_files_sha256=hashes,
        source_code_sha256={p.relative_to(ROOT).as_posix(): hashlib.sha256(b).hexdigest()
                            for p, b in CODE_BYTES.items()},
        asset_root='assets', collision_manifest='assets/part_collision_derivatives.json',
        collision_manifest_sha256=sha(assets / 'part_collision_derivatives.json'),
        mesh_admission={'status': 'PASS', 'unique_collision_assets': len(repository.meshes),
            'scope': 'Closed, outward-oriented tessellation and exact asset hashes only; no motion/contact acceptance.'},
        orientation_revision=orientation, source_visual_bytes_unchanged=True,
        native_validation='NO EJECUTADO', operational_cad_envelope='PENDING')
    write(args.output / 'revision_report.json', report)
    print(json.dumps({'status': report['status'], 'robot_spec_sha256': robot.sha256,
                      'mass_delta_kg': report['native_leaf_mass_delta_kg'],
                      'mesh_admission': report['mesh_admission']}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'asset-root', 'import-report', 'replacement', 'native-mesh', 'native-part', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()
