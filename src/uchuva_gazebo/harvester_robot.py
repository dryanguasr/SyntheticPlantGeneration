"""Replaceable 4WD / five-axis proxy harvester, in SI units, without runtime imports.

All dimensions, masses, gains and limits are ``engineering_heuristic``. This is
an integration fixture, not the final machine or a calibrated arm. Its tool
jaws are visual-only: the harvest runtime provides an explicitly ideal latch.
The five joints belong to the arm; wheel motors are additional actuators.
Robot self-contact is deliberately filtered link-by-link. Model self_collide
remains enabled so attached/released fruit do not inherit its suppression.

Gazebo Harmonic references (gz-sim8):
https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1DiffDrive.html
https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointPositionController.html
https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointStatePublisher.html
https://gazebosim.org/api/sim/8/detachablejoints.html
https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/EntityManagementFeatures.cc
https://github.com/gazebosim/gz-physics/blob/gz-physics7/dartsim/src/SDFFeatures.cc
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Sequence
import xml.etree.ElementTree as ET

from .field import box, element as e, material, numbers

VERSION = "proxy-harvester/1.0"
ARM_JOINT_NAMES = (
    "arm_yaw_joint", "shoulder_joint", "elbow_joint",
    "wrist_pitch_joint", "wrist_roll_joint",
)
JOINT_LIMITS = (
    (-math.pi, math.pi), (-1.3, 1.65), (-2.4, 2.4),
    (-2.4, 2.4), (-math.pi, math.pi),
)
HOME_JOINTS = (0.0, 0.6, -1.2, 0.6, 0.0)


def set_collision_bitmask(model: ET.Element, mask: int) -> None:
    """Set 16-bit contact filters on collisions in a model or link subtree.

    Preserve friction and all unrelated surface settings. DART's filter uses
    the collide bitmask as the category when category_bitmask is absent. If
    a caller already supplied a category, update it too to retain that
    symmetric meaning. New category elements are not required by this pilot.

    The scene composer must explicitly assign 65535 to environment and fruit
    colliders: some DART versions use 0xFF if the XML mask is missing, which
    would not overlap the last two masks of this ten-link proxy.
    """
    if type(mask) is not int or not 0 <= mask <= 0xFFFF:
        raise ValueError("Collision mask must be an integer in [0, 65535]")
    for collision in model.iter("collision"):
        surface = collision.find("surface")
        if surface is None:
            surface = e(collision, "surface")
        contact = surface.find("contact")
        if contact is None:
            contact = e(surface, "contact")
        value = contact.find("collide_bitmask")
        if value is None:
            value = e(contact, "collide_bitmask")
        value.text = str(mask)
        category = contact.find("category_bitmask")
        if category is not None:
            category.text = str(mask)


@dataclass(frozen=True)
class HarvesterConfig:
    """Approximate hardware envelope; every value is an engineering heuristic."""

    model_name: str = "harvester"
    namespace: str = "/harvester"
    shoulder_height_m: float = 0.56
    upper_arm_m: float = 0.34
    forearm_m: float = 0.30
    tool_length_m: float = 0.12
    body_length_m: float = 0.50
    body_width_m: float = 0.36
    body_height_m: float = 0.14
    body_center_z_m: float = 0.22
    wheel_radius_m: float = 0.10
    wheel_width_m: float = 0.05
    wheelbase_m: float = 0.40
    wheel_separation_m: float = 0.44
    base_mass_kg: float = 12.0
    wheel_mass_kg: float = 0.35
    upper_arm_mass_kg: float = 1.0
    forearm_mass_kg: float = 0.7
    tool_mass_kg: float = 0.22
    camera: bool = False

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key in ("model_name", "namespace", "camera"):
                continue
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and positive")
        if not self.model_name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in self.model_name):
            raise ValueError("model_name must be a nonempty ASCII identifier")
        if not self.namespace.startswith("/") or self.namespace.endswith("/"):
            raise ValueError("namespace must start with '/' and have no trailing slash")
        if self.body_center_z_m <= self.body_height_m / 2:
            raise ValueError("The chassis must clear the ground")
        if self.shoulder_height_m <= self.body_center_z_m + self.body_height_m / 2:
            raise ValueError("The shoulder must be above the chassis")
        if self.wheel_separation_m <= self.body_width_m + self.wheel_width_m:
            raise ValueError("Wheel inner faces must clear the chassis sides")


def _finite(values: Sequence[float], count: int, label: str) -> tuple[float, ...]:
    result = tuple(float(v) for v in values)
    if len(result) != count or not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} requires {count} finite values")
    return result


def check_joint_limits(joints: Sequence[float]) -> tuple[float, ...]:
    """Validate ordering, SI units and mechanical limits; never silently clip."""
    values = _finite(joints, 5, "arm joints")
    for name, value, (lower, upper) in zip(ARM_JOINT_NAMES, values, JOINT_LIMITS):
        if value < lower - 1e-10 or value > upper + 1e-10:
            raise ValueError(f"{name} outside [{lower}, {upper}]: {value}")
    return values


def link_origins(joints: Sequence[float], config: HarvesterConfig | None = None) -> dict:
    """Joint landmarks in the robot's ground-level base/model frame, metres.

    Positive shoulder, elbow and wrist-pitch rotate about local -Y, raising +X.
    This convention agrees with the generated SDF axes. Wrist roll has no
    positional effect because the TCP lies along its rotation axis.
    """
    c = config or HarvesterConfig()
    yaw, shoulder, elbow, wrist, _ = check_joint_limits(joints)
    radial = height = 0.0
    landmarks = {"shoulder": [0.0, 0.0, c.shoulder_height_m]}
    for name, length, angle in (
        ("elbow", c.upper_arm_m, shoulder),
        ("wrist", c.forearm_m, shoulder + elbow),
        ("tool", c.tool_length_m, shoulder + elbow + wrist),
    ):
        radial += length * math.cos(angle)
        height += length * math.sin(angle)
        landmarks[name] = [radial * math.cos(yaw), radial * math.sin(yaw),
                           c.shoulder_height_m + height]
    return landmarks


def forward_kinematics(joints: Sequence[float], config: HarvesterConfig | None = None) -> dict:
    """Return TCP ``position_m`` and fixed-axis ``rpy_rad`` in the base frame.

    Orientation is Rz(yaw) Ry(-(shoulder+elbow+wrist_pitch)) Rx(wrist_roll).
    The returned Euler representation need not use the principal pitch range.
    """
    values = check_joint_limits(joints)
    return {"position_m": link_origins(values, config)["tool"],
            "rpy_rad": [values[4], -sum(values[1:4]), values[0]]}


def inverse_kinematics(target_xyz: Sequence[float], pitch: float = 0.0,
                       roll: float = 0.0, config: HarvesterConfig | None = None) -> tuple:
    """Analytic 5-axis IK, with yaw pointing radially toward the target.

    ``target_xyz`` is in the same ground-level robot frame as FK. ``pitch`` and
    ``roll`` are TCP fixed-axis Euler angles, in radians. Both elbow branches
    are considered, preferring the elbow-down branch. Out-of-workspace targets,
    joint-limit violations and the underdetermined base-yaw axis raise
    ValueError. This solver is not a collision or trajectory planner.
    """
    c = config or HarvesterConfig()
    x, y, z = _finite(target_xyz, 3, "target_xyz")
    pitch, roll = _finite((pitch, roll), 2, "tool orientation")
    radius = math.hypot(x, y)
    if radius < 1e-9:
        raise ValueError("Base-yaw singularity: target lies on the shoulder axis")
    yaw = math.atan2(y, x)
    elevation = -pitch
    radial_wrist = radius - c.tool_length_m * math.cos(elevation)
    vertical_wrist = z - c.shoulder_height_m - c.tool_length_m * math.sin(elevation)
    cosine = (radial_wrist**2 + vertical_wrist**2 - c.upper_arm_m**2 - c.forearm_m**2) / (2 * c.upper_arm_m * c.forearm_m)
    if cosine < -1 - 1e-10 or cosine > 1 + 1e-10:
        raise ValueError("Target is outside the arm workspace for the requested pitch")
    magnitude = math.acos(max(-1.0, min(1.0, cosine)))
    for elbow in (-magnitude, magnitude):
        shoulder = math.atan2(vertical_wrist, radial_wrist) - math.atan2(
            c.forearm_m * math.sin(elbow), c.upper_arm_m + c.forearm_m * math.cos(elbow))
        wrist = elevation - shoulder - elbow
        try:
            return check_joint_limits((yaw, shoulder, elbow, wrist, roll))
        except ValueError:
            continue
    raise ValueError("Target has no solution within the proxy arm joint limits")


def robot_contract(config: HarvesterConfig | None = None) -> dict:
    """Stable semantic interface for replacing the proxy by the final robot.

    A replacement may provide its own IK/planning adapter. Plant/fruit identity
    and the cut/latch system depend on model and tool names, not link lengths.
    """
    c = config or HarvesterConfig()
    return {
        "schema_version": VERSION,
        "parameter_provenance": "engineering_heuristic",
        "model_name": c.model_name,
        "base_link": "base_link",
        "tool_link": "tool_link",
        "arm_dof": 5,
        "wheel_count": 4,
        "arm_joint_names": list(ARM_JOINT_NAMES),
        "joint_limits_rad": [list(bounds) for bounds in JOINT_LIMITS],
        "home_joints_rad": list(HOME_JOINTS),
        "topics": {
            "cmd_vel": f"{c.namespace}/cmd_vel",
            "odometry": f"{c.namespace}/odometry",
            "joint_states": f"{c.namespace}/joint_states",
            "joint_commands": {name: f"{c.namespace}/arm/{name}/cmd_pos" for name in ARM_JOINT_NAMES},
        },
        "frame_convention": "model origin at ground; +X forward, +Y left, +Z up; TCP at tool_link origin",
        "kinematic_parameters": asdict(c),
        "capture_model": "ideal constraint latch; jaws visual-only, no force/contact grasp claim",
        "collision_policy": {
            "model_self_collide": True,
            "robot_internal_contacts": "suppressed_by_disjoint_link_bitmasks",
            "environment_and_fruit_bitmask": 65535,
            "detached_fruit_contacts": "enabled_by_export_configuration_pending_native_validation",
        },
        "runtime_validation": "pending_gazebo",
    }


def _inertial(link, mass, dimensions, center=(0.0, 0.0, 0.0)):
    """Box approximation with tensor about its own centre of mass."""
    inertial = e(link, "inertial")
    e(inertial, "pose", numbers((*center, 0, 0, 0)))
    e(inertial, "mass", mass)
    tensor = e(inertial, "inertia")
    x, y, z = dimensions
    for key, value in {"ixx": mass * (y*y + z*z) / 12,
                       "iyy": mass * (x*x + z*z) / 12,
                       "izz": mass * (x*x + y*y) / 12,
                       "ixy": 0, "ixz": 0, "iyz": 0}.items():
        e(tensor, key, value)


def _plugin(model, filename, name, values):
    node = e(model, "plugin", filename=f"gz-sim-{filename}-system",
             name=f"gz::sim::systems::{name}")
    for key, value in values.items():
        e(node, key, value)
    return node


def _solid(link, name, center, size, color):
    box(link, name, center, size, color)
    box(link, f"{name}_collision", center, size, collision=True)


def _revolute(model, name, parent, child, axis, lower, upper, effort=60.0,
              velocity=1.0, pose_relative_to=None):
    joint = e(model, "joint", name=name, type="revolute")
    e(joint, "parent", parent)
    e(joint, "child", child)
    # Explicit frame avoids the SDF default pose-relative-to-child ambiguity.
    e(joint, "pose", "0 0 0 0 0 0", relative_to=pose_relative_to or child)
    node = e(joint, "axis")
    e(node, "xyz", numbers(axis))
    limits = e(node, "limit")
    for key, value in (("lower", lower), ("upper", upper), ("effort", effort), ("velocity", velocity)):
        e(limits, key, value)
    dynamics = e(node, "dynamics")
    e(dynamics, "damping", 0.3)
    e(dynamics, "friction", 0.02)
    return joint


def generic_harvester_model(config: HarvesterConfig | None = None,
                             start=(0.0, 0.0, 0.002, 0.0)) -> ET.Element:
    """Create a self-contained dynamic SDF model; no external meshes needed.

    ``start=(x,y,z,yaw)`` places the model ground origin. Default z=2 mm allows
    the wheels to settle onto a ground plane. All link poses are zero-joint
    poses; native controllers initially command zero and the runner homes them.
    A Sensors system on the world is needed only if ``config.camera`` is true.
    """
    c = config or HarvesterConfig()
    x, y, z, yaw = _finite(start, 4, "robot start")
    model = ET.Element("model", name=c.model_name)
    e(model, "pose", numbers((x, y, z, 0, 0, yaw)))
    e(model, "static", "false")
    # DetachableJoint's documented collision behavior requires self_collide
    # on the parent. Disable only proxy-internal link pairs with masks below.
    e(model, "self_collide", "true")
    base = e(model, "link", name="base_link")
    dimensions = (c.body_length_m, c.body_width_m, c.body_height_m)
    _inertial(base, c.base_mass_kg, dimensions, (0, 0, c.body_center_z_m))
    _solid(base, "chassis", (0, 0, c.body_center_z_m), dimensions, (.12, .27, .18, 1))
    pedestal_bottom = c.body_center_z_m + c.body_height_m / 2
    pedestal_height = c.shoulder_height_m - pedestal_bottom
    _solid(base, "pedestal", (0, 0, pedestal_bottom + pedestal_height / 2),
           (.09, .09, pedestal_height), (.25, .29, .31, 1))
    drive = _plugin(model, "diff-drive", "DiffDrive", {
        "wheel_separation": c.wheel_separation_m,
        "wheel_radius": c.wheel_radius_m,
        "topic": f"{c.namespace}/cmd_vel",
        "odom_topic": f"{c.namespace}/odometry",
        "tf_topic": f"{c.namespace}/tf",
        "frame_id": "odom", "child_frame_id": "base_link",
        "odom_publish_frequency": 30,
        "min_linear_velocity": -.20, "max_linear_velocity": .20,
        "min_angular_velocity": -.5, "max_angular_velocity": .5,
        "max_linear_acceleration": .3, "min_linear_acceleration": -.3,
        "max_angular_acceleration": .6, "min_angular_acceleration": -.6,
    })
    for side, sign in (("left", 1), ("right", -1)):
        for axle, xsign in (("front", 1), ("rear", -1)):
            name = f"{axle}_{side}_wheel"
            link = e(model, "link", name=name)
            e(link, "pose", numbers((xsign*c.wheelbase_m/2,
                sign*c.wheel_separation_m/2, c.wheel_radius_m, 0, 0, 0)))
            # Tensor of a solid cylinder whose rotation axis is local Y.
            inertia = e(link, "inertial")
            e(inertia, "mass", c.wheel_mass_kg)
            tensor = e(inertia, "inertia")
            transverse = c.wheel_mass_kg * (3*c.wheel_radius_m**2 + c.wheel_width_m**2) / 12
            for key, value in {"ixx": transverse, "iyy": .5*c.wheel_mass_kg*c.wheel_radius_m**2,
                               "izz": transverse, "ixy": 0, "ixz": 0, "iyz": 0}.items():
                e(tensor, key, value)
            for tag in ("visual", "collision"):
                item = e(link, tag, name=f"{name}_{tag}")
                e(item, "pose", numbers((0, 0, 0, math.pi/2, 0, 0)))
                cylinder = e(e(item, "geometry"), "cylinder")
                e(cylinder, "radius", c.wheel_radius_m)
                e(cylinder, "length", c.wheel_width_m)
                if tag == "visual":
                    material(item, (.035, .04, .045, 1))
                else:
                    ode = e(e(e(item, "surface"), "friction"), "ode")
                    e(ode, "mu", .9)
                    e(ode, "mu2", .5)
                    # The collision cylinder's Z axis is the wheel axle.
                    # Four fixed wheel axes need lateral slip to skid-steer;
                    # an unspecified friction direction can lock turning and
                    # convert opposite wheel speeds into chassis translation.
                    # Same lateral-compliance convention as Harmonic's
                    # examples/worlds/diff_drive_skid.sdf. Engineering guess,
                    # not a calibrated tyre model; longitudinal slip stays 0.
                    e(ode, "fdir1", "0 0 1")
                    e(ode, "slip1", .035)
                    e(ode, "slip2", 0)
            joint_name = name + "_joint"
            _revolute(model, joint_name, "base_link", name, (0, 1, 0),
                      -1e16, 1e16, effort=15, velocity=8)
            e(drive, f"{side}_joint", joint_name)

    yaw_link = e(model, "link", name="arm_yaw_link")
    e(yaw_link, "pose", numbers((0, 0, c.shoulder_height_m, 0, 0, 0)))
    _inertial(yaw_link, .25, (.075, .075, .065))
    _solid(yaw_link, "yaw_housing", (0, 0, 0), (.075, .075, .065), (.19, .21, .23, 1))
    upper = e(model, "link", name="upper_arm_link")
    e(upper, "pose", "0 0 0 0 0 0", relative_to="arm_yaw_link")
    _inertial(upper, c.upper_arm_mass_kg, (c.upper_arm_m, .055, .055), (c.upper_arm_m/2, 0, 0))
    _solid(upper, "upper_arm", (c.upper_arm_m/2, 0, 0),
           (c.upper_arm_m, .055, .055), (.88, .59, .12, 1))
    fore = e(model, "link", name="forearm_link")
    e(fore, "pose", numbers((c.upper_arm_m, 0, 0, 0, 0, 0)), relative_to="upper_arm_link")
    _inertial(fore, c.forearm_mass_kg, (c.forearm_m, .045, .045), (c.forearm_m/2, 0, 0))
    _solid(fore, "forearm", (c.forearm_m/2, 0, 0),
           (c.forearm_m, .045, .045), (.94, .72, .20, 1))
    wrist = e(model, "link", name="wrist_link")
    e(wrist, "pose", numbers((c.forearm_m, 0, 0, 0, 0, 0)), relative_to="forearm_link")
    _inertial(wrist, .15, (.045, .05, .05))
    _solid(wrist, "wrist", (0, 0, 0), (.045, .05, .05), (.27, .29, .30, 1))
    tool = e(model, "link", name="tool_link")
    e(tool, "pose", numbers((c.tool_length_m, 0, 0, 0, 0, 0)), relative_to="wrist_link")
    _inertial(tool, c.tool_mass_kg, (c.tool_length_m, .085, .06), (-c.tool_length_m/2, 0, .015))
    _solid(tool, "tool_housing", (-c.tool_length_m*.72, 0, .03),
           (c.tool_length_m*.45, .075, .03), (.28, .31, .34, 1))
    # Deliberately non-contact jaws: the pilot tests an ideal retained cut.
    for side, sign in (("left", 1), ("right", -1)):
        box(tool, f"capture_jaw_{side}", (-.025, sign*.04, -.025),
            (.075, .009, .014), (.55, .58, .60, 1))
        box(tool, f"cutter_{side}", (0, sign*.022, 0),
            (.018, .032, .004), (.78, .80, .82, 1))
    arm_specs = (
        ("base_link", "arm_yaw_link", (0, 0, 1), None),
        ("arm_yaw_link", "upper_arm_link", (0, -1, 0), None),
        ("upper_arm_link", "forearm_link", (0, -1, 0), None),
        ("forearm_link", "wrist_link", (0, -1, 0), None),
        ("wrist_link", "tool_link", (1, 0, 0), "wrist_link"),
    )
    for index, (name, limits, spec) in enumerate(zip(ARM_JOINT_NAMES, JOINT_LIMITS, arm_specs)):
        parent, child, axis, pose_frame = spec
        _revolute(model, name, parent, child, axis, *limits, pose_relative_to=pose_frame)
        _plugin(model, "joint-position-controller", "JointPositionController", {
            "joint_name": name, "topic": f"{c.namespace}/arm/{name}/cmd_pos",
            "initial_position": 0, "p_gain": 120 if index < 3 else 45,
            # The tiny wrist inertias cannot use the proximal derivative gain
            # at the 1 ms physics step. d=3 produced persistent +/-1 mrad
            # limit cycling and nonzero TCP relative speed at rest in DART.
            # Keep force-based PID and the same position/guard tolerances.
            "i_gain": 8 if index < 3 else 2,
            "d_gain": 12 if index < 3 else (.20 if index == 3 else .03),
            "i_min": -15, "i_max": 15, "cmd_min": -60, "cmd_max": 60,
        })
    states = _plugin(model, "joint-state-publisher", "JointStatePublisher", {
        "topic": f"{c.namespace}/joint_states"})
    # Omitting update_rate preserves compatibility with earlier Harmonic 8.x.
    for name in ARM_JOINT_NAMES:
        e(states, "joint_name", name)
    if c.camera:
        sensor = e(base, "sensor", name="front_rgb", type="camera")
        e(sensor, "pose", numbers((c.body_length_m/2, 0, c.body_center_z_m+.10, 0, -.10, 0)))
        e(sensor, "always_on", "true")
        e(sensor, "update_rate", 10)
        e(sensor, "topic", f"{c.namespace}/camera/image")
        camera = e(sensor, "camera")
        e(camera, "horizontal_fov", 1.0472)
        image = e(camera, "image")
        e(image, "width", 640)
        e(image, "height", 480)
        e(image, "format", "R8G8B8")
        clip = e(camera, "clip")
        e(clip, "near", .02)
        e(clip, "far", 10)
    colliding_links = [link for link in model.findall("link") if link.find("collision") is not None]
    if len(colliding_links) > 16:
        raise ValueError("Proxy collision policy supports at most sixteen colliding links")
    for index, link in enumerate(colliding_links):
        set_collision_bitmask(link, 1 << index)
    return model
