"""Search base and arm poses for the unchanged V8 cut points before route planning."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys

from preflight_cad_v8_reach import CutChain, angle_z, optimize
from verify_cad_v8_acceptance import verify

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from uchuva_gazebo.harvest_plants import _config, _load_catalog_plant, _metres, calyx_collider, UNITS_PER_METRE
from uchuva_gazebo.harvest_visuals import detailed_calyx_mesh
from uchuva_gazebo.harvest_pilot import sha256_file
from uchuva_gazebo.robot_kinematics import (
    collision_shapes, compose_poses, forward_kinematics, inverse_pose,
    pose_from_rpy, transform_point,
)
from uchuva_gazebo.robot_mesh_geometry import MeshRepository
from uchuva_gazebo.robot_spec import resolve_robot_profile
from uchuva_lsystem.scene import PlantInstance


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def targets(config, manifest, *, collider_mesh=False):
    """Reconstruct eligible positions from the locked catalog, including reserves."""
    plants = _config(config['plants'])
    for index, record in enumerate(manifest['plants']):
        plant_id = record['id']
        instance = PlantInstance(plant_id, plants['seeds'][index],
            position=tuple(v * UNITS_PER_METRE for v in plants['positions_m'][index]),
            rotation_deg=plants['rotations_deg'][index])
        _, _, source, _ = _load_catalog_plant(
            plants['morphology_files'][index], plants['proxy_catalog_files'][index],
            instance, plants['source_units_per_metre'])
        eligible = set(record['selection_audit']['selected_ids'] +
                       record['selection_audit']['unselected_eligible_ids'])
        stems = {p.attachment_id: p for p in source if p.kind == 'pedicel'}
        for calyx in source:
            if calyx.kind != 'calyx' or calyx.attachment_id not in eligible:
                continue
            pedicel = stems[calyx.attachment_id]
            start, end = _metres(pedicel.start), _metres(pedicel.end)
            cut = [a + plants['cut_fraction'] * (b - a) for a, b in zip(start, end)]
            result = {'id': calyx.attachment_id, 'plant_id': plant_id,
                   'center_world_m': list(_metres(calyx.center)), 'cut_point_world_m': cut,
                   'pedicel_start_world_m': list(start), 'pedicel_end_world_m': list(end),
                   'pedicel_radius_m': pedicel.radius / UNITS_PER_METRE,
                   'radius_m': max(calyx.half_extents) / UNITS_PER_METRE}
            if collider_mesh:
                obj = calyx_collider(detailed_calyx_mesh(calyx))
                digest = hashlib.sha256(obj.encode()).hexdigest()
                result.update(collision_obj=obj, collision_geometry={'type': 'mesh', 'scale': [1, 1, 1],
                    'uri': f'calyx_preflight/{digest}.obj', 'sha256': digest})
            yield result


def sample_poses(chain, fruit, height, seeds, clearance, repository, tool_shapes, margin, *, starts=54):
    cut = fruit['cut_point_world_m']
    start, end = fruit['pedicel_start_world_m'], fruit['pedicel_end_world_m']
    norm = math.dist(start, end)
    if norm <= 0:
        return []
    axis = [(b - a) / norm for a, b in zip(start, end)]
    center = fruit['center_world_m']
    radius = fruit['radius_m']
    geometry = fruit.get('collision_geometry')
    solutions = []
    seen = set()
    for sign in (1, -1):
        direction = [v * sign for v in axis]
        theta = angle_z(direction)
        ranked = sorted(seeds, key=lambda seed: (seed[1]['xyz_m'][2]-cut[2]+height)**2
                        + (.3 * (angle_z(seed[2])-theta))**2)
        # Include diverse arm configurations, including extended seeds for aisle access.
        near = starts//3
        selected = ranked[:near] + ranked[near::max(1, len(ranked)//(starts-near))]
        for seed, _, _ in selected:
            q = optimize(chain, seed, cut[2]-height, theta)
            if min(min(v-lo, hi-v) for v, (lo, hi) in zip(q, chain.bounds)) < margin:
                continue
            pose, native_axis = chain.evaluate(q)
            angular_error = abs(angle_z(native_axis)-theta)
            position_error = abs(pose['xyz_m'][2]+height-cut[2])
            if angular_error > .03 or position_error > 1e-5:
                continue
            yaw = math.atan2(direction[1], direction[0])-math.atan2(native_axis[1], native_axis[0])
            yaw = math.atan2(math.sin(yaw), math.cos(yaw))
            x, y, _ = pose['xyz_m']
            base = [cut[0]-math.cos(yaw)*x+math.sin(yaw)*y,
                    cut[1]-math.sin(yaw)*x-math.cos(yaw)*y, height, yaw]
            key = tuple(round(v, 3) for v in (*q, *base))
            if key in seen or base[0] >= 0:
                continue
            seen.add(key)
            world = compose_poses(pose_from_rpy(base[:3], [0, 0, yaw]), pose)
            cut_inverse = inverse_pose(world)
            local_center = transform_point(cut_inverse, center)
            gap, limiting = clearance, None
            for shape in tool_shapes:
                distance = repository.point_distance(shape, local_center, limit=max(0, radius + gap)) - radius
                if geometry and distance < gap:
                    fruit_shape = {'geometry': geometry, 'pose': compose_poses(cut_inverse, pose_from_rpy(center, [0, 0, 0]))}
                    distance = repository.shape_distance(shape, fruit_shape, limit=gap)
                if distance < gap:
                    gap, limiting = distance, shape['link'] + '/' + shape['name']
            solutions.append({'base_pose': base, 'q': q, 'cut_axis_world': direction,
                'target_vs_tool_m': gap, 'limiting_shape': limiting,
                'position_error_m': position_error, 'orientation_error_rad': angular_error})
    return sorted(solutions, key=lambda v: (-v['target_vs_tool_m'], v['base_pose'][0], abs(v['base_pose'][3])))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--reference', type=Path, default=ROOT/'outputs/harvest_pilot_v8_c4_gui/manifest.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--planning-height', type=float, default=.296218017078388)
    parser.add_argument('--exact-calyx', action='store_true', help='Use the unchanged closed calyx surface instead of its historic sphere')
    parser.add_argument('--plant', choices=('plant_000', 'plant_001', 'plant_002'))
    parser.add_argument('--starts', type=int, default=54, help='Bounded number of optimizer starts per axis sign')
    args = parser.parse_args()
    if not 12 <= args.starts <= 216:
        parser.error('--starts must be between 12 and 216')
    config = read(ROOT/'configs/harvest_pilot_v8.json')
    lock = read(ROOT/'configs/robots/cad_v8_acceptance_lock.json')
    if verify(config, lock)['status'] != 'PASS' or sha256_file(args.reference) != lock['frozen_manifest']['sha256']:
        raise ValueError('The historical V8 inputs differ from their lock')
    robot = resolve_robot_profile(args.profile)
    chain = CutChain(robot)
    poses = forward_kinematics(robot)
    tool_links = {chain.frame['parent']}
    # The fixed/prismatic siblings remain rigid relative to this frame at the
    # closed coordinate used for the cut. Do not include the upstream wrist.
    descendants = list(tool_links)
    for parent in descendants:
        descendants.extend(joint['child'] for joint in robot.joints if joint['parent'] == parent)
    tool_links.update(descendants)
    cut_inverse = inverse_pose(poses['cut_point'])
    shapes = [{**shape, 'pose': compose_poses(cut_inverse, shape['pose'])}
              for shape in collision_shapes(robot, poses) if shape['link'] in tool_links]
    repository = MeshRepository(args.asset_root, [shape['geometry'] for shape in shapes])
    rng = random.Random(20261124)
    seeds = [[0.] * 5] + [list(q) for q in itertools.product(*chain.bounds)]
    seeds.extend([rng.uniform(lo, hi) for lo, hi in chain.bounds] for _ in range(6*args.starts))
    samples = [(q, *chain.evaluate(q)) for q in seeds]
    report = {'scope': 'Frozen V8 target vs CAD tool at the cut pose; route and native gates pending.',
              'robot_spec_sha256': robot.sha256, 'reference_sha256': sha256_file(args.reference),
              'height_m': args.planning_height, 'motion_clearance_m': lock['motion_clearance_m'],
              'exact_calyx': args.exact_calyx, 'starts_per_axis_sign': args.starts, 'targets': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest = read(args.reference)
    with args.output.open('x', encoding='utf-8') as file:
        for fruit in targets(config, manifest, collider_mesh=args.exact_calyx):
            if args.plant and fruit['plant_id'] != args.plant:
                continue
            if args.exact_calyx:
                repository.register_generated_obj(fruit['collision_geometry'], fruit.pop('collision_obj'))
            poses = sample_poses(chain, fruit, args.planning_height, samples, lock['motion_clearance_m'],
                                 repository, shapes, lock['joint_margin_rad'], starts=args.starts)
            report['targets'].append({**fruit, 'poses': poses})
            print(f"{fruit['id']} poses={len(poses)} tool_pass={sum(v['limiting_shape'] is None for v in poses)} "
                  f"best={poses[0]['target_vs_tool_m'] if poses else None}", flush=True)
        json.dump(report, file, indent=2, allow_nan=False)
        file.write('\n')


if __name__ == '__main__':
    main()
