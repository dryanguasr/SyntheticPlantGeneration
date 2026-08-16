"""Hybrid outdoor environment for the annotation foreground pilot."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

from .blender_annotations import tag_annotation_object


ASSET_MANIFEST: dict[str, dict[str, Any]] = {
    "soil_diffuse": {
        "asset": "brown_mud",
        "source_page": "https://polyhaven.com/a/brown_mud",
        "license": "CC0",
        "resolution": "2k",
        "filename": "brown_mud_diff_2k.jpg",
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/brown_mud/brown_mud_diff_2k.jpg",
        "md5": "d0c4ee4434b871483e28ad9caecdc54c",
        "internal_name": "UchuvaAsset_brown_mud_diff_2k",
    },
    "soil_normal": {
        "asset": "brown_mud",
        "source_page": "https://polyhaven.com/a/brown_mud",
        "license": "CC0",
        "resolution": "2k",
        "filename": "brown_mud_nor_gl_2k.jpg",
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/brown_mud/brown_mud_nor_gl_2k.jpg",
        "md5": "8aae228fc929498090cd61613533828e",
        "internal_name": "UchuvaAsset_brown_mud_nor_gl_2k",
    },
    "soil_roughness": {
        "asset": "brown_mud",
        "source_page": "https://polyhaven.com/a/brown_mud",
        "license": "CC0",
        "resolution": "2k",
        "filename": "brown_mud_rough_2k.jpg",
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/brown_mud/brown_mud_rough_2k.jpg",
        "md5": "21ecf37d5f307626d7b3fee3af4d9d08",
        "internal_name": "UchuvaAsset_brown_mud_rough_2k",
    },
    "outdoor_hdri": {
        "asset": "farmland_overcast",
        "source_page": "https://polyhaven.com/a/farmland_overcast",
        "license": "CC0",
        "resolution": "2k",
        "filename": "farmland_overcast_2k.hdr",
        "url": "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/farmland_overcast_2k.hdr",
        "md5": "2a2d209d4329d68c8bb7eacc7b6ea5e1",
        "internal_name": "UchuvaAsset_farmland_overcast_2k",
    },
}


LIGHTING_PROFILES: dict[str, dict[str, Any]] = {
    "overcast_soft": {
        "azimuth_deg": (0.0, 360.0),
        "elevation_deg": (35.0, 65.0),
        "sun_energy": (0.15, 0.45),
        "sun_angle_deg": (10.0, 18.0),
        "world_strength": (0.68, 0.92),
        "sun_color": (0.90, 0.95, 1.0),
    },
    "clear_morning": {
        "azimuth_deg": (70.0, 120.0),
        "elevation_deg": (18.0, 32.0),
        "sun_energy": (1.4, 2.4),
        "sun_angle_deg": (2.0, 5.0),
        "world_strength": (0.42, 0.65),
        "sun_color": (1.0, 0.72, 0.48),
    },
    "clear_midday": {
        "azimuth_deg": (130.0, 230.0),
        "elevation_deg": (55.0, 72.0),
        "sun_energy": (2.2, 3.4),
        "sun_angle_deg": (1.0, 3.0),
        "world_strength": (0.40, 0.62),
        "sun_color": (1.0, 0.96, 0.90),
    },
    "late_afternoon": {
        "azimuth_deg": (240.0, 295.0),
        "elevation_deg": (14.0, 28.0),
        "sun_energy": (1.1, 2.2),
        "sun_angle_deg": (2.0, 6.0),
        "world_strength": (0.34, 0.58),
        "sun_color": (1.0, 0.62, 0.38),
    },
}


GROUND_VEGETATION_PROFILES: dict[str, list[dict[str, Any]]] = {
    "isolated_neutral": [
        {
            "name": "lolium_perenne_like",
            "count": 18,
            "height_range": (0.18, 0.62),
            "width_range": (0.002, 0.006),
            "material": "lolium",
        },
        {
            "name": "kikuyu_like",
            "count": 12,
            "height_range": (0.03, 0.15),
            "width_range": (0.001, 0.005),
            "material": "kikuyu",
        },
    ],
    "open_field_hybrid": [
        {
            "name": "lolium_perenne_like",
            "count": 320,
            "height_range": (0.20, 0.90),
            "width_range": (0.002, 0.006),
            "material": "lolium",
        },
        {
            "name": "kikuyu_like",
            "count": 280,
            "height_range": (0.03, 0.16),
            "width_range": (0.001, 0.005),
            "material": "kikuyu",
        },
        {
            "name": "broadleaf_weeds_like",
            "count": 160,
            "height_range": (0.16, 0.54),
            "width_range": (0.090, 0.240),
            "material": "weed",
        },
    ],
    "canopy_close": [
        {
            "name": "lolium_perenne_like",
            "count": 420,
            "height_range": (0.22, 0.90),
            "width_range": (0.002, 0.006),
            "material": "lolium",
        },
        {
            "name": "kikuyu_like",
            "count": 380,
            "height_range": (0.03, 0.16),
            "width_range": (0.001, 0.005),
            "material": "kikuyu",
        },
        {
            "name": "broadleaf_weeds_like",
            "count": 220,
            "height_range": (0.18, 0.60),
            "width_range": (0.100, 0.280),
            "material": "weed",
        },
    ],
    "ground_tangle": [
        {
            "name": "lolium_perenne_like",
            "count": 500,
            "height_range": (0.24, 0.90),
            "width_range": (0.002, 0.006),
            "material": "lolium",
        },
        {
            "name": "kikuyu_like",
            "count": 480,
            "height_range": (0.03, 0.16),
            "width_range": (0.001, 0.005),
            "material": "kikuyu",
        },
        {
            "name": "broadleaf_weeds_like",
            "count": 260,
            "height_range": (0.20, 0.64),
            "width_range": (0.110, 0.310),
            "material": "weed",
        },
    ],
}


def _blender_modules():
    import bpy
    from mathutils import Vector

    return bpy, Vector


def load_environment_assets(
    asset_dir: str | Path | None = None,
    *,
    packed_asset_blend: str | Path | None = None,
) -> dict[str, Any]:
    """Load CC0 images from disk or reuse images already packed in the .blend."""
    bpy, _ = _blender_modules()
    asset_root = Path(asset_dir) if asset_dir is not None else None
    carrier_path = (
        Path(packed_asset_blend)
        if packed_asset_blend is not None
        else None
    )
    if carrier_path is not None and carrier_path.is_file():
        requested_names = [
            spec["internal_name"]
            for spec in ASSET_MANIFEST.values()
            if bpy.data.images.get(spec["internal_name"]) is None
        ]
        if requested_names:
            try:
                with bpy.data.libraries.load(
                    str(carrier_path), link=False
                ) as (data_from, data_to):
                    available = set(data_from.images)
                    data_to.images = [
                        name for name in requested_names if name in available
                    ]
            except (OSError, RuntimeError):
                pass
    images: dict[str, object] = {}
    missing: list[str] = []

    for key, spec in ASSET_MANIFEST.items():
        image = bpy.data.images.get(spec["internal_name"])
        candidate = asset_root / spec["filename"] if asset_root else None
        if image is None and candidate is not None and candidate.exists():
            image = bpy.data.images.load(str(candidate), check_existing=False)
            image.name = spec["internal_name"]
            image["uchuva_packed_asset"] = True
            image["uchuva_asset_key"] = key
            image["uchuva_asset_license"] = spec["license"]
            image.pack()
            image.filepath = f"//packed_assets/{spec['filename']}"
        if image is None:
            missing.append(key)
            continue
        image["uchuva_packed_asset"] = True
        image["uchuva_asset_key"] = key
        if key in {"soil_normal", "soil_roughness"}:
            try:
                image.colorspace_settings.name = "Non-Color"
            except TypeError:
                pass
        images[key] = image

    return {
        "images": images,
        "missing": missing,
        "packed": {
            key: bool(image.packed_file) for key, image in images.items()
        },
        "manifest": ASSET_MANIFEST,
        "packed_asset_carrier": (
            str(carrier_path.resolve())
            if carrier_path is not None and carrier_path.is_file()
            else None
        ),
    }


def create_outdoor_environment(
    *,
    seed: int,
    scene_radius: float,
    terrain_size: float,
    terrain_subdivisions: int,
    background_cluster_count: int,
    asset_dir: str | Path | None = None,
    packed_asset_blend: str | Path | None = None,
    mode: str = "open_field_hybrid",
    background_style: str = "layered_understory_v2",
) -> dict[str, Any]:
    """Create soil, debris, distant vegetation, HDRI world, and distant sun."""
    if background_style not in {"legacy_green_carpet", "layered_understory_v2"}:
        raise ValueError(f"Unknown background style: {background_style}")
    bpy, _ = _blender_modules()
    rng = random.Random(seed + 70_000)
    assets = load_environment_assets(
        asset_dir,
        packed_asset_blend=packed_asset_blend,
    )
    collection = bpy.data.collections.new("uchuva_environment")
    bpy.context.scene.collection.children.link(collection)

    soil_material = _create_soil_material(assets["images"], seed)
    terrain_surface_profile = _terrain_surface_profile(mode)
    terrain_material = (
        _create_vegetated_ground_material(
            seed,
            assets["images"],
            layered=background_style == "layered_understory_v2",
        )
        if terrain_surface_profile == "green_pasture_understory"
        else soil_material
    )
    background_materials = _create_background_materials(seed, background_style)
    effective_terrain_size = _effective_terrain_size(terrain_size, scene_radius)
    effective_subdivisions = max(
        18,
        terrain_subdivisions,
        min(120, int(math.ceil(effective_terrain_size * 2.0))),
    )
    terrain = _create_terrain_mesh(
        seed=seed,
        size=effective_terrain_size,
        subdivisions=effective_subdivisions,
        material=terrain_material,
        collection=collection,
    )
    rocks = _scatter_rocks(rng, terrain_size, soil_material, collection)
    debris = _scatter_debris(
        rng,
        terrain_size,
        background_materials["dry"],
        collection,
        terrain_seed=seed,
        irregular=background_style == "layered_understory_v2",
    )
    ground_vegetation: list[dict[str, Any]] = []
    for item in _ground_vegetation_plan(mode):
        blade_count = _scatter_grasses(
            rng,
            terrain_size,
            background_materials[item["material"]],
            collection,
            count=item["count"],
            name=item["name"],
            height_range=item["height_range"],
            width_range=item["width_range"],
            background_fraction=0.42 if mode != "isolated_neutral" else 0.0,
        )
        ground_vegetation.append(
            {
                "profile": item["name"],
                "blade_count": blade_count,
                "height_range": list(item["height_range"]),
                "width_range": list(item["width_range"]),
                "parameter_status": "manual_initial_guess",
            }
        )
    grasses = sum(item["blade_count"] for item in ground_vegetation)
    # Do not add the former polygonal canopy clusters or cylindrical green
    # enclosure. They produced recognizable flat leaves, vertical tubes, and a
    # uniform green wall. The packed CC0 agricultural HDRI now supplies the
    # distant field/sky while explicit morphology and ground weeds supply
    # finite-depth occlusion.
    background: list[object] = []
    vegetated_backdrop = None
    world_report = _setup_world(assets["images"].get("outdoor_hdri"), rng)
    sun = _create_distant_sun(rng)
    neutral_backdrop = (
        _create_neutral_backdrop(background_materials["dry"], collection)
        if mode == "isolated_neutral"
        else None
    )

    return {
        "mode": mode,
        "background_style": background_style,
        "terrain_object": terrain.name,
        "terrain_size_requested": round(terrain_size, 3),
        "terrain_size": round(effective_terrain_size, 3),
        "terrain_subdivisions": effective_subdivisions,
        "terrain_edge_guard": "camera_outside_patch_prevented",
        "rock_count": len(rocks),
        "debris_count": len(debris),
        "grass_blade_count": grasses,
        "ground_vegetation_profile": (
            "layered_soil_pasture_weeds_and_leaf_litter"
            if background_style == "layered_understory_v2"
            else "mixed_pasture_and_weeds"
        ),
        "terrain_surface_profile": terrain_surface_profile,
        "terrain_surface_parameter_status": "dataset_observed_manual_initial_guess",
        "ground_vegetation": ground_vegetation,
        "background_object_count": len(background),
        "background_canopy_policy": "cc0_agricultural_hdri_no_low_poly_canopy",
        "vegetated_backdrop": (
            vegetated_backdrop.name if vegetated_backdrop is not None else None
        ),
        "neutral_backdrop": neutral_backdrop.name if neutral_backdrop else None,
        "sun": sun,
        "world": world_report,
        "assets": {
            "loaded": sorted(assets["images"]),
            "missing": assets["missing"],
            "packed": assets["packed"],
            "manifest": assets["manifest"],
            "packed_asset_carrier": assets["packed_asset_carrier"],
        },
    }


def _effective_terrain_size(terrain_size: float, scene_radius: float) -> float:
    """Return a ground extent that stays beyond all current camera footprints.

    Current cameras clip at 120 Blender units. A 260-unit square leaves 130
    units from the center to every edge, so the rasterizer clips the ground
    before any square boundary can enter the image, even after target jitter.
    """
    return max(float(terrain_size), float(scene_radius) * 8.0, 260.0)


def pack_environment_assets() -> dict[str, bool]:
    """Pack all tagged CC0 image datablocks and return their packed state."""
    bpy, _ = _blender_modules()
    states: dict[str, bool] = {}
    for image in bpy.data.images:
        if not image.get("uchuva_packed_asset"):
            continue
        if not image.packed_file:
            try:
                image.pack()
            except RuntimeError:
                pass
        states[image.name] = bool(image.packed_file)
    return states


def apply_lighting_profile(profile_name: str, seed: int) -> dict[str, Any]:
    """Apply one deterministic outdoor-lighting capture profile."""
    if profile_name not in LIGHTING_PROFILES:
        raise ValueError(f"Unknown lighting profile: {profile_name}")
    bpy, _ = _blender_modules()
    rng = random.Random(seed + 90_000)
    profile = LIGHTING_PROFILES[profile_name]
    light = bpy.data.objects.get("uchuva_sun_exterior")
    if light is None or light.type != "LIGHT" or light.data.type != "SUN":
        raise RuntimeError("Outdoor sun is missing; create the environment first.")

    azimuth_deg = rng.uniform(*profile["azimuth_deg"])
    elevation_deg = rng.uniform(*profile["elevation_deg"])
    energy = rng.uniform(*profile["sun_energy"])
    angle_deg = rng.uniform(*profile["sun_angle_deg"])
    light.rotation_euler = (
        math.radians(elevation_deg),
        0.0,
        math.radians(azimuth_deg),
    )
    light.data.energy = energy
    light.data.angle = math.radians(angle_deg)
    light.data.color = profile["sun_color"]

    world = bpy.context.scene.world
    background = None
    mapping = None
    if world is not None and world.use_nodes:
        background = world.node_tree.nodes.get("Uchuva_Outdoor_Background")
        mapping = world.node_tree.nodes.get("Uchuva_HDRI_Mapping")
    world_strength = rng.uniform(*profile["world_strength"])
    hdri_rotation_deg = rng.uniform(0.0, 360.0)
    if background is not None:
        background.inputs["Strength"].default_value = world_strength
    if mapping is not None:
        mapping.inputs["Rotation"].default_value[2] = math.radians(hdri_rotation_deg)

    exposure = rng.uniform(-0.35, 0.35)
    bpy.context.scene.view_settings.exposure = exposure
    return {
        "profile": profile_name,
        "seed": seed,
        "azimuth_deg": round(azimuth_deg, 4),
        "elevation_deg": round(elevation_deg, 4),
        "sun_energy": round(energy, 4),
        "sun_angle_deg": round(angle_deg, 4),
        "sun_color": [round(value, 4) for value in profile["sun_color"]],
        "world_strength": round(world_strength, 4),
        "hdri_rotation_deg": round(hdri_rotation_deg, 4),
        "exposure_ev": round(exposure, 4),
        "parameter_status": "manual_initial_guess",
    }


def _create_soil_material(images: dict[str, object], seed: int) -> object:
    bpy, _ = _blender_modules()
    rng = random.Random(seed + 71_000)
    name = "Uchuva_Suelo_agricola_PBR"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new(type="ShaderNodeOutputMaterial")
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (
        0.13 + rng.uniform(-0.015, 0.015),
        0.085 + rng.uniform(-0.01, 0.01),
        0.045,
        1.0,
    )
    bsdf.inputs["Roughness"].default_value = 0.92
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    texture_coordinate = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    # Object coordinates preserve soil texel density when the edge-guard mesh
    # grows; Generated coordinates would stretch 2.8 repeats over 260 units.
    mapping.inputs["Scale"].default_value = (0.45, 0.45, 0.45)
    links.new(texture_coordinate.outputs["Object"], mapping.inputs["Vector"])

    diffuse = images.get("soil_diffuse")
    if diffuse is not None:
        node = nodes.new(type="ShaderNodeTexImage")
        node.image = diffuse
        node.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        links.new(node.outputs["Color"], bsdf.inputs["Base Color"])

    roughness = images.get("soil_roughness")
    if roughness is not None:
        node = nodes.new(type="ShaderNodeTexImage")
        node.image = roughness
        node.extension = "REPEAT"
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        links.new(node.outputs["Color"], bsdf.inputs["Roughness"])

    normal = images.get("soil_normal")
    if normal is not None:
        image_node = nodes.new(type="ShaderNodeTexImage")
        image_node.image = normal
        image_node.extension = "REPEAT"
        normal_map = nodes.new(type="ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = 0.42
        links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def _terrain_surface_profile(mode: str) -> str:
    """Select the visible ground family without using real dataset pixels."""
    return (
        "neutral_soil_reference"
        if mode == "isolated_neutral"
        else "green_pasture_understory"
    )


def _create_vegetated_ground_material(
    seed: int,
    images: dict[str, object] | None = None,
    *,
    layered: bool = True,
) -> object:
    """Create a multi-scale soil/pasture mosaic without real-image pixels."""
    bpy, _ = _blender_modules()
    rng = random.Random(seed + 71_500)
    name = (
        "Uchuva_Sotobosque_estratificado_v2"
        if layered
        else "Uchuva_Cubierta_verde_pasto_maleza"
    )
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.94
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    coordinates = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.72, 0.72, 0.72)
    links.new(coordinates.outputs["Object"], mapping.inputs["Vector"])

    broad_noise = nodes.new(type="ShaderNodeTexNoise")
    broad_noise.inputs["Scale"].default_value = 5.6
    broad_noise.inputs["Detail"].default_value = 6.0
    broad_noise.inputs["Roughness"].default_value = 0.76
    broad_noise.inputs["Distortion"].default_value = 0.32
    links.new(mapping.outputs["Vector"], broad_noise.inputs["Vector"])

    color_ramp = nodes.new(type="ShaderNodeValToRGB")
    color_ramp.color_ramp.elements.remove(color_ramp.color_ramp.elements[1])
    dark = color_ramp.color_ramp.elements[0]
    dark.position = 0.18
    dark.color = (
        0.006 + rng.uniform(-0.001, 0.001),
        0.030 + rng.uniform(-0.004, 0.004),
        0.004,
        1.0,
    )
    middle = color_ramp.color_ramp.elements.new(0.48)
    middle.color = (
        0.016 + rng.uniform(-0.003, 0.003),
        0.082 + rng.uniform(-0.008, 0.008),
        0.010,
        1.0,
    )
    light = color_ramp.color_ramp.elements.new(0.76)
    light.color = (
        0.048 + rng.uniform(-0.006, 0.006),
        0.175 + rng.uniform(-0.012, 0.012),
        0.022,
        1.0,
    )
    dry = color_ramp.color_ramp.elements.new(0.92)
    dry.color = (0.16, 0.14, 0.028, 1.0)
    links.new(broad_noise.outputs["Fac"], color_ramp.inputs["Fac"])

    # Medium-scale chromatic texture prevents the pasture from reading as a
    # blurred green carpet in downward-looking cameras. It modulates albedo,
    # not geometry, and remains much subtler than the explicit grass blades.
    detail_noise = nodes.new(type="ShaderNodeTexNoise")
    detail_noise.inputs["Scale"].default_value = 31.0
    detail_noise.inputs["Detail"].default_value = 4.0
    detail_noise.inputs["Roughness"].default_value = 0.72
    detail_noise.inputs["Distortion"].default_value = 0.18
    links.new(mapping.outputs["Vector"], detail_noise.inputs["Vector"])
    detail_ramp = nodes.new(type="ShaderNodeValToRGB")
    detail_ramp.color_ramp.elements[0].position = 0.20
    detail_ramp.color_ramp.elements[0].color = (0.52, 0.70, 0.46, 1.0)
    detail_ramp.color_ramp.elements[1].position = 0.82
    detail_ramp.color_ramp.elements[1].color = (1.0, 1.0, 0.88, 1.0)
    links.new(detail_noise.outputs["Fac"], detail_ramp.inputs["Fac"])
    albedo_mix = nodes.new(type="ShaderNodeMixRGB")
    albedo_mix.blend_type = "MULTIPLY"
    albedo_mix.inputs["Fac"].default_value = 0.48
    links.new(color_ramp.outputs["Color"], albedo_mix.inputs[1])
    links.new(detail_ramp.outputs["Color"], albedo_mix.inputs[2])
    surface_color = albedo_mix.outputs["Color"]

    if layered:
        # Broad and medium masks expose irregular soil, litter-coloured and
        # vegetated patches. The soil source is the already packed CC0 PBR;
        # no pixels from the real dataset enter this material.
        patch_noise = nodes.new(type="ShaderNodeTexNoise")
        patch_noise.inputs["Scale"].default_value = rng.uniform(0.65, 1.05)
        patch_noise.inputs["Detail"].default_value = 3.2
        patch_noise.inputs["Roughness"].default_value = 0.72
        patch_noise.inputs["Distortion"].default_value = 0.28
        links.new(mapping.outputs["Vector"], patch_noise.inputs["Vector"])
        patch_ramp = nodes.new(type="ShaderNodeValToRGB")
        patch_ramp.color_ramp.elements[0].position = rng.uniform(0.34, 0.42)
        patch_ramp.color_ramp.elements[1].position = rng.uniform(0.56, 0.64)
        links.new(patch_noise.outputs["Fac"], patch_ramp.inputs["Fac"])

        soil_diffuse = (images or {}).get("soil_diffuse")
        soil_color_output = None
        if soil_diffuse is not None:
            soil_node = nodes.new(type="ShaderNodeTexImage")
            soil_node.image = soil_diffuse
            soil_node.extension = "REPEAT"
            links.new(mapping.outputs["Vector"], soil_node.inputs["Vector"])
            soil_color_output = soil_node.outputs["Color"]
        else:
            soil_rgb = nodes.new(type="ShaderNodeRGB")
            soil_rgb.outputs["Color"].default_value = (0.105, 0.065, 0.032, 1.0)
            soil_color_output = soil_rgb.outputs["Color"]

        litter_noise = nodes.new(type="ShaderNodeTexNoise")
        litter_noise.inputs["Scale"].default_value = 8.5
        litter_noise.inputs["Detail"].default_value = 2.0
        litter_noise.inputs["Roughness"].default_value = 0.66
        links.new(mapping.outputs["Vector"], litter_noise.inputs["Vector"])
        litter_ramp = nodes.new(type="ShaderNodeValToRGB")
        litter_ramp.color_ramp.elements[0].color = (0.17, 0.095, 0.025, 1.0)
        litter_ramp.color_ramp.elements[1].color = (0.44, 0.31, 0.09, 1.0)
        links.new(litter_noise.outputs["Fac"], litter_ramp.inputs["Fac"])
        soil_litter_mix = nodes.new(type="ShaderNodeMixRGB")
        soil_litter_mix.blend_type = "MIX"
        soil_litter_mix.inputs["Fac"].default_value = 0.22
        links.new(soil_color_output, soil_litter_mix.inputs[1])
        links.new(litter_ramp.outputs["Color"], soil_litter_mix.inputs[2])

        soil_vegetation_mix = nodes.new(type="ShaderNodeMixRGB")
        soil_vegetation_mix.blend_type = "MIX"
        links.new(patch_ramp.outputs["Color"], soil_vegetation_mix.inputs["Fac"])
        links.new(soil_litter_mix.outputs["Color"], soil_vegetation_mix.inputs[1])
        links.new(surface_color, soil_vegetation_mix.inputs[2])
        surface_color = soil_vegetation_mix.outputs["Color"]

    links.new(surface_color, bsdf.inputs["Base Color"])

    fine_noise = nodes.new(type="ShaderNodeTexNoise")
    fine_noise.inputs["Scale"].default_value = 52.0
    fine_noise.inputs["Detail"].default_value = 3.0
    fine_noise.inputs["Roughness"].default_value = 0.68
    links.new(mapping.outputs["Vector"], fine_noise.inputs["Vector"])
    bump = nodes.new(type="ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.28
    bump.inputs["Distance"].default_value = 0.075
    links.new(fine_noise.outputs["Fac"], bump.inputs["Height"])
    soil_normal = (images or {}).get("soil_normal") if layered else None
    if soil_normal is not None:
        soil_normal_node = nodes.new(type="ShaderNodeTexImage")
        soil_normal_node.image = soil_normal
        soil_normal_node.extension = "REPEAT"
        normal_map = nodes.new(type="ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = 0.24
        links.new(mapping.outputs["Vector"], soil_normal_node.inputs["Vector"])
        links.new(soil_normal_node.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def _create_terrain_mesh(
    *,
    seed: int,
    size: float,
    subdivisions: int,
    material: object,
    collection: object,
) -> object:
    bpy, _ = _blender_modules()
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for row in range(subdivisions + 1):
        y = -size / 2.0 + size * row / subdivisions
        for column in range(subdivisions + 1):
            x = -size / 2.0 + size * column / subdivisions
            vertices.append((x, y, _terrain_height_at(x, y, seed)))
    stride = subdivisions + 1
    for row in range(subdivisions):
        for column in range(subdivisions):
            a = row * stride + column
            b = a + 1
            c = a + stride + 1
            d = a + stride
            faces.append((a, b, c, d))

    mesh = bpy.data.meshes.new("uchuva_terrain_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    terrain = bpy.data.objects.new("uchuva_terrain_agricultural", mesh)
    collection.objects.link(terrain)
    terrain.data.materials.append(material)
    tag_annotation_object(terrain, "soil", organ_id="terrain")
    return terrain


def _terrain_height_at(x: float, y: float, seed: int) -> float:
    """Return the deterministic analytic height used by the terrain mesh."""
    mound = 0.045 * math.cos((y + 0.2) * math.tau / 0.82)
    broad = 0.035 * math.sin(x * 0.72 + seed) * math.cos(y * 0.49 - seed)
    fine = 0.012 * math.sin(x * 4.1 + y * 3.7 + seed * 0.31)
    return mound + broad + fine - 0.055


def audit_calyx_ground_clearance(
    *,
    seed: int,
    terrain_object: object | None = None,
    required_clearance: float = 0.008,
) -> dict[str, Any]:
    """Reject capachos that penetrate or visually rest on the terrain.

    Vertical ray casts query the actual evaluated terrain mesh rather than its
    pre-mesh analytic height function. This avoids interpolation mismatches and
    keeps thousands of background weed faces out of the plant collision audit.
    """
    bpy, Vector = _blender_modules()
    from mathutils.bvhtree import BVHTree

    if terrain_object is None:
        terrain_object = bpy.data.objects.get("uchuva_terrain_agricultural")
    if terrain_object is None:
        return {
            "version": "0.1.0-evaluated-terrain-clearance",
            "status": "invalid",
            "seed": seed,
            "audited_semantic_class": "calyx",
            "tested_object_count": 0,
            "tested_vertex_count": 0,
            "required_clearance_m": required_clearance,
            "physical_collision_count": 1,
            "physical_collisions": [
                {
                    "type": "missing_terrain_for_clearance_audit",
                    "classification": "physical_collision",
                    "object_a": "calyx_set",
                    "object_b": "missing_terrain",
                }
            ],
        }

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_terrain = terrain_object.evaluated_get(depsgraph)
    terrain_mesh = evaluated_terrain.to_mesh()
    terrain_matrix = evaluated_terrain.matrix_world
    terrain_vertices = [
        tuple(terrain_matrix @ vertex.co)
        for vertex in terrain_mesh.vertices
    ]
    terrain_polygons = [tuple(polygon.vertices) for polygon in terrain_mesh.polygons]
    terrain_bvh = BVHTree.FromPolygons(
        terrain_vertices,
        terrain_polygons,
        all_triangles=False,
    )
    ray_origin_z = max(vertex[2] for vertex in terrain_vertices) + 1.0
    evaluated_terrain.to_mesh_clear()
    collisions: list[dict[str, Any]] = []
    tested_object_count = 0
    tested_vertex_count = 0

    for obj in bpy.context.scene.objects:
        if (
            obj.hide_render
            or obj.type not in {"MESH", "CURVE", "SURFACE"}
            or str(obj.get("uchuva_semantic_class", "")) != "calyx"
        ):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        if mesh is None:
            continue
        matrix = evaluated.matrix_world
        vertices = [tuple(matrix @ vertex.co) for vertex in mesh.vertices]
        evaluated.to_mesh_clear()
        tested_object_count += 1
        tested_vertex_count += len(vertices)
        clearances: list[float] = []
        for x, y, z in vertices:
            hit = terrain_bvh.ray_cast(
                Vector((x, y, ray_origin_z)),
                Vector((0.0, 0.0, -1.0)),
            )
            if hit[0] is not None:
                clearances.append(z - float(hit[0].z))
        minimum_clearance = min(clearances) if clearances else None
        if minimum_clearance is None or minimum_clearance >= required_clearance:
            continue
        collisions.append(
            {
                "type": "calyx_ground_clearance",
                "classification": "physical_collision",
                "object_a": obj.name,
                "object_b": "uchuva_terrain_agricultural",
                "plant_a": str(obj.get("uchuva_plant_id", "")),
                "plant_b": "environment",
                "semantic_a": "calyx",
                "semantic_b": "soil",
                "minimum_clearance_m": round(minimum_clearance, 7),
                "required_clearance_m": required_clearance,
                "penetration_or_deficit_m": round(
                    required_clearance - minimum_clearance,
                    7,
                ),
            }
        )

    return {
        "version": "0.1.0-evaluated-terrain-clearance",
        "status": "valid" if not collisions else "invalid",
        "seed": seed,
        "audited_semantic_class": "calyx",
        "tested_object_count": tested_object_count,
        "tested_vertex_count": tested_vertex_count,
        "required_clearance_m": required_clearance,
        "physical_collision_count": len(collisions),
        "physical_collisions": collisions,
    }


def _create_background_materials(
    seed: int,
    background_style: str = "layered_understory_v2",
) -> dict[str, object]:
    from .blender_scene import create_material

    rng = random.Random(seed + 72_000)
    materials = {
        "leaf": create_material(
            "Uchuva_Fondo_vegetacion",
            (0.10 + rng.uniform(-0.02, 0.02), 0.27, 0.08, 1.0),
            roughness=0.92,
        ),
        "lolium": create_material(
            "Uchuva_Fondo_lolium_like",
            (0.095 + rng.uniform(-0.015, 0.015), 0.31, 0.075, 1.0),
            roughness=0.91,
        ),
        "kikuyu": create_material(
            "Uchuva_Fondo_kikuyu_like",
            (0.075 + rng.uniform(-0.012, 0.012), 0.245, 0.055, 1.0),
            roughness=0.94,
        ),
        "weed": create_material(
            "Uchuva_Fondo_malezas_hoja_ancha",
            (0.115 + rng.uniform(-0.018, 0.018), 0.29, 0.07, 1.0),
            roughness=0.93,
        ),
        "stem": create_material(
            "Uchuva_Fondo_tallos",
            (0.10, 0.18, 0.055, 1.0),
            roughness=0.95,
        ),
        "dry": create_material(
            "Uchuva_Rastrojo_seco",
            (0.30, 0.22, 0.09, 1.0),
            roughness=0.98,
        ),
    }
    for key in ("lolium", "kikuyu", "weed"):
        _add_understory_surface_variation(
            materials[key],
            seed + len(key) * 97,
            layered=background_style == "layered_understory_v2",
        )
    return materials


def _add_understory_surface_variation(
    material: object,
    seed: int,
    *,
    layered: bool = True,
) -> None:
    """Break uniform CGI albedo on lightweight pasture geometry."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        return
    base = tuple(float(value) for value in bsdf.inputs["Base Color"].default_value)
    rng = random.Random(seed)
    coordinates = nodes.new(type="ShaderNodeTexCoord")
    noise = nodes.new(type="ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = rng.uniform(3.0, 7.0) if layered else rng.uniform(7.0, 11.0)
    noise.inputs["Detail"].default_value = 4.0 if layered else 3.0
    noise.inputs["Roughness"].default_value = 0.68
    ramp = nodes.new(type="ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.24
    ramp.color_ramp.elements[0].color = tuple(
        max(0.0, value * 0.58) for value in base[:3]
    ) + (1.0,)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = tuple(
        min(1.0, value * 1.32 + 0.012) for value in base[:3]
    ) + (1.0,)
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])


def _scatter_rocks(
    rng: random.Random,
    terrain_size: float,
    material: object,
    collection: object,
) -> list[object]:
    bpy, _ = _blender_modules()
    rocks: list[object] = []
    for index in range(18):
        x = rng.uniform(-terrain_size * 0.42, terrain_size * 0.42)
        y = rng.uniform(-terrain_size * 0.38, terrain_size * 0.42)
        if math.hypot(x, y) < 0.42:
            continue
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.06, location=(x, y, 0.0))
        rock = bpy.context.object
        rock.name = f"uchuva_soil_rock_{index:02d}"
        rock.scale = (
            rng.uniform(0.45, 1.4),
            rng.uniform(0.55, 1.2),
            rng.uniform(0.25, 0.65),
        )
        rock.rotation_euler = tuple(rng.uniform(-0.6, 0.6) for _ in range(3))
        rock.data.materials.append(material)
        _move_to_collection(rock, collection)
        tag_annotation_object(rock, "soil", organ_id=rock.name)
        rocks.append(rock)
    return rocks


def _scatter_debris(
    rng: random.Random,
    terrain_size: float,
    material: object,
    collection: object,
    *,
    terrain_seed: int = 0,
    irregular: bool = True,
) -> list[object]:
    bpy, _ = _blender_modules()
    debris: list[object] = []
    for index in range(48 if irregular else 24):
        x = rng.uniform(-terrain_size * 0.38, terrain_size * 0.38)
        y = rng.uniform(-terrain_size * 0.34, terrain_size * 0.42)
        if irregular:
            length = rng.uniform(0.055, 0.18)
            width = rng.uniform(0.018, min(0.085, length * 0.62))
            vertices = [(0.0, -length * 0.50, 0.0)]
            side_count = rng.randint(3, 5)
            for step in range(1, side_count + 1):
                t = step / (side_count + 1)
                envelope = math.sin(math.pi * t) ** rng.uniform(0.72, 1.12)
                jitter = rng.uniform(0.78, 1.18)
                vertices.append((-width * envelope * jitter, length * (t - 0.5), rng.uniform(0.0, 0.006)))
            vertices.append((0.0, length * 0.50, rng.uniform(0.0, 0.008)))
            for step in reversed(range(1, side_count + 1)):
                t = step / (side_count + 1)
                envelope = math.sin(math.pi * t) ** rng.uniform(0.72, 1.12)
                jitter = rng.uniform(0.78, 1.18)
                vertices.append((width * envelope * jitter, length * (t - 0.5), rng.uniform(0.0, 0.006)))
            mesh = bpy.data.meshes.new(f"uchuva_leaf_litter_{index:02d}_mesh")
            mesh.from_pydata(vertices, [], [tuple(range(len(vertices)))])
            mesh.update()
            item = bpy.data.objects.new(f"uchuva_leaf_litter_{index:02d}", mesh)
            item.location = (
                x,
                y,
                _terrain_height_at(x, y, terrain_seed) + 0.006,
            )
            collection.objects.link(item)
            item.rotation_euler[0] = rng.uniform(-0.12, 0.12)
            item.rotation_euler[1] = rng.uniform(-0.12, 0.12)
        else:
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, -0.005))
            item = bpy.context.object
            item.scale = (
                rng.uniform(0.035, 0.11),
                rng.uniform(0.006, 0.015),
                rng.uniform(0.002, 0.005),
            )
        item.name = f"uchuva_soil_debris_{index:02d}"
        item.rotation_euler[2] = rng.uniform(0.0, math.tau)
        item.data.materials.append(material)
        if not irregular:
            _move_to_collection(item, collection)
        tag_annotation_object(item, "soil", organ_id=item.name)
        debris.append(item)
    return debris


def _ground_vegetation_plan(mode: str) -> list[dict[str, Any]]:
    """Return a pure, deterministic species-like ground-cover plan.

    The ``*_like`` labels describe visual growth forms only. They do not claim
    species-level botanical reconstruction.
    """
    profile_name = (
        mode
        if mode in GROUND_VEGETATION_PROFILES
        else "open_field_hybrid"
    )
    return [
        {
            "name": str(item["name"]),
            "count": int(item["count"]),
            "height_range": tuple(item["height_range"]),
            "width_range": tuple(item["width_range"]),
            "material": str(item["material"]),
        }
        for item in GROUND_VEGETATION_PROFILES[profile_name]
    ]


def _scatter_grasses(
    rng: random.Random,
    terrain_size: float,
    material: object,
    collection: object,
    *,
    count: int,
    name: str = "mixed_grasses",
    height_range: tuple[float, float] = (0.18, 0.72),
    width_range: tuple[float, float] = (0.006, 0.018),
    background_fraction: float = 0.0,
) -> int:
    """Create lightweight, species-shaped vegetation in spatial clumps."""
    bpy, _ = _blender_modules()
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    spread = min(terrain_size * 0.46, 5.5)
    blades_per_clump = 9 if "lolium" in name else 14 if "kikuyu" in name else 6
    clump_count = max(1, math.ceil(count / blades_per_clump))
    clump_centers: list[tuple[float, float]] = []
    for _ in range(clump_count):
        if rng.random() < background_fraction:
            clump_centers.append(
                (
                    rng.uniform(-spread, spread),
                    rng.uniform(spread * 0.42, spread * 1.12),
                )
            )
        else:
            near_spread = min(spread, 3.1)
            clump_centers.append(
                (
                    rng.uniform(-near_spread, near_spread),
                    rng.uniform(-near_spread * 0.42, near_spread * 1.12),
                )
            )

    for blade_index in range(count):
        center_x, center_y = clump_centers[blade_index % clump_count]
        clump_radius = 0.11 if "lolium" in name else 0.18 if "kikuyu" in name else 0.24
        x = center_x + rng.gauss(0.0, clump_radius)
        y = center_y + rng.gauss(0.0, clump_radius)
        height = rng.uniform(*height_range)
        width = rng.uniform(*width_range)
        bend_angle = rng.uniform(0.0, math.tau)
        bend_distance = height * rng.uniform(0.08, 0.34)
        lean_x = math.cos(bend_angle) * bend_distance
        lean_y = math.sin(bend_angle) * bend_distance
        angle = rng.uniform(0.0, math.tau)
        side = (math.cos(angle) * width * 0.5, math.sin(angle) * width * 0.5)

        if "kikuyu" in name and blade_index % 10 == 0:
            stolon_start = len(vertices)
            stolon_angle = rng.uniform(0.0, math.tau)
            stolon_length = rng.uniform(0.20, 0.52)
            stolon_width = rng.uniform(0.0015, 0.0035)
            along = (
                math.cos(stolon_angle) * stolon_length,
                math.sin(stolon_angle) * stolon_length,
            )
            across = (
                -math.sin(stolon_angle) * stolon_width,
                math.cos(stolon_angle) * stolon_width,
            )
            vertices.extend(
                [
                    (x - across[0], y - across[1], 0.004),
                    (x + across[0], y + across[1], 0.004),
                    (x + along[0] + across[0], y + along[1] + across[1], 0.006),
                    (x + along[0] - across[0], y + along[1] - across[1], 0.006),
                ]
            )
            faces.append(tuple(range(stolon_start, stolon_start + 4)))

        start = len(vertices)
        if "broadleaf" in name:
            # A short inclined, cupped ovate blade replaces the former vertical
            # eight-sided diamond. Several leaves share each clump centre, so
            # their random radial directions read as a weed rosette.
            base_z = rng.uniform(0.012, 0.045)
            forward_x = math.cos(bend_angle)
            forward_y = math.sin(bend_angle)
            lateral_x = -forward_y
            lateral_y = forward_x
            cross_sections = 13
            for section in range(cross_sections):
                t = section / (cross_sections - 1)
                envelope = max(0.0, math.sin(math.pi * t)) ** 0.72
                basal_lobe = 1.0 + 0.16 * math.exp(-((t - 0.22) / 0.15) ** 2)
                half_width = 0.5 * width * envelope * basal_lobe
                radial_distance = height * (0.10 * t + 0.82 * t**0.82)
                local_z = base_z + height * (0.12 * t + 0.50 * math.sin(t * math.pi * 0.62))
                edge_wave = 1.0 + 0.035 * math.sin(angle + t * 15.0)
                cup = height * 0.035 * envelope
                center_px = x + forward_x * radial_distance
                center_py = y + forward_y * radial_distance
                vertices.extend(
                    [
                        (
                            center_px - lateral_x * half_width * edge_wave,
                            center_py - lateral_y * half_width * edge_wave,
                            local_z + cup,
                        ),
                        (
                            center_px + lateral_x * half_width / edge_wave,
                            center_py + lateral_y * half_width / edge_wave,
                            local_z + cup * 0.82,
                        ),
                    ]
                )
        else:
            vertices.extend(
                [
                    (x - side[0], y - side[1], -0.01),
                    (x + side[0], y + side[1], -0.01),
                    (
                        x + lean_x * 0.48 + side[0] * 0.62,
                        y + lean_y * 0.48 + side[1] * 0.62,
                        height * 0.52,
                    ),
                    (
                        x + lean_x * 0.48 - side[0] * 0.62,
                        y + lean_y * 0.48 - side[1] * 0.62,
                        height * 0.52,
                    ),
                    (
                        x + lean_x + side[0] * 0.10,
                        y + lean_y + side[1] * 0.10,
                        height,
                    ),
                    (
                        x + lean_x - side[0] * 0.10,
                        y + lean_y - side[1] * 0.10,
                        height,
                    ),
                ]
            )
        if "broadleaf" in name:
            for section in range(cross_sections - 1):
                left_0 = start + section * 2
                right_0 = left_0 + 1
                left_1 = left_0 + 2
                right_1 = left_0 + 3
                faces.append((left_0, right_0, right_1, left_1))
        else:
            faces.append((start, start + 1, start + 3, start + 2))
            faces.append((start + 2, start + 3, start + 5, start + 4))
    mesh = bpy.data.meshes.new(f"uchuva_background_{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    grasses = bpy.data.objects.new(f"uchuva_background_{name}", mesh)
    collection.objects.link(grasses)
    grasses.data.materials.append(material)
    grasses["uchuva_ground_vegetation_profile"] = name
    grasses["uchuva_parameter_status"] = "manual_initial_guess"
    tag_annotation_object(grasses, "background", organ_id=grasses.name)
    return count


def _create_vegetated_backdrop(
    *,
    seed: int,
    scene_radius: float,
    collection: object,
) -> object:
    """Surround cameras with a distant, softly mottled green field backdrop."""
    bpy, _ = _blender_modules()
    material = _create_vegetated_backdrop_material(seed)
    radius = max(16.0, float(scene_radius) + 12.0)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=128,
        radius=radius,
        depth=14.0,
        end_fill_type="NOTHING",
        location=(0.0, 0.0, 6.4),
    )
    backdrop = bpy.context.object
    backdrop.name = "uchuva_fondo_verde_texturizado"
    backdrop.data.materials.append(material)
    _move_to_collection(backdrop, collection)
    tag_annotation_object(backdrop, "background", organ_id=backdrop.name)
    backdrop["uchuva_background_role"] = "distant_pasture_and_weeds_proxy"
    backdrop["uchuva_parameter_status"] = "dataset_observed_manual_initial_guess"
    return backdrop


def _create_vegetated_backdrop_material(seed: int) -> object:
    """Create multi-scale green variation that reads as distant vegetation."""
    bpy, _ = _blender_modules()
    rng = random.Random(seed + 71_900)
    material = bpy.data.materials.get(
        "Uchuva_Fondo_verde_texturizado"
    ) or bpy.data.materials.new("Uchuva_Fondo_verde_texturizado")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new(type="ShaderNodeOutputMaterial")
    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.96
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    coordinates = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.42, 0.42, 0.78)
    links.new(coordinates.outputs["Object"], mapping.inputs["Vector"])

    broad_noise = nodes.new(type="ShaderNodeTexNoise")
    broad_noise.inputs["Scale"].default_value = 3.1
    broad_noise.inputs["Detail"].default_value = 7.0
    broad_noise.inputs["Roughness"].default_value = 0.78
    broad_noise.inputs["Distortion"].default_value = 0.38
    links.new(mapping.outputs["Vector"], broad_noise.inputs["Vector"])

    color_ramp = nodes.new(type="ShaderNodeValToRGB")
    color_ramp.color_ramp.elements.remove(color_ramp.color_ramp.elements[1])
    dark = color_ramp.color_ramp.elements[0]
    dark.position = 0.20
    dark.color = (0.008, 0.035, 0.005, 1.0)
    middle = color_ramp.color_ramp.elements.new(0.46)
    middle.color = (
        0.018 + rng.uniform(-0.003, 0.003),
        0.082 + rng.uniform(-0.008, 0.008),
        0.012,
        1.0,
    )
    bright = color_ramp.color_ramp.elements.new(0.71)
    bright.color = (
        0.050 + rng.uniform(-0.006, 0.006),
        0.170 + rng.uniform(-0.014, 0.014),
        0.026,
        1.0,
    )
    pale = color_ramp.color_ramp.elements.new(0.90)
    pale.color = (0.12, 0.24, 0.055, 1.0)
    links.new(broad_noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], bsdf.inputs["Base Color"])

    fine_noise = nodes.new(type="ShaderNodeTexNoise")
    fine_noise.inputs["Scale"].default_value = 22.0
    fine_noise.inputs["Detail"].default_value = 3.0
    links.new(mapping.outputs["Vector"], fine_noise.inputs["Vector"])
    bump = nodes.new(type="ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.08
    links.new(fine_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def _create_neutral_backdrop(material: object, collection: object) -> object:
    bpy, _ = _blender_modules()
    bpy.ops.mesh.primitive_plane_add(
        size=30.0,
        location=(0.0, 8.0, 7.0),
        rotation=(math.pi / 2.0, 0.0, 0.0),
    )
    backdrop = bpy.context.object
    backdrop.name = "uchuva_neutral_reference_backdrop"
    backdrop.scale = (1.0, 1.0, 1.0)
    backdrop.data.materials.append(material)
    _move_to_collection(backdrop, collection)
    tag_annotation_object(backdrop, "background", organ_id=backdrop.name)
    return backdrop


def _create_background_canopy(
    rng: random.Random,
    *,
    count: int,
    scene_radius: float,
    materials: dict[str, object],
    collection: object,
    close: bool = False,
) -> list[object]:
    bpy, _ = _blender_modules()
    objects: list[object] = []
    for cluster_index in range(count):
        angle = math.radians(rng.uniform(22.0, 158.0))
        distance = (
            rng.uniform(scene_radius + 0.45, scene_radius + 1.75)
            if close
            else rng.uniform(scene_radius + 1.8, scene_radius + 3.7)
        )
        base_x = math.cos(angle) * distance
        base_y = (0.55 if close else 1.8) + math.sin(angle) * distance * 0.62
        height = rng.uniform(1.1, 2.4)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=8,
            radius=rng.uniform(0.025, 0.055),
            depth=height,
            location=(base_x, base_y, height * 0.5),
        )
        stem = bpy.context.object
        stem.name = f"uchuva_background_cluster_{cluster_index:02d}_stem"
        stem.data.materials.append(materials["stem"])
        _move_to_collection(stem, collection)
        tag_annotation_object(stem, "background", organ_id=stem.name)
        objects.append(stem)

        leaf_count = rng.randint(12, 20) if close else rng.randint(7, 13)
        for leaf_index in range(leaf_count):
            z = rng.uniform(height * 0.22, height * 1.05)
            radial = rng.uniform(0.08, 0.45)
            leaf_angle = rng.uniform(0.0, math.tau)
            leaf = _create_background_leaf(
                name=f"uchuva_background_cluster_{cluster_index:02d}_leaf_{leaf_index:02d}",
                location=(
                    base_x + math.cos(leaf_angle) * radial,
                    base_y + math.sin(leaf_angle) * radial,
                    z,
                ),
                length=rng.uniform(0.34, 0.78) if close else rng.uniform(0.18, 0.44),
                width=rng.uniform(0.20, 0.52) if close else rng.uniform(0.10, 0.28),
            )
            leaf.rotation_euler = tuple(rng.uniform(-0.7, 0.7) for _ in range(3))
            leaf.data.materials.append(materials["leaf"])
            _move_to_collection(leaf, collection)
            tag_annotation_object(leaf, "background", organ_id=leaf.name)
            objects.append(leaf)
    return objects


def _create_background_leaf(
    *,
    name: str,
    location: tuple[float, float, float],
    length: float,
    width: float,
) -> object:
    bpy, _ = _blender_modules()
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(
        [
            (0.0, 0.0, 0.0),
            (-width * 0.34, length * 0.18, 0.010),
            (-width * 0.50, length * 0.42, 0.018),
            (-width * 0.34, length * 0.72, 0.008),
            (0.0, length, -0.025),
            (width * 0.34, length * 0.72, 0.008),
            (width * 0.50, length * 0.42, 0.018),
            (width * 0.34, length * 0.18, 0.010),
        ],
        [],
        [tuple(range(8))],
    )
    mesh.update()
    leaf = bpy.data.objects.new(name, mesh)
    leaf.location = location
    bpy.context.collection.objects.link(leaf)
    return leaf


def _setup_world(hdri_image: object | None, rng: random.Random) -> dict[str, Any]:
    bpy, _ = _blender_modules()
    world = bpy.data.worlds.get("Uchuva_Outdoor_World") or bpy.data.worlds.new(
        "Uchuva_Outdoor_World"
    )
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new(type="ShaderNodeOutputWorld")
    background = nodes.new(type="ShaderNodeBackground")
    background.name = "Uchuva_Outdoor_Background"
    background.inputs["Strength"].default_value = rng.uniform(0.42, 0.72)
    links.new(background.outputs["Background"], output.inputs["Surface"])
    mode = "procedural_fallback"
    if hdri_image is not None:
        texture_coordinate = nodes.new(type="ShaderNodeTexCoord")
        mapping = nodes.new(type="ShaderNodeMapping")
        mapping.name = "Uchuva_HDRI_Mapping"
        mapping.inputs["Rotation"].default_value[2] = rng.uniform(0.0, math.tau)
        environment = nodes.new(type="ShaderNodeTexEnvironment")
        environment.image = hdri_image
        links.new(texture_coordinate.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], environment.inputs["Vector"])
        links.new(environment.outputs["Color"], background.inputs["Color"])
        mode = "packed_cc0_hdri"
    else:
        background.inputs["Color"].default_value = (0.28, 0.36, 0.48, 1.0)
    bpy.context.scene.world = world
    return {
        "mode": mode,
        "image": hdri_image.name if hdri_image is not None else None,
        "strength": round(float(background.inputs["Strength"].default_value), 4),
    }


def _create_distant_sun(rng: random.Random) -> dict[str, Any]:
    bpy, _ = _blender_modules()
    bpy.ops.object.light_add(type="SUN", location=(0.0, 0.0, 8.0))
    light = bpy.context.object
    light.name = "uchuva_sun_exterior"
    light.data.name = "uchuva_sun_exterior_data"
    azimuth = rng.uniform(math.radians(125.0), math.radians(235.0))
    elevation = rng.uniform(math.radians(38.0), math.radians(62.0))
    light.rotation_euler = (elevation, 0.0, azimuth)
    light.data.energy = rng.uniform(1.4, 2.8)
    light.data.angle = rng.uniform(math.radians(2.0), math.radians(7.0))
    return {
        "name": light.name,
        "type": "SUN",
        "azimuth_deg": round(math.degrees(azimuth), 3),
        "elevation_deg": round(math.degrees(elevation), 3),
        "energy": round(float(light.data.energy), 4),
        "angle_deg": round(math.degrees(float(light.data.angle)), 4),
    }


def _move_to_collection(obj: object, collection: object) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)
