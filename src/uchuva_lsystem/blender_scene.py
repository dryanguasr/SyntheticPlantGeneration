"""Blender scene setup for the uchuva morphology preview."""

from __future__ import annotations

import math
import json
import random
from pathlib import Path

PROJECT_PREFIX = "uchuva_"
PROJECT_MATERIAL_PREFIX = "Uchuva_"


def _blender_modules():
    import bpy
    from mathutils import Vector

    return bpy, Vector


def cleanup_scene() -> None:
    """Clear generated objects and project materials from the active scene."""
    bpy, _ = _blender_modules()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    for material in list(bpy.data.materials):
        if material.name.startswith(PROJECT_MATERIAL_PREFIX):
            bpy.data.materials.remove(material, do_unlink=True)

    for data_collection in (
        bpy.data.meshes,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.curves,
        bpy.data.images,
    ):
        for datablock in list(data_collection):
            if (
                data_collection is bpy.data.images
                and datablock.get("uchuva_packed_asset")
            ):
                continue
            if datablock.users == 0:
                try:
                    data_collection.remove(datablock)
                except RuntimeError:
                    pass

    for collection in list(bpy.data.collections):
        if collection.name.startswith(PROJECT_PREFIX):
            bpy.data.collections.remove(collection)

    try:
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True,
            do_linked_ids=True,
            do_recursive=True,
        )
    except Exception:
        pass


def create_material(
    name: str,
    color: tuple[float, float, float, float],
    roughness: float = 0.65,
    metallic: float = 0.0,
) -> object:
    """Create or update a Blender material."""
    bpy, _ = _blender_modules()
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True

    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is not None:
        if "Base Color" in bsdf.inputs:
            bsdf.inputs["Base Color"].default_value = color
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic

    if color[3] < 1.0:
        try:
            material.blend_method = "BLEND"
            material.use_screen_refraction = True
            material.show_transparent_back = True
        except Exception:
            pass
    else:
        try:
            material.blend_method = "OPAQUE"
            material.use_screen_refraction = False
            material.show_transparent_back = False
        except Exception:
            pass

    return material


def create_project_materials(
    seed: int,
    texture_asset_dir: str | Path | None = None,
) -> dict[str, object]:
    """Create the material palette and attach generated 2D organ maps when available."""
    rng = random.Random(seed)
    materials = {
        "stem_green": create_material(
            "Uchuva_Tallo_verde",
            _jitter(_srgb_rgba((54, 91, 43)), rng, 0.010),
            roughness=0.82,
        ),
        "stem_dark_green": create_material(
            "Uchuva_Tallo_verde_oscuro",
            _jitter(_srgb_rgba((38, 69, 34)), rng, 0.009),
            roughness=0.84,
        ),
        "stem_drying_olive": create_material(
            "Uchuva_Tallo_secado_oliva",
            _jitter(_srgb_rgba((91, 83, 48)), rng, 0.010),
            roughness=0.87,
        ),
        "stem_drying_brown": create_material(
            "Uchuva_Tallo_secado_cafe",
            _jitter(_srgb_rgba((88, 59, 39)), rng, 0.010),
            roughness=0.89,
        ),
        "petiole_green": create_material(
            "Uchuva_Peciolo_verde",
            _jitter(_srgb_rgba((57, 96, 43)), rng, 0.010),
            roughness=0.83,
        ),
        "petiole_drying": create_material(
            "Uchuva_Peciolo_secado",
            _jitter(_srgb_rgba((93, 71, 43)), rng, 0.010),
            roughness=0.88,
        ),
        "leaf": create_material(
            "Uchuva_Hoja_verde",
            _jitter(_srgb_rgba((88, 112, 57)), rng, 0.010),
            roughness=0.94,
        ),
        "leaf_senescent": create_material(
            "Uchuva_Hoja_senescente",
            _jitter(_srgb_rgba((128, 124, 64)), rng, 0.012),
            roughness=0.96,
        ),
        "leaf_vein": create_material(
            "Uchuva_Nervadura",
            _jitter(_srgb_rgba((100, 121, 66)), rng, 0.008),
            roughness=0.84,
        ),
        "calyx": create_material(
            "Uchuva_Caliz_capacho_pajizo",
            _jitter(_srgb_rgba((199, 186, 121)), rng, 0.022),
            roughness=0.74,
        ),
        "calyx_inflated_green": create_material(
            "Uchuva_Caliz_inflado_verde",
            _jitter(_srgb_rgba((125, 141, 70)), rng, 0.018),
            roughness=0.93,
        ),
        "calyx_straw_yellow": create_material(
            "Uchuva_Caliz_amarillo_pajizo",
            _jitter(_srgb_rgba((199, 186, 121)), rng, 0.022),
            roughness=0.96,
        ),
        "calyx_dry_deteriorated": create_material(
            "Uchuva_Caliz_seco_deteriorado",
            _jitter(_srgb_rgba((168, 145, 103)), rng, 0.022),
            roughness=0.98,
        ),
        "calyx_rib": create_material(
            "Uchuva_Caliz_nervadura",
            _jitter(_srgb_rgba((112, 78, 62)), rng, 0.012),
            roughness=0.76,
        ),
        "calyx_rib_inflated_green": create_material(
            "Uchuva_Caliz_nervadura_verde",
            _jitter(_srgb_rgba((66, 58, 48)), rng, 0.010),
            roughness=0.70,
        ),
        "calyx_rib_straw_yellow": create_material(
            "Uchuva_Caliz_nervadura_pajiza",
            _jitter(_srgb_rgba((112, 78, 62)), rng, 0.010),
            roughness=0.76,
        ),
        "calyx_rib_dry_deteriorated": create_material(
            "Uchuva_Caliz_nervadura_seca",
            _jitter(_srgb_rgba((91, 64, 46)), rng, 0.010),
            roughness=0.84,
        ),
        "fruit_unripe": create_material(
            "Uchuva_Fruto_inmaduro",
            _jitter((0.62, 0.66, 0.12, 1.0), rng, 0.045),
            roughness=0.46,
        ),
        "fruit_ripe": create_material(
            "Uchuva_Fruto_maduro",
            _jitter((0.96, 0.54, 0.08, 1.0), rng, 0.055),
            roughness=0.4,
        ),
        "flower": create_material(
            "Uchuva_Flor_amarilla",
            _jitter((0.98, 0.82, 0.20, 1.0), rng, 0.035),
            roughness=0.62,
        ),
        "stake_wood": create_material(
            "Uchuva_Tutor_madera_rectangular",
            _jitter(_srgb_rgba((119, 92, 51)), rng, 0.010),
            roughness=0.92,
        ),
        "stake_tie": create_material(
            "Uchuva_Amarre_tutor",
            _jitter(_srgb_rgba((167, 157, 119)), rng, 0.008),
            roughness=0.91,
        ),
        "trellis_wire": create_material(
            "Uchuva_Alambre_trellis",
            _jitter(_srgb_rgba((91, 98, 94)), rng, 0.006),
            roughness=0.58,
            metallic=0.72,
        ),
    }
    materials["stem"] = materials["stem_green"]
    materials["petiole"] = materials["petiole_green"]
    materials["stake_bamboo"] = materials["stake_wood"]
    for key in (
        "stem_green",
        "stem_dark_green",
        "stem_drying_olive",
        "stem_drying_brown",
    ):
        _add_stem_surface_texture(materials[key], strength=0.07)
    _add_stem_surface_texture(materials["petiole_green"], strength=0.055)
    _add_stem_surface_texture(materials["petiole_drying"], strength=0.065)
    _configure_closed_calyx_sheet(materials["leaf"], 0.005, 0.0)
    _configure_closed_calyx_sheet(materials["leaf_senescent"], 0.003, 0.0)

    from .texture_assets import CALYX_TEXTURE_PRESETS

    for preset in CALYX_TEXTURE_PRESETS:
        materials[preset.name] = create_material(
            f"Uchuva_{preset.name}",
            _jitter(_srgb_rgba(preset.base_srgb), rng, 0.006),
            roughness=preset.roughness,
        )
        _configure_closed_calyx_sheet(
            materials[preset.name],
            preset.subsurface_weight,
            preset.sheen_weight,
        )
    materials["calyx"] = materials["calyx_straw_v1"]
    materials["calyx_inflated_green"] = materials["calyx_green_v1"]
    materials["calyx_transitioning_yellow"] = materials["calyx_transition_v0"]
    materials["calyx_straw_yellow"] = materials["calyx_straw_v1"]
    materials["calyx_dry_deteriorated"] = materials["calyx_dry_v1"]
    _add_fruit_surface_texture(materials["fruit_unripe"], scale=32.0, strength=0.025)
    _add_fruit_surface_texture(materials["fruit_ripe"], scale=36.0, strength=0.028)
    _apply_generated_organ_textures(materials, texture_asset_dir)
    return materials


def setup_camera_and_lights(
    plant_height: float,
    target: tuple[float, float, float] = (0.0, 0.0, 1.0),
    seed: int = 0,
    scene_radius: float = 3.0,
) -> tuple[object, object]:
    """Create a camera and a distant outdoor-like area light."""
    bpy, Vector = _blender_modules()
    rng = random.Random(seed + 5000)
    height = max(plant_height, 1.5)
    radius = max(scene_radius, 3.0)
    light_distance = rng.uniform(radius * 4.0, radius * 6.5)
    azimuth = rng.uniform(math.radians(135.0), math.radians(235.0))
    elevation = rng.uniform(math.radians(34.0), math.radians(58.0))
    light_location = (
        target[0] + light_distance * math.cos(azimuth) * math.cos(elevation),
        target[1] + light_distance * math.sin(azimuth) * math.cos(elevation),
        target[2] + light_distance * math.sin(elevation),
    )

    bpy.ops.object.light_add(type="AREA", location=light_location)
    light = bpy.context.object
    light.name = f"{PROJECT_PREFIX}luz_area_exterior"
    light.data.name = f"{PROJECT_PREFIX}luz_area_exterior_data"
    light.data.energy = rng.uniform(2400.0, 4200.0)
    light.data.size = rng.uniform(radius * 1.6, radius * 2.8)
    _look_at(light, target)

    bpy.ops.object.camera_add(location=(3.0, -5.2, height * 0.72))
    camera = bpy.context.object
    camera.name = f"{PROJECT_PREFIX}camara_principal"
    camera.data.name = f"{PROJECT_PREFIX}camara_principal_data"
    camera.data.lens = 55

    _look_at(camera, target)

    bpy.context.scene.camera = camera
    return camera, light


ANNOTATION_CAMERA_PROFILES = {
    "real_close": {
        "distance_factor": 0.82,
        "radius_factor": 1.25,
        "minimum_distance": 2.25,
        "azimuth_deg": -84.0,
        "azimuth_jitter_deg": 44.0,
        "elevation_deg": 8.0,
        "elevation_jitter_deg": 12.0,
        "lens_mm": 70.0,
        "lens_jitter_mm": 8.0,
        "fstop": 3.2,
    },
    "real_mid": {
        "distance_factor": 2.60,
        "radius_factor": 3.80,
        "minimum_distance": 8.00,
        "azimuth_deg": -78.0,
        "azimuth_jitter_deg": 52.0,
        "elevation_deg": 12.0,
        "elevation_jitter_deg": 13.0,
        "lens_mm": 92.0,
        "lens_jitter_mm": 12.0,
        "fstop": 4.5,
    },
    "real_context": {
        "distance_factor": 1.65,
        "radius_factor": 2.35,
        "minimum_distance": 4.70,
        "azimuth_deg": -72.0,
        "azimuth_jitter_deg": 58.0,
        "elevation_deg": 15.0,
        "elevation_jitter_deg": 14.0,
        "lens_mm": 38.0,
        "lens_jitter_mm": 7.0,
        "fstop": 6.3,
    },
    "robot_close_oblique": {
        "distance_factor": 1.35,
        "radius_factor": 2.0,
        "minimum_distance": 4.2,
        "azimuth_deg": -92.0,
        "azimuth_jitter_deg": 14.0,
        "elevation_deg": 10.0,
        "elevation_jitter_deg": 4.0,
        "lens_mm": 58.0,
        "lens_jitter_mm": 4.0,
        "fstop": 4.8,
    },
    "human_oblique_mid": {
        "distance_factor": 1.65,
        "radius_factor": 2.45,
        "minimum_distance": 5.6,
        "azimuth_deg": -78.0,
        "azimuth_jitter_deg": 18.0,
        "elevation_deg": 15.0,
        "elevation_jitter_deg": 5.0,
        "lens_mm": 50.0,
        "lens_jitter_mm": 4.0,
        "fstop": 5.6,
    },
    "context_wide": {
        "distance_factor": 2.15,
        "radius_factor": 3.05,
        "minimum_distance": 7.2,
        "azimuth_deg": -68.0,
        "azimuth_jitter_deg": 24.0,
        "elevation_deg": 18.0,
        "elevation_jitter_deg": 5.0,
        "lens_mm": 40.0,
        "lens_jitter_mm": 3.0,
        "fstop": 7.1,
    },
}


def create_annotation_cameras(
    *,
    target: tuple[float, float, float],
    plant_height: float,
    scene_radius: float,
    seed: int,
) -> dict[str, object]:
    """Create the three reproducible camera profiles used by the pilot."""
    bpy, _ = _blender_modules()
    cameras: dict[str, object] = {}
    for index, profile_name in enumerate(ANNOTATION_CAMERA_PROFILES):
        camera = create_annotation_camera(
            profile_name=profile_name,
            target=target,
            plant_height=plant_height,
            scene_radius=scene_radius,
            seed=seed + index * 997,
        )
        cameras[profile_name] = camera

    if cameras:
        bpy.context.scene.camera = cameras["robot_close_oblique"]
    return cameras


def create_annotation_camera(
    *,
    profile_name: str,
    target: tuple[float, float, float],
    plant_height: float,
    scene_radius: float,
    seed: int,
    name_suffix: str = "",
    target_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> object:
    """Create one reproducibly jittered camera for a dataset capture."""
    if profile_name not in ANNOTATION_CAMERA_PROFILES:
        raise ValueError(f"Unknown annotation camera profile: {profile_name}")
    bpy, Vector = _blender_modules()
    profile = ANNOTATION_CAMERA_PROFILES[profile_name]
    rng = random.Random(seed + 60_000)
    target = tuple(float(value) + float(offset) for value, offset in zip(target, target_offset))
    distance = max(
        plant_height * profile["distance_factor"],
        scene_radius * profile["radius_factor"],
        profile["minimum_distance"],
    )
    azimuth = math.radians(
        profile["azimuth_deg"]
        + rng.uniform(-profile["azimuth_jitter_deg"], profile["azimuth_jitter_deg"])
    )
    elevation = math.radians(
        profile["elevation_deg"]
        + rng.uniform(-profile["elevation_jitter_deg"], profile["elevation_jitter_deg"])
    )
    horizontal_distance = distance * math.cos(elevation)
    location = (
        target[0] + horizontal_distance * math.cos(azimuth),
        target[1] + horizontal_distance * math.sin(azimuth),
        target[2] + distance * math.sin(elevation),
    )
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    suffix = f"_{name_suffix}" if name_suffix else ""
    camera.name = f"{PROJECT_PREFIX}camera_{profile_name}{suffix}"
    camera.data.name = f"{camera.name}_data"
    camera.data.lens = profile["lens_mm"] + rng.uniform(
        -profile["lens_jitter_mm"], profile["lens_jitter_mm"]
    )
    camera.data.sensor_width = 36.0
    camera.data.clip_start = 0.05
    camera.data.clip_end = 120.0
    _look_at(camera, target)
    focus = bpy.data.objects.new(f"{camera.name}_focus", None)
    focus.location = Vector(target)
    focus.empty_display_size = 0.03
    focus.hide_viewport = True
    focus.hide_render = True
    bpy.context.scene.collection.objects.link(focus)
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = focus
    camera.data.dof.aperture_fstop = profile["fstop"]
    camera["uchuva_camera_profile"] = profile_name
    camera["uchuva_seed"] = seed
    camera["uchuva_azimuth_deg"] = math.degrees(azimuth)
    camera["uchuva_elevation_deg"] = math.degrees(elevation)
    return camera


def _look_at(obj: object, target: tuple[float, float, float]) -> None:
    _, Vector = _blender_modules()
    direction = Vector(target) - obj.location
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_render_settings(width: int = 1280, height: int = 960) -> None:
    """Set conservative render defaults for preview scenes."""
    bpy, _ = _blender_modules()
    scene = bpy.context.scene
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    if scene.world is not None:
        scene.world.color = (0.035, 0.035, 0.035)
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"


def save_blend_file(output_path: str | Path) -> Path:
    """Save the active Blender scene to a .blend file."""
    bpy, _ = _blender_modules()
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    return path


def _jitter(
    color: tuple[float, float, float, float],
    rng: random.Random,
    amount: float,
) -> tuple[float, float, float, float]:
    r, g, b, a = color
    return (
        _clamp01(r + rng.uniform(-amount, amount)),
        _clamp01(g + rng.uniform(-amount, amount)),
        _clamp01(b + rng.uniform(-amount, amount)),
        a,
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _srgb_rgba(rgb: tuple[int, int, int]) -> tuple[float, float, float, float]:
    """Convert authored sRGB bytes to Blender's linear fallback color."""
    linear = []
    for channel in rgb:
        value = channel / 255.0
        linear.append(
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
        )
    return linear[0], linear[1], linear[2], 1.0


def _apply_generated_organ_textures(
    materials: dict[str, object],
    texture_asset_dir: str | Path | None,
) -> dict[str, object]:
    """Attach auditable PNG maps, retaining procedural nodes as a fallback."""
    default_dir = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "textures"
        / "current"
    )
    asset_dir = Path(texture_asset_dir) if texture_asset_dir is not None else default_dir
    manifest_path = asset_dir / "manifest.json"
    manifest: dict[str, object] | None = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None

    assignments: dict[str, tuple[str, str]] = {
        "leaf": ("leaf_healthy", "leaf_uv"),
        "leaf_senescent": ("leaf_senescent", "leaf_uv"),
    }
    if manifest is not None:
        for preset_name, item in manifest.get("texture_sets", {}).items():
            if (
                isinstance(item, dict)
                and isinstance(item.get("preset"), dict)
                and item["preset"].get("organ") == "calyx"
                and preset_name in materials
            ):
                assignments[preset_name] = (preset_name, "calyx_uv")
    applied: dict[str, object] = {}
    for material_key, (preset_name, uv_map_name) in assignments.items():
        material = materials.get(material_key)
        if material is None:
            continue
        item = None
        if manifest is not None:
            item = manifest.get("texture_sets", {}).get(preset_name)
        report = _configure_image_texture_set(
            material,
            preset_name=preset_name,
            uv_map_name=uv_map_name,
            asset_dir=asset_dir,
            manifest_item=item if isinstance(item, dict) else None,
        )
        applied[material_key] = report
    return applied


def _configure_image_texture_set(
    material: object,
    *,
    preset_name: str,
    uv_map_name: str,
    asset_dir: Path,
    manifest_item: dict[str, object] | None,
) -> dict[str, object]:
    bpy, _ = _blender_modules()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return {"status": "missing_principled_bsdf"}
    files = manifest_item.get("files", {}) if manifest_item else {}
    file_names = {
        map_name: str(files.get(map_name, f"{preset_name}_{map_name}.png"))
        for map_name in ("albedo", "normal", "roughness")
    }
    images = {}
    for map_name, file_name in file_names.items():
        image = _load_generated_texture_image(
            preset_name=preset_name,
            map_name=map_name,
            path=asset_dir / file_name,
            non_color=map_name != "albedo",
        )
        if image is not None:
            images[map_name] = image
    if "albedo" not in images or "normal" not in images or "roughness" not in images:
        return {"status": "procedural_fallback", "loaded_maps": sorted(images)}

    uv = nodes.new(type="ShaderNodeUVMap")
    uv.name = f"{preset_name}_uv"
    uv.uv_map = uv_map_name
    extension = "REPEAT" if uv_map_name == "calyx_uv" else "EXTEND"
    texture_nodes = {}
    for map_name, image in images.items():
        node = nodes.new(type="ShaderNodeTexImage")
        node.name = f"{preset_name}_{map_name}"
        node.label = f"{preset_name} {map_name}"
        node.image = image
        node.extension = extension
        node.interpolation = "Linear"
        links.new(uv.outputs["UV"], node.inputs["Vector"])
        texture_nodes[map_name] = node
    links.new(texture_nodes["albedo"].outputs["Color"], bsdf.inputs["Base Color"])
    links.new(texture_nodes["roughness"].outputs["Color"], bsdf.inputs["Roughness"])
    normal_map = nodes.new(type="ShaderNodeNormalMap")
    normal_map.name = f"{preset_name}_tangent_normal"
    normal_map.uv_map = uv_map_name
    normal_strength = _organ_normal_strength(preset_name)
    normal_map.inputs["Strength"].default_value = normal_strength
    links.new(texture_nodes["normal"].outputs["Color"], normal_map.inputs["Color"])
    micro_noise = nodes.new(type="ShaderNodeTexNoise")
    micro_noise.name = f"{preset_name}_pubescent_microrelief"
    micro_noise.inputs["Scale"].default_value = (
        118.0 if preset_name.startswith("calyx_") else 156.0
    )
    micro_noise.inputs["Detail"].default_value = 3.2
    micro_noise.inputs["Roughness"].default_value = 0.78
    micro_bump = nodes.new(type="ShaderNodeBump")
    micro_bump.name = f"{preset_name}_pubescent_micro_bump"
    micro_bump.inputs["Strength"].default_value = (
        0.16 if preset_name.startswith("calyx_") else 0.09
    )
    micro_bump.inputs["Distance"].default_value = 0.001
    links.new(uv.outputs["UV"], micro_noise.inputs["Vector"])
    links.new(micro_noise.outputs["Fac"], micro_bump.inputs["Height"])
    links.new(normal_map.outputs["Normal"], micro_bump.inputs["Normal"])
    links.new(micro_bump.outputs["Normal"], bsdf.inputs["Normal"])

    preset = manifest_item.get("preset", {}) if manifest_item else {}
    for input_name, key in (
        ("IOR", "ior"),
        ("Subsurface Weight", "subsurface_weight"),
        ("Sheen Weight", "sheen_weight"),
        ("Specular IOR Level", "specular_ior_level"),
    ):
        if input_name in bsdf.inputs and key in preset:
            bsdf.inputs[input_name].default_value = float(preset[key])
    material["uchuva_texture_preset"] = preset_name
    _configure_matte_principled(bsdf)
    material["uchuva_texture_generator_version"] = "0.4.3"
    material["uchuva_texture_asset_dir"] = str(asset_dir)
    material["uchuva_normal_strength"] = normal_strength
    material["uchuva_normal_strength_status"] = "engineering_heuristic"
    material["uchuva_texture_interpolation"] = "Linear"
    material["uchuva_pubescent_microrelief"] = True
    return {
        "status": "generated_maps",
        "loaded_maps": sorted(images),
        "normal_strength": normal_strength,
        "normal_strength_status": "engineering_heuristic",
        "interpolation": "Linear",
    }


def _organ_normal_strength(preset_name: str) -> float:
    """Return conservative per-organ normal strength for final review renders."""
    if preset_name.startswith("leaf_"):
        return 0.22
    if preset_name.startswith("calyx_green"):
        return 0.22
    if preset_name.startswith("calyx_transition"):
        return 0.23
    if preset_name.startswith("calyx_straw"):
        return 0.24
    if preset_name.startswith("calyx_dry"):
        return 0.28
    return 0.25


def _load_generated_texture_image(
    *,
    preset_name: str,
    map_name: str,
    path: Path,
    non_color: bool,
) -> object | None:
    bpy, _ = _blender_modules()
    internal_name = f"UchuvaTexture_{preset_name}_{map_name}"
    image = bpy.data.images.get(internal_name)
    if image is None and path.is_file():
        try:
            image = bpy.data.images.load(str(path), check_existing=False)
            image.name = internal_name
        except RuntimeError:
            image = None
    if image is None:
        return None
    image["uchuva_packed_asset"] = True
    image["uchuva_asset_key"] = f"texture:{preset_name}:{map_name}"
    image["uchuva_asset_license"] = "generated_project_asset"
    image["uchuva_texture_generator_version"] = "0.4.3"
    try:
        image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    except TypeError:
        pass
    return image


def _add_leaf_surface_texture(material: object) -> None:
    """Add directional procedural minor veins/bump to a leaf material."""
    bpy, _ = _blender_modules()
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return

    base = tuple(float(value) for value in bsdf.inputs["Base Color"].default_value)
    color_noise = nodes.new(type="ShaderNodeTexNoise")
    color_noise.name = "leaf_mottled_color"
    color_noise.inputs["Scale"].default_value = 5.5
    color_noise.inputs["Detail"].default_value = 5.0
    color_noise.inputs["Roughness"].default_value = 0.72
    color_ramp = nodes.new(type="ShaderNodeValToRGB")
    color_ramp.name = "leaf_mottled_color_ramp"
    color_ramp.color_ramp.elements[0].position = 0.28
    color_ramp.color_ramp.elements[0].color = tuple(
        _clamp01(value * 0.52) for value in base[:3]
    ) + (1.0,)
    color_ramp.color_ramp.elements[1].position = 0.78
    color_ramp.color_ramp.elements[1].color = tuple(
        _clamp01(value * 1.18 + 0.015) for value in base[:3]
    ) + (1.0,)
    links.new(color_noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])

    wave = nodes.new(type="ShaderNodeTexWave")
    wave.name = "minor_leaf_veins_directional"
    wave.inputs["Scale"].default_value = 18.0
    wave.inputs["Distortion"].default_value = 8.0
    try:
        wave.bands_direction = "DIAGONAL"
    except Exception:
        pass

    ramp = nodes.new(type="ShaderNodeValToRGB")
    ramp.name = "minor_leaf_vein_mask"
    ramp.color_ramp.elements[0].position = 0.43
    ramp.color_ramp.elements[0].color = (0.06, 0.06, 0.06, 1.0)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.42, 0.42, 0.42, 1.0)

    bump = nodes.new(type="ShaderNodeBump")
    bump.name = "minor_leaf_vein_bump"
    bump.inputs["Strength"].default_value = 0.022
    bump.inputs["Distance"].default_value = 0.012

    links.new(wave.outputs["Color"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _add_stem_surface_texture(material: object, strength: float) -> None:
    """Add longitudinal micro-relief that reads as subtle pubescence."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return
    wave = nodes.new(type="ShaderNodeTexWave")
    wave.name = "stem_longitudinal_ridges"
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 46.0
    wave.inputs["Distortion"].default_value = 5.0
    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.name = "stem_pubescence_noise"
    noise.inputs["Scale"].default_value = 92.0
    noise.inputs["Detail"].default_value = 4.0
    mix = nodes.new(type="ShaderNodeMath")
    mix.operation = "MULTIPLY"
    bump = nodes.new(type="ShaderNodeBump")
    bump.name = "stem_pubescence_bump"
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.012
    links.new(wave.outputs["Fac"], mix.inputs[0])
    links.new(noise.outputs["Fac"], mix.inputs[1])
    links.new(mix.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _configure_closed_calyx_sheet(
    material: object,
    subsurface_weight: float,
    sheen_weight: float,
) -> None:
    """Give the opaque closed husk a thin fibrous response without alpha."""
    nodes = material.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return
    _configure_matte_principled(bsdf)
    for input_name in ("Subsurface Weight", "Subsurface"):
        if input_name in bsdf.inputs:
            bsdf.inputs[input_name].default_value = subsurface_weight
            break
    for input_name in ("Sheen Weight", "Sheen"):
        if input_name in bsdf.inputs:
            # A small grazing lobe helps pubescent/papery organs read without
            # restoring the hard glossy response users identified as plastic.
            bsdf.inputs[input_name].default_value = min(0.08, sheen_weight)
            break
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 1.0


def _configure_matte_principled(bsdf: object) -> None:
    """Remove glossy lobes while retaining an opaque diffuse plant response."""
    for input_name, value in (
        ("Coat Weight", 0.0),
        ("Sheen Weight", 0.0),
        ("Transmission Weight", 0.0),
        ("Specular IOR Level", 0.15),
    ):
        if input_name in bsdf.inputs:
            bsdf.inputs[input_name].default_value = value


def _add_calyx_surface_texture(
    material: object,
    vein_scale: float,
    spot_scale: float,
    strength: float,
) -> None:
    """Add procedural secondary venation and spots to a capacho material."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return


    base = tuple(float(value) for value in bsdf.inputs["Base Color"].default_value)
    color_noise = nodes.new(type="ShaderNodeTexNoise")
    color_noise.name = "calyx_fibrous_color"
    color_noise.inputs["Scale"].default_value = max(5.0, vein_scale * 0.42)
    color_noise.inputs["Detail"].default_value = 6.0
    color_noise.inputs["Roughness"].default_value = 0.68
    color_ramp = nodes.new(type="ShaderNodeValToRGB")
    color_ramp.name = "calyx_fibrous_color_ramp"
    color_ramp.color_ramp.elements[0].position = 0.30
    color_ramp.color_ramp.elements[0].color = tuple(
        _clamp01(value * 0.62) for value in base[:3]
    ) + (1.0,)
    color_ramp.color_ramp.elements[1].position = 0.74
    color_ramp.color_ramp.elements[1].color = tuple(
        _clamp01(value * 1.22 + 0.012) for value in base[:3]
    ) + (1.0,)
    links.new(color_noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])

    wave = nodes.new(type="ShaderNodeTexWave")
    wave.name = "secondary_calyx_veins"
    wave.inputs["Scale"].default_value = vein_scale
    wave.inputs["Distortion"].default_value = 10.0
    try:
        wave.bands_direction = "Z"
    except Exception:
        pass

    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.name = "calyx_spots_noise"
    noise.inputs["Scale"].default_value = spot_scale
    noise.inputs["Detail"].default_value = 10.0
    noise.inputs["Roughness"].default_value = 0.62

    vein_weight = nodes.new(type="ShaderNodeMath")
    vein_weight.name = "secondary_vein_weight"
    vein_weight.operation = "MULTIPLY"
    vein_weight.inputs[1].default_value = 0.68

    spot_weight = nodes.new(type="ShaderNodeMath")
    spot_weight.name = "spot_weight"
    spot_weight.operation = "MULTIPLY"
    spot_weight.inputs[1].default_value = 0.32

    combined = nodes.new(type="ShaderNodeMath")
    combined.name = "calyx_texture_height"
    combined.operation = "ADD"

    bump = nodes.new(type="ShaderNodeBump")
    bump.name = "calyx_secondary_vein_bump"
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.022

    links.new(wave.outputs["Fac"], vein_weight.inputs[0])
    links.new(noise.outputs["Fac"], spot_weight.inputs[0])
    links.new(vein_weight.outputs["Value"], combined.inputs[0])
    links.new(spot_weight.outputs["Value"], combined.inputs[1])
    links.new(combined.outputs["Value"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _add_fruit_surface_texture(
    material: object,
    scale: float,
    strength: float,
) -> None:
    """Add subtle procedural speckling/bump to fruit materials."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return

    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.name = "fruit_subtle_speckles"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.56

    bump = nodes.new(type="ShaderNodeBump")
    bump.name = "fruit_micro_bump"
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = 0.018

    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
