#!/usr/bin/env python3
"""Repartition frozen CAD occurrences into suspension and gripper mechanisms.

Every source occurrence, mesh, color, oriented collision bound and CAD inertia
is retained. Joint coordinates start at the saved CAD posture. The explicit
settings describe simulation hypotheses, never measured hardware limits.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from uchuva_gazebo.robot_spec import resolve_robot_profile, verify_robot_assets
from uchuva_gazebo.robot_kinematics import (forward_kinematics, compose_poses,
    inverse_pose, pose_identity, transform_point, rotate_vector)
from prepare_cad_robot import aggregate_inertia, CAD_ROTATION


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pose(point):
    return {**pose_identity(), 'xyz_m': list(point)}


def scaled_inertia(inertia, fraction):
    return {'mass_kg': inertia['mass_kg']*fraction,
            'com_m': list(inertia['com_m']),
            'tensor_kg_m2': [v*fraction for v in inertia['tensor_kg_m2']]}


def raw_mass(inertia):
    xx, yy, zz, xy, xz, yz = inertia['tensor_kg_m2']
    return {'mass_kg': inertia['mass_kg'], 'center_of_mass_m': inertia['com_m'],
            'xyz_moments_kg_m2': [xx, yy, zz, xy, yz, xz]}


def body_total(links, poses):
    return aggregate_inertia([(raw_mass(row['inertial']), poses[row['name']]) for row in links])


def apply_collision_derivatives(robot, manifest, manifest_sha256):
    """Bind audited collision-only revisions; keep original visual CAD bytes.

    The caller verifies the manifest's complete asset root. This operation
    changes only collision URI/hash and records the explicit derivation in
    provenance; masses, poses, limits, gains and collision exclusions stay put.
    """
    entries=manifest.get('entries')
    if not isinstance(entries,dict) or not entries:
        raise ValueError('Collision derivative manifest needs source-hash entries')
    data=robot.to_dict()
    changes=[]
    for link in data['links']:
        for collision in link['collisions']:
            geometry=collision['geometry']
            if geometry['type']!='mesh':
                continue
            source=geometry['sha256']
            entry=entries.get(source)
            if not isinstance(entry,dict):
                raise ValueError('Collision derivative missing for source '+source)
            unchanged=(entry.get('positions_unchanged') is True and
                       entry.get('unoriented_triangles_unchanged') is True)
            if not unchanged:
                repair=entry.get('report',{})
                displacement=repair.get('maximum_position_change_m')
                if (repair.get('change_class')!='restore_native_source_and_numeric_seam' or
                    type(displacement) not in (int,float) or not math.isfinite(displacement) or
                    not 0<=displacement<=5e-9 or
                    not isinstance(repair.get('native_source_sha256'),str) or
                    len(repair['native_source_sha256'])!=64):
                    raise ValueError('Undocumented collision geometry change for '+source)
            before=copy.deepcopy(geometry)
            geometry['uri']=entry['collision_uri']
            geometry['sha256']=entry['collision_sha256']
            changes.append({'link':link['name'],'collision_id':collision['name'],
                'source_geometry':before,'collision_geometry':copy.deepcopy(geometry),
                'surface_preserved':unchanged,'repair_report':copy.deepcopy(entry.get('report',{}))})
    if not changes:
        raise ValueError('Collision derivation requires the explicit per-part mesh representation')
    data['provenance']['source']+='; collision-only derivative manifest SHA256 '+manifest_sha256
    resolved=resolve_robot_profile(data)
    return resolved, {'manifest_sha256':manifest_sha256,'changed_colliders':len(changes),
        'changes':changes,'all_visual_assets_mass_poses_dynamics_and_exclusions_preserved':True,
        'scope':'Native physics and auditor must use these same collision-only bytes. Visual CAD assets remain original. Winding repair alone changes no triangle surface; any restored native triangle/nanometre seam is listed explicitly.'}


def suspension_preload_estimates(links, poses, base_mapping):
    """Static virtual-work estimate; four-wheel load split is not measured.

    The minimum-norm normal-force allocation satisfies total vertical force
    and pitch/roll moments. It does not assert an identified suspension load
    distribution or deformable tire law.
    """
    bodies = {row['name']: row for row in links}
    total = body_total(links, poses)
    mass, com = total['mass_kg'], total['com_m']
    wheel_points = [row['center_base_m'] for row in base_mapping['wheels']]
    x2 = sum(p[0]**2 for p in wheel_points)
    y2 = sum(p[1]**2 for p in wheel_points)
    result = {}
    for row, wheel in zip(base_mapping['suspension'], base_mapping['wheels']):
        if row['name'] != wheel['name']:
            raise ValueError('Suspension/wheel mapping order mismatch')
        a = row['chassis_biela_hinge_axis_evidence']['axis_line_point_base_m']
        b = row['chassis_shock_eye_axis_evidence']['axis_line_point_base_m']
        c = row['biela_shock_eye_axis_evidence']['axis_line_point_base_m']
        distance = math.dist(b, c)
        direction = [(v-u)/distance for u, v in zip(b, c)]
        c_derivative = [c[2]-a[2], 0, -(c[0]-a[0])]
        length_derivative = sum(u*v for u, v in zip(direction, c_derivative))
        theta_derivative = (direction[2]*c_derivative[0]-direction[0]*c_derivative[2])/distance
        normal = mass*9.81*(.25+com[0]*wheel['center_base_m'][0]/x2+com[1]*wheel['center_base_m'][1]/y2)
        potential_derivative = 0.0
        names = [row['carrier_group'], wheel['group'], row['shock_group']+'_upper', row['shock_group']+'_lower']
        for name in names:
            inertia = bodies[name]['inertial']
            # A closure splits the carrier mass at identical pose/COM.
            factor = 2 if name+'_closure_aux' in bodies else 1
            center = transform_point(poses[name], inertia['com_m'])
            if name.endswith('_upper'):
                z_derivative = -theta_derivative*(center[0]-b[0])
            elif name.endswith('_lower'):
                z_derivative = c_derivative[2]-theta_derivative*(center[0]-c[0])
            else:
                z_derivative = -(center[0]-a[0])
            potential_derivative += factor*inertia['mass_kg']*9.81*z_derivative
        wheel_vertical_derivative = -(wheel['center_base_m'][0]-a[0])
        force = (potential_derivative-normal*wheel_vertical_derivative)/length_derivative
        result[row['name']] = {'wheel_normal_force_n': normal, 'spring_extension_force_n': force,
            'spring_length_derivative_m_rad': length_derivative,
            'gravity_potential_derivative_nm': potential_derivative,
            'force_status': 'estimated_static_virtual_work_not_measured_preload'}
    return result


def gripper_reduced_dynamics(links, poses, topology, axis, step_s, stiffness, damping):
    """Linearized one-DOF four-bar inertia from rigid-body kinetic energy."""
    bodies = {row['name']: row for row in links}
    dot = lambda a,b: sum(x*y for x,y in zip(a,b))
    def cross(a,b):
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
    def lever(point, pivot):
        return cross(axis, [x-y for x,y in zip(point,pivot)])
    result = {}
    for side in ('left', 'right'):
        row = next(row for row in topology if row['name'] == 'gripper_'+side)
        a,b,c,d = [row['points_base_m'][key] for key in 'ABCD']
        short_v, jaw_v, c_v = lever(d,a), lever(d,c), lever(c,b)
        column = [-v for v in jaw_v]
        aa, ab, bb = dot(short_v,short_v), dot(short_v,column), dot(column,column)
        rhs_a, rhs_b = dot(short_v,c_v), dot(column,c_v)
        determinant = aa*bb-ab*ab
        if determinant <= 1e-20:
            raise ValueError('Gripper is singular at the CAD reference configuration')
        short_rate = (rhs_a*bb-rhs_b*ab)/determinant
        jaw_rate = (rhs_b*aa-rhs_a*ab)/determinant
        effective_inertia, gravity_effort = 0.0, 0.0
        for suffix, rate, pivot in (('gear',1,b),('short',short_rate,a),('jaw',jaw_rate,c)):
            name = 'gripper_'+side+'_'+suffix
            inertia = bodies[name]['inertial']
            factor = 2 if name+'_closure_aux' in bodies else 1
            center = transform_point(poses[name],inertia['com_m'])
            velocity = [rate*v for v in lever(center,pivot)]
            if suffix == 'jaw':
                velocity = [v+w for v,w in zip(velocity,c_v)]
            q = poses[name]['quaternion_xyzw']
            local_axis = rotate_vector([-q[0],-q[1],-q[2],q[3]],axis)
            xx,yy,zz,xy,xz,yz = inertia['tensor_kg_m2']
            tensor = [[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]]
            axial = dot(local_axis,[dot(trow,local_axis) for trow in tensor])
            effective_inertia += factor*(inertia['mass_kg']*dot(velocity,velocity)+rate*rate*axial)
            gravity_effort += factor*inertia['mass_kg']*9.81*velocity[2]
        result[side] = {'effective_inertia_kg_m2': effective_inertia, 'gravity_compensation_nm': gravity_effort,
                        'short_angular_ratio': short_rate, 'jaw_angular_ratio': jaw_rate}
    relative = 1/sum(1/result[side]['effective_inertia_kg_m2'] for side in ('left','right'))
    alpha, beta = damping*step_s/relative, stiffness*step_s*step_s/relative
    result['relative_gear_mode'] = {'effective_inertia_kg_m2': relative,
        'explicit_damping_alpha': alpha, 'explicit_stiffness_beta': beta,
        'semiimplicit_linear_stability_expression_2alpha_plus_beta': 2*alpha+beta,
        'linear_isolated_mode_stable_if_below': 4,
        'scope': 'CAD-reference ideal four-bar velocity reduction. This isolated semiimplicit explicit-force screen omits motor PID, native damping, contact and closure solver errors; it is not native acceptance.'}
    return result


def mechanism_profile(source, import_report, arm_mapping, base_mapping, inventory, settings, motion_inventory=None):
    original = resolve_robot_profile(source)
    data = original.to_dict()
    if data.get('closures'):
        raise ValueError('Source must be the frozen reduced CAD profile, not an already expanded mechanism')
    initial = copy.deepcopy(data)
    zero = {row['name']: 0 for row in data['joints'] if row['type'] != 'fixed'}
    old_poses = forward_kinematics(original, zero)
    old_links = {row['name']: row for row in data['links']}
    group_poses = {name: copy.deepcopy(old_poses[name]) for name in old_links}
    assignment = {row['occurrence_id']: row['link'] for row in import_report['parts']}
    if len(assignment) != len(import_report['parts']):
        raise ValueError('Duplicate source physical occurrences')
    for source_row in import_report['parts']:
        if source_row['link'] not in old_links:
            raise ValueError('Import report does not match the input CAD groups')
    settings_evidence = {'status': 'estimado', 'source': settings['revision_id'],
        'revision': settings['revision_id'], 'method': settings['scope']}
    joints = data['joints']
    closures = []
    closure_requests = []
    topology_evidence = []

    def add_joint(name, parent, child, point, axis, kind, limits, group='passive', dynamics=None):
        frame = pose(point)
        row = {'name': name, 'type': kind, 'group': group, 'parent': parent, 'child': child,
               'origin': compose_poses(inverse_pose(group_poses[parent]), frame),
               'child_pose': compose_poses(inverse_pose(frame), group_poses[child]),
               'axis': list(axis), 'zero_offset': 0, 'limits': dict(limits)}
        row.update(dynamics or {})
        joints.append(row)

    # The old mapping's document ids vary with export order. Stable occurrence
    # names are taken from its preserved root placements, never id arithmetic.
    top_groups = {}
    for group in base_mapping['groups']:
        for root in group['root_placements']:
            if root['name'] in top_groups:
                raise ValueError('Ambiguous base occurrence assignment')
            top_groups[root['name']] = group['name']
    for row in import_report['parts']:
        if row['source_path'].startswith('base/') or row['link'].startswith('wheel_') or row['link'] == 'base_link':
            top = row['occurrence_name_path'][0]
            if top not in top_groups:
                raise ValueError('Unclassified base root occurrence: '+top)
            group = top_groups[top]
            if group == 'base_chassis':
                group = 'base_link'
            if group.startswith('shock_'):
                name = row['occurrence_name_path'][-1]
                # Bolt and nut retain the lower slider's rigid motion. The
                # visible coil is a rigid CAD reference on upper, while the
                # force law is independently applied at the telescope joint.
                upper = {'Main Body v10:1', 'Adjust Nut v2:1', 'Muelle de compresión1:1'}
                lower = {'Second Body v3:1', 'Bolt v2:1', 'Nut v2:1', 'Cap v9:1'}
                if name not in upper | lower:
                    raise ValueError('Unclassified physical shock component: '+name)
                group += '_upper' if name in upper else '_lower'
            assignment[row['occurrence_id']] = group
    suspension = settings['suspension']
    for row in base_mapping['suspension']:
        suffix, carrier = row['name'], row['carrier_group']
        upper, lower = row['shock_group']+'_upper', row['shock_group']+'_lower'
        a = row['chassis_biela_hinge_axis_evidence']['axis_line_point_base_m']
        b = row['chassis_shock_eye_axis_evidence']['axis_line_point_base_m']
        c = row['biela_shock_eye_axis_evidence']['axis_line_point_base_m']
        direction = [v-u for u, v in zip(b, c)]
        norm = math.sqrt(sum(v*v for v in direction))
        direction = [v/norm for v in direction]
        group_poses.update({carrier: pose(a), upper: pose(b), lower: pose(c)})
        hinge_limits = {'lower': suspension['pivot_limits_rad'][0], 'upper': suspension['pivot_limits_rad'][1],
                        'effort': suspension['passive_effort_bound'], 'velocity': suspension['pivot_velocity_rad_s']}
        add_joint('suspension_'+suffix+'_pivot', 'base_link', carrier, a, [0, 1, 0], 'revolute', hinge_limits,
                  dynamics={'damping': suspension['pivot_damping_nms_rad']})
        add_joint('shock_'+suffix+'_upper_eye', 'base_link', upper, b, [0, 1, 0], 'revolute', hinge_limits)
        add_joint('shock_'+suffix+'_telescope', upper, lower, c, direction, 'prismatic',
                  {'lower': suspension['slider_travel_m'][0], 'upper': suspension['slider_travel_m'][1],
                   'effort': suspension['passive_effort_bound'], 'velocity': suspension['slider_velocity_m_s']},
                  dynamics={'damping': suspension['damping_ns_m'], 'spring_stiffness': suspension['stiffness_n_m'],
                            'spring_reference': (suspension['spring_reference_m'][suffix]
                                if isinstance(suspension['spring_reference_m'], dict) else suspension['spring_reference_m'])})
        closure_requests.append(('shock_'+suffix+'_lower_eye', lower, carrier, c, [0, 1, 0], hinge_limits))
        wheel_joint = next(j for j in joints if j['name'] == suffix+'_wheel_joint')
        wheel_joint['parent'] = carrier
        wheel_joint['origin'] = compose_poses(inverse_pose(group_poses[carrier]), group_poses[wheel_joint['child']])
        topology_evidence.append({'name': suffix, 'CAD_eye_distance_m': norm, 'axes': 'parallel base +Y',
            'relations': [row[key]['relation_name'] for key in ('chassis_biela_hinge_axis_evidence',
                         'chassis_shock_eye_axis_evidence', 'biela_shock_eye_axis_evidence')]})

    gripper_doc = next(row for row in inventory['documents'] if row['source_path'] == arm_mapping['gripper']['document_path'])
    if gripper_doc['sha256'] != arm_mapping['gripper']['document_sha256']:
        raise ValueError('Gripper topology comes from a different CAD revision')
    relations = {row['name']: row for row in gripper_doc['relations']}
    mount = old_poses['arm_base_mount']
    gripper_pose = compose_poses(compose_poses(mount, CAD_ROTATION), arm_mapping['frames']['gripper_assembly_reference']['pose_root'])
    axis = rotate_vector(gripper_pose['quaternion_xyzw'], [0, 1, 0])
    gripper_groups = {
        'Eslabon 1:1': 'gripper_right_short', 'Eslabon 1:2': 'gripper_left_short',
        'Engranaje recto2:1': 'gripper_right_gear', 'Engranaje recto1:1': 'gripper_left_gear',
        'Wheel_gear v2:1': 'gripper_left_gear',
        **{name: 'gripper_left_jaw' for name in arm_mapping['gripper']['subgroups']['jaw_left']},
        **{name: 'gripper_right_jaw' for name in arm_mapping['gripper']['subgroups']['jaw_right']},
    }
    allowed_housing = set(arm_mapping['gripper']['subgroups']['housing'])
    for row in import_report['parts']:
        path = row['occurrence_name_path']
        if path[0] == arm_mapping['gripper']['root_occurrence']:
            if path[1] not in gripper_groups and path[1] not in allowed_housing:
                raise ValueError('Unclassified gripper occurrence: '+str(path))
            assignment[row['occurrence_id']] = gripper_groups.get(path[1], 'arm_wrist_roll')
    grip = settings['gripper']
    grip_limits = {'lower': grip['joint_limits_rad'][0], 'upper': grip['joint_limits_rad'][1],
                   'effort': grip['effort_nm'], 'velocity': grip['velocity_rad_s']}
    for side, references in (
        ('right', [('Coincidencia:10', 'EntityOne'), ('Coincidencia:1', 'EntityTwo'),
                   ('Coincidencia:22', 'EntityOne'), ('Coincidencia:15', 'EntityOne')]),
        ('left', [('Coincidencia:9', 'EntityOne'), ('Coincidencia:7', 'EntityTwo'),
                  ('Coincidencia:23', 'EntityOne'), ('Coincidencia:13', 'EntityOne')])):
        points = []
        for relation, entity in references:
            geometry = relations[relation][entity]
            if abs(abs(geometry['AxisVector'][1])-1) > 1e-8:
                raise ValueError('Gripper four-bar pin is not parallel to CAD Y')
            point = geometry['BasePoint_m']
            points.append(transform_point(gripper_pose, [point[0], 0, point[2]]))
        a, b, c, d = points
        short, gear, jaw = ('gripper_'+side+'_'+suffix for suffix in ('short', 'gear', 'jaw'))
        group_poses.update({short: pose(a), gear: pose(b), jaw: pose(c)})
        add_joint(short+'_pivot', 'arm_wrist_roll', short, a, axis, 'revolute', grip_limits,
                  dynamics={'damping': grip['passive_damping_nms_rad']})
        gear_joint = 'gripper_left_driver' if side == 'left' else 'gripper_right_follower'
        add_joint(gear_joint, 'arm_wrist_roll', gear, b, axis, 'revolute', grip_limits,
                  group='gripper' if side == 'left' else 'passive')
        add_joint(jaw+'_pivot', gear, jaw, c, axis, 'revolute', grip_limits,
                  dynamics={'damping': grip['passive_damping_nms_rad']})
        closure_requests.append((short+'_closure_pin', jaw, short, d, axis, grip_limits))
        topology_evidence.append({'name': 'gripper_'+side, 'points_base_m': dict(zip('ABCD', points)),
                                  'relations': references})
    drive_name = 'gripper_left_driver'
    data['control']['gripper'][drive_name] = {
        'p_gain': grip['p_gain'], 'i_gain': 0, 'd_gain': grip['d_gain'],
        'i_min': 0, 'i_max': 0, 'cmd_min': -grip['effort_nm'], 'cmd_max': grip['effort_nm'],
        'command_velocity': grip.get('command_velocity_rad_s',grip['velocity_rad_s'])}
    data['actuators'].append({'name': drive_name+'_actuator', 'joint': drive_name,
        'continuous_effort': grip['effort_nm'], 'peak_effort': grip['effort_nm'],
        'transmission_ratio': 1, 'efficiency': 1, 'effort_reference': 'joint_output', 'status': 'estimado'})
    if settings.get('gear_coupling'):
        if not motion_inventory or not motion_inventory.get('source_integrity') or motion_inventory['source_integrity']['changed_files']:
            raise ValueError('Gear coupling requires explicit source-intact native motion inventory')
        motion_doc = next(row for row in motion_inventory['documents'] if row['source_path'] == arm_mapping['gripper']['document_path'])
        if motion_doc['sha256'] != gripper_doc['sha256']:
            raise ValueError('Motion metadata differs from the gripper geometry revision')
        gear_relation = next(row for row in motion_doc['relations'] if row['name'] == 'Rotación:1')
        if (gear_relation.get('ForwardDirection') is not False or gear_relation.get('suppressed') is not False or
            gear_relation.get('parameters', {}).get('Ratio', {}).get('si_value') != 1 or
            settings['gear_coupling']['parameters']['ratio'] != -1 or settings['gear_coupling']['parameters']['offset'] != 0):
            raise ValueError('This explicit common-Y gear adapter requires the verified opposite 1:1 CAD relation')
        topology_evidence.append({'name': 'gripper_gear_pair', 'document_sha256': motion_doc['sha256'],
            'relation': gear_relation['name'], 'native_ratio': 1, 'native_forward_direction': False,
            'coordinate_convention': 'Both joint axes are common +Y in the gripper document; q0 is the saved CAD reference, not encoder calibration.'})
        data['gear_couplings'] = [{'name': 'gripper_gear_pair', 'driver': drive_name,
            'follower': 'gripper_right_follower', **settings['gear_coupling']['parameters']}]

    links = {name: {'name': name, 'visuals': [], 'collisions': []} for name in group_poses}
    parts = {name: [] for name in links}
    assignments = []
    consumed_visuals, consumed_collisions = set(), set()
    for index, row in enumerate(import_report['parts']):
        group = assignment[row['occurrence_id']]
        source_link = old_links[row['link']]
        move = compose_poses(inverse_pose(group_poses[group]), old_poses[row['link']])
        placement = compose_poses(move, row['link_T_document'])
        parts[group].append((row['mass_properties'], placement))
        key = 'part_'+str(index)
        for category, expected in (('visuals', key), ('collisions', key+'_bounds')):
            matches = [shape for shape in source_link[category] if shape['name'] == expected]
            for shape in matches:
                if category == 'visuals' and shape['geometry']['sha256'] != row['mesh_sha256']:
                    raise ValueError('Source part visual hash mismatch')
                moved = copy.deepcopy(shape)
                moved['pose'] = compose_poses(move, moved['pose'])
                links[group][category].append(moved)
                (consumed_visuals if category == 'visuals' else consumed_collisions).add((row['link'], expected))
        assignments.append({'occurrence_id': row['occurrence_id'], 'occurrence_name_path': row['occurrence_name_path'],
                            'old_link': row['link'], 'link': group, 'link_T_document': placement,
                            'mass_kg': row['mass_properties']['mass_kg']})
    # Tire primitives are assembly-level collision bodies, not per-leaf bounds.
    for name, link in old_links.items():
        for category, consumed in (('visuals', consumed_visuals), ('collisions', consumed_collisions)):
            for shape in link[category]:
                if (name, shape['name']) in consumed:
                    continue
                if category != 'collisions' or not name.startswith('wheel_') or not shape['name'].endswith('_tire'):
                    raise ValueError('Unaccounted source geometry: '+name+'/'+shape['name'])
                links[name][category].append(copy.deepcopy(shape))
    for name in links:
        links[name]['inertial'] = aggregate_inertia(parts[name])
    for name, parent, body, point, direction, limits in closure_requests:
        auxiliary = body+'_closure_aux'
        original_inertia = copy.deepcopy(links[body]['inertial'])
        links[body]['inertial'] = scaled_inertia(original_inertia, .5)
        links[auxiliary] = {'name': auxiliary, 'visuals': [], 'collisions': [],
                            'inertial': scaled_inertia(original_inertia, .5)}
        group_poses[auxiliary] = copy.deepcopy(group_poses[body])
        add_joint(name, parent, auxiliary, point, direction, 'revolute', limits)
        closures.append({'name': name+'_weld', 'moving_joint': name, 'body': body,
                         'auxiliary': auxiliary, 'mass_fraction': .5, 'original_inertial': original_inertia})
    data['links'] = list(links.values())
    data['closures'] = closures
    data['collision_policy']['excluded_pairs'] = [
        {'links': [row['parent'], row['child']], 'reason': 'Mechanically adjacent tree joint '+row['name']}
        for row in joints]
    for row in closures:
        parent = next(j['parent'] for j in joints if j['name'] == row['moving_joint'])
        data['collision_policy']['excluded_pairs'].append({'links': [parent, row['body']],
            'reason': 'Physical closing pin '+row['moving_joint']+'; auxiliary only repartitions its body inertia'})
    data['collision_policy']['excluded_pairs'].append({'links': ['gripper_left_gear', 'gripper_right_gear'],
        'reason': 'Meshing gear pair represented by its explicit force transmission; full-part bounds are not tooth contact'})
    data['profile_id'] += '_mechanisms'
    data['provenance'] = {**settings_evidence, 'source': initial['provenance']['source']+'; '+settings['revision_id']}
    if settings.get('physics'):
        data['physics'] = copy.deepcopy(settings['physics'])
    # Named parameters make the estimated dynamics visible in the contract.
    for name, value in (('suspension_stiffness_n_m', suspension['stiffness_n_m']),
                        ('suspension_damping_ns_m', suspension['damping_ns_m'])):
        data['parameters'][name] = value
        data['parameter_metadata']['/parameters/'+name] = {**settings_evidence, 'update_class': 'model_regeneration'}
    for index, joint in enumerate(joints):
        if joint['name'].endswith('_telescope'):
            reference_parameter = joint['name']+'_spring_reference_m'
            data['parameters'][reference_parameter] = joint['spring_reference']
            data['parameter_metadata']['/parameters/'+reference_parameter] = {**settings_evidence, 'update_class': 'model_regeneration'}
            for field, parameter in (('spring_stiffness', 'suspension_stiffness_n_m'),
                                     ('damping', 'suspension_damping_ns_m'),
                                     ('spring_reference', reference_parameter)):
                data['derived_values'].append({'path': f'/joints/{index}/{field}', 'expression': {'parameter': parameter}})
    resolved = resolve_robot_profile(data)
    new_poses = forward_kinematics(resolved, {row['name']: 0 for row in joints if row['type'] != 'fixed'})
    before, after = body_total(initial['links'], old_poses), body_total(data['links'], new_poses)
    values = lambda row: [row['mass_kg'], *row['com_m'], *row['tensor_kg_m2']]
    if max(abs(a-b) for a, b in zip(values(before), values(after))) > 1e-10:
        raise AssertionError('Repartition failed total CAD mass/COM/inertia conservation')
    errors = []
    for category in ('visuals', 'collisions'):
        expected = {shape['name']: (link['name'], shape) for link in initial['links'] for shape in link[category]}
        actual = {shape['name']: (link['name'], shape) for link in data['links'] for shape in link[category]}
        if len(expected) != sum(len(link[category]) for link in initial['links']) or expected.keys() != actual.keys():
            raise AssertionError('Missing/duplicate source geometry identities')
        for name, (old_link, shape) in expected.items():
            new_link, moved = actual[name]
            if {k:v for k,v in shape.items() if k != 'pose'} != {k:v for k,v in moved.items() if k != 'pose'}:
                raise AssertionError('Geometry, color, mesh binding or contact changed: '+name)
            a = compose_poses(old_poses[old_link], shape['pose'])
            b = compose_poses(new_poses[new_link], moved['pose'])
            errors.append(math.dist(a['xyz_m'], b['xyz_m']))
            if errors[-1] > 1e-10 or 1-abs(sum(x*y for x,y in zip(a['quaternion_xyzw'], b['quaternion_xyzw']))) > 1e-12:
                raise AssertionError('CAD reference geometry moved: '+name)
    report = {'schema_version': 'cad-articulated-mechanisms/1.0', 'status': 'PREPARED_NOT_NATIVE_VALIDATED',
        'source_robot_spec_sha256': original.sha256, 'robot_spec_sha256': resolved.sha256,
        'source_occurrences': len(assignments), 'source_mass_kg': before['mass_kg'], 'new_mass_kg': after['mass_kg'],
        'mass_com_tensor_conserved': True, 'maximum_q0_geometry_position_change_m': max(errors),
        'all_mesh_colors_collisions_preserved': True, 'assignments': assignments, 'topology_evidence': topology_evidence,
        'settings': settings, 'closures': closures,
        'static_preload_estimates': suspension_preload_estimates(data['links'], new_poses, base_mapping),
        'limitations': ['Shock coil retains its CAD reference mesh rigidly on upper body; no deforming spring mesh.',
                        'Internal slider grouping is an explicit engineering interpretation of CAD coincidences, not measured travel.',
                        'Gear coupling, passive-joint contact filtering and full-model native stability require separate validation.',
                        'TCP/cut/grasp stay on the rigid housing calibration; moving blade contact is not inferred from these frames.']}
    if settings.get('gear_coupling'):
        gear = settings['gear_coupling']['parameters']
        report['gripper_reduced_dynamics'] = gripper_reduced_dynamics(data['links'], new_poses, topology_evidence,
            axis, data.get('physics', {}).get('maximum_step_s', gear['maximum_step_s']),
            gear['stiffness_nm_rad'], gear['damping_nms_rad'])
    if settings.get('collision_representation') == 'cad_meshes':
        refined = resolved.to_dict()
        refined_links = {row['name']: row for row in refined['links']}
        changed = []
        for index, row in enumerate(import_report['parts']):
            group = assignment[row['occurrence_id']]
            target = refined_links[group]
            matches = [shape for shape in target['collisions'] if shape['name'] == 'part_'+str(index)+'_bounds']
            if not matches:
                # The three wheel components share the admitted tire cylinder.
                if not group.startswith('wheel_'):
                    raise ValueError('Physical source occurrence lost its collision identity')
                continue
            visual = next((shape for shape in target['visuals'] if shape['name'] == 'part_'+str(index)), None)
            if visual is None:
                raise ValueError('Mesh collision requires the exact admitted part visual placement/geometry')
            if visual['geometry']['sha256'] != row['mesh_sha256']:
                raise ValueError('Mesh collision source differs from its CAD occurrence report')
            old_geometry = copy.deepcopy(matches[0]['geometry'])
            matches[0]['geometry'] = copy.deepcopy(visual['geometry'])
            matches[0]['pose'] = copy.deepcopy(visual['pose'])
            changed.append({'collision_id': matches[0]['name'], 'occurrence_id': row['occurrence_id'],
                'source_mesh_sha256': row['mesh_sha256'], 'old_geometry': old_geometry,
                'new_geometry': copy.deepcopy(visual['geometry']), 'new_pose': copy.deepcopy(visual['pose'])})
        if 'collision_meshes' not in refined['capabilities']:
            refined['capabilities'].append('collision_meshes')
        resolved = resolve_robot_profile(refined)
        report['robot_spec_sha256'] = resolved.sha256
        report['all_mesh_colors_collisions_preserved'] = False
        report['all_visual_meshes_colors_mass_and_occurrences_preserved'] = True
        report['collision_revision'] = {'representation':'native_admitted_CAD_triangle_mesh_per_part',
            'changed': changed, 'part_colliders_replaced': len(changed), 'tire_cylinders_retained': 4,
            'stable_collision_ids':'Former *_bounds identifiers retained for provenance; geometry.type now explicitly mesh.',
            'conformance': settings.get('collision_conformance', {}),
            'scope':'Actual admitted tessellated CAD solids preserve cavities; not a mechanical redesign or exact BRep. Original mesh chord tolerance still bounds discretization uncertainty.'}
        report['limitations'].append('Robot self-clearance uses admitted CAD meshes rather than former whole-part OBBs; this is an explicit collision representation revision.')
    return resolved, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'import-report', 'arm-mapping', 'base-mapping', 'inventory', 'settings', 'output', 'asset-root'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--motion-inventory', type=Path,
                        help='Required when the settings enable gear coupling; native ratio/direction evidence')
    parser.add_argument('--collision-derivatives',type=Path,
                        help='Audited collision-only manifest with a complete portable asset_root')
    args = parser.parse_args()
    robot, report = mechanism_profile(args.profile, read(args.import_report), read(args.arm_mapping),
                                     read(args.base_mapping), read(args.inventory), read(args.settings),
                                     read(args.motion_inventory) if args.motion_inventory else None)
    asset_root=args.asset_root
    if args.collision_derivatives:
        manifest=read(args.collision_derivatives)
        root_uri=manifest.get('asset_root')
        if not isinstance(root_uri,str) or Path(root_uri).is_absolute() or '..' in Path(root_uri).parts:
            raise ValueError('Collision derivative asset_root must be portable within its manifest directory')
        asset_root=(args.collision_derivatives.parent/root_uri).resolve(strict=True)
        if not asset_root.is_relative_to(args.collision_derivatives.parent.resolve()):
            raise ValueError('Collision derivative asset root escapes its manifest directory')
        robot,derivation=apply_collision_derivatives(robot,manifest,sha(args.collision_derivatives))
        report['collision_asset_derivation']=derivation
        report['robot_spec_sha256']=robot.sha256
        report['limitations'].append('Collision-only orientation/native-facet repairs are a separate hashed derivative, not the unchanged original visual OBJ.')
    report['asset_root']=str(asset_root.resolve())
    report['verified_assets_sha256'] = verify_robot_assets(robot, asset_root)
    report['source_files_sha256'] = {str(path): sha(path) for path in (args.profile, args.import_report,
        args.arm_mapping, args.base_mapping, args.inventory, args.settings, Path(__file__))}
    if args.motion_inventory:
        report['source_files_sha256'][str(args.motion_inventory)] = sha(args.motion_inventory)
    if args.collision_derivatives:
        report['source_files_sha256'][str(args.collision_derivatives)]=sha(args.collision_derivatives)
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, value in (('profile.json', robot.to_dict()), ('mechanisms_report.json', report)):
        (args.output/filename).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k in ('status', 'source_occurrences', 'source_mass_kg',
        'new_mass_kg', 'robot_spec_sha256', 'maximum_q0_geometry_position_change_m')}))


if __name__ == '__main__':
    main()
