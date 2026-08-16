"""Pure-Python procedural texture assets for uchuva leaves and calyxes.

The generator deliberately has no Blender, NumPy, or Pillow dependency.  It
turns a small botanical vein graph into audit-friendly PNG maps that Blender
can interpret as albedo, normal, height, roughness, and vein masks.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
import zlib
from array import array
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


TEXTURE_GENERATOR_VERSION = "0.5.0-maturity-continuum"
DEFAULT_TEXTURE_ASSET_DIR = Path("assets") / "textures" / "current"


@dataclass(frozen=True)
class TexturePreset:
    """Appearance parameters for one organ/phenology texture set."""

    name: str
    organ: str
    state: str
    base_srgb: tuple[int, int, int]
    vein_srgb: tuple[int, int, int]
    roughness: float
    roughness_variation: float
    normal_strength: float
    ior: float
    subsurface_weight: float
    sheen_weight: float
    parameter_status: str
    specular_ior_level: float = 0.15
    vein_contrast: float = 0.5
    apical_darkening: float = 0.0
    primary_relief_scale: float = 1.0


LEAF_TEXTURE_PRESETS: tuple[TexturePreset, ...] = (
    TexturePreset(
        name="leaf_healthy",
        organ="leaf",
        state="healthy",
        base_srgb=(92, 123, 66),
        vein_srgb=(142, 162, 104),
        roughness=0.92,
        roughness_variation=0.050,
        normal_strength=0.35,
        ior=1.45,
        subsurface_weight=0.005,
        sheen_weight=0.0,
        parameter_status="dataset_inferred_camera_srgb+literature_bounded_reflection",
        vein_contrast=0.58,
    ),
    TexturePreset(
        name="leaf_senescent",
        organ="leaf",
        state="senescent",
        base_srgb=(132, 130, 69),
        vein_srgb=(157, 150, 94),
        roughness=0.95,
        roughness_variation=0.050,
        normal_strength=0.40,
        ior=1.45,
        subsurface_weight=0.003,
        sheen_weight=0.0,
        parameter_status="manual_initial_guess_from_dataset_range",
        vein_contrast=0.48,
    ),
)


def _calyx_preset(
    name: str,
    state: str,
    base_srgb: tuple[int, int, int],
    vein_srgb: tuple[int, int, int],
    contrast: float,
    apical_darkening: float,
    roughness: float,
    normal_strength: float,
    primary_relief_scale: float,
) -> TexturePreset:
    return TexturePreset(
        name=name,
        organ="calyx",
        state=state,
        base_srgb=base_srgb,
        vein_srgb=vein_srgb,
        roughness=roughness,
        roughness_variation=0.035 if state == "inflated_green" else 0.045,
        normal_strength=normal_strength,
        ior=1.45,
        subsurface_weight=0.004 if state == "inflated_green" else 0.002,
        sheen_weight=0.0,
        parameter_status="dataset_inferred_camera_srgb+manual_initial_guess_reflection",
        vein_contrast=contrast,
        apical_darkening=apical_darkening,
        primary_relief_scale=primary_relief_scale,
    )


CALYX_TEXTURE_PRESETS: tuple[TexturePreset, ...] = (
    _calyx_preset("calyx_green_v0", "inflated_green", (116, 133, 61), (68, 78, 38), 0.58, 0.00, 0.93, 0.22, 0.24),
    _calyx_preset("calyx_green_v1", "inflated_green", (119, 137, 62), (55, 68, 35), 0.70, 0.08, 0.94, 0.24, 0.22),
    _calyx_preset("calyx_green_v2", "inflated_green", (123, 143, 65), (45, 55, 30), 0.82, 0.24, 0.95, 0.26, 0.20),
    _calyx_preset("calyx_green_v3", "inflated_green", (127, 148, 68), (38, 44, 25), 0.94, 0.45, 0.97, 0.28, 0.18),
    _calyx_preset("calyx_transition_v0", "transitioning_yellow", (151, 158, 78), (83, 76, 43), 0.68, 0.05, 0.95, 0.23, 0.24),
    _calyx_preset("calyx_transition_v1", "transitioning_yellow", (174, 169, 94), (96, 82, 52), 0.78, 0.10, 0.96, 0.24, 0.23),
    _calyx_preset("calyx_straw_v0", "straw_yellow", (198, 187, 132), (128, 104, 72), 0.58, 0.00, 0.94, 0.24, 0.26),
    _calyx_preset("calyx_straw_v1", "straw_yellow", (193, 180, 117), (105, 79, 57), 0.72, 0.04, 0.96, 0.26, 0.24),
    _calyx_preset("calyx_straw_v2", "straw_yellow", (183, 164, 102), (82, 60, 45), 0.86, 0.10, 0.98, 0.28, 0.22),
    _calyx_preset("calyx_dry_v0", "dry_deteriorated", (191, 177, 140), (116, 91, 64), 0.64, 0.00, 0.95, 0.28, 0.28),
    _calyx_preset("calyx_dry_v1", "dry_deteriorated", (174, 151, 109), (91, 67, 49), 0.78, 0.06, 0.97, 0.31, 0.26),
    _calyx_preset("calyx_dry_v2", "dry_deteriorated", (143, 117, 80), (67, 48, 38), 0.90, 0.12, 0.99, 0.34, 0.24),
)


TEXTURE_PRESETS: tuple[TexturePreset, ...] = LEAF_TEXTURE_PRESETS + CALYX_TEXTURE_PRESETS


LEGACY_PRESET_ALIASES = {
    "calyx_green": "calyx_green_v1",
    "calyx_straw": "calyx_straw_v1",
    "calyx_dry": "calyx_dry_v1",
    "calyx_transition": "calyx_transition_v0",
}


_REMOVED_V1_PRESETS = (
    # Kept as an explicit marker in source history: v2 variants above replace
    # the single calyx presets without deleting assets/textures/legacy/uchuva_v1.
)


LEAF_VENATION_TAXONOMY: dict[str, Any] = {
    "primary_category": "suprabasal",
    "secondary_category": "semicraspedodromous",
    "lateral_veins_per_side": [5, 7],
    "secondary_angle": "acute",
    "tertiary_category": "alternate_percurrent",
    "tertiary_course": "sinuous",
    "quaternary_category": "regular_polygonal_reticulate",
    "areolation": "moderately_developed",
    "freely_ending_ultimate_veins": "two_or_more_branched",
    "highest_modeled_order": 4,
    "evidence_status": "literature_reported",
}


CALYX_VENATION_TAXONOMY: dict[str, Any] = {
    "fruiting_calyx": "ovoid_inflated_reticulate",
    "major_sepal_midribs": 5,
    "longitudinal_ribs_or_angles": 10,
    "secondary_network": "reticulate_cross_linked",
    "surface": "persistently_hairy_chartaceous",
    "ripe_vein_color": "sometimes_purplish_to_brown",
    "evidence_status": "literature_reported_and_dataset_confirmed",
}


def texture_preset(name: str) -> TexturePreset:
    """Return a named preset or raise a descriptive error."""
    name = LEGACY_PRESET_ALIASES.get(name, name)
    for preset in TEXTURE_PRESETS:
        if preset.name == name:
            return preset
    raise KeyError(f"Unknown texture preset: {name}")


def generate_texture_asset_library(
    output_dir: str | Path = DEFAULT_TEXTURE_ASSET_DIR,
    *,
    seed: int = 1701,
    resolution: int = 512,
) -> dict[str, Any]:
    """Generate the complete deterministic leaf/calyx texture library."""
    if resolution < 32 or resolution > 4096:
        raise ValueError("resolution must be between 32 and 4096 pixels")
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    generated: dict[str, dict[str, Any]] = {}
    preview_tiles: list[dict[str, bytes]] = []
    for index, preset in enumerate(TEXTURE_PRESETS):
        preset_seed = seed + index * 1009
        maps, diagnostics = _generate_texture_set(preset, resolution, preset_seed)
        files: dict[str, str] = {}
        hashes: dict[str, str] = {}
        for map_name, (channels, pixels) in maps.items():
            file_name = f"{preset.name}_{map_name}.png"
            file_path = output_path / file_name
            _write_png(file_path, resolution, resolution, channels, pixels)
            files[map_name] = file_name
            hashes[map_name] = _sha256(file_path)
        generated[preset.name] = {
            "preset": _preset_manifest(preset),
            "seed": preset_seed,
            "files": files,
            "sha256": hashes,
            "diagnostics": diagnostics,
        }
        preview_tiles.append({name: pixels for name, (_channels, pixels) in maps.items()})

    preview_name = "texture_contact_sheet.png"
    preview_pixels, preview_width, preview_height = _contact_sheet(
        preview_tiles, resolution
    )
    _write_png(
        output_path / preview_name,
        preview_width,
        preview_height,
        3,
        preview_pixels,
    )

    manifest = {
        "generator": "uchuva_lsystem.texture_assets",
        "generator_version": TEXTURE_GENERATOR_VERSION,
        "seed": seed,
        "resolution_px": resolution,
        "color_space": {
            "albedo": "sRGB IEC 61966-2-1",
            "height_normal_roughness_masks": "non-color linear data",
            "colorimetric_caution": (
                "Dataset colors are camera/render-domain inferences, not a "
                "spectrophotometer measurement of intrinsic reflectance."
            ),
        },
        "venation_taxonomy": {
            "leaf": LEAF_VENATION_TAXONOMY,
            "calyx": CALYX_VENATION_TAXONOMY,
        },
        "calibration": {
            "dataset": "Dataset Original (read-only)",
            "leaf_sample": {
                "frames": 400,
                "green_pixels": 300000,
                "median_srgb": [111, 136, 74],
                "midtone_median_srgb": [111, 136, 77],
                "method_status": "dataset_inferred_camera_srgb",
            },
            "calyx_sample": {
                "boxes_sampled": 800,
                "boxes_available": 3820,
                "cluster_median_srgb": [
                    [81, 94, 37],
                    [122, 125, 60],
                    [164, 164, 94],
                    [199, 192, 133],
                ],
                "method_status": "dataset_inferred_camera_srgb",
            },
            "literature_calyx_cielch_mean": {
                "L_star": 52.53,
                "C_star": 31.34,
                "h_degrees": 94.91,
                "sampling": "mean_across_20_27_34_41_days_after_anthesis",
                "method_status": "literature_reported",
            },
            "reflection": {
                "leaf_ior": 1.45,
                "leaf_blender_roughness_range": [0.92, 0.96],
                "calyx_blender_roughness_range": [0.93, 0.99],
                "specular_ior_level_max": 0.15,
                "method_status": "literature_bounded_manual_initial_guess",
                "note": (
                    "Blender Principled roughness is not numerically identical "
                    "to the roughness parameter fitted by leaf BRDF models."
                ),
            },
        },
        "texture_sets": generated,
        "preview": preview_name,
    }
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_asset_readme(output_path, manifest)
    return manifest


def _generate_texture_set(
    preset: TexturePreset,
    resolution: int,
    seed: int,
) -> tuple[dict[str, tuple[int, bytes]], dict[str, Any]]:
    if preset.organ == "leaf":
        height, order, diagnostics = _leaf_vein_fields(resolution, seed)
    else:
        height, order, diagnostics = _calyx_vein_fields(resolution, seed)

    albedo = _albedo_map(preset, height, order, resolution, seed)
    relief_height = _relief_height(preset, height, order)
    height_pixels = _grayscale_field(relief_height)
    normal = _normal_map(relief_height, resolution, preset.normal_strength, preset.organ)
    roughness = _roughness_map(preset, relief_height, resolution, seed)
    vein_mask = _vein_mask(height)
    vein_debug = _vein_debug(order)
    return (
        {
            "albedo": (3, albedo),
            "height": (1, height_pixels),
            "normal": (3, normal),
            "roughness": (1, roughness),
            "vein_mask": (1, vein_mask),
            "vein_debug": (3, vein_debug),
        },
        diagnostics,
    )


def _relief_height(
    preset: TexturePreset,
    height: array,
    order: bytearray,
) -> array:
    """Decouple chromatic vascular contrast from exaggerated main-rib relief."""
    if preset.organ != "calyx":
        return array("f", height)
    output = array("f", [0.0]) * len(height)
    for index, value in enumerate(height):
        vascular_order = order[index]
        if vascular_order == 1:
            scale = preset.primary_relief_scale
        elif vascular_order == 2:
            scale = min(0.62, preset.primary_relief_scale + 0.20)
        elif vascular_order in {3, 4}:
            scale = 0.78
        else:
            scale = 0.70
        output[index] = value * scale
    return output


def _leaf_vein_fields(
    resolution: int,
    seed: int,
) -> tuple[array, bytearray, dict[str, Any]]:
    rng = random.Random(seed)
    height = array("f", [0.0]) * (resolution * resolution)
    order = bytearray(resolution * resolution)
    strokes = {"primary": 0, "secondary": 0, "tertiary": 0, "quaternary": 0}

    midrib = [
        (0.5 + 0.006 * math.sin(t * math.tau), 0.015 + 0.975 * t)
        for t in (i / 80 for i in range(81))
    ]
    _draw_stroke(height, order, resolution, midrib, 0.0090, 1.0, 1)
    strokes["primary"] += 1

    basal_curves: dict[int, list[tuple[float, float]]] = {}
    for side in (-1, 1):
        end_x = 0.14 if side < 0 else 0.86
        curve = _bezier(
            (0.5, 0.065),
            (0.5 + side * 0.08, 0.10),
            (0.5 + side * 0.28, 0.25),
            (end_x, 0.39 + rng.uniform(-0.015, 0.015)),
            52,
        )
        _draw_stroke(height, order, resolution, curve, 0.0065, 0.88, 1)
        basal_curves[side] = curve
        strokes["primary"] += 1

    secondary_curves: dict[int, list[list[tuple[float, float]]]] = {-1: [], 1: []}
    bases = (0.16, 0.28, 0.40, 0.52, 0.64, 0.75)
    for side in (-1, 1):
        for index, base_y in enumerate(bases):
            end_x = (0.075 + 0.012 * index) if side < 0 else (0.925 - 0.012 * index)
            rise = 0.105 + 0.012 * index + rng.uniform(-0.012, 0.012)
            curve = _bezier(
                (0.5 + side * rng.uniform(0.0, 0.008), base_y),
                (0.5 + side * 0.095, base_y + 0.012),
                (0.5 + side * 0.31, base_y + rise * 0.56),
                (end_x, min(0.955, base_y + rise)),
                52,
            )
            secondary_curves[side].append(curve)
            _draw_stroke(height, order, resolution, curve, 0.0044, 0.72, 2)
            strokes["secondary"] += 1

    # Semicraspedodromous marginal branches: one branch approaches the margin,
    # while another links toward the super-adjacent secondary.
    for side in (-1, 1):
        curves = secondary_curves[side]
        for index in range(len(curves) - 1):
            start = curves[index][45]
            end = curves[index + 1][47]
            margin_x = 0.055 if side < 0 else 0.945
            loop = _bezier(
                start,
                (margin_x, start[1] + 0.015),
                (margin_x, end[1] - 0.020),
                end,
                32,
            )
            _draw_stroke(height, order, resolution, loop, 0.0028, 0.55, 2)
            strokes["secondary"] += 1

    # Alternate percurrent, sinuous tertiary veins between neighboring
    # secondaries. Each connector crosses an intercostal field.
    for side in (-1, 1):
        curves = secondary_curves[side]
        for band in range(len(curves) - 1):
            for connector in range(3):
                fraction = 0.24 + connector * 0.23
                a = curves[band][int(fraction * 51)]
                shifted = min(0.92, fraction + (0.05 if (band + connector) % 2 else -0.03))
                b = curves[band + 1][int(shifted * 51)]
                tertiary = _sinuous_connector(a, b, side, rng, 24)
                _draw_stroke(height, order, resolution, tertiary, 0.0021, 0.39, 3)
                strokes["tertiary"] += 1

    # A staggered fine lattice produces regular polygonal reticulate fourth-
    # order areoles. The leaf mesh clips the network at the true blade edge.
    rows, columns = 13, 12
    lattice: list[list[tuple[float, float]]] = []
    for row_index in range(rows):
        row: list[tuple[float, float]] = []
        y = 0.115 + row_index * 0.064
        for column_index in range(columns):
            x = 0.125 + column_index * 0.068
            stagger = 0.018 if row_index % 2 else 0.0
            row.append(
                (
                    min(0.90, x + stagger + rng.uniform(-0.010, 0.010)),
                    min(0.94, y + rng.uniform(-0.009, 0.009)),
                )
            )
        lattice.append(row)
    for row_index, row in enumerate(lattice):
        for column_index, point in enumerate(row):
            if column_index + 1 < len(row):
                _draw_stroke(
                    height,
                    order,
                    resolution,
                    _sinuous_connector(point, row[column_index + 1], 1, rng, 8),
                    0.00125,
                    0.21,
                    4,
                )
                strokes["quaternary"] += 1
            if row_index + 1 < len(lattice):
                target_column = min(
                    len(lattice[row_index + 1]) - 1,
                    column_index + (1 if (row_index + column_index) % 2 else 0),
                )
                _draw_stroke(
                    height,
                    order,
                    resolution,
                    [point, lattice[row_index + 1][target_column]],
                    0.00115,
                    0.18,
                    4,
                )
                strokes["quaternary"] += 1

    _add_microrelief(height, resolution, seed + 31, amplitude=0.016, fibrous=False)
    return height, order, {
        "topology": LEAF_VENATION_TAXONOMY,
        "stroke_counts": strokes,
        "suprabasal_primary_pair": True,
        "generated_lateral_veins_per_side": len(bases),
    }


def _calyx_vein_fields(
    resolution: int,
    seed: int,
) -> tuple[array, bytearray, dict[str, Any]]:
    rng = random.Random(seed)
    height = array("f", [0.0]) * (resolution * resolution)
    order = bytearray(resolution * resolution)
    strokes = {"major_midrib": 0, "intercostal": 0, "reticulate": 0}

    # Five sepal midribs align with the dominant physical lobes; five weaker
    # intercostal strands complete the reported 10-ribbed/angled appearance.
    for index in range(5):
        u = index / 5.0
        line = [
            (
                u + 0.006 * math.sin(t * math.tau * 1.3 + index),
                0.015 + 0.97 * t,
            )
            for t in (point / 80 for point in range(81))
        ]
        _draw_stroke(height, order, resolution, line, 0.0078, 1.0, 1, wrap_x=True)
        strokes["major_midrib"] += 1
        inter_u = (index + 0.5) / 5.0
        inter = [
            (
                inter_u + 0.009 * math.sin(t * math.tau * 1.7 + index * 0.8),
                0.04 + 0.91 * t,
            )
            for t in (point / 64 for point in range(65))
        ]
        _draw_stroke(height, order, resolution, inter, 0.0037, 0.67, 2, wrap_x=True)
        strokes["intercostal"] += 1

    rows, columns = 22, 24
    lattice: list[list[tuple[float, float]]] = []
    for row_index in range(rows):
        y = 0.09 + row_index * 0.074
        row: list[tuple[float, float]] = []
        for column_index in range(columns):
            u = column_index / columns
            u += (0.034 if row_index % 2 else 0.0) + rng.uniform(-0.012, 0.012)
            row.append((u % 1.0, min(0.94, y + rng.uniform(-0.014, 0.014))))
        lattice.append(row)

    for row_index, row in enumerate(lattice):
        for column_index, point in enumerate(row):
            neighbor = row[(column_index + 1) % columns]
            target = neighbor
            if target[0] < point[0]:
                target = (target[0] + 1.0, target[1])
            _draw_stroke(
                height,
                order,
                resolution,
                _sinuous_connector(point, target, 1, rng, 13),
                    0.0028,
                    0.50,
                3,
                wrap_x=True,
            )
            strokes["reticulate"] += 1
            if row_index + 1 < rows:
                offset = 1 if (row_index + column_index) % 3 == 0 else 0
                vertical_target = lattice[row_index + 1][(column_index + offset) % columns]
                target_u = vertical_target[0]
                if target_u - point[0] > 0.5:
                    target_u -= 1.0
                elif point[0] - target_u > 0.5:
                    target_u += 1.0
                _draw_stroke(
                    height,
                    order,
                    resolution,
                    _sinuous_connector(
                        point,
                        (target_u, vertical_target[1]),
                        1,
                        rng,
                        10,
                    ),
                    0.0024,
                    0.39,
                    3,
                    wrap_x=True,
                )
                strokes["reticulate"] += 1

    _add_microrelief(height, resolution, seed + 47, amplitude=0.024, fibrous=True)
    return height, order, {
        "topology": CALYX_VENATION_TAXONOMY,
        "stroke_counts": strokes,
        "seamless_u": True,
    }


def _bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    samples: int,
) -> list[tuple[float, float]]:
    points = []
    for index in range(samples):
        t = index / max(1, samples - 1)
        inv = 1.0 - t
        x = inv**3 * p0[0] + 3 * inv**2 * t * p1[0] + 3 * inv * t**2 * p2[0] + t**3 * p3[0]
        y = inv**3 * p0[1] + 3 * inv**2 * t * p1[1] + 3 * inv * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def _sinuous_connector(
    start: tuple[float, float],
    end: tuple[float, float],
    side: int,
    rng: random.Random,
    samples: int,
) -> list[tuple[float, float]]:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1e-6, math.hypot(dx, dy))
    normal = (-dy / length, dx / length)
    amplitude = min(0.012, length * 0.10) * rng.uniform(0.55, 1.0)
    phase = rng.uniform(0.0, math.tau)
    points = []
    for index in range(samples):
        t = index / max(1, samples - 1)
        wave = amplitude * math.sin(t * math.tau * 1.5 + phase) * math.sin(math.pi * t)
        points.append(
            (
                start[0] + dx * t + normal[0] * wave * side,
                start[1] + dy * t + normal[1] * wave * side,
            )
        )
    return points


def _draw_stroke(
    field: array,
    order_map: bytearray,
    resolution: int,
    points: Iterable[tuple[float, float]],
    width_uv: float,
    strength: float,
    vein_order: int,
    *,
    wrap_x: bool = False,
) -> None:
    pixel_points = [
        (x * (resolution - 1), (1.0 - y) * (resolution - 1)) for x, y in points
    ]
    radius = max(0.55, width_uv * resolution * 0.5)
    for left, right in zip(pixel_points, pixel_points[1:]):
        dx, dy = right[0] - left[0], right[1] - left[1]
        steps = max(1, int(max(abs(dx), abs(dy)) * 1.2))
        for step in range(steps + 1):
            t = step / steps
            _splat(
                field,
                order_map,
                resolution,
                left[0] + dx * t,
                left[1] + dy * t,
                radius,
                strength,
                vein_order,
                wrap_x,
            )


def _splat(
    field: array,
    order_map: bytearray,
    resolution: int,
    x: float,
    y: float,
    radius: float,
    strength: float,
    vein_order: int,
    wrap_x: bool,
) -> None:
    reach = max(1, int(math.ceil(radius * 1.65)))
    denominator = max(0.20, radius * radius * 0.74)
    for py in range(int(y) - reach, int(y) + reach + 1):
        if py < 0 or py >= resolution:
            continue
        for px_unwrapped in range(int(x) - reach, int(x) + reach + 1):
            px = px_unwrapped % resolution if wrap_x else px_unwrapped
            if px < 0 or px >= resolution:
                continue
            distance_sq = (px_unwrapped - x) ** 2 + (py - y) ** 2
            weight = math.exp(-distance_sq / denominator)
            if weight < 0.025:
                continue
            index = py * resolution + px
            candidate = strength * weight
            if candidate > field[index]:
                field[index] = candidate
                order_map[index] = vein_order


def _add_microrelief(
    field: array,
    resolution: int,
    seed: int,
    *,
    amplitude: float,
    fibrous: bool,
) -> None:
    rng = random.Random(seed)
    phases = [rng.uniform(0.0, math.tau) for _ in range(6)]
    for y in range(resolution):
        v = y / max(1, resolution - 1)
        for x in range(resolution):
            u = x / max(1, resolution - 1)
            broad = 0.50
            broad += 0.18 * math.sin(
                u * 43.7 + v * 17.3 + phases[0]
            )
            broad += 0.12 * math.sin(
                u * 91.1 - v * 63.5 + phases[1]
            )
            if fibrous:
                broad += 0.08 * math.sin(
                    v * 151.7 + 0.37 * math.sin(u * 18.9 + phases[2])
                )
            else:
                broad += 0.06 * math.sin(
                    u * 137.3 + v * 109.9 + phases[3]
                )
            index = y * resolution + x
            field[index] = min(1.0, max(0.0, field[index] + amplitude * broad))


def _value_noise_2d(
    u: float,
    v: float,
    seed: int,
    scale_x: float,
    scale_y: float,
    *,
    wrap_x: bool,
) -> float:
    """Return deterministic coherent noise without visible analytic waves."""
    period_x = max(2, int(round(scale_x)))
    x = u * period_x
    y = v * max(2.0, scale_y)
    x0 = math.floor(x)
    y0 = math.floor(y)
    fx = x - x0
    fy = y - y0
    sx = fx * fx * (3.0 - 2.0 * fx)
    sy = fy * fy * (3.0 - 2.0 * fy)

    def sample(ix: int, iy: int) -> float:
        if wrap_x:
            ix %= period_x
        value = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
        value = (value ^ (value >> 13)) * 1274126177 & 0xFFFFFFFF
        value ^= value >> 16
        return value / 0xFFFFFFFF

    top = sample(x0, y0) * (1.0 - sx) + sample(x0 + 1, y0) * sx
    bottom = sample(x0, y0 + 1) * (1.0 - sx) + sample(x0 + 1, y0 + 1) * sx
    return top * (1.0 - sy) + bottom * sy


def _fractal_noise_2d(
    u: float,
    v: float,
    seed: int,
    *,
    wrap_x: bool,
) -> float:
    weights = (0.58, 0.28, 0.14)
    scales = ((5.0, 4.0), (13.0, 11.0), (31.0, 27.0))
    return sum(
        weight
        * _value_noise_2d(
            u,
            v,
            seed + octave * 101,
            scale_x,
            scale_y,
            wrap_x=wrap_x,
        )
        for octave, (weight, (scale_x, scale_y)) in enumerate(zip(weights, scales))
    )


def _albedo_map(
    preset: TexturePreset,
    height: array,
    order: bytearray,
    resolution: int,
    seed: int,
) -> bytes:
    output = bytearray(resolution * resolution * 3)
    for y in range(resolution):
        v = y / max(1, resolution - 1)
        for x in range(resolution):
            u = x / max(1, resolution - 1)
            index = y * resolution + x
            wrap_x = preset.organ == "calyx"
            mottling = 0.12 * (
                _value_noise_2d(
                    u, v, seed + 101, 7.0, 6.0, wrap_x=wrap_x
                )
                - 0.50
            )
            mottling += 0.035 * (
                _value_noise_2d(
                    u, v, seed + 137, 47.0, 41.0, wrap_x=wrap_x
                )
                - 0.50
            )
            if preset.organ == "calyx":
                mottling += 0.025 * (
                    _value_noise_2d(
                        u, v, seed + 173, 17.0, 103.0, wrap_x=True
                    )
                    - 0.50
                )
            if preset.state == "dry_deteriorated":
                stain = _value_noise_2d(
                    u, v, seed + 211, 19.0, 17.0, wrap_x=True
                )
                mottling -= 0.075 * max(0.0, (stain - 0.73) / 0.27) ** 2
            vein = min(1.0, max(0.0, (height[index] - 0.055) * 1.35))
            if order[index] == 0:
                vein *= 0.15
            # Major veins carry more chromatic contrast than fourth-order areoles.
            order_weight = {0: 0.0, 1: 1.0, 2: 0.90, 3: 0.80, 4: 0.48}.get(order[index], 0.0)
            contrast_gain = 0.32 + 0.66 * preset.vein_contrast
            vein_mix = min(0.96, vein * order_weight * contrast_gain)
            apical_mask = (
                preset.apical_darkening
                * math.exp(-((v / 0.235) ** 2.0))
                if preset.organ == "calyx"
                else 0.0
            )
            for channel in range(3):
                base = preset.base_srgb[channel] * (1.0 + mottling) * (1.0 - 0.045 * apical_mask)
                vein_color = preset.vein_srgb[channel] * (1.0 - 0.46 * apical_mask)
                color = base * (1.0 - vein_mix) + vein_color * vein_mix
                output[index * 3 + channel] = _byte(color)
    return bytes(output)


def _roughness_map(
    preset: TexturePreset,
    height: array,
    resolution: int,
    seed: int,
) -> bytes:
    output = bytearray(resolution * resolution)
    for y in range(resolution):
        v = y / max(1, resolution - 1)
        for x in range(resolution):
            u = x / max(1, resolution - 1)
            index = y * resolution + x
            variation = 2.0 * _value_noise_2d(
                u,
                v,
                seed + 211,
                13.0,
                11.0,
                wrap_x=preset.organ == "calyx",
            ) - 1.0
            value = preset.roughness + preset.roughness_variation * variation
            value -= min(0.008, height[index] * 0.006)
            minimum = (
                0.92
                if preset.organ == "leaf"
                else 0.93
                if preset.state == "inflated_green"
                else 0.94
            )
            output[index] = _byte(max(minimum, min(1.0, value)) * 255.0)
    return bytes(output)


def _normal_map(
    height: array,
    resolution: int,
    strength: float,
    organ: str,
) -> bytes:
    output = bytearray(resolution * resolution * 3)
    wrap_x = organ == "calyx"
    for y in range(resolution):
        ym = max(0, y - 1)
        yp = min(resolution - 1, y + 1)
        for x in range(resolution):
            xm = (x - 1) % resolution if wrap_x else max(0, x - 1)
            xp = (x + 1) % resolution if wrap_x else min(resolution - 1, x + 1)
            dx = (height[y * resolution + xp] - height[y * resolution + xm]) * strength
            dy = (height[yp * resolution + x] - height[ym * resolution + x]) * strength
            nx, ny, nz = -dx, dy, 1.0
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            index = (y * resolution + x) * 3
            output[index] = _byte((nx / length * 0.5 + 0.5) * 255.0)
            output[index + 1] = _byte((ny / length * 0.5 + 0.5) * 255.0)
            output[index + 2] = _byte((nz / length * 0.5 + 0.5) * 255.0)
    return bytes(output)


def _grayscale_field(field: array) -> bytes:
    return bytes(_byte(value * 255.0) for value in field)


def _vein_mask(field: array) -> bytes:
    return bytes(_byte(max(0.0, min(1.0, (value - 0.05) * 1.7)) * 255.0) for value in field)


def _vein_debug(order: bytearray) -> bytes:
    colors = {
        0: (16, 18, 16),
        1: (244, 63, 49),
        2: (249, 153, 48),
        3: (65, 201, 214),
        4: (96, 112, 232),
    }
    output = bytearray(len(order) * 3)
    for index, value in enumerate(order):
        output[index * 3 : index * 3 + 3] = bytes(colors.get(value, colors[0]))
    return bytes(output)


def _contact_sheet(
    tiles: list[dict[str, bytes]],
    resolution: int,
) -> tuple[bytes, int, int]:
    tile_size = min(256, resolution)
    columns = len(tiles)
    rows = 4
    width = columns * tile_size
    height = rows * tile_size
    output = bytearray(width * height * 3)
    map_names = ("albedo", "vein_debug", "normal", "roughness")
    for column, maps in enumerate(tiles):
        for row, map_name in enumerate(map_names):
            source = maps[map_name]
            source_channels = 1 if map_name == "roughness" else 3
            for py in range(tile_size):
                sy = min(resolution - 1, int(py * resolution / tile_size))
                for px in range(tile_size):
                    sx = min(resolution - 1, int(px * resolution / tile_size))
                    source_index = (sy * resolution + sx) * source_channels
                    target_index = ((row * tile_size + py) * width + column * tile_size + px) * 3
                    if source_channels == 1:
                        value = source[source_index]
                        output[target_index : target_index + 3] = bytes((value, value, value))
                    else:
                        output[target_index : target_index + 3] = source[source_index : source_index + 3]
    return bytes(output), width, height


def _preset_manifest(preset: TexturePreset) -> dict[str, Any]:
    result = asdict(preset)
    result["base_cielab_d65"] = [round(value, 3) for value in _srgb_to_lab(preset.base_srgb)]
    result["vein_cielab_d65"] = [round(value, 3) for value in _srgb_to_lab(preset.vein_srgb)]
    return result


def _srgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    values = []
    for channel in rgb:
        value = channel / 255.0
        values.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    r, g, b = values
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def transform(value: float) -> float:
        delta = 6.0 / 29.0
        return value ** (1.0 / 3.0) if value > delta**3 else value / (3.0 * delta**2) + 4.0 / 29.0

    fx, fy, fz = transform(x), transform(y), transform(z)
    return 116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _write_png(
    path: Path,
    width: int,
    height: int,
    channels: int,
    pixels: bytes,
) -> None:
    if channels not in {1, 3}:
        raise ValueError("PNG writer supports grayscale or RGB maps")
    expected = width * height * channels
    if len(pixels) != expected:
        raise ValueError(f"Expected {expected} pixel bytes, received {len(pixels)}")
    color_type = 0 if channels == 1 else 2
    stride = width * channels
    raw = b"".join(
        b"\x00" + pixels[row * stride : (row + 1) * stride]
        for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", header)
    payload += _png_chunk(b"IDAT", zlib.compress(raw, level=9))
    payload += _png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


def _write_asset_readme(output_path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Texturas sintéticas de uchuva v3",
        "",
        "Biblioteca generada de forma reproducible y sin depender de Blender.",
        "Los colores inferidos del dataset son valores de dominio de cámara, no",
        "mediciones espectrofotométricas de reflectancia intrínseca.",
        "",
        "## Vista conjunta",
        "",
        "![Albedo, venación por orden, normales y rugosidad](texture_contact_sheet.png)",
        "",
        "Columnas: dos hojas, cuatro capachos verdes, tres pajizos y tres secos.",
        "Filas: albedo, orden de venación, normal y rugosidad.",
        "",
        "## Mapas por conjunto",
        "",
    ]
    for name, item in manifest["texture_sets"].items():
        files = item["files"]
        lines.extend(
            [
                f"### {name}",
                "",
                f"![Albedo]({files['albedo']}) ![Normal]({files['normal']})",
                "",
                f"![Máscara de venas]({files['vein_mask']}) ![Órdenes de venación]({files['vein_debug']})",
                "",
            ]
        )
    lines.extend(
        [
            "## Regeneración",
            "",
            "```powershell",
            "python scripts/generate_uchuva_texture_library.py --seed 1701 --resolution 512",
            "```",
            "",
            "Los parámetros, estados de evidencia y hashes SHA-256 están en",
            "`manifest.json`.",
            "",
        ]
    )
    (output_path / "README.md").write_text("\n".join(lines), encoding="utf-8")
