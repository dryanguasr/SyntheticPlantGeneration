#!/usr/bin/env python3
"""Bound fruit clearance for every axial rotation at the frozen V8 cut pose.

This examines only rigid wrist surfaces and a target's existing collision
sphere. It relaxes the robot's joint constraints, so a failed upper bound
rules out the declared position/direction task even with a free base.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.robot_kinematics import (
    collision_shapes, compose_poses, forward_kinematics, inverse_pose,
)
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_spec import resolve_robot_profile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_native_sphere(world, fruit):
    model = world.find(f"model[@name='{fruit['model_name']}']")
    if model is None:
        raise ValueError('Missing frozen native fruit model')
    link = model.find(f"link[@name='{fruit['link_name']}']")
    if link is None:
        raise ValueError('Missing frozen native fruit link')
    collider = link.find("collision[@name='harvest_collision']")
    if collider is None or collider.find('geometry/sphere/radius') is None:
        raise ValueError('Frozen target does not use the expected native sphere')
    model_pose = model.find('pose')
    if model_pose is None or model_pose.attrib or any(
        item is not None and (item.attrib or any(float(v) != 0 for v in item.text.split()))
        for item in (link.find('pose'), collider.find('pose'))
    ):
        raise ValueError('Unexpected fruit model/link/collider frame')
    values = [float(v) for v in model_pose.text.split()]
    if len(values) != 6 or not all(math.isfinite(v) for v in values):
        raise ValueError('Invalid frozen SDF pose')
    native_center = values[:3]
    native_radius = float(collider.findtext('geometry/sphere/radius'))
    delta = math.dist(native_center, fruit['center_world_m']) + abs(native_radius-fruit['radius_m'])
    if not math.isfinite(delta) or native_radius <= 0:
        raise ValueError('Invalid native sphere')
    return {'centre_and_radius_serialization_error_m': delta, 'native_radius_m': native_radius,
            'native_centre_m': native_center}


def blade_box_upper_bound(meshes, shapes, box, axial, radial, radius, common_padding, required):
    """Cover the circle plus the full CAD blade envelope with rectangular cells."""
    low, high = box['min_m'], box['max_m']
    if (len(low) != 3 or len(high) != 3 or any(not math.isfinite(v) for v in (*low, *high))
            or any(a > b for a, b in zip(low, high))):
        raise ValueError('Invalid blade envelope bounds')

    def grid(index):
        start = low[index]-radial
        width = high[index]+radial-start
        count = max(1, math.ceil(width/.001))
        step = width/count
        return [start+(i+.5)*step for i in range(count)], step

    xs, dx = grid(0)
    zs, dz = grid(2)
    mid_y = (low[1]+high[1])/2
    base_allowance = (high[1]-low[1])/2 + common_padding
    output = []
    for sign in (1, -1):
        pending = [(x, z, dx, dz, 0) for x in xs for z in zs]
        best = None
        retained, refined = 0, 0
        upper = -math.inf
        while pending:
            x, z, width, depth, level = pending.pop()
            half_diagonal = math.hypot(width, depth)/2
            near = math.hypot(max(low[0]-x, x-high[0], 0), max(low[2]-z, z-high[2], 0))
            far = math.hypot(max(abs(x-low[0]), abs(x-high[0])), max(abs(z-low[2]), abs(z-high[2])))
            # Both distances to the offset rectangle are 1-Lipschitz; a
            # skipped cell cannot contain any point on a translated circle.
            if near > radial+half_diagonal+1e-9 or far < radial-half_diagonal-1e-9:
                continue
            point = (x, sign*axial+mid_y, z)
            distance, name = min((meshes.surface_distance(shape, point), shape['name']) for shape in shapes)
            gap = distance-radius
            if best is None or best['surface_gap_m'] < gap:
                best = {'sphere_centre_cut_m': point, 'surface_gap_m': gap, 'limiting_shape': name}
            cell_upper = gap + base_allowance + half_diagonal
            if cell_upper >= required and level < 2:
                pending.extend((x+sx*width/4, z+sz*depth/4, width/2, depth/2, level+1)
                               for sx in (-1, 1) for sz in (-1, 1))
                refined += 1
            else:
                retained += 1
                upper = max(upper, cell_upper)
        if not retained:
            raise ValueError('No cells cover the blade envelope')
        output.append({'axis_sign': sign, 'covered_cells': retained, 'refined_cells': refined,
                       'initial_cell_size_xz_m': [dx, dz], 'maximum_refinement_levels': 2,
                       'maximum_sampled_surface_gap': best, 'nonspatial_padding_m': base_allowance,
                       'clearance_upper_bound_m': upper})
    return output


def run(profile, asset_root, manifest_path, plant_sdf, preflight_path, lock_path, output, edge_envelope=None):
    robot = resolve_robot_profile(profile)
    manifest = json.loads(manifest_path.read_text())
    protocol = json.loads(preflight_path.read_text())['protocol']
    lock = json.loads(lock_path.read_text())
    if protocol['robot_spec_sha256'] != robot.sha256 or protocol['manifest_sha256'] != sha(manifest_path):
        raise ValueError('Cut task does not match the frozen profile/manifest identity')
    if sha(manifest_path) != lock['frozen_manifest']['sha256']:
        raise ValueError('V8 manifest does not match the acceptance lock')
    if plant_sdf.name != manifest['world_file'] or sha(plant_sdf) != manifest['files_sha256'][plant_sdf.name]:
        raise ValueError('Native V8 SDF does not match the frozen manifest')
    fruit_ids = [fruit['id'] for fruit in manifest['fruits']]
    if not fruit_ids or fruit_ids != lock['plants']['target_ids'] or fruit_ids != protocol['plant_target_ids']:
        raise ValueError('Frozen target identities differ')
    if protocol['cut_axis_bidirectional'] is not True:
        raise ValueError('Expected the declared bidirectional CAD cut task')

    frames = {f['name']: f for f in robot.frames}
    link_name = frames['cut_point']['parent']
    if link_name != 'arm_wrist_roll':
        raise ValueError('This bound requires a cut frame rigid on the CAD wrist')
    poses = forward_kinematics(robot)
    world_to_cut = inverse_pose(poses['cut_point'])
    mobile_shapes = [shape for shape in collision_shapes(robot, poses) if shape['link'] == link_name]
    if not mobile_shapes or any(shape['geometry']['type'] != 'mesh' for shape in mobile_shapes):
        raise ValueError('Expected traced wrist collision triangle meshes')
    shapes = [{**shape, 'pose': compose_poses(world_to_cut, shape['pose'])} for shape in mobile_shapes]
    meshes = MeshRepository(asset_root, shapes)

    samples = 720
    numerical_pad = 1e-9
    position = protocol['position_tolerance_m']
    angle = protocol['direction_tolerance_rad']
    clearance = lock['motion_clearance_m']
    if not all(type(v) in (float, int) and math.isfinite(v) and v > 0 for v in (position, angle, clearance)) or angle >= math.pi:
        raise ValueError('Expected positive finite locked cut/clearance criteria')
    world = ET.parse(plant_sdf).getroot().find('world')
    if world is None:
        raise ValueError('Missing frozen SDF world')
    sources = [profile, manifest_path, plant_sdf, preflight_path, lock_path, Path(__file__),
               ROOT/'src/uchuva_gazebo/robot_kinematics.py', ROOT/'src/uchuva_gazebo/robot_mesh_geometry.py']
    blade_box = None
    if edge_envelope is not None:
        edge = json.loads(edge_envelope.read_text())
        if (edge['schema_version'] != 'cad-blade-edge-envelope/1.0' or
                edge['status'] != 'NOMINAL_GEOMETRIC_ENVELOPE_ONLY' or edge['robot_spec_sha256'] != robot.sha256 or
                any(sha(ROOT/name) != expected for name, expected in edge['source_files_sha256'].items())):
            raise ValueError('Blade envelope lacks matching CAD and profile provenance')
        blade_box = edge['continuous_convex_bridge_aabb_cut_m']
        sources.append(edge_envelope)
    source_hashes = {str(path): sha(path) for path in sources}
    result = {
        'schema_version': 'cad-v8-cut-clearance-bound/1.0', 'scope': __doc__,
        'robot_spec_sha256': robot.sha256, 'wrist_collision_assets_sha256': meshes.asset_hashes,
        'file_sha256': source_hashes,
        'tool_axis': [0, 1, 0], 'position_tolerance_m': position,
        'direction_tolerance_rad': angle, 'required_clearance_m': clearance,
        'twist_samples_per_direction': samples, 'numerical_upper_bound_padding_m': numerical_pad,
        'method': ('A direction-constrained cut places the frozen fruit centre on a circle in the tool frame, for each axis sign. '
                   'Distance to the nearest wrist surface is 1-Lipschitz and upper bounds distance to the wrist solids. '
                   'Cover points between samples using the nearest-sample arc length. Add translation error and the maximum '
                   'chord displacement induced by the allowed tilt. Ordinary double precision with conservative padding.'),
        'targets': [],
    }
    for fruit in manifest['fruits']:
        native_sphere = verify_native_sphere(world, fruit)
        delta = [b-a for a, b in zip(fruit['cut_point_world_m'], fruit['center_world_m'])]
        pedicel = [b-a for a, b in zip(fruit['pedicel_start_world_m'], fruit['pedicel_end_world_m'])]
        length = math.hypot(*pedicel)
        if length <= 0 or fruit['radius_m'] <= 0:
            raise ValueError('Nonpositive frozen pedicel length or fruit-sphere radius')
        axis = [v/length for v in pedicel]
        axial = sum(a*b for a, b in zip(delta, axis))
        radial = math.hypot(*(d-axial*a for d, a in zip(delta, axis)))
        common_padding = (position + 2*math.hypot(*delta)*math.sin(angle/2)
                          + numerical_pad + native_sphere['centre_and_radius_serialization_error_m'])
        pad = common_padding + radial*math.pi/samples
        bounds = []
        for sign in (1, -1):
            distances = []
            for index in range(samples):
                twist = math.tau*index/samples
                point = (radial*math.cos(twist), sign*axial, radial*math.sin(twist))
                surface_distance, name = min((meshes.surface_distance(shape, point), shape['name']) for shape in shapes)
                distances.append({'twist_rad': twist, 'surface_gap_m': surface_distance-fruit['radius_m'], 'limiting_shape': name})
            best = max(distances, key=lambda row: row['surface_gap_m'])
            bounds.append({'axis_sign': sign, 'maximum_sampled_surface_gap': best,
                           'clearance_upper_bound_m': best['surface_gap_m']+pad, 'samples': distances})
        upper = max(row['clearance_upper_bound_m'] for row in bounds)
        result['targets'].append({'fruit_id': fruit['id'], 'fruit_sphere_radius_m': fruit['radius_m'], 'native_sphere': native_sphere,
            'axial_offset_m': axial, 'radial_offset_m': radial, 'coverage_padding_m': pad,
            'clearance_upper_bound_m': upper, 'excluded_by_wrist_alone': upper < clearance, 'axis_signs': bounds})
        if blade_box is not None:
            blade = blade_box_upper_bound(meshes, shapes, blade_box, axial, radial, fruit['radius_m'], common_padding, clearance)
            blade_upper = max(row['clearance_upper_bound_m'] for row in blade)
            result['targets'][-1]['blade_envelope_screen'] = {
                'scope': 'Any point within the nominal CAD blade segment envelope and its convex bridge; no functional calibration',
                'clearance_upper_bound_m': blade_upper, 'excluded_by_wrist_alone': blade_upper < clearance,
                'blade_box_cut_m': blade_box, 'axis_signs': blade,
            }
    result['status'] = 'ANALYZED_NOT_NATIVE'
    if any(sha(path) != source_hashes[str(path)] for path in sources):
        raise ValueError('Cut analysis inputs changed during evaluation')
    output.mkdir(parents=True, exist_ok=False)
    (output/'result.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (output/'source.py').write_bytes(Path(__file__).read_bytes())
    return [{'fruit_id': row['fruit_id'], 'clearance_upper_bound_m': row['clearance_upper_bound_m'],
             'excluded': row['excluded_by_wrist_alone'],
             'blade_envelope_upper_bound_m': row.get('blade_envelope_screen', {}).get('clearance_upper_bound_m')}
            for row in result['targets']]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('profile', 'asset-root', 'manifest', 'plant-sdf', 'preflight', 'acceptance-lock', 'output'):
        parser.add_argument('--'+flag, type=Path, required=True)
    parser.add_argument('--edge-envelope', type=Path, help='Separate, conservative CAD blade-locus sensitivity study')
    args = parser.parse_args()
    print(json.dumps(run(args.profile, args.asset_root, args.manifest, args.plant_sdf, args.preflight,
                         args.acceptance_lock, args.output, args.edge_envelope)))
