"""SDF and runtime interfaces generated from a resolved robot description.

This module does not infer missing CAD dimensions or substitute proxy bodies.
The historical exporter remains a separate, explicit regression adapter.
"""
from __future__ import annotations

import math
import itertools
import xml.etree.ElementTree as ET

from .field import element as e, numbers, material
from .robot_kinematics import forward_kinematics, pose_identity, compose_poses, inverse_pose


def pose_rpy(pose):
    x, y, z, w = pose['quaternion_xyzw']
    roll = math.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))
    pitch = math.asin(max(-1.0, min(1.0, 2*(w*y-z*x))))
    yaw = math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
    return [*pose['xyz_m'], roll, pitch, yaw]


def _geometry(parent, geometry):
    kind = geometry['type']
    node = e(e(parent, 'geometry'), kind)
    fields = {'box': [('size', 'size_m')], 'sphere': [('radius', 'radius_m')],
              'cylinder': [('radius', 'radius_m'), ('length', 'length_m')],
              'mesh': [('uri', 'uri')]}
    if kind not in fields:
        raise ValueError(f'Unsupported robot SDF geometry: {kind}')
    for tag, key in fields[kind]:
        value = geometry[key]
        e(node, tag, numbers(value) if isinstance(value, (list, tuple)) else value)
    if kind == 'mesh':
        # Geometry is already exported in SI. Scaling must be an explicit
        # geometry revision, never a silent correction of a frozen CAD mesh.
        e(node, 'scale', '1 1 1')


def resolved_robot_contract(robot):
    data = robot.to_dict()
    namespace = data['namespace']
    names = list(robot.joint_names)
    by_name = {j['name']: j for j in data['joints']}
    if any(by_name[name]['type'] != 'revolute' for name in names):
        raise ValueError('The harvester contract supports revolute arm joints only; '
                         'a prismatic arm requires an explicit unit-aware contract')
    frames = {row['name']: row for row in data['frames']}
    if 'tcp' not in frames:
        raise ValueError('Robot profile must define its tcp frame')
    # A massless SDF frame is not an attachable link. The harvest adapter must
    # explicitly resolve the TCP offset on its physical parent link.
    tool_parent = frames['tcp']['parent']
    links = {row['name'] for row in data['links']}
    while tool_parent not in links:
        if tool_parent not in frames:
            raise ValueError('TCP has no physical link ancestor')
        tool_parent = frames[tool_parent]['parent']
    zero_poses = forward_kinematics(robot, {j['name']: 0 for j in data['joints'] if j['type'] != 'fixed'}, check_limits=False)
    tool_frames = {}
    for role, name in (('tcp_pose', 'tcp'), ('cut_pose', 'cut_point'), ('grasp_pose', 'grasp_center')):
        if name not in zero_poses:
            raise ValueError(f'Missing interaction frame: {name}')
        # These frames must remain rigid with the link used by the latch.
        parent = name
        while parent in frames:
            parent = frames[parent]['parent']
        if parent != tool_parent:
            raise ValueError(f'{name} must be rigidly attached to TCP physical link {tool_parent}')
        tool_frames[role] = pose_rpy(compose_poses(inverse_pose(zero_poses[tool_parent]), zero_poses[name]))
    contract = {
        'schema_version': 'resolved-harvester-contract/1.0',
        'robot_spec_sha256': robot.sha256, 'profile_id': robot.profile_id,
        'model_name': data['model_name'], 'base_link': data['root_link'],
        'tool_link': tool_parent, 'tcp_frame': 'tcp',
        'arm_dof': len(names), 'arm_joint_names': names,
        'joint_limits_rad': [[by_name[n]['limits']['lower'], by_name[n]['limits']['upper']] for n in names],
        'joint_velocity_limits_rad_s': [by_name[n]['limits']['velocity'] for n in names],
        'home_joints_rad': [data['arm_home_positions'][n] for n in names],
        'wheel_count': sum(j.get('group') == 'drive' for j in data['joints']),
        'topics': {'cmd_vel': namespace+'/cmd_vel', 'odometry': namespace+'/odometry',
                   'joint_states': namespace+'/joint_states',
                   'joint_commands': {n: namespace+'/arm/'+n+'/cmd_pos' for n in names}},
        'frames': data['frames'], 'tool_frame_poses': tool_frames,
        'drive': data['control']['drive'],
        'topics_robot_telemetry': namespace+'/robot_telemetry',
        'sensor_interfaces': [{'name': s['name'], 'frame': s['frame'], 'enabled': s['enabled'],
            'topic': namespace+'/sensors/'+s['name'], 'noise_and_latency_validation': 'pending'} for s in data['sensors']],
        'collision_backend': {'engine': 'DART', 'native_pair_semantics': 'joint_adjacent_pairs_excluded',
            'scope': 'Verified with Gazebo 8.14 / gz-physics 7.8 / DART 6.13.2; other backends need a new probe'},
        'capture_model': 'ideal constraint; physical gripping and cutting forces are not validated',
        'native_validation': 'pending_gazebo',
        'native_harvest_eligible': 'native_harvest' in data['capabilities'],
    }
    if data.get('closures') or data.get('gear_couplings') or data.get('physics'):
        contract['schema_version'] = 'resolved-harvester-contract/1.1'
        contract['closures'] = data.get('closures', [])
        contract['gear_couplings'] = data.get('gear_couplings', [])
        contract['physics'] = data.get('physics')
        contract['all_joint_names'] = [j['name'] for j in data['joints'] if j['type'] != 'fixed']
        contract['topics']['gripper_commands'] = {n: namespace+'/gripper/'+n+'/cmd_pos'
                                                   for n in data['control'].get('gripper', {})}
        if data.get('closures') or data.get('gear_couplings'):
            contract['topics']['link_poses'] = namespace+'/link_poses'
        contract['collision_backend']['native_pair_semantics'] = 'adjacency_plus_verified_16_bit_pair_masks'
    ramped = {name: data['namespace']+'/'+group+'/'+name+'/force_control_state/v1'
              for group in ('arm', 'gripper')
              for name, settings in data['control'].get(group, {}).items()
              if settings.get('reference_mode') == 'ramped_position'}
    if ramped:
        contract['schema_version'] = 'resolved-harvester-contract/1.2'
        contract['topics']['position_force_states'] = ramped
    return contract


def resolved_robot_model(robot, start=(0, 0, 0, 0)):
    """Emit links, joints and collision geometry from the same resolved graph as FK.

No model-wide collision suppression is inherited from the historical proxy.
Unsupported mechanisms fail rather than silently become fixed/ideal joints.
"""
    robot.require_capability('fk')
    data = robot.to_dict()
    poses = forward_kinematics(robot, {j['name']: 0.0 for j in data['joints'] if j['type'] != 'fixed'}, check_limits=False)
    model = ET.Element('model', name=data['model_name'])
    e(model, 'static', 'false')
    e(model, 'self_collide', 'true')
    if len(start) != 4 or not all(math.isfinite(v) for v in start):
        raise ValueError('Robot start requires finite x, y, z, yaw')
    e(model, 'pose', numbers((*start[:3], 0, 0, start[3])))
    exclusions = {tuple(sorted(x['links'])) for x in data['collision_policy']['excluded_pairs']}
    all_pairs = {tuple(sorted(pair)) for pair in itertools.combinations([l['name'] for l in data['links']], 2)}
    legacy_filter = exclusions and exclusions == all_pairs and 'legacy_proxy' in data['capabilities'] and len(data['links']) <= 16
    adjacent_pairs = {tuple(sorted((j['parent'], j['child']))) for j in data['joints']}
    # gz-physics 7.8 DART sets Skeleton self-collision without enabling its
    # separate adjacent-body flag. The three native gravity/contact controls in
    # probe_robot_self_collision.py verify adjacency suppression and continued
    # nonadjacent contact. Declare that exact policy rather than hide it.
    native_adjacency = data['collision_policy']['mode'] == 'explicit_pairs' and adjacent_pairs <= exclusions
    if not legacy_filter and not native_adjacency:
        raise ValueError('DART requires explicit adjacency exclusions and verified pair masks')
    from .robot_collision_filters import collision_masks
    masks = collision_masks(data) if not legacy_filter else {}
    for link_index, row in enumerate(data['links']):
        link = e(model, 'link', name=row['name'])
        e(link, 'pose', numbers(pose_rpy(poses[row['name']])))
        inertia = row['inertial']
        inertial = e(link, 'inertial')
        e(inertial, 'mass', inertia['mass_kg'])
        e(inertial, 'pose', numbers((*inertia['com_m'], 0, 0, 0)))
        tensor = e(inertial, 'inertia')
        for name, value in zip(('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz'), inertia['tensor_kg_m2']):
            e(tensor, name, value)
        for kind, key in (('collision', 'collisions'), ('visual', 'visuals')):
            for shape in row.get(key, []):
                node = e(link, kind, name=shape['name'])
                e(node, 'pose', numbers(pose_rpy(shape.get('pose', pose_identity()))))
                _geometry(node, shape['geometry'])
                if kind == 'visual':
                    material(node, shape.get('color_rgba', [.4, .45, .4, 1]))
                else:
                    surface = e(node, 'surface')
                    e(e(surface, 'contact'), 'collide_bitmask', (1 << link_index) if legacy_filter else masks[row['name']])
                    if shape.get('surface'):
                        friction = e(e(surface, 'friction'), 'ode')
                        for name, value in shape['surface'].items():
                            if name not in ('mu', 'mu2', 'slip1', 'slip2', 'fdir1'):
                                raise ValueError(f'Unsupported surface parameter: {name}')
                            e(friction, name, numbers(value) if isinstance(value, (list, tuple)) else value)
    for row in data['joints']:
        joint = e(model, 'joint', name=row['name'], type=row['type'])
        e(joint, 'parent', row['parent'])
        e(joint, 'child', row['child'])
        e(joint, 'pose', numbers(pose_rpy(row['origin'])), relative_to=row['parent'])
        if row['type'] != 'fixed':
            axis = e(joint, 'axis')
            e(axis, 'xyz', numbers(row['axis']))
            limit = e(axis, 'limit')
            for name, value in row['limits'].items():
                if name in ('lower', 'upper', 'effort', 'velocity'):
                    e(limit, name, value)
            if any(name in row for name in ('damping', 'friction', 'spring_reference', 'spring_stiffness')):
                dynamics = e(axis, 'dynamics')
                for name in ('damping', 'friction', 'spring_reference', 'spring_stiffness'):
                    if name in row:
                        e(dynamics, name, row[name])
    for row in data['frames']:
        frame = e(model, 'frame', name=row['name'], attached_to=row['parent'])
        e(frame, 'pose', numbers(pose_rpy(row['pose'])), relative_to=row['parent'])
    _sensors(model, data, poses)
    _controllers(model, robot)
    if data.get('closures'):
        plugin = e(model, 'plugin', filename='libUchuvaClosedLoopSystem.so', name='uchuva::ClosedLoopSystem')
        for row in data['closures']:
            closure = e(plugin, 'closure', name=row['name'])
            e(closure, 'body', row['body'])
            e(closure, 'auxiliary', row['auxiliary'])
    for row in data.get('gear_couplings', []):
        plugin = e(model, 'plugin', filename='libUchuvaGearCouplingSystem.so', name='uchuva::GearCouplingSystem')
        for key, value in row.items():
            if key != 'name':
                e(plugin, key, value)
        e(plugin, 'robot_spec_sha256', robot.sha256)
        e(plugin, 'topic', data['namespace']+'/gear_couplings/'+row['name'])
    return model


def _controllers(model, robot):
    data = robot.to_dict()
    contract = resolved_robot_contract(robot)
    positions = [(name, gains, contract['topics']['joint_commands'][name]) for name, gains in data['control']['arm'].items()]
    positions += [(name, gains, data['namespace']+'/gripper/'+name+'/cmd_pos') for name, gains in data['control'].get('gripper', {}).items()]
    joints = {j['name']: j for j in data['joints']}
    for name, gains, topic in positions:
        ramped = gains.get('reference_mode') == 'ramped_position'
        plugin = e(model, 'plugin',
                   filename='libUchuvaJointPositionForceSystem.so' if ramped else 'gz-sim-joint-position-controller-system',
                   name='uchuva::JointPositionForceSystem' if ramped else 'gz::sim::systems::JointPositionController')
        e(plugin, 'joint_name', name)
        e(plugin, 'topic', topic)
        if ramped:
            e(plugin, 'command_velocity', gains['command_velocity'])
            e(plugin, 'lower_limit', joints[name]['limits']['lower'])
            e(plugin, 'upper_limit', joints[name]['limits']['upper'])
            e(plugin, 'initial_position', 0)
            e(plugin, 'state_topic', contract['topics']['position_force_states'][name])
            e(plugin, 'robot_spec_sha256', robot.sha256)
        else:
            e(plugin, 'use_velocity_commands', 'false')
        for key in ('p_gain', 'i_gain', 'd_gain', 'i_min', 'i_max', 'cmd_min', 'cmd_max'):
            e(plugin, key, gains[key])
    publisher = e(model, 'plugin', filename='gz-sim-joint-state-publisher-system',
                  name='gz::sim::systems::JointStatePublisher')
    e(publisher, 'topic', contract['topics']['joint_states'])
    for row in data['joints']:
        if row['type'] != 'fixed':
            e(publisher, 'joint_name', row['name'])
    if 'link_poses' in contract['topics']:
        poses = e(model, 'plugin', filename='gz-sim-pose-publisher-system',
                  name='gz::sim::systems::PosePublisher')
        for key, value in {'publish_link_pose': 'true', 'publish_model_pose': 'false',
                'publish_nested_model_pose': 'false', 'publish_sensor_pose': 'false',
                'publish_collision_pose': 'false', 'publish_visual_pose': 'false', 'use_pose_vector_msg': 'true',
                'static_publisher': 'false', 'update_frequency': 100,
                'topic': contract['topics']['link_poses']}.items():
            e(poses, key, value)
    for name, gains in data['control']['drive'].get('joints', {}).items():
        plugin = e(model, 'plugin', filename='gz-sim-joint-controller-system', name='gz::sim::systems::JointController')
        e(plugin, 'joint_name', name)
        e(plugin, 'topic', data['namespace']+'/drive/'+name+'/cmd_vel')
        e(plugin, 'use_force_commands', 'true')
        for key in ('p_gain', 'i_gain', 'd_gain', 'i_min', 'i_max', 'cmd_min', 'cmd_max'):
            e(plugin, key, gains[key])
    observer = e(model, 'plugin', filename='libUchuvaRobotTelemetrySystem.so', name='uchuva::RobotTelemetrySystem')
    e(observer, 'robot_spec_sha256', robot.sha256)
    e(observer, 'topic', data['namespace']+'/robot_telemetry')
    for row in data['joints']:
        if row['type'] != 'fixed':
            item = e(observer, 'joint', name=row['name'])
            e(item, 'effort_limit', row['limits']['effort'] if row['group'] != 'passive' else 0)


def _sensors(model, data, poses):
    frames = {f['name']: f for f in data['frames']}
    for row in data['sensors']:
        if not row['enabled']:
            continue
        kind = row['type']
        if kind not in ('camera', 'depth_camera', 'imu'):
            raise ValueError(f'{kind}: a complete scan/noise descriptor and validated SDF adapter are required')
        parent = row['frame']
        while parent in frames:
            parent = frames[parent]['parent']
        link = model.find(f"link[@name='{parent}']")
        if link is None:
            raise ValueError(f'Sensor {row["name"]} has no physical parent link')
        sensor = e(link, 'sensor', name=row['name'], type=kind)
        offset = compose_poses(inverse_pose(poses[parent]), poses[row['frame']])
        e(sensor, 'pose', numbers(pose_rpy(offset)))
        e(sensor, 'always_on', 'true')
        e(sensor, 'update_rate', row['update_rate_hz'])
        e(sensor, 'topic', data['namespace']+'/sensors/'+row['name'])
        if kind in ('camera', 'depth_camera'):
            camera = e(sensor, 'camera')
            e(camera, 'horizontal_fov', row['horizontal_fov_rad'])
            image = e(camera, 'image')
            e(image, 'width', row['width'])
            e(image, 'height', row['height'])
            e(image, 'format', 'R8G8B8')
            clip = e(camera, 'clip')
            e(clip, 'near', row['near_m'])
            e(clip, 'far', row['far_m'])
        else:
            e(sensor, 'imu')


def require_native_harvest_adapter(robot, task=None):
    """Fail before starting Gazebo if this integration cannot realize a profile."""
    robot.require_capability('native_force_drive')
    data = robot.to_dict()
    drive = data['control']['drive']
    names = set(drive['left_joints'] + drive['right_joints'])
    if set(drive.get('joints', {})) != names or set(drive.get('joint_signs', {})) != names:
        raise ValueError('Native harvest requires force-controller gains and joint signs for every drive motor')
    actuators = {a['joint']: a for a in data['actuators']}
    controls = {**data['control']['arm'], **drive['joints'], **data['control'].get('gripper', {})}
    for name, gains in controls.items():
        if name not in actuators or actuators[name].get('effort_reference') != 'joint_output':
            raise ValueError(f'{name}: native effort control requires a traced effective joint-output actuator')
        if max(abs(gains['cmd_min']), abs(gains['cmd_max'])) > actuators[name]['continuous_effort']:
            raise ValueError(f'{name}: command exceeds continuous effort; a validated peak-duration/duty-cycle model is required')
    demonstration = isinstance(task, dict) and 'demo_fixture' in task
    if not demonstration and any(j['group'] in ('passive', 'gripper') for j in data['joints']):
        raise ValueError('Native harvest for articulated gripper/suspension requires their motion and stability protocol')
    if not isinstance(task, dict) or task.get('tool_frame') != 'cut_point' or task.get('target_direction_source') != 'pedicel_axis':
        raise ValueError('Native resolved harvest requires cut_point and the morphological pedicel_axis direction')
    if type(task.get('cut_axis_bidirectional')) is not bool:
        raise ValueError('Native cut-axis symmetry must be an explicit cut_axis_bidirectional boolean')
    from .robot_validation import acceptance_config
    acceptance_config(task)
    if demonstration:
        from .harvest_basket import validated_demonstration
        validated_demonstration(robot, task)
    else:
        robot.require_capability('native_harvest')
