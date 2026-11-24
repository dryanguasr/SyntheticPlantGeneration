#!/usr/bin/env python3
"""Concatenate unchanged CAD collision triangles within each rigid link.

This is a representation experiment, not a native-physics acceptance. All
gripper links, arm_wrist_roll and primitive colliders remain byte-equivalent
in RobotSpec. Original assets, visual shapes and rigid-body inertias remain.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
CODE_PATHS = [Path(__file__).resolve(), ROOT/'src/uchuva_gazebo/robot_mesh_geometry.py',
              ROOT/'src/uchuva_gazebo/robot_kinematics.py', ROOT/'src/uchuva_gazebo/robot_spec.py',
              ROOT/'configs/robots/robot_spec.schema.json']
CODE_BYTES = {p: p.read_bytes() for p in CODE_PATHS}
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_kinematics import pose_identity, rotate_vector, transform_point
from uchuva_gazebo.robot_mesh_geometry import TriangleMesh, read_collision_obj
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def groups_for(link):
    """Only equal contact surfaces within one rigid link may be grouped."""
    if link['name'] == 'arm_wrist_roll' or link['name'].startswith('gripper'):
        return []
    grouped = {}
    for i, shape in enumerate(link['collisions']):
        if shape['geometry']['type'] != 'mesh':
            continue
        if set(shape)-{'name', 'pose', 'geometry', 'surface', 'color_rgba'}:
            raise ValueError('Unknown collision properties cannot be concatenated safely')
        # A nonzero local friction direction would need its own frame adapter.
        # Do not silently rotate anisotropy when baking a collision pose.
        if any(shape.get('surface', {}).get('fdir1', [])):
            continue
        surface = {k: shape[k] for k in ('surface', 'color_rgba') if k in shape}
        grouped.setdefault(json.dumps(surface, sort_keys=True), []).append(i)
    return [indices for indices in grouped.values() if len(indices) >= 2]


def decimal_transform(pose, point):
    """Independent 50-digit reference for the same normalized float rotation."""
    q = pose['quaternion_xyzw']
    norm = math.sqrt(sum(x*x for x in q))
    x, y, z, w = [Decimal.from_float(x/norm) for x in q]
    X, Y, Z = map(Decimal.from_float, map(float, point))
    t = list(map(Decimal.from_float, map(float, pose['xyz_m'])))
    return (t[0]+(w*w+x*x-y*y-z*z)*X+2*(x*y-w*z)*Y+2*(x*z+w*y)*Z,
            t[1]+2*(x*y+w*z)*X+(w*w-x*x+y*y-z*z)*Y+2*(y*z-w*x)*Z,
            t[2]+2*(x*z-w*y)*X+2*(y*z+w*x)*Y+(w*w-x*x-y*y+z*z)*Z)


def concatenate(shapes, asset_root, destination, imported_parts=None):
    """Preserve every ordered face, vertex and component's contact surface."""
    vertices, faces, normals, normal_faces, components = [], [], [], [], []
    bindings = {}
    max_roundoff = Decimal(0)
    with localcontext() as context:
        context.prec = 50
        for shape in shapes:
            geometry = shape['geometry']
            path = (Path(asset_root)/geometry['uri']).resolve()
            if not path.is_relative_to(Path(asset_root).resolve()) or sha(path) != geometry['sha256']:
                raise ValueError('Source collision URI/hash changed or escaped its root')
            if geometry.get('scale', [1, 1, 1]) != [1, 1, 1]:
                raise ValueError('Only already-SI unit-scale meshes may be grouped')
            for key, value in geometry['bound_parameters'].items():
                if key in bindings and bindings[key] != value:
                    raise ValueError('Inconsistent frozen parameter bindings')
                bindings[key] = value
            vs, fs, ns, nfs = read_collision_obj(path)
            vo, fo, no = len(vertices), len(faces), len(normals)
            for point in vs:
                transformed = transform_point(shape['pose'], point)
                reference = decimal_transform(shape['pose'], point)
                max_roundoff = max(max_roundoff, *(abs(Decimal.from_float(a)-b) for a, b in zip(transformed, reference)))
                vertices.append(tuple(transformed))
            faces.extend(tuple(i+vo for i in face) for face in fs)
            normals.extend(tuple(rotate_vector(shape['pose']['quaternion_xyzw'], n)) for n in ns)
            normal_faces.extend(tuple(i+no for i in face) for face in nfs)
            component = {'collision_name': shape['name'], 'original_collision': copy.deepcopy(shape),
                         'source_sha256': geometry['sha256'], 'source_uri': geometry['uri'],
                         'vertex_range_zero_based_half_open': [vo, len(vertices)],
                         'face_range_zero_based_half_open': [fo, len(faces)],
                         'normal_range_zero_based_half_open': [no, len(normals)]}
            match = re.fullmatch(r'part_(\d+)_bounds', shape['name'])
            if match and imported_parts is not None:
                index = int(match[1]); part = imported_parts[index]
                component.update(part_index=index, occurrence_id=part['occurrence_id'],
                                 occurrence_name_path=part['occurrence_name_path'])
            components.append(component)
    # These are the actual collision vertices, not a remesh/union/decimation.
    content = '# Concatenated rigid-link collision surfaces; component identity in manifest.\n'
    content += ''.join('v '+' '.join(format(v, '.17g') for v in p)+'\n' for p in vertices)
    content += ''.join('vn '+' '.join(format(v, '.17g') for v in n)+'\n' for n in normals)
    content += ''.join('f '+' '.join(f'{i+1}//{n+1}' for i, n in zip(f, nf))+'\n' for f, nf in zip(faces, normal_faces))
    destination.write_text(content, encoding='utf-8')
    decoded = read_collision_obj(destination)
    expected = (vertices, faces, normals, normal_faces)
    if any(list(a) != list(b) for a, b in zip(decoded, expected)):
        raise ValueError('OBJ serialization changed a transformed vertex or face')
    # No coordinate welding, face deletion, orientation repair or relabeling is
    # applied here. A topology rejection blocks this candidate and is preserved.
    mesh = TriangleMesh(vertices, faces)
    report = {'components': components, 'component_count': len(components),
              'vertices': len(vertices), 'triangles': len(faces),
              'all_source_vertices_and_ordered_triangles_preserved': True,
              'maximum_storage_roundtrip_error_m': 0.0,
              'maximum_transform_roundoff_m': float(max_roundoff),
              'roundoff_reference': '50-digit independent matrix formula using the same normalized float quaternion; not CAD or native contact accuracy.',
              'closed_oriented_triangle_mesh_admission': 'PASS',
              'admitted_solid_components': len(mesh.component_points)}
    return bindings, report


def prepare(args):
    if args.output.exists():
        raise ValueError('Use a fresh output directory')
    source = resolve_robot_profile(args.profile)
    data = source.to_dict()
    if 'native_harvest' in data['capabilities']:
        raise ValueError('Experimental representation cannot inherit native harvest eligibility')
    if any('/collisions/' in path for path in data['parameter_metadata']):
        raise ValueError('Indexed collision metadata needs an explicit remapping before grouping')
    if any('/collisions/' in row['path'] for row in data.get('derived_values', [])):
        raise ValueError('Derived collision geometry cannot be silently rebound')
    input_hash = sha(args.profile)
    source_assets = verify_robot_assets(source, args.asset_root)
    imported = read(args.import_report)['parts'] if args.import_report else None
    args.output.mkdir(parents=True)
    assets = args.output/'assets'; shutil.copytree(args.asset_root, assets)
    target = assets/'grouped_collisions'; target.mkdir()
    grouped_data = copy.deepcopy(data); groups = []
    try:
        for link_index, link in enumerate(data['links']):
            replacements = {}; removed = set()
            for number, indices in enumerate(groups_for(link)):
                rows = [link['collisions'][i] for i in indices]
                name = f"rigid_mesh_{link['name']}_{number}"
                path = target/(name+'.obj')
                bindings, report = concatenate(rows, assets, path, imported)
                digest = sha(path); hashed_path = target/(digest+'.obj'); path.rename(hashed_path)
                uri = hashed_path.relative_to(assets).as_posix()
                replacement = {k: copy.deepcopy(v) for k, v in rows[0].items() if k not in ('name', 'pose', 'geometry')}
                replacement.update(name=name, pose=pose_identity(), geometry={
                    'type': 'mesh', 'uri': uri, 'sha256': digest, 'scale': [1, 1, 1], 'bound_parameters': bindings})
                replacements[indices[0]] = replacement; removed.update(indices[1:])
                report.update(link=link['name'], collision_name=name, collision_uri=uri,
                              collision_sha256=digest, source_collision_indices=indices,
                              unchanged_surface=copy.deepcopy(rows[0].get('surface')))
                groups.append(report)
            grouped_data['links'][link_index]['collisions'] = [replacements.get(i, c)
                for i, c in enumerate(link['collisions']) if i not in removed]
        evidence = copy.deepcopy(data['provenance'])
        evidence['source'] += '; rigid collision grouping source RobotSpec SHA256 '+source.sha256
        evidence['revision'] += '; exact_rigid_link_mesh_grouping_v1'
        evidence['method'] += '; Same oriented triangles transformed into link coordinates, no simplification; native contact/performance validation pending.'
        grouped_data['provenance'] = evidence
        reverse = copy.deepcopy(grouped_data); reverse['provenance'] = data['provenance']
        for i in range(len(data['links'])):
            reverse['links'][i]['collisions'] = data['links'][i]['collisions']
        if reverse != data:
            raise ValueError('Grouping changed fields other than collision representation/provenance')
        robot = resolve_robot_profile(grouped_data)
        if robot.to_dict() != grouped_data:
            raise ValueError('Resolution changed the grouped candidate')
        verify_robot_assets(robot, assets)
        write(args.output/'profile.json', robot.to_dict())
        status = 'PREPARED_NOT_NATIVE_VALIDATED'
    except Exception as error:
        write(args.output/'grouping_failure.json', {'status': 'BLOCKED', 'error': str(error),
              'completed_groups': groups, 'source_robot_spec_sha256': source.sha256,
              'native_validation': 'NO EJECUTADO'})
        raise
    if sha(args.profile) != input_hash:
        raise ValueError('Input profile changed during grouping')
    for uri, digest in source_assets.items():
        if sha(Path(args.asset_root)/uri) != digest or sha(assets/uri) != digest:
            raise ValueError('An original asset changed')
    snapshots = args.output/'source_snapshot'; snapshots.mkdir()
    for path, content in CODE_BYTES.items():
        if path.read_bytes() != content:
            raise ValueError('Implementation changed during grouping')
        (snapshots/path.name).write_bytes(content)
    report = {'schema_version': 'cad-rigid-collision-grouping/1.0', 'status': status,
              'source_robot_spec_sha256': source.sha256, 'source_profile_file_sha256': input_hash,
              'robot_spec_sha256': robot.sha256, 'asset_root': 'assets',
              'native_harvest_eligible': False, 'native_validation': 'NO EJECUTADO',
              'all_visuals_inertias_joints_masks_controls_frames_physics_unchanged': True,
              'protected_links': [l['name'] for l in data['links'] if l['name']=='arm_wrist_roll' or l['name'].startswith('gripper')],
              'source_collision_count': sum(len(l['collisions']) for l in data['links']),
              'grouped_collision_count': sum(len(l['collisions']) for l in grouped_data['links']),
              'source_visual_count': sum(len(l['visuals']) for l in data['links']),
              'groups': groups, 'source_assets_sha256': source_assets,
              'source_code_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(b).hexdigest() for p, b in CODE_BYTES.items()},
              'contact_semantics_note': 'Component IDs map to exact face ranges. Grouped native contact names differ; manifold/contact distribution may change and requires new validation.'}
    write(args.output/'grouping_manifest.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'robot_spec_sha256', 'source_collision_count', 'grouped_collision_count', 'source_visual_count')}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'asset-root', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--import-report', type=Path)
    prepare(parser.parse_args())


if __name__ == '__main__':
    main()
