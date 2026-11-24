#!/usr/bin/env python3
"""Prepare a continuous V8 take with prescribed CAD motion and native fruit physics."""

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from uchuva_gazebo.harvest_pilot import load_verified_package, sha256_file


PLAYBACK = 'libUchuvaHarvestDemoPlaybackSystem.so'


class Take:
    """Time the stops, arm passes and jaw motion without changing the cut guards."""

    def __init__(self, manifest, start, *, carry=None):
        robot = manifest['robot']
        drive = robot['drive']
        self.fixture = manifest['robot_task']['demo_fixture']
        self.jaw = self.fixture['gripper']
        self.arm = list(robot['arm_joint_names'])
        self.carry = manifest['mission']['carry_joints_rad'] if carry is None else carry
        self.joints = self.arm + [self.jaw['joint']] + drive['left_joints'] + drive['right_joints']
        self.speeds = [min(.30, limit) for limit in robot['joint_velocity_limits_rad_s']]
        self.speeds += [self.jaw['command_velocity_m_s']] + [3.] * 4
        self.wheel_radius = drive['wheel_radius_m']
        self.half_track = drive['wheel_separation_m'] / 2
        self.wheel_sign = [drive['joint_signs'][name] for name in self.joints[-4:]]
        initial_arm = robot['home_joints_rad'] if carry is None else self.carry
        self.rows = [[0., *start, *initial_arm, self.jaw['closed_position_m'], 0., 0., 0., 0.]]
        self.commands = []
        self.phases = []

    def add(self, state, minimum=.12):
        previous = self.rows[-1]
        duration = max(minimum, *(1.88 * abs(a - b) / speed
                                  for a, b, speed in zip(previous[5:], state[4:], self.speeds)))
        self.rows.append([previous[0] + duration, *state])

    def hold(self, duration):
        self.add(self.rows[-1][1:], duration)

    def arm_to(self, angles, *, opened=None):
        turn = self.rows[-1][1:].copy()
        turn[4:9] = angles
        if opened is not None:
            turn[9] = self.jaw['open_position_m' if opened else 'closed_position_m']
        if turn != self.rows[-1][1:]:
            self.add(turn)

    def drive_part(self, *, x=None, y=None, yaw=None, reverse=False):
        old = self.rows[-1][1:]
        state = old.copy()
        if yaw is not None:
            state[3] += math.remainder(yaw - state[3], math.tau)
        if x is not None and y is not None:
            state[:2] = [x, y]
        distance = math.dist(old[:2], state[:2])
        delta_yaw = state[3] - old[3]
        if distance + abs(delta_yaw) < 1e-8:
            return
        travel = -distance if reverse else distance
        paths = [travel - self.half_track * delta_yaw] * 2 + [travel + self.half_track * delta_yaw] * 2
        state[10:] = [q + sign * path / self.wheel_radius
                      for q, sign, path in zip(old[10:], self.wheel_sign, paths)]
        duration = max(1.88 * distance / .30, 1.88 * abs(delta_yaw) / .72,
                       math.sqrt(6 * distance / .24), math.sqrt(6 * abs(delta_yaw) / .65))
        self.add(state, duration)

    def drive(self, waypoint, *, allow_reverse=False):
        x, y, yaw = waypoint
        _, old_x, old_y, _, old_yaw, *_ = self.rows[-1]
        if math.dist([old_x, old_y], [x, y]) > 1e-8:
            heading = math.atan2(y - old_y, x - old_x)
            reverse = False
            if allow_reverse:
                def total_turn(angle):
                    return abs(math.remainder(angle - old_yaw, math.tau)) + abs(math.remainder(yaw - angle, math.tau))

                reverse = total_turn(heading + math.pi) + .10 < total_turn(heading)
            self.drive_part(yaw=heading + math.pi if reverse else heading)
            self.drive_part(x=x, y=y, reverse=reverse)
        self.drive_part(yaw=yaw)

    def phase(self, name, identifier):
        self.phases.append({'sim_time': self.rows[-1][0], 'phase': name, 'id': identifier})

    def command(self, action, identifier):
        self.commands.append([self.rows[-1][0], action, identifier])

    def harvest(self, target):
        identifier = target['id']
        q = target['nominal_joints_rad']
        self.phase('acercamiento_carro', identifier)
        self.arm_to(self.carry)
        for waypoint in target['base_route']:
            self.drive(waypoint, allow_reverse=target.get('allow_reverse', False))
        self.phase('acercamiento_pinza', identifier)
        for waypoint in target.get('approach_sequence', [q['preapproach']]):
            self.arm_to(waypoint, opened=True)
        self.arm_to(q['cut'], opened=True)

        self.phase('corte', identifier)
        self.hold(.36)
        self.command('arm', identifier)
        self.hold(.12)
        self.arm_to(q['cut'], opened=False)
        self.hold(.36)
        self.command('cut', identifier)
        self.hold(.42)

        self.phase('separacion', identifier)
        withdrawal = target.get('separation_sequence', [q[name] for name in target['withdrawal_sequence']])
        for waypoint in withdrawal:
            self.arm_to(waypoint)
        self.phase('deposito', identifier)
        for waypoint in target['deposit_sequence']:
            self.arm_to(waypoint)
        self.arm_to(target['deposit_joints'], opened=True)
        self.hold(.36)
        self.command('release', identifier)
        self.hold(1.5)
        if 'stow_sequence' in target:
            for waypoint in target['stow_sequence']:
                self.arm_to(waypoint)
            self.arm_to(self.carry, opened=False)

    def save(self, directory):
        trajectory = directory / 'trajectory.tsv'
        commands = directory / 'commands.tsv'
        trajectory.write_text(''.join(' '.join(format(n, '.16g') for n in row) + '\n'
                                      for row in self.rows), encoding='utf-8')
        commands.write_text(''.join(f'{time:.16g} {action} {identifier}\n'
                                    for time, action, identifier in self.commands), encoding='utf-8')
        return trajectory, commands


def set_text(parent, name, value):
    child = parent.find(name)
    if child is None:
        child = ET.SubElement(parent, name)
    child.text = str(value)


def make_world(package, manifest, directory, take, step, *, use_follow_camera, fps):
    tree = ET.parse(package / manifest['world_file'])
    world = tree.getroot().find('world')
    robot_name = manifest['robot']['model_name']
    robot = world.find(f"model[@name='{robot_name}']")
    x, y, z, yaw = take.rows[0][1:5]
    set_text(robot, 'pose', f'{x:.16g} {y:.16g} {z:.16g} 0 0 {yaw:.16g}')
    fixture_names = set(manifest['bin']['collision_names'])
    plant_names = {plant['model_name'] for plant in manifest['plants']}
    removed_contacts = {'plant': [], 'robot': []}
    for model in world.findall('model'):
        name = model.get('name')
        if name.startswith('view_'):
            world.remove(model)
        if name not in plant_names and model is not robot:
            continue
        for link in model.findall('link'):
            if model is robot:
                set_text(link, 'gravity', 'false')
                set_text(link, 'self_collide', 'false')
            for collision in link.findall('collision'):
                if model is robot and collision.get('name') in fixture_names:
                    continue
                removed_contacts['robot' if model is robot else 'plant'].append(
                    f"{name}/{link.get('name')}/{collision.get('name')}")
                link.remove(collision)

    if {part.get('name') for part in robot.findall('.//collision')} != fixture_names:
        raise ValueError('The original basket floor and walls must remain physical')
    for plugin in robot.findall('plugin'):
        robot.remove(plugin)
    for joint in robot.findall('joint'):
        if joint.get('name') not in take.joints and joint.get('type') != 'fixed':
            joint.set('type', 'fixed')
            for field in ('axis', 'axis2', 'physics'):
                for child in joint.findall(field):
                    joint.remove(child)

    trajectory, commands = take.save(directory)
    playback = ET.SubElement(robot, 'plugin', filename=PLAYBACK,
                             name='uchuva::HarvestDemoPlaybackSystem')
    set_text(playback, 'trajectory_file', trajectory)
    set_text(playback, 'commands_file', commands)
    set_text(playback, 'harvest_command_topic', manifest['interaction']['command_topic'])
    set_text(playback, 'observations_file', directory / 'native_motion.tsv')
    for name, speed in zip(take.joints, take.speeds):
        ET.SubElement(playback, 'joint', name=name, max_speed=str(speed))

    physics = world.find('physics')
    set_text(physics, 'max_step_size', step)
    set_text(physics, 'real_time_factor', 0)
    if use_follow_camera:
        from run_cad_v8_demo_capture import prepare_camera

        observer = prepare_camera(world, robot_name=robot_name, fps=fps)
    else:
        observer = manifest['video_observer']
    asset_tags = {'uri', 'albedo_map', 'normal_map', 'roughness_map', 'metalness_map'}
    for asset in world.iter():
        if asset.tag in asset_tags:
            name = (asset.text or '').strip()
            if name not in manifest['files_sha256']:
                raise ValueError(f'Demonstration refers to an unverified asset: {name}')
            asset.text = str(package / name)
    ET.indent(tree, space='  ')
    output = directory / 'demo.sdf'
    tree.write(output, encoding='utf-8', xml_declaration=True)
    return output, observer, removed_contacts


def audit_elbow_up(manifest, package, take):
    from uchuva_gazebo.elbow_up_clearance import ElbowUpClearance
    from uchuva_gazebo.robot_spec import resolve_robot_profile

    clearance = take.fixture['motion_clearance_m']
    auxiliary = manifest['robot_task']['auxiliary_joint_positions']
    if any(value != 0. for name, value in auxiliary.items() if name != take.jaw['joint']):
        raise ValueError('Elbow-up verification requires the same CAD-zero suspension used in the take')
    admission = ElbowUpClearance(resolve_robot_profile(manifest['robot_config']),
                                 manifest['robot_task'], asset_root=package)
    by_motion = {}
    intervals = []
    for start, end in zip(take.rows, take.rows[1:]):
        a, b = tuple(start[5:11]), tuple(end[5:11])
        key = tuple(sorted((a, b)))
        if key not in by_motion:
            if a == b:
                result = admission.pose(a[:5], a[5], clearance=clearance)
            else:
                result = admission.segment(a[:5], b[:5], a[5], b[5], clearance=clearance)
            by_motion[key] = result
        result = by_motion[key]
        if not result['passed']:
            raise ValueError(f'Elbow-up clearance failed at {start[0]:.3f}–{end[0]:.3f} s: {result}')
        intervals.append({'start_sim_s': start[0], 'end_sim_s': end[0], **result})
    return {'passed': True, 'clearance_m': clearance, 'robot_spec_sha256': manifest['robot_spec_sha256'],
            'arm_chassis_pairs': len(admission.arm_chassis_pairs), 'intervals': intervals}


def prepare(package, routes, output, *, limit, step, use_follow_camera=True, fps=15, elbow_up=False):
    package, output = package.resolve(), output.resolve()
    manifest = load_verified_package(package)
    source_hash = sha256_file(package / 'manifest.json')
    route_source = routes.read_bytes()
    proposal = json.loads(route_source)
    if proposal['source_manifest_sha256'] != source_hash:
        raise ValueError('Route belongs to a different frozen crop and robot')
    elbow_up = elbow_up or proposal.get('schema_version') == 'v8-elbow-up-take-route/1.0'
    targets = proposal['mission']['targets'][:limit]
    original = {target['id']: target for target in manifest['mission']['targets']}
    completed = set(proposal['completed_candidate_ids'])
    target_ids = [target['id'] for target in targets]
    if len(set(target_ids)) != limit or any(t['id'] not in completed or t['id'] not in original or
                                          t['cut_axis_world'] != original[t['id']]['cut_axis_world'] for t in targets):
        raise ValueError('Require routes with completed release geometry and matching cut axes')
    if limit == 9:
        plants = {fruit['id']: fruit['plant_id'] for fruit in manifest['fruits']}
        if Counter(plants[identifier] for identifier in target_ids) != {p['id']: 3 for p in manifest['plants']}:
            raise ValueError('A full take requires three distinct fruits from each frozen bush')

    config = json.loads((package / 'configuration.json').read_text(encoding='utf-8'))
    start = config['robot_start_xyzyaw']
    first = targets[0]
    first_x, first_y, _ = first['base_route'][0]
    dock_x, dock_y, _ = first['pickup_base_xyyaw']
    if abs(first_y - dock_y) < 1e-8 and first_x < dock_x:
        start[:2] = [min(first_x - .30, dock_x - .9), dock_y]
        if len(first['base_route']) == 2:
            first['base_route'] = first['base_route'][1:]
    first_x, first_y, _ = first['base_route'][0]
    if math.dist(start[:2], (first_x, first_y)) > 1e-8:
        start[3] = math.atan2(first_y - start[1], first_x - start[0])
    carry = proposal['mission']['carry_joints_rad'] if elbow_up else None
    take = Take(manifest, start, carry=carry)
    take.hold(1.25)
    for target in targets:
        take.harvest(target)
    take.phase('verificacion_final', None)
    take.arm_to(take.carry, opened=False)
    if limit > 1:
        for waypoint in targets[-1]['after_deposit_route']:
            take.drive(waypoint)
    take.hold(1.8)
    evidence = audit_elbow_up(manifest, package, take) if elbow_up else None
    output.mkdir(parents=True, exist_ok=False)
    world, observer, removed = make_world(package, manifest, output, take, step,
                                          use_follow_camera=use_follow_camera, fps=fps)
    result = {
        'schema_version': 'cad-v8-continuous-demo-take/1.0',
        'scope': 'prescribed_arm_and_chassis_motion_with_native_cut_retention_release_and_gravity',
        'crop_handling': 'original_visuals_and_poses; no prescribed vehicle or arm collision response',
        'passive_mechanisms': 'frozen_at_cad_zero_for_this_take',
        'source_package': str(package), 'source_manifest_sha256': source_hash,
        'route_source_sha256': hashlib.sha256(route_source).hexdigest(), 'world_file': world.name,
        'world_name': manifest['world_name'], 'video_observer': observer,
        'targets': targets, 'target_ids': target_ids,
        'duration_s': take.rows[-1][0], 'physics_step_s': step,
        'phases': take.phases, 'interaction': manifest['interaction'], 'removed_contacts': removed,
        'files_sha256': {name: sha256_file(output / name)
                         for name in (world.name, 'trajectory.tsv', 'commands.tsv')},
    }
    if evidence is not None:
        report = output / 'elbow_up_clearance.json'
        report.write_text(json.dumps(evidence, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        result['elbow_up_clearance'] = report.name
        result['arm_motion_policy'] = 'elbow_above_shoulder_wrist_chord_and_continuously_verified_CAD_clearance'
        result['files_sha256'][report.name] = sha256_file(report)
    (output / 'demo_manifest.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('routes', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--limit', type=int, choices=range(1, 10), default=9)
    parser.add_argument('--physics-step', type=float, choices=(.001, .002, .004), default=.002)
    parser.add_argument('--fps', type=int, choices=(10, 12, 15, 20, 24), default=15)
    parser.add_argument('--fixed-camera', action='store_true')
    parser.add_argument('--elbow-up', action='store_true',
                        help='Require certified elbow-up motion and CAD arm clearance throughout the take')
    args = parser.parse_args()
    result = prepare(args.package, args.routes, args.output, limit=args.limit, step=args.physics_step,
                     use_follow_camera=not args.fixed_camera, fps=args.fps, elbow_up=args.elbow_up)
    print(f"Prepared {len(result['target_ids'])} fruits over {result['duration_s']:.1f} simulation seconds")


if __name__ == '__main__':
    main()
