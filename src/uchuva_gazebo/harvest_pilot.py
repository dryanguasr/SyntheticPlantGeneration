"""Compose a reproducible mechanics pilot without importing Blender, ROS or Gazebo.

Botanical architecture comes exclusively from harvest_plants / uchuva_lsystem.
The robot is a separate adapter; fruit identities and the native cut system do
not depend on its link lengths. Motion waypoints are engineering fixtures and
must still pass native contact / stability tests.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from .field import box, element as e, numbers
from .harvest_plants import build_harvest_plants
from .harvest_clearance import plan_harvest_motion
from .harvester_robot import (HarvesterConfig, generic_harvester_model,
                             inverse_kinematics, robot_contract, set_collision_bitmask)
from .harvest_validation import local_point
from .harvest_visuals import apply_soil_material, procedural_soil_assets

VERSION = "harvest-pilot/1.0"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "configs/harvest_pilot_v1.json"


def read_config(path=None):
    config = json.loads(Path(path or DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    if config.get("schema_version") != VERSION:
        raise ValueError(f"Expected configuration schema {VERSION}")
    return config


def _pose(x, y, z=0, yaw=0):
    return [x, y, z, 0, 0, math.sin(yaw / 2), math.cos(yaw / 2)]


def _video_observer(world, settings):
    """A collision-free experiment camera, never a claimed robot sensor."""
    required = {'pose', 'width', 'height', 'fps', 'horizontal_fov_rad', 'topic'}
    if set(settings) != required or len(settings['pose']) != 6 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in settings['pose']):
        raise ValueError('Invalid explicit native video observer configuration')
    if any(type(settings[k]) is not int or settings[k] <= 0 for k in ('width', 'height', 'fps')):
        raise ValueError('Native video resolution/rate must be positive integers')
    if not 0 < settings['horizontal_fov_rad'] < math.pi or not settings['topic'].startswith('/'):
        raise ValueError('Invalid video field of view or topic')
    model = e(world, 'model', name='harvest_video_observer')
    e(model, 'static', 'true')
    e(model, 'pose', numbers(settings['pose']))
    sensor = e(e(model, 'link', name='observer_link'), 'sensor', name='rgb', type='camera')
    e(sensor, 'always_on', 'true')
    e(sensor, 'update_rate', settings['fps'])
    e(sensor, 'topic', settings['topic'])
    camera = e(sensor, 'camera')
    e(camera, 'horizontal_fov', settings['horizontal_fov_rad'])
    image = e(camera, 'image')
    for key in ('width', 'height'):
        e(image, key, settings[key])
    e(image, 'format', 'R8G8B8')
    clip = e(camera, 'clip')
    e(clip, 'near', .03)
    e(clip, 'far', 50)


def _bin(world, center):
    x, y = center
    # Small open tray. Each size and pose is a heuristic, not a measured design.
    interior, thickness, floor, top = .32, .025, .045, .27
    model = e(world, "model", name="collection_bin")
    e(model, "static", "true")
    e(model, "pose", numbers((x, y, 0, 0, 0, 0)))
    link = e(model, "link", name="bin_link")
    color = (.095, .20, .28, 1)
    pieces = [("floor", (0, 0, floor - thickness / 2), (interior + 2 * thickness, interior + 2 * thickness, thickness))]
    for sign, label in ((-1, "negative"), (1, "positive")):
        offset = sign * (interior + thickness) / 2
        pieces.extend([(f"x_{label}", (offset, 0, (top + floor) / 2), (thickness, interior + 2 * thickness, top - floor)),
                       (f"y_{label}", (0, offset, (top + floor) / 2), (interior, thickness, top - floor))])
    for name, position, size in pieces:
        box(link, name, position, size, color)
        box(link, name + "_collision", position, size, collision=True)
    # Injection-moulded rim and feet remain within the existing collision
    # envelope: this is visual finish, not a larger or more permissive tray.
    for sign in (-1, 1):
        offset = sign * (interior + thickness) / 2
        for axis in ('x', 'y'):
            position = (offset, 0, top-.012) if axis == 'x' else (0, offset, top-.012)
            size = (thickness, interior+2*thickness, .024) if axis == 'x' else (interior, thickness, .024)
            box(link, f'rim_{axis}_{sign}', position, size, (.17, .30, .36, 1))
    return {"model_name": "collection_bin", "center_xy_m": list(center),
            "inner_min_m": [x - interior / 2, y - interior / 2, floor],
            "inner_max_m": [x + interior / 2, y + interior / 2, top],
            "parameter_status": "engineering_heuristic"}


def plan_targets(plant_bundle, config, robot_config):
    """Check every waypoint is within IK workspace before writing the package.

    Joint interpolation and Gazebo contacts still require native acceptance;
    an IK solution alone is never marked collision-free.
    """
    resolved = hasattr(robot_config, 'world_shapes')
    if resolved:
        carry = list(robot_config.task.get('carry_joints_rad',
            [robot_config.robot.data['arm_home_positions'][n] for n in robot_config.robot.joint_names]))
        carry_point = robot_config.fk(carry)['position_m']
    else:
        carry = list(inverse_kinematics(config["carry_tcp_base_m"], config=robot_config))
        carry_point = config['carry_tcp_base_m']
    fixture = robot_config.task.get('demo_fixture') if resolved else None
    if fixture:
        from .harvest_clearance import planned_crop_obstacles
        from .robot_harvest_planning import audited_drive_route, plan_resolved_harvest
        screened = plan_resolved_harvest(plant_bundle, robot_config,
            clearance_m=fixture['motion_clearance_m'], pickup_standoff_m=config['pickup_standoff_m'])
        plans = []
        aisle = config['aisle_x_m']
        initial = config['robot_start_xyzyaw']
        previous = [initial[0], initial[1], initial[3]]
        cylinders = planned_crop_obstacles(plant_bundle)
        fruits = plant_bundle['fruits'] + plant_bundle.get('static_fruit_obstacles', [])
        for identifier in config['plants']['target_ids']:
            row = screened['targets'][identifier]
            if not row['audit']['passed']:
                raise ValueError(f'No admitted CAD motion for {identifier}')
            x, y, _, yaw = row['pickup_base_pose']
            station = [x, y, yaw]
            outbound = [[aisle, previous[1], math.pi], [aisle, y, 0.], station]
            route = [[aisle, y, math.pi]]
            if abs(aisle-x) < .15:
                route.append([aisle, y+.20, 0.])
            audits = [audited_drive_route(s, waypoints, robot_config, cylinders, fruits, fixture['motion_clearance_m'])
                      for s, waypoints in ((previous, outbound), (station, route))]
            if not all(value['passed'] for value in audits):
                raise ValueError(f'No stowed base route for {identifier}: {audits}')
            plans.append({'id': identifier, 'pickup_base_xyyaw': [x, y, yaw],
                          'tool_waypoints_world_m': row['tcp_waypoints_world_m'],
                          'nominal_joints_rad': row['joint_waypoints'],
                          'withdrawal_sequence': [n for n in row['sequence'] if n.startswith('extraction_')],
                          'deposit_joints': row['deposit_joints'], 'sampled_clearance': row['audit'],
                          **({'deposit_sequence': row['deposit_sequence']} if 'deposit_sequence' in row else {}),
                          'base_route': outbound, 'after_deposit_route': route, 'base_route_audit': audits,
                          'cut_axis_world': row['cut_axis_world']})
            previous = station
        return {'targets': plans, 'carry_joints_rad': carry, 'carry_tcp_base_m': carry_point,
                'aisle_x_m': config['aisle_x_m'], 'sampled_motion_audit': screened['audit'],
                'target_source': 'native_camera_gate_and_privileged_simulation_cut_coordinates'}
    deposit_base = config["deposit_base_xyyaw"]
    release = [*config["bin_center_xy_m"], config["deposit_tool_height_m"]]
    deposit_pose = _pose(deposit_base[0], deposit_base[1], yaw=deposit_base[2])
    if resolved:
        deposit_pose[2] = robot_config.task['planning_base_height_m']
    deposit_joints = list(inverse_kinematics(local_point(release, deposit_pose), config=robot_config))
    screened = plan_harvest_motion(plant_bundle, robot_config,
                                  carry_tcp_base_m=config['carry_tcp_base_m'],
                                  pickup_standoff_m=config['pickup_standoff_m'])
    plans = []
    for fruit in plant_bundle['fruits']:
        target = screened['targets'][fruit['id']]
        base = target['pickup_base_pose']
        plans.append({"id": fruit["id"], "pickup_base_xyyaw": [base[0], base[1], base[3]],
                      "tool_waypoints_world_m": target['tcp_waypoints_world_m'],
                      "nominal_joints_rad": target['joint_waypoints'], "workspace_check": "passed",
                      "withdrawal_sequence": [name for name in target['sequence'] if name.startswith('extraction_')],
                      "sampled_clearance": target['audit'],
                      "collision_and_dynamic_validation": "pending_gazebo"})
        if 'cut_axis_world' in target:
            plans[-1]['cut_axis_world'] = target['cut_axis_world']
    return {"targets": plans, "carry_joints_rad": carry, "carry_tcp_base_m": carry_point,
            "deposit_base_xyyaw": deposit_base, "deposit_tool_world_m": release,
            "deposit_nominal_joints_rad": deposit_joints, "aisle_x_m": config["aisle_x_m"],
            "deposit_via_y_m": config["bin_center_xy_m"][1] - .8,
            "sampled_motion_audit": screened['audit'],
            "target_source": "privileged_simulation_truth_for_mechanics_only",
            "motion_type": "bounded_joint_commands_and_physical_wheel_drive_no_pose_teleportation"}


def _bridge_yaml(contract, interaction, world_name):
    """Optional Jazzy ros_gz bridge; the native pilot does not require ROS."""
    entries = [('/clock', '/clock', 'rosgraph_msgs/msg/Clock', 'gz.msgs.Clock', 'GZ_TO_ROS'),
               (contract['topics']['cmd_vel'], contract['topics']['cmd_vel'], 'geometry_msgs/msg/Twist', 'gz.msgs.Twist', 'ROS_TO_GZ'),
               (contract['topics']['odometry'], contract['topics']['odometry'], 'nav_msgs/msg/Odometry', 'gz.msgs.Odometry', 'GZ_TO_ROS'),
               (contract['topics']['joint_states'], contract['topics']['joint_states'], 'sensor_msgs/msg/JointState', 'gz.msgs.Model', 'GZ_TO_ROS')]
    if 'robot_spec_sha256' in contract:
        entries = [entries[0], entries[-1]]
        namespace = contract['topics']['cmd_vel'].removesuffix('/cmd_vel')
        for name in contract['drive'].get('joints', {}):
            topic = namespace+'/drive/'+name+'/cmd_vel'
            entries.append((topic, topic, 'std_msgs/msg/Float64', 'gz.msgs.Double', 'ROS_TO_GZ'))
    for name in contract['arm_joint_names']:
        topic = contract['topics']['joint_commands'][name]
        entries.append((topic, topic, 'std_msgs/msg/Float64', 'gz.msgs.Double', 'ROS_TO_GZ'))
    for key, direction in (('command_topic', 'ROS_TO_GZ'), ('state_topic', 'GZ_TO_ROS'), ('event_topic', 'GZ_TO_ROS')):
        entries.append((interaction[key], interaction[key], 'std_msgs/msg/String', 'gz.msgs.StringMsg', direction))
    return '\n'.join('\n'.join((f'- ros_topic_name: "{ros}"', f'  gz_topic_name: "{gz}"',
                                f'  ros_type_name: "{rt}"', f'  gz_type_name: "{gt}"', f'  direction: {direction}'))
                     for ros, gz, rt, gt, direction in entries) + '\n'


def _jaw_guard(parent, specification):
    guard = e(parent, 'jaw_guard')
    for tag, key in (('joint_name', 'joint'), ('open_position', 'open_position_m'),
                     ('closed_position', 'closed_position_m'), ('position_tolerance', 'position_tolerance_m'),
                     ('max_speed', 'maximum_speed_m_s'), ('stable_time', 'stable_time_s')):
        e(guard, tag, specification[key])
    e(guard, 'joint_type', 'prismatic')
    return guard


def build_pilot(config):
    """Return SDF + deterministic serializable inputs; no native success claim."""
    c = deepcopy(config)
    if c.get('schema_version') != VERSION or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', c.get('world_name', '')):
        raise ValueError('Invalid pilot schema or world name')
    resolved_robot = None
    fixture = None
    robot_assets, robot_asset_hashes = {}, {}
    if 'robot_profile' in c:
        from .robot_spec import resolve_robot_profile
        from .robot_motion import ResolvedMotionConfig
        from .robot_sdf import resolved_robot_contract, require_native_harvest_adapter
        from .harvest_basket import validated_demonstration
        if c.get('robot'):
            raise ValueError('Use robot_overrides for a resolved profile; legacy robot fields cannot be mixed with it')
        resolved_robot = resolve_robot_profile(c['robot_profile'], c.get('robot_overrides'))
        if 'demo_fixture' in c.get('robot_task', {}):
            require_native_harvest_adapter(resolved_robot, c['robot_task'])
            fixture = validated_demonstration(resolved_robot, c['robot_task'])
        robot_config = ResolvedMotionConfig(resolved_robot, c.get('robot_task'), asset_root=c.get('robot_asset_root'))
        contract = resolved_robot_contract(resolved_robot)
        mesh_uris = [v['geometry']['uri'] for link in resolved_robot.links
                     for v in (*link['visuals'], *link['collisions']) if v['geometry']['type'] == 'mesh']
        if mesh_uris:
            from .robot_spec import verify_robot_assets
            if not c.get('robot_asset_root'):
                raise ValueError('Robot CAD meshes require an explicit robot_asset_root')
            asset_root = Path(c['robot_asset_root']).resolve()
            robot_asset_hashes = verify_robot_assets(resolved_robot, asset_root)
            robot_assets = {uri: str(asset_root / uri) for uri in mesh_uris}
    else:
        robot_config = HarvesterConfig(**c['robot'])
        contract = robot_contract(robot_config)
    if resolved_robot is None and c['pickup_standoff_m'] <= .35:
        raise ValueError('Pickup standoff must clear the proxy chassis')
    if not all(math.isfinite(float(v)) for key in ('robot_start_xyzyaw', 'carry_tcp_base_m',
                                                  'bin_center_xy_m', 'deposit_base_xyyaw') for v in c[key]):
        raise ValueError('Non-finite scene parameters')
    plants = build_harvest_plants(c['plants'])
    crop_policy = None
    if resolved_robot is not None:
        from .robot_crop_collision_policy import scene_crop_collision_policy
        crop_policy = scene_crop_collision_policy(resolved_robot, c['robot_task'],
            [row['model_name'] for row in (*plants['plants'], *plants['fruits'])])
    if fixture:
        for fruit in plants['fruits']:
            if 'collision_geometry' in fruit:
                geometry = fruit['collision_geometry']
                robot_config.mesh_repository.register_generated_obj(geometry, plants['meshes'][geometry['uri']])
    plan = plan_targets(plants, c, robot_config)
    root = ET.Element('sdf', version='1.9')
    world = e(root, 'world', name=c['world_name'])
    e(world, 'gravity', '0 0 -9.81')
    physics = e(world, 'physics', name='default_physics', type='ignored')
    physics_spec = resolved_robot.to_dict().get('physics', {}) if resolved_robot else {}
    e(physics, 'max_step_size', physics_spec.get('maximum_step_s', .001))
    if physics_spec:
        dart = e(physics, 'dart')
        e(e(dart, 'solver'), 'solver_type', physics_spec['solver_type'])
        e(dart, 'collision_detector', physics_spec.get('collision_detector', 'ode'))
    e(physics, 'real_time_factor', 1)
    for filename, name in (('physics', 'Physics'), ('user-commands', 'UserCommands'), ('scene-broadcaster', 'SceneBroadcaster')):
        e(world, 'plugin', filename=f'gz-sim-{filename}-system', name=f'gz::sim::systems::{name}')
    camera_enabled = (any(s['enabled'] and s['type'] in ('camera', 'depth_camera', 'lidar') for s in resolved_robot.data['sensors']) if resolved_robot else robot_config.camera)
    if camera_enabled or c.get('video_observer'):
        sensors = e(world, 'plugin', filename='gz-sim-sensors-system', name='gz::sim::systems::Sensors')
        e(sensors, 'render_engine', 'ogre2')
    if c.get('video_observer'):
        _video_observer(world, c['video_observer'])
    if resolved_robot and any(s['enabled'] and s['type'] == 'imu' for s in resolved_robot.data['sensors']):
        e(world, 'plugin', filename='gz-sim-imu-system', name='gz::sim::systems::Imu')
    scene = e(world, 'scene')
    e(scene, 'ambient', '.38 .40 .42 1')
    e(scene, 'background', '.63 .72 .77 1')
    e(scene, 'shadows', 'true')
    e(scene, 'grid', 'false')
    light = e(world, 'light', name='sun', type='directional')
    e(light, 'pose', '0 0 10 0 0 0')
    e(light, 'diffuse', '.95 .91 .82 1')
    e(light, 'specular', '.2 .2 .2 1')
    e(light, 'direction', '-.4 .2 -1')
    e(light, 'cast_shadows', 'true')
    ground = e(world, 'model', name='ground')
    e(ground, 'static', 'true')
    link = e(ground, 'link', name='ground_link')
    soil_assets = procedural_soil_assets()
    floor = e(link, 'visual', name='ground_visual')
    e(e(e(floor, 'geometry'), 'mesh'), 'uri', 'meshes/harvest_soil.obj')
    apply_soil_material(floor)
    box(link, 'ground_collision', (0, 2, -.05), (16, 16, .1), collision=True)
    for model in plants['models']:
        world.append(model)
    if resolved_robot is None:
        world.append(generic_harvester_model(robot_config, start=c['robot_start_xyzyaw']))
    else:
        from .robot_sdf import resolved_robot_model
        robot_model = resolved_robot_model(resolved_robot, start=c['robot_start_xyzyaw'])
        if crop_policy:
            from .robot_crop_collision_policy import apply_robot_crop_collision_masks
            apply_robot_crop_collision_masks(robot_model, crop_policy)
        world.append(robot_model)
    bin_spec = fixture['bin'] if fixture else _bin(world, c['bin_center_xy_m'])
    observers = {}
    if fixture:
        from .harvest_perception import add_instance_observer
        for plant, camera in fixture['camera_by_plant'].items():
            if any(fruit['plant_id'] == plant for fruit in plants['fruits']):
                observers[plant] = add_instance_observer(world, name=f'view_{plant}', pose=camera,
                    targets=plants['fruits'], width=960, height=540, horizontal_fov_rad=1.0, fps=4)
    # Robot links use disjoint masks to suppress proxy self-collision. All
    # external bodies expose all 16 bits, including fruit-fruit contacts after
    # successive attachments to the same tool skeleton in DART.
    for model in world.findall('model'):
        if model.get('name') != contract['model_name']:
            mask = (crop_policy['crop_mask'] if crop_policy and
                    model.get('name') in crop_policy['crop_model_names'] else 0xFFFF)
            set_collision_bitmask(model, mask)
    if crop_policy:
        from .robot_crop_collision_policy import verify_scene_crop_collision_masks
        verify_scene_crop_collision_masks(world, contract['model_name'], crop_policy)
    interaction = e(world, 'plugin', filename='UchuvaHarvestSystem', name='uchuva::HarvestSystem')
    e(interaction, 'robot_model', contract['model_name'])
    e(interaction, 'tool_link', contract['tool_link'])
    for name, pose in contract.get('tool_frame_poses', {}).items():
        e(interaction, name, numbers(pose))
    for key, value in c['interaction'].items():
        e(interaction, key, value)
    if fixture:
        _jaw_guard(interaction, fixture['gripper'])
    if resolved_robot:
        task = c['robot_task']
        e(interaction, 'tool_cut_axis', numbers(task['tool_axis']))
        e(interaction, 'cut_axis_tolerance', task['orientation_tolerance_rad'])
        e(interaction, 'cut_axis_bidirectional', 'true' if task.get('cut_axis_bidirectional', False) else 'false')
        directions = {target['id']: target['cut_axis_world'] for target in plan['targets']}
    for fruit in plants['fruits']:
        entry = e(interaction, 'fruit', id=fruit['id'])
        for key in ('model', 'link', 'parent_model', 'parent_link'):
            e(entry, key, fruit[key])
        e(entry, 'cut_point', numbers(fruit['cut_point_local_m']))
        if resolved_robot:
            e(entry, 'cut_axis', numbers(directions[fruit['id']]))
    ET.indent(root, space='  ')
    reports = []
    morphologies = {}
    source_assets = {}
    source_asset_hashes = {}
    for plant in plants['plants']:
        report = dict(plant)
        morphologies[f'morphologies/{plant["id"]}.json'] = report.pop('source_morphology')
        if 'source_catalog' in report:
            catalog = report['source_catalog']
            for key, filename in (('morphology_file', 'plant.json'), ('proxy_catalog_file', 'proxy_catalog.json')):
                uri = f'sources/{plant["id"]}/{filename}'
                source_assets[uri] = catalog[key]
                source_asset_hashes[uri] = catalog['morphology_sha256' if key == 'morphology_file' else 'proxy_catalog_sha256']
                # Preserve the original location as provenance, while exposing
                # a portable byte-identical input in the prepared package.
                catalog[key + '_packaged'] = uri
        reports.append(report)
    manifest = {
        'schema_version': VERSION, 'world_name': c['world_name'], 'world_file': 'harvest.sdf',
        'fruits': plants['fruits'], 'plants': reports, 'robot': contract,
        'robot_config': resolved_robot.to_dict() if resolved_robot else asdict(robot_config),
        'bin': bin_spec, 'mission': plan, 'interaction': c['interaction'], 'plant_provenance': plants['provenance'],
        'validation': {'pure_export': 'checked_during_preparation', 'sdf_native': 'pending_gazebo',
                       'plugin_compilation': 'pending_gazebo', 'physical_harvest': 'pending_gazebo'},
        'limitations': plants['provenance']['limitations'] + [
            'Five arm axes plus four wheel motors; the cutting/retention actuator is an ideal logical mechanism.',
            'Cutter guard is a spherical neighbourhood of the morphological pedicel point, not blade collision/fracture.',
            'Kinematic waypoints are not a general obstacle-avoiding planner.',
            'A successful pure test is not a Gazebo physics or visual validation.',
            'Reset requires restarting Gazebo with a fresh world; in-process reset fails closed.',
        ],
    }
    if resolved_robot is not None:
        manifest['robot_spec_sha256'] = resolved_robot.sha256
        manifest['robot_task'] = c['robot_task']
        manifest['robot_effective_file'] = 'robot_effective.json'
        manifest['robot_model_source'] = 'resolved_robot_graph'
        plan['robot_spec_sha256'] = resolved_robot.sha256
        manifest['robot_assets_sha256'] = robot_asset_hashes
        manifest['limitations'][0] = 'Resolved robot topology; cutting/retention still uses an ideal logical attachment and is not a validated physical gripper.'
    if c.get('video_observer'):
        manifest['video_observer'] = c['video_observer']
    if fixture:
        manifest['perception_observers'] = observers
        if crop_policy:
            manifest['crop_collision_policy'] = crop_policy
            if crop_policy.get('wrist_housing_extension'):
                manifest['limitations'].append('User-authorized video approximation: eight hash-verified finger/blade/pad shapes, including CAD Mordaza blanda parts 111/112, and eleven wrist/housing shapes omit crop contacts in both planning and native physics. The rest of the arm, ground, basket, internal mask pairs and all other crop contacts retain their existing policy. This is not physical gripper/cutting validation.')
            else:
                manifest['limitations'].append('User-authorized video approximation: only the six hash-verified CAD finger, blade and pad shapes omit crop contacts in both planning and native physics. Supports 111/112, wrist, housing, ground, basket, internal mask pairs and all other crop contacts retain their existing policy. This is not physical gripper/cutting validation.')
        if c['plants'].get('ideal_cut_segment_m'):
            manifest['limitations'].append('The designated terminal pedicel span is a virtual cutting zone. Only the named blades and pads may enter it during the matching pickup. The retained plant support remains a native collider.')
    occupied = set(plants['meshes']) | set(soil_assets['meshes']) | set(plants.get('texture_assets', {})) | set(source_assets) | set(soil_assets['generated_binary_assets'])
    if occupied.intersection(robot_assets):
        raise ValueError('Robot asset URI collides with a plant/scene asset')
    return {'sdf': ET.tostring(root, encoding='unicode', xml_declaration=True), 'manifest': manifest,
            'meshes': {**plants['meshes'], **soil_assets['meshes']}, 'morphologies': morphologies, 'configuration': c,
            'binary_assets': {**plants.get('texture_assets', {}), **source_assets, **robot_assets},
            'source_asset_hashes': {**source_asset_hashes, **robot_asset_hashes},
            'generated_binary_assets': soil_assets['generated_binary_assets'],
            'bridge': _bridge_yaml(contract, c['interaction'], c['world_name'])}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_package(output, config, source_metadata=None):
    """Create a fresh bundle; never overwrite a previous run's inputs."""
    bundle = build_pilot(config)
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    assets = {'harvest.sdf': bundle['sdf'], 'ros_gz_bridge.yaml': bundle['bridge'], **bundle['meshes']}
    json_assets = {'configuration.json': bundle['configuration'], 'robot_contract.json': bundle['manifest']['robot'],
                   'selection_report.json': bundle['manifest']['plants'], **bundle['morphologies']}
    if 'robot_spec_sha256' in bundle['manifest']:
        json_assets['robot_effective.json'] = bundle['manifest']['robot_config']
    assets.update({name: json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
                   for name, data in json_assets.items()})
    for name, content in assets.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
    binary_assets = bundle.get('binary_assets', {})
    for name, source in binary_assets.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or name in assets:
            raise ValueError(f'Invalid or duplicate binary asset destination: {name}')
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
        expected = bundle.get('source_asset_hashes', {}).get(name)
        if expected is not None and sha256_file(path) != expected:
            raise ValueError(f'Source changed after morphology interpretation: {name}')
    generated_binary_assets = bundle.get('generated_binary_assets', {})
    for name, content in generated_binary_assets.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or name in assets or name in binary_assets:
            raise ValueError(f'Invalid or duplicate generated asset destination: {name}')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = bundle['manifest']
    manifest['files_sha256'] = {name: sha256_file(directory / name) for name in sorted(set(assets) | set(binary_assets) | set(generated_binary_assets))}
    manifest['source'] = source_metadata or {'status': 'unspecified'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return manifest


def load_verified_package(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != VERSION:
        raise ValueError('Unsupported harvest manifest')
    if not manifest.get('files_sha256'):
        raise ValueError('Missing bundle checksums')
    for name, expected in manifest['files_sha256'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f'Prepared asset missing, escaped or changed: {name}')
    if manifest['world_file'] not in manifest['files_sha256']:
        raise ValueError('World file is not covered by checksums')
    if 'robot_spec_sha256' in manifest:
        from .robot_spec import resolve_robot_profile, verify_robot_assets
        from .robot_sdf import resolved_robot_contract, resolved_robot_model
        effective_name = manifest.get('robot_effective_file')
        if effective_name != 'robot_effective.json' or effective_name not in manifest['files_sha256']:
            raise ValueError('Resolved robot effective configuration is not covered by package checksums')
        effective = json.loads((directory / effective_name).read_text(encoding='utf-8'))
        robot = resolve_robot_profile(effective)
        if robot.sha256 != manifest['robot_spec_sha256'] or effective != robot.to_dict() or effective != manifest['robot_config']:
            raise ValueError('Resolved robot configuration/hash differs from the manifest')
        admitted_assets = verify_robot_assets(robot, directory)
        if admitted_assets != manifest.get('robot_assets_sha256') or any(manifest['files_sha256'].get(uri) != digest for uri, digest in admitted_assets.items()):
            raise ValueError('Robot assets do not match effective robot geometry/package checksums')
        if manifest['robot'] != resolved_robot_contract(robot) or manifest['mission'].get('robot_spec_sha256') != robot.sha256:
            raise ValueError('Robot contract or planned motion refers to a different robot')
        if json.loads((directory / 'robot_contract.json').read_text(encoding='utf-8')) != manifest['robot']:
            raise ValueError('Packaged robot contract differs from the manifest')
        # Hashes bind bytes; regenerating and comparing binds those bytes to
        # their declared robot semantics, including inertias and controllers.
        world = ET.parse(directory / manifest['world_file']).getroot().find('world')
        physics_spec = robot.to_dict().get('physics')
        if physics_spec:
            if (float(world.findtext('physics/max_step_size', 'nan')) != physics_spec['maximum_step_s'] or
                    world.findtext('physics/dart/solver/solver_type') != physics_spec['solver_type'] or
                    world.findtext('physics/dart/collision_detector', 'ode') != physics_spec.get('collision_detector', 'ode')):
                raise ValueError('SDF physics differs from the resolved robot integration requirements')
        actual = world.find(f"model[@name='{manifest['robot']['model_name']}']")
        settings = json.loads((directory / 'configuration.json').read_text(encoding='utf-8'))
        if settings.get('robot_task') != manifest['robot_task']:
            raise ValueError('Task constraints differ between effective mission and frozen configuration')
        expected = resolved_robot_model(robot, start=settings['robot_start_xyzyaw'])
        from .robot_crop_collision_policy import (scene_crop_collision_policy,
            apply_robot_crop_collision_masks, verify_scene_crop_collision_masks)
        crop_policy = scene_crop_collision_policy(robot, settings['robot_task'],
            [row['model_name'] for row in (*manifest['plants'], *manifest['fruits'])])
        if manifest.get('crop_collision_policy') != crop_policy:
            raise ValueError('Crop-contact policy differs from the frozen robot/task/plant inventory')
        if crop_policy:
            apply_robot_crop_collision_masks(expected, crop_policy)
            verify_scene_crop_collision_masks(world, robot.data['model_name'], crop_policy)
        def canonical(node):
            return (node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(), tuple(canonical(child) for child in node))
        if actual is None or canonical(actual) != canonical(expected):
            raise ValueError('SDF robot differs from the effective resolved robot description')
        interaction = world.find("plugin[@name='uchuva::HarvestSystem']")
        if interaction is None or interaction.findtext('tool_link') != manifest['robot']['tool_link'] or interaction.findtext('robot_model') != robot.data['model_name']:
            raise ValueError('Harvest plugin refers to a different physical robot/tool link')
        for name, pose in manifest['robot']['tool_frame_poses'].items():
            if interaction.findtext(name) != numbers(pose):
                raise ValueError(f'Harvest plugin has a different interaction frame: {name}')
        task = manifest['robot_task']
        if (interaction.findtext('tool_cut_axis') != numbers(task['tool_axis']) or
                float(interaction.findtext('cut_axis_tolerance')) != task['orientation_tolerance_rad'] or
                interaction.findtext('cut_axis_bidirectional') != ('true' if task.get('cut_axis_bidirectional', False) else 'false')):
            raise ValueError('Harvest plugin orientation guard differs from frozen task constraints')
        target_axes = {t['id']: numbers(t['cut_axis_world']) for t in manifest['mission']['targets']}
        if {f.get('id'): f.findtext('cut_axis') for f in interaction.findall('fruit')} != target_axes:
            raise ValueError('Harvest plugin fruit axes differ from the frozen mission')
        if 'demo_fixture' in task:
            from .harvest_basket import validated_demonstration
            from .harvest_perception import add_instance_observer
            fixture = validated_demonstration(robot, task)
            guard = interaction.find('jaw_guard')
            expected_guard = _jaw_guard(ET.Element('guard'), fixture['gripper'])
            if guard is None or canonical(guard) != canonical(expected_guard) or manifest['bin'] != fixture['bin']:
                raise ValueError('Native jaw guard or basket differs from the resolved demonstration')
            camera_world = ET.Element('world')
            for fruit in manifest['fruits']:
                e(camera_world, 'model', name=fruit['model_name'])
            cameras = {plant: add_instance_observer(camera_world, name=f'view_{plant}', pose=pose,
                       targets=manifest['fruits'], width=960, height=540, horizontal_fov_rad=1.0, fps=4)
                       for plant, pose in fixture['camera_by_plant'].items()
                       if any(f['plant_id'] == plant for f in manifest['fruits'])}
            if cameras != manifest['perception_observers']:
                raise ValueError('Camera contract differs from the frozen CAD demonstration')
            for reference in camera_world.findall('model'):
                name = reference.get('name')
                actual_model = world.find(f"model[@name='{name}']")
                if actual_model is None:
                    raise ValueError('Missing target or observation camera in the native scene')
                if name.startswith('view_'):
                    matches = canonical(reference) == canonical(actual_model)
                else:
                    matches = [canonical(p) for p in reference.findall('plugin')] == [canonical(p) for p in actual_model.findall('plugin')]
                if not matches:
                    raise ValueError('Native cameras or target labels disagree with their contract')
            for fruit in manifest['fruits']:
                geom = fruit.get('collision_geometry')
                if geom:
                    model = world.find(f"model[@name='{fruit['model_name']}']")
                    uri = model.findtext("link/collision[@name='harvest_collision']/geometry/mesh/uri")
                    if uri != geom['uri'] or manifest['files_sha256'].get(uri) != geom['sha256']:
                        raise ValueError('Native fruit collider differs from the audited V8 mesh')
    return manifest
