"""Canonical, immutable robot inputs. Pure standard library; no simulator imports.

SI values describe simulation inputs, not validation against a physical robot.
An incomplete CAD profile remains inspectable but cannot become ResolvedRobot.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType

VERSION = "robot-spec/1.0"
ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIRECTORY = ROOT / "configs/robots"
SCHEMA_PATH = PROFILE_DIRECTORY / "robot_spec.schema.json"
UPDATE_CLASSES = {"runtime", "model_regeneration", "cad_reexport"}
PROVENANCE_STATES = {"medido", "derivado_de_CAD", "ficha_tecnica", "estimado", "pendiente"}


def _thaw(value):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def canonical_hash(value):
    payload = json.dumps(_thaw(value), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _number(value, label, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label}: expected a finite number (not a boolean)")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError(f"{label}: invalid sign")
    return float(value)


def _vector(value, size, label):
    if not isinstance(value, (tuple, list)) or len(value) != size:
        raise ValueError(f"{label}: expected {size} entries")
    return [_number(item, label) for item in value]


def _schema_check(value, schema, document, path="$"):
    """Evaluate the deliberately small JSON Schema vocabulary shipped here."""
    if "$ref" in schema:
        target = document
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return _schema_check(value, target, document, path)
    expected = schema.get("type")
    matches = {"object": isinstance(value, dict), "array": isinstance(value, list),
               "string": isinstance(value, str), "number": type(value) in (int, float),
               "integer": type(value) is int, "boolean": type(value) is bool,
               "null": value is None}
    if expected and not any(matches.get(kind, False) for kind in ([expected] if isinstance(expected, str) else expected)):
        raise ValueError(f"{path}: expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path}: value outside enum")
    if isinstance(value, dict):
        missing = set(schema.get("required", ())) - value.keys()
        if missing:
            raise ValueError(f"{path}: missing fields {sorted(missing)}")
        props = schema.get("properties", {})
        for key, item in value.items():
            child = props.get(key, schema.get("additionalProperties", {}))
            if child is False:
                raise ValueError(f"{path}: unknown field {key}")
            if isinstance(child, dict):
                _schema_check(item, child, document, path + "/" + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            raise ValueError(f"{path}: invalid array length")
        for index, item in enumerate(value):
            _schema_check(item, schema.get("items", {}), document, f"{path}/{index}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or ("pattern" in schema and not re.search(schema["pattern"], value)):
            raise ValueError(f"{path}: invalid string")
    if type(value) in (float, int):
        _number(value, path)
        if value < schema.get("minimum", -math.inf) or value > schema.get("maximum", math.inf):
            raise ValueError(f"{path}: outside numeric bounds")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path}: must exceed {schema['exclusiveMinimum']}")


def _pointer(document, pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Parameter paths must be JSON pointers beginning with /")
    if re.search(r"~(?![01])", pointer):
        raise ValueError("Invalid JSON pointer escape")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    parent = document
    def key_for(container, part):
        if isinstance(container, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", part):
                raise ValueError("Array paths require nonnegative canonical indices")
            return int(part)
        return part
    try:
        for part in parts[:-1]:
            parent = parent[key_for(parent, part)]
        key = key_for(parent, parts[-1])
        return parent, key, parent[key]
    except (KeyError, IndexError, ValueError, TypeError) as error:
        raise ValueError(f"Unresolved parameter path: {pointer}") from error


def _evidence(item, label):
    if not isinstance(item, dict) or item.get("status") not in PROVENANCE_STATES:
        raise ValueError(f"{label}: provenance status is required")
    for key in ("source", "revision", "method"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError(f"{label}: missing provenance {key}")


def _pose(value, label):
    _vector(value["xyz_m"], 3, label)
    q = _vector(value["quaternion_xyzw"], 4, label)
    if abs(sum(v*v for v in q) - 1) > 1e-7:
        raise ValueError(f"{label}: quaternion must be unit length")


def _det3(a):
    return (a[0][0]*(a[1][1]*a[2][2]-a[1][2]*a[2][1])
            - a[0][1]*(a[1][0]*a[2][2]-a[1][2]*a[2][0])
            + a[0][2]*(a[1][0]*a[2][1]-a[1][1]*a[2][0]))


def _inertia(value, label):
    _number(value["mass_kg"], label, positive=True)
    _vector(value["com_m"], 3, label)
    xx, yy, zz, xy, xz, yz = _vector(value["tensor_kg_m2"], 6, label)
    matrix = [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]
    scale = max(abs(v) for row in matrix for v in row)
    if scale == 0:
        raise ValueError(f"{label}: inertia cannot vanish")
    a = [[v/scale for v in row] for row in matrix]
    if a[0][0] <= 0 or a[0][0]*a[1][1]-a[0][1]**2 <= 0 or _det3(a) <= 0:
        raise ValueError(f"{label}: inertia must be symmetric positive definite")
    # A realizable mass distribution also requires second-moment covariance
    # C=trace(I)/2*identity-I >= 0 (principal moments obey triangle inequalities).
    half_trace = sum(a[i][i] for i in range(3))/2
    c = [[(half_trace if i == j else 0)-a[i][j] for j in range(3)] for i in range(3)]
    minors = [c[i][i] for i in range(3)] + [c[i][i]*c[j][j]-c[i][j]**2 for i in range(3) for j in range(i+1, 3)] + [_det3(c)]
    if min(minors) < -1e-10:
        raise ValueError(f"{label}: inertia violates principal-moment triangle inequalities")


def _expression(value, parameters, depth=0):
    if depth > 12:
        raise ValueError("Derived expression exceeds bounded depth")
    if type(value) in (int, float):
        return _number(value, "expression")
    if not isinstance(value, dict):
        raise ValueError("Derived expression must be a number or explicit operation")
    if set(value) == {"parameter"}:
        if value["parameter"] not in parameters:
            raise ValueError("Unknown parameter in expression")
        return _number(parameters[value["parameter"]], "parameter")
    if set(value) != {"op", "args"} or value["op"] not in {"add", "mul", "div"}:
        raise ValueError("Unsupported derived expression; no executable expressions accepted")
    args = value["args"]
    if not isinstance(args, list) or not 2 <= len(args) <= 16 or value["op"] == "div" and len(args) != 2:
        raise ValueError("Invalid expression arguments")
    args = [_expression(arg, parameters, depth+1) for arg in args]
    if value["op"] == "div" and args[1] == 0:
        raise ValueError("Division by zero in expression")
    result = sum(args) if value["op"] == "add" else math.prod(args) if value["op"] == "mul" else args[0]/args[1]
    return _number(result, "derived value")


def _validate_closures(document, links, joints):
    """A native non-tree weld reunites a mass-partitioned physical body.

    Only the auxiliary enters the extra moving tree joint. No physical mass,
    visual or collision is duplicated, and the CAD reference must close before
    dynamics begins. Runtime residuals still need native observation.
    """
    closures = document.get('closures', [])
    if not closures:
        return
    from .robot_kinematics import compose_poses, pose_identity, axis_quaternion
    poses = {document['root_link']: pose_identity()}
    pending = list(joints.values())
    while pending:
        ready = [j for j in pending if j['parent'] in poses]
        if not ready:
            raise ValueError('Disconnected closure tree')
        for joint in ready:
            motion = pose_identity()
            if joint['type'] == 'revolute':
                motion['quaternion_xyzw'] = axis_quaternion(joint['axis'], joint['zero_offset'])
            elif joint['type'] == 'prismatic':
                motion['xyz_m'] = [v*joint['zero_offset'] for v in joint['axis']]
            poses[joint['child']] = compose_poses(compose_poses(compose_poses(
                poses[joint['parent']], joint['origin']), motion), joint['child_pose'])
            pending.remove(joint)
    names, auxiliaries, bodies = set(), set(), set()
    for row in closures:
        name, body, auxiliary = row['name'], row['body'], row['auxiliary']
        if name in names or auxiliary in auxiliaries or body in bodies:
            raise ValueError('Duplicate closure name/auxiliary/body; explicit unique partition required')
        names.add(name); auxiliaries.add(auxiliary); bodies.add(body)
        if body not in links or auxiliary not in links or body == auxiliary:
            raise ValueError('Closure refers to missing/identical links')
        joint = joints.get(row['moving_joint'])
        if joint is None or joint['child'] != auxiliary or joint['type'] == 'fixed':
            raise ValueError('Closure must preserve its named moving joint on the auxiliary')
        if links[auxiliary]['collisions'] or links[auxiliary]['visuals']:
            raise ValueError('Closure auxiliary must not duplicate geometry')
        fraction = row['mass_fraction']
        if not 0 < fraction < 1:
            raise ValueError('Closure mass fraction must lie strictly between zero and one')
        original = row['original_inertial']
        _inertia(original, name)
        for link_name, factor in ((body, 1-fraction), (auxiliary, fraction)):
            inertia = links[link_name]['inertial']
            if math.dist(inertia['com_m'], original['com_m']) > 1e-10:
                raise ValueError('Closure COM frames differ')
            expected = [original['mass_kg']*factor, *(v*factor for v in original['tensor_kg_m2'])]
            actual = [inertia['mass_kg'], *inertia['tensor_kg_m2']]
            if any(not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-13) for a,b in zip(actual, expected)):
                raise ValueError('Closure split does not conserve the original mass/tensor')
        a, b = poses[body], poses[auxiliary]
        if (math.dist(a['xyz_m'], b['xyz_m']) > 1e-8 or
            1-abs(sum(x*y for x,y in zip(a['quaternion_xyzw'],b['quaternion_xyzw']))) > 1e-10):
            raise ValueError('Closure does not coincide at the CAD reference pose')


def validate_robot_spec(document, *, require_complete=True):
    """Validate shape, references, physics, topology and provenance; no mutation."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _schema_check(document, schema, schema)
    if document["namespace"].endswith("/") or "//" in document["namespace"]:
        raise ValueError("Namespace cannot end with / or contain empty segments")
    _evidence(document["provenance"], "profile")
    if any("/parameters/"+name not in document["parameter_metadata"] for name in document["parameters"]):
        raise ValueError("Every canonical parameter requires provenance and update_class")
    for path, metadata in document["parameter_metadata"].items():
        _pointer(document, path)
        _evidence(metadata, path)
        if metadata.get("update_class") not in UPDATE_CLASSES:
            raise ValueError(f"{path}: explicit update_class required")
    if document["status"] != "complete":
        if not document.get("missing_evidence"):
            raise ValueError("Incomplete profile must identify missing evidence")
        if require_complete:
            raise ValueError("Incomplete robot profile: " + "; ".join(document["missing_evidence"]))
        return
    if document.get("missing_evidence"):
        raise ValueError("Complete profile cannot retain unresolved required evidence")
    links = {row["name"]: row for row in document["links"]}
    joints = {row["name"]: row for row in document["joints"]}
    frames = {row["name"]: row for row in document["frames"]}
    if any(len(rows) != len(document[key]) for rows, key in [(links, "links"), (joints, "joints"), (frames, "frames")]):
        raise ValueError("Duplicate link, joint or frame name")
    if document["root_link"] not in links or set(links) & set(frames):
        raise ValueError("Missing root link or ambiguous frame/link names")
    parents = {}
    for row in joints.values():
        name = row["name"]
        if row["parent"] not in links or row["child"] not in links or row["parent"] == row["child"]:
            raise ValueError(f"{name}: invalid parent/child")
        if row["child"] in parents or row["child"] == document["root_link"]:
            raise ValueError("Closed chains/multiple parents require a separately validated adapter")
        parents[row["child"]] = row["parent"]
        _pose(row["origin"], name)
        _pose(row["child_pose"], name)
        _number(row["zero_offset"], name)
        axis = _vector(row["axis"], 3, name)
        if row["type"] != "fixed":
            if abs(sum(v*v for v in axis)-1) > 1e-7:
                raise ValueError(f"{name}: joint axis must be unit length")
            limits = row["limits"]
            if limits["lower"] >= limits["upper"]:
                raise ValueError(f"{name}: inverted joint limits")
            _number(limits["velocity"], name, positive=True)
            _number(limits["effort"], name, positive=True)
        elif row["zero_offset"] != 0:
            raise ValueError("Fixed joint cannot apply an ignored zero_offset")
    if set(parents) != set(links)-{document["root_link"]}:
        raise ValueError("Every non-root link must belong to the joint tree")
    for name in links:
        seen = set()
        while name in parents:
            if name in seen:
                raise ValueError("Joint tree contains a cycle")
            seen.add(name)
            name = parents[name]
        if name != document["root_link"]:
            raise ValueError("Disconnected joint tree")
    for frame in frames.values():
        _pose(frame["pose"], frame["name"])
        name, seen = frame["name"], set()
        while name in frames:
            if name in seen:
                raise ValueError("Cyclic frame references")
            seen.add(name)
            name = frames[name]["parent"]
        if name not in links:
            raise ValueError("Frame refers to a nonexistent parent")
    for link in links.values():
        _inertia(link["inertial"], link["name"])
        for category in ("collisions", "visuals"):
            names = set()
            for shape in link[category]:
                if shape["name"] in names:
                    raise ValueError("Duplicate geometry name within link")
                names.add(shape["name"])
                _pose(shape["pose"], shape["name"])
                g = shape["geometry"]
                allowed = {"box": {"type", "size_m"}, "sphere": {"type", "radius_m"},
                           "cylinder": {"type", "radius_m", "length_m"},
                           "mesh": {"type", "uri", "sha256", "bound_parameters", "scale"}}
                if set(g)-allowed[g["type"]]:
                    raise ValueError("Geometry fields do not match the declared primitive")
                if g["type"] == "box":
                    if any(v <= 0 for v in _vector(g.get("size_m"), 3, "box")):
                        raise ValueError("Box dimensions must be positive")
                elif g["type"] in ("sphere", "cylinder"):
                    _number(g.get("radius_m"), "radius", positive=True)
                    if g["type"] == "cylinder":
                        _number(g.get("length_m"), "length", positive=True)
                elif g["type"] == "mesh":
                    if category == "collisions" and ('collision_meshes' not in document['capabilities'] or
                            document.get('physics', {}).get('backend') != 'DART'):
                        raise ValueError("Mesh collision requires the explicit DART mesh adapter capability")
                    uri = g.get("uri", "")
                    if not uri or Path(uri).is_absolute() or ":" in uri or "\\" in uri or ".." in Path(uri).parts:
                        raise ValueError("Mesh URI must stay relative to its asset root")
                    if not re.fullmatch(r"[a-f0-9]{64}", g.get("sha256", "")):
                        raise ValueError("Mesh requires source content SHA-256")
                    if "scale" in g and any(v != 1 for v in g["scale"]):
                        raise ValueError("Frozen SI CAD meshes require unit scale; reexport geometry instead")
                    bindings = g.get("bound_parameters", {})
                    if not bindings:
                        raise ValueError("Frozen mesh requires explicit bound_parameters")
                    for path, frozen in bindings.items():
                        if _pointer(document, path)[2] != frozen:
                            raise ValueError(f"Stale mesh {uri}: {path} changed; CAD reexport required")
    arm = {name for name, row in joints.items() if row["group"] == "arm" and row["type"] != "fixed"}
    if set(document["arm_home_positions"]) != arm:
        raise ValueError("Home positions must cover exactly the arm joints")
    for name, value in document["arm_home_positions"].items():
        if not joints[name]["limits"]["lower"] <= value <= joints[name]["limits"]["upper"]:
            raise ValueError("Home position exceeds joint limits")
    exclusions = set()
    _validate_closures(document, links, joints)
    if 'physics' in document:
        _number(document['physics']['maximum_step_s'], 'maximum physics step', positive=True)
    coupling_names, coupling_joints = set(), set()
    for row in document.get('gear_couplings', []):
        driver, follower = row['driver'], row['follower']
        if (row['name'] in coupling_names or driver == follower or
                {driver, follower} & coupling_joints or
                not {driver, follower} <= joints.keys()):
            raise ValueError('Gear couplings require unique known driver/follower joints')
        coupling_names.add(row['name'])
        coupling_joints.update((driver, follower))
        if any(joints[n]['type'] != 'revolute' for n in (driver, follower)):
            raise ValueError('Gear coupling currently supports revolute joints only')
        if joints[follower]['group'] != 'passive' or follower in document['control'].get('gripper', {}):
            raise ValueError('Gear follower must be passive with no actuator controller')
        if driver not in document['control'].get('gripper', {}):
            raise ValueError('Gear driver requires one explicit gripper controller')
        if abs(row['ratio']) < 1e-12:
            raise ValueError('Gear ratio cannot be zero')
        for key in ('stiffness_nm_rad', 'maximum_step_s'):
            _number(row[key], key, positive=True)
        _number(row['damping_nms_rad'], 'coupling damping', nonnegative=True)
        if document.get('physics', {}).get('maximum_step_s', row['maximum_step_s']) > row['maximum_step_s']:
            raise ValueError('Physics step exceeds the declared gear-coupling integration bound')
    if document["collision_policy"]["mode"] == "legacy_disjoint_link_masks" and "legacy_proxy" not in document["capabilities"]:
        raise ValueError("Legacy all-link contact suppression is restricted to the proxy adapter")
    for exclusion in document["collision_policy"]["excluded_pairs"]:
        pair = tuple(sorted(exclusion["links"]))
        if len(set(pair)) != 2 or not set(pair) <= set(links) or pair in exclusions:
            raise ValueError("Invalid or duplicate collision exclusion pair")
        if not exclusion["reason"].strip():
            raise ValueError("Collision exclusion requires a reason")
        exclusions.add(pair)
    actuator_names = set()
    actuator_joints = set()
    for actuator in document["actuators"]:
        if actuator["name"] in actuator_names or actuator["joint"] in actuator_joints:
            raise ValueError("Duplicate actuator name or joint assignment")
        actuator_names.add(actuator["name"])
        actuator_joints.add(actuator["joint"])
        if actuator["joint"] not in joints:
            raise ValueError("Actuator refers to unknown joint")
        if actuator["effort_reference"] != "joint_output":
            raise ValueError("Motor-shaft torque requires an explicit conversion to effective joint-output effort")
        _number(actuator["continuous_effort"], "continuous effort", positive=True)
        if actuator["peak_effort"] < actuator["continuous_effort"]:
            raise ValueError("Peak effort must not be below continuous effort")
        if joints[actuator["joint"]]["limits"]["effort"] > actuator["peak_effort"]:
            raise ValueError("Joint effort limit exceeds the actuator peak effort at its output")
        if not 0 < actuator["efficiency"] <= 1 or actuator["transmission_ratio"] <= 0:
            raise ValueError("Invalid transmission")
    for name, settings in document["control"]["arm"].items():
        if name not in arm:
            raise ValueError("Controller refers to unknown/non-arm joint")
        limit = joints[name]["limits"]
        if settings["cmd_min"] >= settings["cmd_max"] or max(abs(settings["cmd_min"]), abs(settings["cmd_max"])) > limit["effort"]:
            raise ValueError("Controller effort limits exceed joint capacity")
        if not 0 < settings["command_velocity"] <= limit["velocity"]:
            raise ValueError("Controller velocity exceeds joint capacity")
        if settings["i_min"] > settings["i_max"]:
            raise ValueError("Inverted integral limits")
        if settings.get("reference_mode") == "ramped_position" and not limit["lower"] <= 0 <= limit["upper"]:
            raise ValueError("Ramped controller initial zero is outside joint limits")
    if set(document["control"]["arm"]) != arm:
        raise ValueError("Every arm joint requires controller settings")
    drive = document["control"]["drive"]
    driven = drive["left_joints"] + drive["right_joints"]
    if len(driven) != len(set(driven)) or any(name not in joints or joints[name]["group"] != "drive" for name in driven):
        raise ValueError("Invalid drive joint mapping")
    signs = drive.get("joint_signs", {})
    if signs and (set(signs) != set(driven) or any(type(v) is not int or v not in (-1, 1) for v in signs.values())):
        raise ValueError("Drive signs must cover exactly the driven joints with integer +/-1")
    if "native_force_drive" in document["capabilities"] and set(drive.get("joints", {})) != set(driven):
        raise ValueError("Finite-force drive requires gains for every driven joint")
    feedback = drive.get('base_feedback')
    if feedback is not None:
        _number(feedback['p_gain'], 'Base yaw feedback gain', nonnegative=True)
        for key in ('window_s', 'max_observation_age_s'):
            _number(feedback[key], 'Base feedback '+key, positive=True)
        if feedback['enabled'] and ('native_force_drive' not in document['capabilities'] or not driven):
            raise ValueError('Native base feedback requires explicit finite-force wheel control')
        for key in feedback:
            if '/control/drive/base_feedback/'+key not in document['parameter_metadata']:
                raise ValueError('Every base feedback setting requires explicit provenance/update_class')
    for name, settings in drive.get("joints", {}).items():
        if name not in driven:
            raise ValueError("Drive gains refer to a non-drive joint")
        limit = joints[name]["limits"]
        if (settings["cmd_min"] >= settings["cmd_max"] or
                max(abs(settings["cmd_min"]), abs(settings["cmd_max"])) > limit["effort"] or
                settings["command_velocity"] > limit["velocity"]):
            raise ValueError("Drive controller exceeds the joint limits")
    for name, settings in document["control"].get("gripper", {}).items():
        if name not in joints or joints[name]["group"] != "gripper":
            raise ValueError("Gripper controller refers to a non-gripper joint")
        limit = joints[name]["limits"]
        if (settings["cmd_min"] >= settings["cmd_max"] or
                max(abs(settings["cmd_min"]), abs(settings["cmd_max"])) > limit["effort"] or
                settings["command_velocity"] > limit["velocity"]):
            raise ValueError("Gripper controller exceeds the joint limits")
        if settings.get("reference_mode") == "ramped_position" and not limit["lower"] <= 0 <= limit["upper"]:
            raise ValueError("Ramped controller initial zero is outside joint limits")
    sensor_names = set()
    for sensor in document["sensors"]:
        if sensor["name"] in sensor_names:
            raise ValueError("Duplicate sensor name")
        sensor_names.add(sensor["name"])
        if sensor["frame"] not in links and sensor["frame"] not in frames:
            raise ValueError("Sensor has an unresolved frame")
        if sensor["type"] in ("camera", "depth_camera"):
            if not {"width", "height", "horizontal_fov_rad", "near_m", "far_m"} <= sensor.keys():
                raise ValueError("Camera specification is incomplete")
            if not 0 < sensor["horizontal_fov_rad"] < math.pi or sensor["near_m"] >= sensor["far_m"]:
                raise ValueError("Invalid camera field of view or clipping range")


@dataclass(frozen=True)
class RobotSpec:
    """Immutable parsed input, which may still identify missing CAD evidence."""
    data: Mapping

    def __post_init__(self):
        document = _thaw(self.data)
        validate_robot_spec(document, require_complete=False)
        object.__setattr__(self, "data", _freeze(document))

    @classmethod
    def from_dict(cls, value):
        document = _thaw(value)
        validate_robot_spec(document, require_complete=False)
        return cls(_freeze(document))

    def to_dict(self):
        return _thaw(self.data)


@dataclass(frozen=True)
class ResolvedRobot:
    data: Mapping
    sha256: str

    def __post_init__(self):
        document = _thaw(self.data)
        validate_robot_spec(document)
        if canonical_hash(document) != self.sha256:
            raise ValueError("Resolved robot hash does not match its content")
        object.__setattr__(self, "data", _freeze(document))

    @property
    def profile_id(self):
        return self.data["profile_id"]

    @property
    def links(self):
        return self.data["links"]

    @property
    def joints(self):
        return self.data["joints"]

    @property
    def frames(self):
        return self.data["frames"]

    @property
    def joint_names(self):
        return tuple(row["name"] for row in self.joints if row["group"] == "arm" and row["type"] != "fixed")

    def to_dict(self):
        return _thaw(self.data)

    def require_capability(self, name):
        if name not in self.data["capabilities"]:
            raise ValueError(f"Robot profile {self.profile_id} lacks capability: {name}")


def resolve_robot_profile(reference, overrides=None):
    """Resolve a profile and audited JSON-pointer overrides; never edit inputs.

    Overrides are {pointer: {value: ..., provenance: {...}}}. A runtime update
    still requires a new resolved hash; this function does not mutate Gazebo.
    """
    if isinstance(reference, ResolvedRobot):
        document = reference.to_dict()
    elif isinstance(reference, RobotSpec):
        document = reference.to_dict()
    elif isinstance(reference, Mapping):
        document = _thaw(reference)
    else:
        path = Path(reference)
        if not path.exists() and path.name == str(reference):
            path = PROFILE_DIRECTORY / (str(reference).removesuffix(".json") + ".json")
        document = load_robot_json(path)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    _schema_check(document, schema, schema)
    history = document.setdefault("override_history", [])
    for path, change in (overrides or {}).items():
        metadata = document["parameter_metadata"].get(path)
        if metadata is None:
            raise ValueError(f"Override path lacks explicit provenance/update_class: {path}")
        if any(binding["path"] == path or binding["path"].startswith(path+"/") or path.startswith(binding["path"]+"/")
               for binding in document["derived_values"]):
            raise ValueError(f"Override {path} targets a derived value; change its canonical parameter instead")
        if not isinstance(change, Mapping) or set(change) != {"value", "provenance"}:
            raise ValueError("Each override requires value and provenance")
        _evidence(change["provenance"], path)
        parent, key, old = _pointer(document, path)
        if metadata["update_class"] == "cad_reexport" and old != change["value"]:
            raise ValueError(f"{path}: CAD reexport required; supply a new revision with matching assets")
        parent[key] = _thaw(change["value"])
        history.append({"path": path, "previous_value": old, "value": _thaw(change["value"]),
                        "provenance": _thaw(change["provenance"]), "update_class": metadata["update_class"]})
        document["parameter_metadata"][path] = {**_thaw(change["provenance"]), "update_class": metadata["update_class"]}
    seen = set()
    for binding in document["derived_values"]:
        path = binding["path"]
        if path in seen or path.startswith(("/parameters/", "/parameter_metadata/", "/derived_values/")):
            raise ValueError("Derived targets must be unique and cannot alter inputs or recipes")
        seen.add(path)
        parent, key, _ = _pointer(document, path)
        parent[key] = _expression(binding["expression"], document["parameters"])
    validate_robot_spec(document)
    return ResolvedRobot(_freeze(document), canonical_hash(document))


resolve_robot = resolve_robot_profile


def load_robot_json(path):
    """Strict JSON reader: duplicate fields and nonstandard numbers are errors."""
    def reject(value):
        raise ValueError(f"Non-finite JSON constant: {value}")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject, object_pairs_hook=pairs)


def verify_robot_assets(robot, asset_root):
    """Verify every visual/collision mesh inside an explicit local asset root.

    No downloads, scaling, CAD conversion or executable side effects occur.
    Returns the portable URI->content-hash mapping used for package admission.
    """
    root = Path(asset_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Robot asset root must be a directory")
    verified = {}
    for link in robot.links:
        for shape in (*link["visuals"], *link["collisions"]):
            geometry = shape["geometry"]
            if geometry["type"] != "mesh":
                continue
            path = (root/geometry["uri"]).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError("Robot mesh escapes its asset root or is not a file")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(chunk)
            actual = digest.hexdigest()
            if actual != geometry["sha256"]:
                raise ValueError(f"Robot mesh content differs from admitted SHA-256: {geometry['uri']}")
            verified[geometry["uri"]] = actual
    return verified
