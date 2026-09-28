"""Pure SDF assembly in metres; botanical geometry is supplied by an interpreter."""
from __future__ import annotations

import math
from pathlib import Path
import xml.etree.ElementTree as ET

VERSION = "gazebo-field/0.1"


def prepare_mesh_assets(directory, meshes):
    """Keep one OBJ submesh per material batch, avoiding thousands of draw calls.

    Source organ names remain comments and in the identity sidecar. MTL and SDF
    both declare the color, avoiding renderer-specific material fallback.
    Explicit face normals are required for correct Ogre2 lighting.
    """
    directory = Path(directory)
    colors = {Path(mesh["uri"]).stem:mesh["color"] for mesh in meshes}
    with (directory / "surface.mtl").open("w",encoding="utf-8") as material_file:
        for name, color in sorted(colors.items()):
            rgb = numbers(color[:3])
            material_file.write(f"newmtl {name}\nKa {rgb}\nKd {rgb}\nd {color[3]}\n")
    for path in sorted(directory.glob("*.obj")):
        temporary = path.with_suffix(".obj.tmp")
        with path.open(encoding="utf-8") as source, temporary.open("w",encoding="utf-8") as target:
            if path.stem not in colors:
                raise ValueError(f"Missing mesh color: {path.name}")
            target.write(f"mtllib surface.mtl\nusemtl {path.stem}\no merged\n")
            vertices = []
            normal_index = 0
            for line in source:
                if line.startswith(("mtllib ","usemtl ","vn ")) or line == "o merged\n":
                    continue
                if line.startswith("v "):
                    vertices.append(tuple(float(v) for v in line.split()[1:4]))
                if line.startswith("f "):
                    indices = [int(v.split('/')[0]) for v in line.split()[1:]]
                    if len(indices) != 3:
                        raise ValueError("Expected evaluated triangular mesh faces")
                    a,b,c = [vertices[i-1] for i in indices]
                    u = [b[i]-a[i] for i in range(3)]
                    v = [c[i]-a[i] for i in range(3)]
                    normal = (u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                    length = math.sqrt(sum(x*x for x in normal))
                    normal = tuple(x/length for x in normal) if length else (0,0,1)
                    normal_index += 1
                    target.write("vn " + numbers(normal) + "\n")
                    target.write("f " + " ".join(f"{i}//{normal_index}" for i in indices) + "\n")
                    continue
                target.write("# source " + line[2:] if line.startswith("o ") else line)
        temporary.replace(path)


def element(parent, tag, text=None, **attributes):
    child = ET.SubElement(parent, tag, attributes)
    if text is not None:
        child.text = str(text)
    return child


def numbers(values):
    if not all(math.isfinite(v) for v in values):
        raise ValueError("SDF coordinates must be finite")
    return " ".join(f"{v:.9g}" for v in values)


def material(visual, color):
    mat = element(visual, "material")
    element(mat, "ambient", numbers(color))
    element(mat, "diffuse", numbers(color))
    element(mat, "double_sided", "true")


def box(link, name, center, size, color=None, collision=False):
    if any(v <= 0 for v in size):
        raise ValueError("Box dimensions must be positive")
    item = element(link, "collision" if collision else "visual", name=name)
    element(item, "pose", numbers((*center, 0, 0, 0)))
    element(element(element(item, "geometry"), "box"), "size", numbers(size))
    if color is not None and not collision:
        material(item, color)
    return item


def cylinder_collision(link, name, start, end, radius):
    delta = [b-a for a, b in zip(start, end)]
    length = math.sqrt(sum(v*v for v in delta))
    if length <= 0 or radius <= 0:
        raise ValueError("Invalid cylinder")
    pitch = math.acos(max(-1, min(1, delta[2]/length)))
    yaw = math.atan2(delta[1], delta[0])
    item = element(link, "collision", name=name)
    element(item, "pose", numbers((*[(a+b)/2 for a,b in zip(start,end)], 0, pitch, yaw)))
    shape = element(element(item, "geometry"), "cylinder")
    element(shape, "radius", radius)
    element(shape, "length", length)


def camera(world, name, pose, width=1280, height=960):
    model = element(world, "model", name=name)
    element(model, "static", "true")
    element(model, "pose", numbers(pose))
    link = element(model, "link", name="camera_link")
    sensor = element(link, "sensor", name="rgb", type="camera")
    element(sensor, "always_on", "true")
    element(sensor, "update_rate", 5)
    element(sensor, "topic", f"/uchuva/{name}/image")
    cam = element(sensor, "camera")
    element(cam, "horizontal_fov", 1.0471975512)
    image = element(cam, "image")
    element(image, "width", width)
    element(image, "height", height)
    element(image, "format", "R8G8B8")
    clip = element(cam, "clip")
    element(clip, "near", .02)
    element(clip, "far", 100)


def build_world(meshes, markers, patterns, colliders, *, margin=.02):
    """Build portable SDF with explicit marker fronts and opaque backs.

    Mesh vertices and collider coordinates are already in world metres.
    Cameras are movable inspection rigs, not aircraft dynamics.
    """
    root = ET.Element("sdf", version="1.9")
    world = element(root, "world", name="uchuva_field")
    element(world, "gravity", "0 0 -9.81")
    physics = element(world, "physics", name="physics", type="ignored")
    element(physics, "max_step_size", .002)
    element(physics, "real_time_factor", 1)
    for filename, name in (("physics", "Physics"), ("user-commands", "UserCommands"),
                           ("scene-broadcaster", "SceneBroadcaster"), ("sensors", "Sensors")):
        plugin = element(world, "plugin", filename=f"gz-sim-{filename}-system",
                         name=f"gz::sim::systems::{name}")
        if name == "Sensors":
            element(plugin, "render_engine", "ogre2")
    scene = element(world, "scene")
    element(scene, "ambient", "0.65 0.65 0.65 1")
    element(scene, "background", "0.60 0.75 0.90 1")
    sun = element(world, "light", name="sun", type="directional")
    element(sun, "pose", "0 0 10 0 0 0")
    element(sun, "diffuse", "0.8 0.8 0.8 1")
    element(sun, "direction", "-0.3 0.2 -1")
    element(sun, "cast_shadows", "true")
    model = element(world, "model", name="field")
    element(model, "static", "true")
    link = element(model, "link", name="field_link")
    box(link, "soil", (0,0,-.1), (24,24,.2), (.22,.14,.065,1))
    box(link, "soil_collision", (0,0,-.1), (24,24,.2), collision=True)
    for index, mesh in enumerate(meshes):
        visual = element(link, "visual", name=f"mesh_{index}")
        geo = element(element(visual, "geometry"), "mesh")
        element(geo, "uri", mesh["uri"])
        material(visual, mesh["color"])
    for index, collider in enumerate(colliders):
        cylinder_collision(link, f"structural_{index}", collider["start_m"],
                           collider["end_m"], collider["radius_m"])
    seen = set()
    for spec in markers:
        identifier = spec["id"]
        if identifier in seen:
            raise ValueError("Duplicate marker ID")
        seen.add(identifier)
        if spec["dictionary"] != "DICT_4X4_100" or not 0 <= identifier < 100:
            raise ValueError("Unsupported ArUco identity")
        cells = patterns[str(identifier)]
        if len(cells) != 6 or any(len(row) != 6 or any(v not in (0,1) for v in row) for row in cells):
            raise ValueError("Expected a 6x6 ArUco bitmap including its border")
        x,y,z = spec["center_world_m"]
        nx, sign, nz = spec["normal_world"]
        if nx != 0 or nz != 0 or sign not in (-1,1):
            raise ValueError("This field supports aisle-facing vertical markers")
        side = spec["side_m"]
        thick = spec["backing_thickness_m"]
        # Printed plane is at the declared center, backing extends inward.
        backing = (x,y-sign*thick/2,z)
        size = (side+2*margin, thick, side+2*margin)
        box(link, f"marker_{identifier}_backing", backing, size, (1,1,1,1))
        box(link, f"marker_{identifier}_collision", backing, size, collision=True)
        for row in range(6):
            for col in range(6):
                if cells[row][col]:
                    center = (x-sign*((col+.5)/6-.5)*side,
                              y+sign*.00005, z+(.5-(row+.5)/6)*side)
                    visual = box(link, f"marker_{identifier}_{row}_{col}", center,
                                 (side/6,.0001,side/6), (0,0,0,1))
                    element(visual, "cast_shadows", "false")
    camera(world, "overview", (10,-13,10,0,.65,2.20))
    # Near plant_00: +X optical forward, positive pitch points downward.
    first = markers[0]["center_world_m"] if markers else (-3.5,-4.68,.12)
    camera(world, "drone_camera", (first[0],first[1]-1.3,.65,0,.38,math.pi/2))
    return root


def write_world(path, *args, **kwargs):
    root = build_world(*args, **kwargs)
    ET.indent(root)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return Path(path)
