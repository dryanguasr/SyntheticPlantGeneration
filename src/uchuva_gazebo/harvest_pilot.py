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
    carry = list(inverse_kinematics(config["carry_tcp_base_m"], config=robot_config))
    deposit_base = config["deposit_base_xyyaw"]
    release = [*config["bin_center_xy_m"], config["deposit_tool_height_m"]]
    deposit_pose = _pose(deposit_base[0], deposit_base[1], yaw=deposit_base[2])
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
    return {"targets": plans, "carry_joints_rad": carry, "carry_tcp_base_m": config["carry_tcp_base_m"],
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
    for name in contract['arm_joint_names']:
        topic = contract['topics']['joint_commands'][name]
        entries.append((topic, topic, 'std_msgs/msg/Float64', 'gz.msgs.Double', 'ROS_TO_GZ'))
    for key, direction in (('command_topic', 'ROS_TO_GZ'), ('state_topic', 'GZ_TO_ROS'), ('event_topic', 'GZ_TO_ROS')):
        entries.append((interaction[key], interaction[key], 'std_msgs/msg/String', 'gz.msgs.StringMsg', direction))
    return '\n'.join('\n'.join((f'- ros_topic_name: "{ros}"', f'  gz_topic_name: "{gz}"',
                                f'  ros_type_name: "{rt}"', f'  gz_type_name: "{gt}"', f'  direction: {direction}'))
                     for ros, gz, rt, gt, direction in entries) + '\n'


def build_pilot(config):
    """Return SDF + deterministic serializable inputs; no native success claim."""
    c = deepcopy(config)
    if c.get('schema_version') != VERSION or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', c.get('world_name', '')):
        raise ValueError('Invalid pilot schema or world name')
    robot_config = HarvesterConfig(**c['robot'])
    if c['pickup_standoff_m'] <= .35:
        raise ValueError('Pickup standoff must clear the proxy chassis')
    if not all(math.isfinite(float(v)) for key in ('robot_start_xyzyaw', 'carry_tcp_base_m',
                                                  'bin_center_xy_m', 'deposit_base_xyyaw') for v in c[key]):
        raise ValueError('Non-finite scene parameters')
    plants = build_harvest_plants(c['plants'])
    contract = robot_contract(robot_config)
    plan = plan_targets(plants, c, robot_config)
    root = ET.Element('sdf', version='1.9')
    world = e(root, 'world', name=c['world_name'])
    e(world, 'gravity', '0 0 -9.81')
    physics = e(world, 'physics', name='default_physics', type='ignored')
    e(physics, 'max_step_size', .001)
    e(physics, 'real_time_factor', 1)
    for filename, name in (('physics', 'Physics'), ('user-commands', 'UserCommands'), ('scene-broadcaster', 'SceneBroadcaster')):
        e(world, 'plugin', filename=f'gz-sim-{filename}-system', name=f'gz::sim::systems::{name}')
    if robot_config.camera:
        sensors = e(world, 'plugin', filename='gz-sim-sensors-system', name='gz::sim::systems::Sensors')
        e(sensors, 'render_engine', 'ogre2')
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
    world.append(generic_harvester_model(robot_config, start=c['robot_start_xyzyaw']))
    bin_spec = _bin(world, c['bin_center_xy_m'])
    # Robot links use disjoint masks to suppress proxy self-collision. All
    # external bodies expose all 16 bits, including fruit-fruit contacts after
    # successive attachments to the same tool skeleton in DART.
    for model in world.findall('model'):
        if model.get('name') != contract['model_name']:
            set_collision_bitmask(model, 0xFFFF)
    interaction = e(world, 'plugin', filename='UchuvaHarvestSystem', name='uchuva::HarvestSystem')
    e(interaction, 'robot_model', contract['model_name'])
    e(interaction, 'tool_link', contract['tool_link'])
    for key, value in c['interaction'].items():
        e(interaction, key, value)
    for fruit in plants['fruits']:
        entry = e(interaction, 'fruit', id=fruit['id'])
        for key in ('model', 'link', 'parent_model', 'parent_link'):
            e(entry, key, fruit[key])
        e(entry, 'cut_point', numbers(fruit['cut_point_local_m']))
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
        'fruits': plants['fruits'], 'plants': reports, 'robot': contract, 'robot_config': asdict(robot_config),
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
    return {'sdf': ET.tostring(root, encoding='unicode', xml_declaration=True), 'manifest': manifest,
            'meshes': {**plants['meshes'], **soil_assets['meshes']}, 'morphologies': morphologies, 'configuration': c,
            'binary_assets': {**plants.get('texture_assets', {}), **source_assets},
            'source_asset_hashes': source_asset_hashes,
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
    assets.update({name: json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
                   for name, data in json_assets.items()})
    for name, content in assets.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
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
    return manifest
