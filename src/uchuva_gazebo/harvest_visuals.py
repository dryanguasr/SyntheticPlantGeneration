"""Textured harvest visuals, downstream of the existing morphology proxies.

These meshes are a visual interpretation only.  They neither generate organs
nor change collision geometry.  The leaf envelope and five-sepal calyx profile
reuse the current Blender interpreter; material maps are the repository's
procedural ``assets/textures/current`` library.  Relief is an engineering
heuristic, not a botanical measurement or a fruit-maturity observation.
"""

from __future__ import annotations

from collections import defaultdict
import math
from pathlib import Path
import random
import struct
import xml.etree.ElementTree as ET
import zlib

from uchuva_lsystem.blender_geometry import (
    _calyx_profile_radius_factor,
    _leaf_shape_profile,
)
from uchuva_lsystem.texture_assets import TEXTURE_PRESETS


VERSION = "0.1.0-textured-harvest-visuals"
SOIL_TEXTURE_SEED = 20261031
_PRESETS = {preset.name: preset for preset in TEXTURE_PRESETS}
_MAP_KINDS = ("albedo", "roughness", "normal")


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(sum(x * x for x in a))
    if length < 1e-15:
        raise ValueError("A visual mesh has a degenerate normal or basis")
    return tuple(x / length for x in a)


def _obj(vertices, uvs, faces, *, double_sided=False, normal_aliases=None):
    """Write smooth indexed OBJ, with separate reversed normals for leaf backs."""
    aliases = normal_aliases or list(range(len(vertices)))
    accumulated = defaultdict(lambda: [0.0, 0.0, 0.0])
    for face in faces:
        a, b, c = (vertices[index] for index in face)
        normal = _cross(_sub(b, a), _sub(c, a))
        if sum(x * x for x in normal) <= 1e-28:
            raise ValueError("A visual mesh contains a degenerate triangle")
        for index in face:
            for coordinate in range(3):
                accumulated[aliases[index]][coordinate] += normal[coordinate]
    normals = [_unit(accumulated[key]) for key in aliases]
    lines = [f"# {VERSION}; visual_only; relief=engineering_heuristic", "s 1"]
    lines.extend("v " + " ".join(f"{value:.10f}" for value in point) for point in vertices)
    lines.extend("vt " + " ".join(f"{value:.8f}" for value in point) for point in uvs)
    lines.extend("vn " + " ".join(f"{value:.9f}" for value in point) for point in normals)
    if double_sided:
        lines.extend("vn " + " ".join(f"{-value:.9f}" for value in point) for point in normals)
    for face in faces:
        lines.append("f " + " ".join(f"{i + 1}/{i + 1}/{i + 1}" for i in face))
        if double_sided:
            lines.append("f " + " ".join(f"{i + 1}/{i + 1}/{i + 1 + len(vertices)}" for i in reversed(face)))
    return "\n".join(lines) + "\n"


def _leaf_centerline(proxies, t):
    """Recover the quadratic centerline sampled by the three collision slabs."""
    samples = (0.24, 0.53, 0.81)
    weights = [math.prod((t - samples[j]) / (sample - samples[j]) for j in range(3) if i != j)
               for i, sample in enumerate(samples)]
    return tuple(sum(weight * proxy.center[coordinate] for weight, proxy in zip(weights, proxies))
                 for coordinate in range(3))


def detailed_leaf_mesh(proxies, origin, *, leaf_shapes=None, units_per_metre=8.0, longitudinal_segments=16):
    """Batch continuous curved leaves in plant-local metres, with UVs and backs.

    Each source leaf must contain the three ``blade_0/1/2`` slabs emitted by
    ``build_scene_proxies``.  A slab is not an independent leaf.  Centers retain
    source sag and pose; dimensions are recovered from that proxy contract.
    ``leaf_shapes`` maps source attachment IDs to morphology ``leaf.shape``;
    missing entries retain the compatible ovate default. No organ is added and
    no proxy is mutated. ``origin`` is already in metres.
    """
    if units_per_metre <= 0 or longitudinal_segments < 4:
        raise ValueError("Positive units and at least four leaf segments are required")
    grouped = defaultdict(list)
    for proxy in proxies:
        grouped[proxy.attachment_id].append(proxy)
    vertices, uvs, faces = [], [], []
    across = 4
    for attachment, slabs in sorted(grouped.items()):
        shape = (leaf_shapes or {}).get(attachment, "ovate")
        slabs.sort(key=lambda item: item.proxy_id)
        if len(slabs) != 3 or any(not slab.proxy_id.endswith(f":blade_{i}") for i, slab in enumerate(slabs)):
            raise ValueError(f"{attachment}: expected three morphology leaf slabs blade_0/1/2")
        source_width = slabs[1].half_extents[1] / 0.62
        thickness = min(slab.half_extents[2] for slab in slabs)
        width_axis = _unit(slabs[1].axes[1])
        base = len(vertices)

        def add_point(t, transverse):
            center = _leaf_centerline(slabs, t)
            before = _leaf_centerline(slabs, t - 0.001)
            after = _leaf_centerline(slabs, t + 0.001)
            normal = _unit(_cross(_sub(after, before), width_axis))
            # The ovate envelope is shared with the current Blender interpreter.
            profile, lobes = _leaf_shape_profile(shape, t)
            half_width = min(source_width * 0.62, source_width * 0.5 * profile * lobes)
            side = transverse * half_width
            camber = thickness * 0.7 * transverse * transverse * math.sin(math.pi * t)
            point = tuple((center[i] + side * width_axis[i] + camber * normal[i]) / units_per_metre - origin[i]
                          for i in range(3))
            vertices.append(point)
            # Same planar UV convention as Blender: width horizontally, length vertically.
            uvs.append((min(1.0, max(0.0, 0.5 + side / source_width)), t))

        add_point(0.0, 0.0)
        for row in range(1, longitudinal_segments):
            for column in range(across + 1):
                add_point(row / longitudinal_segments, 2.0 * column / across - 1.0)
        tip = len(vertices)
        add_point(1.0, 0.0)
        for column in range(across):
            faces.append((base, base + 1 + column, base + 2 + column))
        for row in range(longitudinal_segments - 2):
            start = base + 1 + row * (across + 1)
            for column in range(across):
                a = start + column
                b = a + 1
                c = a + across + 1
                d = c + 1
                faces.extend(((a, c, d), (a, d, b)))
        last = tip - across - 1
        for column in range(across):
            faces.append((last + column, tip, last + column + 1))
    if not vertices:
        return f"# {VERSION}; empty leaf batch\n"
    return _obj(vertices, uvs, faces, double_sided=True)


def detailed_calyx_mesh(proxy, *, units_per_metre=8.0, rings=16, sectors=40):
    """Closed five-rib husk, centered at its existing proxy, in world axes.

    UV-seam vertices share smooth normals.  The source ellipsoid bounds every
    vertex, preserving the conservative collision sphere used by harvesting.
    The distal taper, venation and five main ribs follow the current Blender
    visual vocabulary; local relief remains explicitly heuristic.
    """
    if units_per_metre <= 0 or rings < 4 or sectors < 10 or sectors % 5:
        raise ValueError("Positive units, >=4 rings and sectors divisible by five are required")
    half = tuple(value / units_per_metre for value in proxy.half_extents)
    if min(half) <= 0:
        raise ValueError("Calyx half-extents must be positive")
    vertices, uvs, faces, aliases = [], [], [], []

    def add_point(t, angle, u, alias):
        axial = 2.0 * t - 1.0
        spherical = math.sqrt(max(0.0, 1.0 - axial * axial))
        profile = _calyx_profile_radius_factor(t, 0.0, 1.0, "lantern_squash")
        rib_phase = math.cos(5.0 * angle)
        relief = (0.93 + 0.07 * max(0.0, rib_phase) ** 6 - 0.02 * max(0.0, -rib_phase) ** 4)
        # Restrict the profile to the pre-existing ellipsoid; no collider grows.
        radial = min(spherical, profile) * relief
        local = (half[0] * axial, half[1] * radial * math.cos(angle), half[2] * radial * math.sin(angle))
        vertices.append(tuple(sum(local[j] * proxy.axes[j][i] for j in range(3)) for i in range(3)))
        uvs.append((u, t))
        aliases.append(alias)

    add_point(0.0, 0.0, 0.5, "base")
    for ring in range(1, rings):
        for sector in range(sectors + 1):
            add_point(ring / rings, math.tau * sector / sectors, sector / sectors, (ring, sector % sectors))
    tip = len(vertices)
    add_point(1.0, 0.0, 0.5, "tip")
    for sector in range(sectors):
        faces.append((0, sector + 2, sector + 1))
    for ring in range(rings - 2):
        start = 1 + ring * (sectors + 1)
        for sector in range(sectors):
            a = start + sector
            b = a + 1
            c = a + sectors + 1
            d = c + 1
            faces.extend(((a, b, d), (a, d, c)))
    last = tip - sectors - 1
    for sector in range(sectors):
        faces.append((last + sector, last + sector + 1, tip))
    return _obj(vertices, uvs, faces, normal_aliases=aliases)


def merge_obj_meshes(meshes):
    """Batch ``(OBJ text, translation_m)`` pairs, retaining UV and normal indices.

    Input is triangle OBJ emitted by this module.  Translation is applied only
    to positions.  Use one batch per material; moving harvest bodies must stay
    independent.  ``offset`` is typically calyx.center / units - plant.origin.
    """
    positions, uvs, normals, faces = [], [], [], []
    for content, offset in meshes:
        position_start, uv_start, normal_start = len(positions), len(uvs), len(normals)
        for line in content.splitlines():
            fields = line.split()
            if not fields or fields[0].startswith("#"):
                continue
            if fields[0] == "v":
                point = [float(value) + delta for value, delta in zip(fields[1:], offset)]
                positions.append("v " + " ".join(f"{value:.10f}" for value in point))
            elif fields[0] == "vt":
                uvs.append(line)
            elif fields[0] == "vn":
                normals.append(line)
            elif fields[0] == "f":
                indices = [tuple(map(int, field.split("/"))) for field in fields[1:]]
                faces.append("f " + " ".join(f"{p + position_start}/{uv + uv_start}/{normal + normal_start}"
                                             for p, uv, normal in indices))
    return "\n".join([f"# {VERSION}; static material batch", "s 1", *positions, *uvs, *normals, *faces]) + "\n"


def cylinder_batch_mesh(segments, *, sectors=12):
    """Batch stem/petiole visuals from ``(start_m, end_m, radius_m)`` tuples.

    Callers retain their existing cylinder collisions and pass already-cut
    endpoints for selected pedicels.  Caps have independent normals for crisp
    cut surfaces. All coordinates and radii are already in plant-local metres.
    """
    if sectors < 6:
        raise ValueError("Cylinder visuals require at least six sectors")
    vertices, uvs, faces, aliases = [], [], [], []
    for segment, (start, end, radius) in enumerate(segments):
        if radius <= 0:
            raise ValueError("Cylinder radius must be positive")
        direction = _unit(_sub(end, start))
        reference = (0.0, 0.0, 1.0) if abs(direction[2]) < 0.9 else (0.0, 1.0, 0.0)
        side = _unit(_cross(direction, reference))
        up = _cross(direction, side)
        base = len(vertices)
        for ring, center in enumerate((start, end)):
            for sector in range(sectors + 1):
                angle = math.tau * sector / sectors
                vertices.append(tuple(center[i] + radius * (math.cos(angle) * side[i] + math.sin(angle) * up[i])
                                      for i in range(3)))
                uvs.append((sector / sectors, float(ring)))
                aliases.append((segment, "side", ring, sector % sectors))
        for sector in range(sectors):
            a = base + sector
            b = a + 1
            c = a + sectors + 1
            d = c + 1
            faces.extend(((a, b, d), (a, d, c)))
        for cap, center in enumerate((start, end)):
            middle = len(vertices)
            vertices.append(tuple(center))
            uvs.append((0.5, 0.5))
            aliases.append((segment, "cap", cap))
            for sector in range(sectors):
                angle = math.tau * sector / sectors
                vertices.append(tuple(center[i] + radius * (math.cos(angle) * side[i] + math.sin(angle) * up[i])
                                      for i in range(3)))
                uvs.append((0.5 + 0.5 * math.cos(angle), 0.5 + 0.5 * math.sin(angle)))
                aliases.append((segment, "cap", cap))
            for sector in range(sectors):
                a, b = middle + 1 + sector, middle + 1 + (sector + 1) % sectors
                faces.append((middle, b, a) if cap == 0 else (middle, a, b))
    if not vertices:
        return f"# {VERSION}; empty cylinder batch\n"
    return _obj(vertices, uvs, faces, normal_aliases=aliases)


def plant_texture_preset(kind="leaf", state="", variant=0):
    """Map appearance state to existing material names, never to fruit maturity."""
    if kind == "leaf":
        return "leaf_senescent" if "senescent" in state else "leaf_healthy"
    if kind != "calyx":
        raise ValueError(f"Unsupported textured plant organ: {kind}")
    if "dry" in state or "papery" in state:
        prefix, count = "calyx_dry", 3
    elif "straw" in state:
        prefix, count = "calyx_straw", 3
    elif "transition" in state:
        prefix, count = "calyx_transition", 2
    else:
        prefix, count = "calyx_green", 4
    return f"{prefix}_v{variant % count}"


def texture_asset_paths(presets=None):
    """Return package-relative URI -> repository-relative PNG source paths.

    Pass used preset names to copy only necessary files.  This function does
    not read or write files; source hashes can be recorded by the packager.
    """
    result = {}
    for name in sorted(set(_PRESETS if presets is None else presets)):
        if name not in _PRESETS:
            raise ValueError(f"Unknown current plant texture preset: {name}")
        for kind in _MAP_KINDS:
            filename = f"{name}_{kind}.png"
            result[f"textures/{filename}"] = Path("assets") / "textures" / "current" / filename
    return result


def apply_plant_material(visual, kind="leaf", state="", variant=0, *, preset=None):
    """Replace only an SDF visual's material; return the selected texture preset."""
    name = preset or plant_texture_preset(kind, state, variant)
    if name not in _PRESETS:
        raise ValueError(f"Unknown current plant texture preset: {name}")
    for old in list(visual.findall("material")):
        visual.remove(old)
    material = ET.SubElement(visual, "material")
    for key, value in (("ambient", "1 1 1 1"), ("diffuse", "1 1 1 1"), ("specular", "0.04 0.04 0.04 1")):
        ET.SubElement(material, key).text = value
    metal = ET.SubElement(ET.SubElement(material, "pbr"), "metal")
    ET.SubElement(metal, "metalness").text = "0"
    ET.SubElement(metal, "roughness").text = str(_PRESETS[name].roughness)
    for map_kind in _MAP_KINDS:
        node = ET.SubElement(metal, f"{map_kind}_map")
        node.text = f"textures/{name}_{map_kind}.png"
        if map_kind == "normal":
            node.set("type", "tangent")
    return name


def _procedural_png(width, height, pixels, channels):
    """Encode original procedural RGB or grayscale pixels with standard PNG."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    stride = width * channels
    rows = b"".join(b"\x00" + bytes(pixels[y * stride:(y + 1) * stride]) for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2 if channels == 3 else 0, 0, 0, 0)
    comment = b"Comment\x00Original SyntheticPlantGeneration procedural soil; engineering_heuristic"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"tEXt", comment)
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def procedural_soil_assets(*, seed=SOIL_TEXTURE_SEED):
    """Create an unchanged flat ground envelope and seamless original soil maps.

    The 16 x 16 metre plane is centered at world (0, 2), z=0. Its material tiles
    eight times. Periodic, smoothly interpolated noise supplies broad earth
    variation and fine granules; no displacement, obstacles or physics are
    generated. Appearance and seed are explicit engineering heuristics.
    PNG bytes are original project assets generated without external sources.
    """
    size = 256
    rng = random.Random(seed)
    layers = [(frequency, weight, [rng.uniform(-1, 1) for _ in range(frequency * frequency)])
              for frequency, weight in ((4, 0.46), (11, 0.28), (29, 0.16), (83, 0.10))]

    def periodic_noise(x, y, frequency, lattice):
        sx, sy = x * frequency, y * frequency
        ix, iy = math.floor(sx), math.floor(sy)
        tx, ty = sx - ix, sy - iy
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = lattice[(iy % frequency) * frequency + ix % frequency]
        b = lattice[(iy % frequency) * frequency + (ix + 1) % frequency]
        c = lattice[((iy + 1) % frequency) * frequency + ix % frequency]
        d = lattice[((iy + 1) % frequency) * frequency + (ix + 1) % frequency]
        return (a + (b - a) * tx) * (1 - ty) + (c + (d - c) * tx) * ty

    albedo, roughness = bytearray(), bytearray()
    for y in range(size):
        for x in range(size):
            variation = sum(weight * periodic_noise(x / (size - 1), y / (size - 1), frequency, lattice)
                            for frequency, weight, lattice in layers)
            # Pixel-scale granules are periodic too, including identical edge pixels.
            grain_hash = ((x % (size - 1)) * 374761393 + (y % (size - 1)) * 668265263 + seed) & 0xFFFFFFFF
            grain_hash = ((grain_hash ^ (grain_hash >> 13)) * 1274126177) & 0xFFFFFFFF
            grain = ((grain_hash ^ (grain_hash >> 16)) & 65535) / 65535
            brightness = 24 * variation + 9 * (grain - 0.5)
            if grain < 0.025:
                brightness -= 15
            elif grain > 0.982:
                brightness += 12
            albedo.extend(max(0, min(255, round(base + brightness * tint)))
                          for base, tint in ((91, 1.0), (77, 0.88), (58, 0.69)))
            roughness.append(max(244, min(255, round(250 + 4 * variation + 3 * (grain - 0.5)))))
    vertices = [(-8, -6, 0), (8, -6, 0), (8, 10, 0), (-8, 10, 0)]
    return {
        "meshes": {"meshes/harvest_soil.obj": _obj(vertices, [(0, 0), (8, 0), (8, 8), (0, 8)], [(0, 1, 2), (0, 2, 3)])},
        "generated_binary_assets": {
            "textures/harvest_soil_albedo.png": _procedural_png(size, size, albedo, 3),
            "textures/harvest_soil_roughness.png": _procedural_png(size, size, roughness, 1),
        },
    }


def apply_soil_material(visual):
    """Apply rough original soil appearance to a visual; leave physics intact."""
    for old in list(visual.findall("material")):
        visual.remove(old)
    material = ET.SubElement(visual, "material")
    for key, value in (("ambient", "1 1 1 1"), ("diffuse", "1 1 1 1"), ("specular", "0.02 0.02 0.02 1")):
        ET.SubElement(material, key).text = value
    metal = ET.SubElement(ET.SubElement(material, "pbr"), "metal")
    ET.SubElement(metal, "metalness").text = "0"
    ET.SubElement(metal, "roughness").text = "0.98"
    for kind in ("albedo", "roughness"):
        ET.SubElement(metal, f"{kind}_map").text = f"textures/harvest_soil_{kind}.png"
