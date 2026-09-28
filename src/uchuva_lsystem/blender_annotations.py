"""Blender tagging, RGB rendering, and lossless annotation-mask exports."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .yolo_export import global_reproductive_id


SEMANTIC_CLASSES: dict[str, int] = {
    "background": 0,
    "soil": 1,
    "leaf": 2,
    "stem": 3,
    "flower": 4,
    "calyx": 5,
}

SEMANTIC_PALETTE: dict[int, tuple[int, int, int]] = {
    0: (0, 0, 0),
    1: (128, 90, 55),
    2: (25, 180, 60),
    3: (30, 90, 25),
    4: (255, 210, 30),
    5: (210, 160, 70),
}
ANNOTATION_COLOR_SNAP_MAX_DISTANCE_SQ = 2700


def _blender_modules():
    import bpy

    return bpy


def tag_annotation_object(
    obj: object | None,
    semantic_class: str,
    *,
    plant_id: str = "",
    plant_role: str = "",
    organ_id: str = "",
    reproductive_id: str = "",
    calyx_state: str = "",
    maturity: str = "",
    reproductive_stage: str = "",
    annotation_visible: bool = True,
    organ_kind: str = "",
    axis_id: str = "",
    axis_parent_node_id: str = "",
    internode_index: int = -1,
    parent_node_id: str = "",
    axis_order: int = -1,
    orientation_adjustment_deg: float = 0.0,
    clearance_lift_cm: float = 0.0,
    clearance_lift_reason: str = "",
) -> None:
    """Attach stable annotation metadata directly to a Blender object."""
    if obj is None:
        return
    if semantic_class not in SEMANTIC_CLASSES and semantic_class != "ignore":
        raise ValueError(f"Unknown semantic annotation class: {semantic_class}")
    obj["uchuva_semantic_class"] = semantic_class
    obj["uchuva_plant_id"] = plant_id
    obj["uchuva_plant_role"] = plant_role
    obj["uchuva_organ_id"] = organ_id
    obj["uchuva_reproductive_id"] = reproductive_id
    obj["uchuva_reproductive_instance_id"] = global_reproductive_id(
        plant_id, reproductive_id
    )
    obj["uchuva_calyx_state"] = calyx_state
    obj["uchuva_maturity"] = maturity
    obj["uchuva_reproductive_stage"] = reproductive_stage
    obj["uchuva_annotation_visible"] = bool(annotation_visible)
    obj["uchuva_organ_kind"] = organ_kind
    obj["uchuva_axis_id"] = axis_id
    obj["uchuva_axis_parent_node_id"] = axis_parent_node_id
    obj["uchuva_internode_index"] = int(internode_index)
    obj["uchuva_parent_node_id"] = parent_node_id
    obj["uchuva_axis_order"] = int(axis_order)
    obj["uchuva_orientation_adjustment_deg"] = float(
        orientation_adjustment_deg
    )
    obj["uchuva_clearance_lift_cm"] = float(clearance_lift_cm)
    obj["uchuva_clearance_lift_reason"] = clearance_lift_reason


def render_camera_outputs(
    camera: object,
    profile_name: str,
    output_dir: str | Path,
    *,
    width: int,
    height: int,
    cycles_samples: int,
    render_rgb: bool = True,
    render_cycles: bool = False,
) -> dict[str, Any]:
    """Render standard RGB plus masks; Cycles remains an explicit opt-in."""
    output_path = Path(output_dir) / profile_name
    output_path.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "profile": profile_name,
        "camera": camera_metadata(camera, width, height),
        "rgb": {},
    }

    if render_rgb:
        eevee_path = output_path / "rgb_eevee.png"
        _render_rgb(
            camera,
            eevee_path,
            engine="BLENDER_EEVEE_NEXT",
            width=width,
            height=height,
            cycles_samples=cycles_samples,
        )
        report["rgb"]["eevee"] = str(eevee_path)

        if render_cycles:
            cycles_path = output_path / "rgb_cycles.png"
            _render_rgb(
                camera,
                cycles_path,
                engine="CYCLES",
                width=width,
                height=height,
                cycles_samples=cycles_samples,
            )
            report["rgb"]["cycles"] = str(cycles_path)

    report["annotations"] = _render_annotation_masks(
        camera,
        output_path,
        width=width,
        height=height,
    )
    return report


def render_rgb_image(
    camera: object,
    output_path: str | Path,
    *,
    width: int,
    height: int,
    engine: str = "BLENDER_EEVEE_NEXT",
    cycles_samples: int = 64,
    image_format: str = "PNG",
    jpeg_quality: int = 90,
    exposure_ev: float = 0.0,
    gamma: float = 1.0,
    filter_size: float = 1.5,
    dither_intensity: float = 0.0,
    white_balance_temperature: float = 6500.0,
    white_balance_tint: float = 0.0,
) -> Path:
    """Render one RGB image while preserving the caller's scene settings."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _render_rgb(
        camera,
        path,
        engine=engine,
        width=width,
        height=height,
        cycles_samples=cycles_samples,
        image_format=image_format,
        jpeg_quality=jpeg_quality,
        exposure_ev=exposure_ev,
        gamma=gamma,
        filter_size=filter_size,
        dither_intensity=dither_intensity,
        white_balance_temperature=white_balance_temperature,
        white_balance_tint=white_balance_tint,
    )
    return path


def render_reproductive_annotations(
    camera: object,
    output_dir: str | Path,
    *,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Render only the reproductive-instance pass used for YOLO boxes."""
    results = _render_annotation_masks(
        camera,
        Path(output_dir),
        width=width,
        height=height,
        pass_names=("reproductive_instance",),
    )
    return results["reproductive_instance"]


def render_crisp_calyx_annotations(camera: object, output_dir: str | Path, *, width: int, height: int) -> dict[str, Any]:
    """Rasterize single-sample IDs without blended colors becoming other instances.

Workbench flat object colors do not depend on lights/materials. Anti-aliasing
is disabled explicitly; RGB rendering stays EEVEE. All non-target objects
remain present as black depth occluders.
    """
    bpy = _blender_modules()
    scene = bpy.context.scene
    registry = annotation_registry()
    spec = _annotation_pass_definitions(registry)["reproductive_instance"]
    previous = _capture_render_state(scene)
    shading = scene.display.shading
    shading_keys = ("light","color_type","show_shadows","show_cavity","show_specular_highlight","background_type","background_color","show_object_outline","show_xray","show_backface_culling")
    old_shading = {k: tuple(getattr(shading,k)) if k=="background_color" else getattr(shading,k) for k in shading_keys}
    old_aa = scene.display.render_aa
    colors = {obj.name:tuple(obj.color) for obj in scene.objects}
    folder = Path(output_dir).resolve()
    raw, final = folder/".crisp_raw.png",folder/"mask_calyx_crisp_v2.png"
    try:
        scene.camera = camera
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.render_aa = "OFF"
        shading.light = "FLAT"
        shading.color_type = "OBJECT"
        shading.show_shadows = shading.show_cavity = shading.show_specular_highlight = False
        shading.show_object_outline = shading.show_xray = shading.show_backface_culling = False
        shading.background_type = "VIEWPORT"
        shading.background_color = (0,0,0)
        for obj in scene.objects:
            obj.color = (0,0,0,1)
        for obj in registry["objects"]:
            obj.color = _linear_rgba(spec["object_color"](obj)) if obj.get("uchuva_semantic_class")=="calyx" else (0,0,0,1)
        scene.render.resolution_x,scene.render.resolution_y = width,height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "8"
        scene.render.film_transparent = True
        scene.render.dither_intensity = 0
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0
        scene.view_settings.gamma = 1
        scene.render.filepath = str(raw)
        bpy.ops.render.render(write_still=True)
        stats = _snap_and_save_image(raw, final, spec["palette"],width,height)
        raw.unlink()
        return {"path":str(final),"engine":"BLENDER_WORKBENCH","anti_aliasing":"OFF",
                "palette_version":"rgb_lattice_4095_v1", "palette":{str(k):list(v) for k,v in spec["palette"].items()},
                "items":_enrich_mask_stats("reproductive_instance",stats,registry)}
    finally:
        for obj in scene.objects:
            if obj.name in colors: obj.color = colors[obj.name]
        for key,value in old_shading.items(): setattr(shading,key,value)
        scene.display.render_aa = old_aa
        _restore_render_state(scene,previous)


def camera_metadata(camera: object, width: int, height: int) -> dict[str, Any]:
    """Return camera pose and a compact pinhole intrinsic matrix."""
    lens_mm = float(camera.data.lens)
    sensor_width = float(camera.data.sensor_width)
    fx = width * lens_mm / max(sensor_width, 1e-6)
    pixel_aspect = 1.0
    fy = fx * pixel_aspect
    matrix_world = [
        [round(float(value), 8) for value in row]
        for row in camera.matrix_world
    ]
    return {
        "name": camera.name,
        "width": width,
        "height": height,
        "lens_mm": round(lens_mm, 4),
        "sensor_width_mm": round(sensor_width, 4),
        "clip_start": round(float(camera.data.clip_start), 5),
        "clip_end": round(float(camera.data.clip_end), 3),
        "intrinsic_matrix": [
            [round(fx, 6), 0.0, width / 2.0],
            [0.0, round(fy, 6), height / 2.0],
            [0.0, 0.0, 1.0],
        ],
        "matrix_world": matrix_world,
        "depth_of_field": {
            "enabled_for_rgb": bool(camera.data.dof.use_dof),
            "fstop": round(float(camera.data.dof.aperture_fstop), 4),
        },
    }


def annotation_registry() -> dict[str, Any]:
    """Describe all tagged objects and assign deterministic integer IDs."""
    bpy = _blender_modules()
    objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}
        and bool(obj.get("uchuva_annotation_visible", False))
        and not obj.hide_render
    ]
    plant_names = sorted(
        {str(obj.get("uchuva_plant_id", "")) for obj in objects if obj.get("uchuva_plant_id")}
    )
    reproductive_names = sorted(
        {
            _object_reproductive_instance_id(obj)
            for obj in objects
            if _object_reproductive_instance_id(obj)
            and obj.get("uchuva_semantic_class") in {"flower", "calyx"}
        }
    )
    plant_ids = {name: index + 1 for index, name in enumerate(plant_names)}
    reproductive_ids = {
        name: index + 1 for index, name in enumerate(reproductive_names)
    }
    reproductive_classes: dict[str, str] = {}
    reproductive_metadata: dict[str, dict[str, str]] = {}
    for obj in objects:
        reproductive_name = _object_reproductive_instance_id(obj)
        semantic_class = str(obj.get("uchuva_semantic_class", "background"))
        if reproductive_name and semantic_class in {"flower", "calyx"}:
            reproductive_classes[reproductive_name] = semantic_class
            reproductive_metadata[reproductive_name] = {
                "instance_id": reproductive_name,
                "local_reproductive_id": str(obj.get("uchuva_reproductive_id", "")),
                "plant_id": str(obj.get("uchuva_plant_id", "")),
                "plant_role": str(obj.get("uchuva_plant_role", "")),
                "semantic_class": semantic_class,
                "calyx_state": str(obj.get("uchuva_calyx_state", "")),
                "maturity": str(obj.get("uchuva_maturity", "")),
                "reproductive_stage": str(obj.get("uchuva_reproductive_stage", "")),
            }

    return {
        "objects": objects,
        "plant_ids": plant_ids,
        "reproductive_ids": reproductive_ids,
        "reproductive_classes": reproductive_classes,
        "reproductive_metadata": reproductive_metadata,
    }


def _object_reproductive_instance_id(obj: object) -> str:
    stored = str(obj.get("uchuva_reproductive_instance_id", ""))
    if stored:
        return stored
    return global_reproductive_id(
        str(obj.get("uchuva_plant_id", "")),
        str(obj.get("uchuva_reproductive_id", "")),
    )


def _render_rgb(
    camera: object,
    output_path: Path,
    *,
    engine: str,
    width: int,
    height: int,
    cycles_samples: int,
    image_format: str = "PNG",
    jpeg_quality: int = 90,
    exposure_ev: float = 0.0,
    gamma: float = 1.0,
    filter_size: float = 1.5,
    dither_intensity: float = 0.0,
    white_balance_temperature: float = 6500.0,
    white_balance_tint: float = 0.0,
) -> None:
    bpy = _blender_modules()
    scene = bpy.context.scene
    previous = _capture_render_state(scene)
    try:
        scene.camera = camera
        effective_engine = _set_render_engine(scene, engine)
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = image_format
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        if image_format == "JPEG":
            scene.render.image_settings.quality = max(1, min(100, int(jpeg_quality)))
        scene.render.film_transparent = False
        scene.render.filter_size = max(0.01, float(filter_size))
        if hasattr(scene.render, "dither_intensity"):
            scene.render.dither_intensity = max(0.0, float(dither_intensity))
        scene.view_settings.exposure = float(exposure_ev)
        scene.view_settings.gamma = max(0.5, min(2.0, float(gamma)))
        if hasattr(scene.view_settings, "use_white_balance"):
            scene.view_settings.use_white_balance = True
        if hasattr(scene.view_settings, "white_balance_temperature"):
            scene.view_settings.white_balance_temperature = float(white_balance_temperature)
        if hasattr(scene.view_settings, "white_balance_tint"):
            scene.view_settings.white_balance_tint = float(white_balance_tint)
        scene.render.filepath = str(output_path)
        if effective_engine == "CYCLES":
            scene.cycles.samples = cycles_samples
            scene.cycles.use_denoising = True
            scene.cycles.use_adaptive_sampling = True
        bpy.ops.render.render(write_still=True)
    finally:
        _restore_render_state(scene, previous)


def _render_annotation_masks(
    camera: object,
    output_path: Path,
    *,
    width: int,
    height: int,
    pass_names: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    bpy = _blender_modules()
    scene = bpy.context.scene
    registry = annotation_registry()
    annotation_material = _annotation_override_material()
    annotation_world = _annotation_world()
    passes = _annotation_pass_definitions(registry)
    if pass_names is not None:
        unknown = set(pass_names) - set(passes)
        if unknown:
            raise ValueError(f"Unknown annotation passes: {sorted(unknown)}")
        passes = {name: passes[name] for name in pass_names}
    results: dict[str, Any] = {}
    previous = _capture_render_state(scene)
    original_world = scene.world
    original_override = scene.view_layers[0].material_override
    original_colors = {obj.name: tuple(obj.color) for obj in registry["objects"]}
    original_dof = bool(camera.data.dof.use_dof)

    try:
        scene.camera = camera
        camera.data.dof.use_dof = False
        _set_render_engine(scene, "BLENDER_EEVEE_NEXT")
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        scene.render.film_transparent = False
        scene.render.filter_size = 0.01
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"
        scene.view_settings.exposure = 0.0
        scene.view_settings.gamma = 1.0
        scene.world = annotation_world
        scene.view_layers[0].material_override = annotation_material

        for pass_name, pass_spec in passes.items():
            for obj in registry["objects"]:
                obj.color = _linear_rgba(pass_spec["object_color"](obj))
            mask_path = output_path / f"mask_{pass_name}.png"
            raw_path = output_path / f".{pass_name}_raw.png"
            scene.render.filepath = str(raw_path)
            bpy.ops.render.render(write_still=True)
            stats = _snap_and_save_image(
                raw_path,
                mask_path,
                pass_spec["palette"],
                width,
                height,
            )
            raw_path.unlink(missing_ok=True)
            results[pass_name] = {
                "palette_version": "rgb_lattice_4095_v1",
                "path": str(mask_path),
                "palette": {
                    str(identifier): list(color)
                    for identifier, color in pass_spec["palette"].items()
                },
                "items": _enrich_mask_stats(pass_name, stats, registry),
            }
    finally:
        for obj in registry["objects"]:
            if obj.name in original_colors:
                obj.color = original_colors[obj.name]
        camera.data.dof.use_dof = original_dof
        scene.view_layers[0].material_override = original_override
        scene.world = original_world
        _restore_render_state(scene, previous)
    return results


_PREVIEW_COLORS: dict[str, tuple[int, int, int]] = {
    "calyx": (245, 205, 65),
}

_FONT_5X7: dict[str, tuple[str, ...]] = {
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "a": ("00000", "01110", "00001", "01111", "10001", "01111", "00000"),
    "c": ("00000", "01110", "10000", "10000", "10000", "01110", "00000"),
    "d": ("00001", "00001", "01111", "10001", "10001", "01111", "00000"),
    "e": ("00000", "01110", "10001", "11111", "10000", "01110", "00000"),
    "f": ("00110", "01001", "01000", "11100", "01000", "01000", "00000"),
    "g": ("00000", "01111", "10001", "01111", "00001", "01110", "00000"),
    "l": ("01100", "00100", "00100", "00100", "00100", "01110", "00000"),
    "n": ("00000", "10110", "11001", "10001", "10001", "10001", "00000"),
    "o": ("00000", "01110", "10001", "10001", "10001", "01110", "00000"),
    "r": ("00000", "10110", "11001", "10000", "10000", "10000", "00000"),
    "s": ("00000", "01111", "10000", "01110", "00001", "11110", "00000"),
    "t": ("01000", "11100", "01000", "01000", "01001", "00110", "00000"),
    "w": ("00000", "10001", "10001", "10101", "10101", "01010", "00000"),
    "x": ("00000", "10001", "01010", "00100", "01010", "10001", "00000"),
    "y": ("00000", "10001", "10001", "01111", "00001", "01110", "00000"),
}


def render_detection_preview(
    rgb_path: str | Path,
    output_path: str | Path,
    detections: list[object],
) -> Path:
    """Draw class-labelled boxes using Blender image buffers only."""
    bpy = _blender_modules()
    source_path = Path(rgb_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image = bpy.data.images.load(str(source_path), check_existing=False)
    try:
        width, height = (int(value) for value in image.size)
        pixels = list(image.pixels)
        for detection in detections:
            class_name = str(detection.class_name)
            color = _PREVIEW_COLORS.get(class_name, (255, 255, 255))
            x, y, box_width, box_height = detection.bbox_xywh
            _draw_rectangle(
                pixels, width, height, x, y, box_width, box_height, color, thickness=2
            )
            label_y = max(0, y - 9)
            _draw_label(pixels, width, height, x, label_y, class_name, color)
        temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
        image.file_format = "PNG"
        image.filepath_raw = str(temporary)
        image.pixels.foreach_set(pixels)
        image.save()
        temporary.replace(destination)
    finally:
        bpy.data.images.remove(image)
    return destination


def _draw_rectangle(
    pixels: list[float],
    image_width: int,
    image_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
    *,
    thickness: int,
) -> None:
    x2 = min(image_width - 1, x + width - 1)
    y2 = min(image_height - 1, y + height - 1)
    for offset in range(thickness):
        for pixel_x in range(max(0, x), x2 + 1):
            _set_preview_pixel(pixels, image_width, image_height, pixel_x, y + offset, color)
            _set_preview_pixel(pixels, image_width, image_height, pixel_x, y2 - offset, color)
        for pixel_y in range(max(0, y), y2 + 1):
            _set_preview_pixel(pixels, image_width, image_height, x + offset, pixel_y, color)
            _set_preview_pixel(pixels, image_width, image_height, x2 - offset, pixel_y, color)


def _draw_label(
    pixels: list[float],
    image_width: int,
    image_height: int,
    x: int,
    y: int,
    label: str,
    color: tuple[int, int, int],
) -> None:
    text_width = len(label) * 6 + 2
    for pixel_y in range(y, min(image_height, y + 9)):
        for pixel_x in range(x, min(image_width, x + text_width)):
            _set_preview_pixel(pixels, image_width, image_height, pixel_x, pixel_y, (0, 0, 0))
    cursor_x = x + 1
    for character in label.lower():
        glyph = _FONT_5X7.get(character)
        if glyph is not None:
            for row, pattern in enumerate(glyph):
                for column, enabled in enumerate(pattern):
                    if enabled == "1":
                        _set_preview_pixel(
                            pixels,
                            image_width,
                            image_height,
                            cursor_x + column,
                            y + 1 + row,
                            color,
                        )
        cursor_x += 6


def _set_preview_pixel(
    pixels: list[float],
    width: int,
    height: int,
    x: int,
    y_top: int,
    color: tuple[int, int, int],
) -> None:
    if x < 0 or y_top < 0 or x >= width or y_top >= height:
        return
    y_bottom = height - 1 - y_top
    offset = (y_bottom * width + x) * 4
    pixels[offset] = _srgb_to_linear(color[0] / 255.0)
    pixels[offset + 1] = _srgb_to_linear(color[1] / 255.0)
    pixels[offset + 2] = _srgb_to_linear(color[2] / 255.0)
    pixels[offset + 3] = 1.0


def _annotation_pass_definitions(registry: dict[str, Any]) -> dict[str, Any]:
    plant_palette = {0: (0, 0, 0)}
    plant_palette.update(
        {
            identifier: _instance_color(identifier)
            for identifier in registry["plant_ids"].values()
        }
    )
    reproductive_palette = {0: (0, 0, 0)}
    reproductive_palette.update(
        {
            identifier: _instance_color(identifier)
            for identifier in registry["reproductive_ids"].values()
        }
    )

    return {
        "semantic": {
            "palette": SEMANTIC_PALETTE,
            "object_color": lambda obj: SEMANTIC_PALETTE[
                SEMANTIC_CLASSES.get(str(obj.get("uchuva_semantic_class", "background")), 0)
            ],
        },
        "plant_instance": {
            "palette": plant_palette,
            "object_color": lambda obj: plant_palette[
                registry["plant_ids"].get(str(obj.get("uchuva_plant_id", "")), 0)
            ],
        },
        "reproductive_instance": {
            "palette": reproductive_palette,
            "object_color": lambda obj: reproductive_palette[
                registry["reproductive_ids"].get(
                    _object_reproductive_instance_id(obj), 0
                )
                if obj.get("uchuva_semantic_class") in {"flower", "calyx"}
                else 0
            ],
        },
    }


def _snap_and_save_image(
    source_path: Path,
    output_path: Path,
    palette: dict[int, tuple[int, int, int]],
    width: int,
    height: int,
) -> dict[int, dict[str, Any]]:
    bpy = _blender_modules()
    source_image = bpy.data.images.load(str(source_path), check_existing=False)
    actual_width, actual_height = source_image.size
    if actual_width != width or actual_height != height:
        bpy.data.images.remove(source_image)
        raise RuntimeError(
            f"Annotation render has size {actual_width}x{actual_height}, expected {width}x{height}."
        )
    pixels = list(source_image.pixels)
    bpy.data.images.remove(source_image)
    palette_items = list(palette.items())
    output_palette = {
        identifier: _normalized_rgba(color) for identifier, color in palette_items
    }
    quantized_cache: dict[tuple[int, int, int], tuple[int, tuple[float, float, float, float]]] = {}
    pixel_count = width * height
    identifiers = [0] * pixel_count
    snapped = [0.0] * (pixel_count * 4)
    stats: dict[int, dict[str, Any]] = {
        identifier: {
            "visible_pixels": 0,
            "min_x": width,
            "min_y": height,
            "max_x": -1,
            "max_y": -1,
        }
        for identifier in palette
    }

    for pixel_index in range(pixel_count):
        offset = pixel_index * 4
        rgb8 = (
            _normalized_channel_to_byte(pixels[offset]),
            _normalized_channel_to_byte(pixels[offset + 1]),
            _normalized_channel_to_byte(pixels[offset + 2]),
        )
        if pixels[offset + 3] < 0.5:
            rgb8 = (0, 0, 0)
        matched = quantized_cache.get(rgb8)
        if matched is None:
            identifier = _nearest_palette_identifier(rgb8, palette_items)
            matched = (identifier, output_palette[identifier])
            quantized_cache[rgb8] = matched
        identifier, _ = matched
        identifiers[pixel_index] = identifier

    if not bpy.context.scene.get("uchuva_preserve_mask_components", False):
        _remove_tiny_annotation_components(identifiers, width, height)
    for pixel_index, identifier in enumerate(identifiers):
        offset = pixel_index * 4
        snapped[offset : offset + 4] = output_palette[identifier]
        x = pixel_index % width
        y_bottom = pixel_index // width
        y = height - 1 - y_bottom
        item = stats[identifier]
        item["visible_pixels"] += 1
        item["min_x"] = min(item["min_x"], x)
        item["min_y"] = min(item["min_y"], y)
        item["max_x"] = max(item["max_x"], x)
        item["max_y"] = max(item["max_y"], y)

    image = bpy.data.images.new(
        name=f"uchuva_annotation_{output_path.stem}",
        width=width,
        height=height,
        alpha=True,
        float_buffer=False,
    )
    try:
        image.pixels.foreach_set(snapped)
        image.file_format = "PNG"
        image.filepath_raw = str(output_path)
        image.save_render(str(output_path), scene=bpy.context.scene)
    finally:
        bpy.data.images.remove(image)

    for identifier, item in stats.items():
        if item["visible_pixels"] <= 0:
            item["bbox_xywh"] = None
            item["bbox_area"] = 0
            item["occlusion_proxy"] = None
            for key in ("min_x", "min_y", "max_x", "max_y"):
                item.pop(key, None)
            continue
        box_width = item["max_x"] - item["min_x"] + 1
        box_height = item["max_y"] - item["min_y"] + 1
        area = box_width * box_height
        item["bbox_xywh"] = [item["min_x"], item["min_y"], box_width, box_height]
        item["bbox_area"] = area
        item["occlusion_proxy"] = round(
            1.0 - item["visible_pixels"] / max(area, 1), 6
        )
        for key in ("min_x", "min_y", "max_x", "max_y"):
            item.pop(key, None)
    return stats


def _nearest_palette_identifier(
    rgb8: tuple[int, int, int],
    palette_items: list[tuple[int, tuple[int, int, int]]],
) -> int:
    """Snap genuine pass colors while forcing unrelated bright geometry to background."""
    identifier, _color = min(
        palette_items,
        key=lambda item: sum(
            (rgb8[channel] - item[1][channel]) ** 2 for channel in range(3)
        ),
    )
    if identifier == 0:
        return 0
    distance_sq = sum(
        (rgb8[channel] - _color[channel]) ** 2 for channel in range(3)
    )
    return (
        identifier
        if distance_sq <= ANNOTATION_COLOR_SNAP_MAX_DISTANCE_SQ
        else 0
    )


def _remove_tiny_annotation_components(
    identifiers: list[int],
    width: int,
    height: int,
    min_component_pixels: int = 3,
) -> None:
    """Remove isolated quantization specks without discarding occluded organs."""
    visited = bytearray(len(identifiers))
    for start, identifier in enumerate(identifiers):
        if identifier == 0 or visited[start]:
            continue
        visited[start] = 1
        stack = [start]
        component: list[int] = []
        while stack:
            current = stack.pop()
            component.append(current)
            x = current % width
            for neighbor in (
                current - 1 if x > 0 else -1,
                current + 1 if x + 1 < width else -1,
                current - width if current >= width else -1,
                current + width if current + width < width * height else -1,
            ):
                if (
                    neighbor >= 0
                    and not visited[neighbor]
                    and identifiers[neighbor] == identifier
                ):
                    visited[neighbor] = 1
                    stack.append(neighbor)
        if len(component) < min_component_pixels:
            for pixel_index in component:
                identifiers[pixel_index] = 0


def _enrich_mask_stats(
    pass_name: str,
    stats: dict[int, dict[str, Any]],
    registry: dict[str, Any],
) -> dict[str, Any]:
    inverse_plants = {value: key for key, value in registry["plant_ids"].items()}
    inverse_reproductive = {
        value: key for key, value in registry["reproductive_ids"].items()
    }
    inverse_semantic = {value: key for key, value in SEMANTIC_CLASSES.items()}
    result: dict[str, Any] = {}
    for identifier, item in stats.items():
        if pass_name == "semantic":
            label = inverse_semantic.get(identifier, "unknown")
            name = label
            semantic_class = label
        elif pass_name == "plant_instance":
            name = inverse_plants.get(identifier, "background")
            semantic_class = "plant" if identifier else "background"
        else:
            name = inverse_reproductive.get(identifier, "background")
            semantic_class = registry["reproductive_classes"].get(
                name, "background"
            )
            metadata = registry.get("reproductive_metadata", {}).get(name, {})
        result[str(identifier)] = {
            "name": name,
            "semantic_class": semantic_class,
            **(metadata if pass_name == "reproductive_instance" else {}),
            **item,
        }
    return result


def _annotation_override_material() -> object:
    bpy = _blender_modules()
    name = "Uchuva_Annotation_ObjectColor"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission = nodes.new(type="ShaderNodeEmission")
    object_info = nodes.new(type="ShaderNodeObjectInfo")
    links.new(object_info.outputs["Color"], emission.inputs["Color"])
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _annotation_world() -> object:
    bpy = _blender_modules()
    world = bpy.data.worlds.get("Uchuva_Annotation_World") or bpy.data.worlds.new(
        "Uchuva_Annotation_World"
    )
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        background.inputs["Strength"].default_value = 0.0
    return world


def _capture_render_state(scene: object) -> dict[str, Any]:
    return {
        "camera": scene.camera,
        "engine": scene.render.engine,
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth,
        "quality": scene.render.image_settings.quality,
        "film_transparent": scene.render.film_transparent,
        "dither_intensity": getattr(scene.render, "dither_intensity", 0.0),
        "filter_size": scene.render.filter_size,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "gamma": scene.view_settings.gamma,
        "use_white_balance": getattr(scene.view_settings, "use_white_balance", None),
        "white_balance_temperature": getattr(
            scene.view_settings, "white_balance_temperature", None
        ),
        "white_balance_tint": getattr(scene.view_settings, "white_balance_tint", None),
    }


def _set_render_engine(scene: object, requested: str) -> str:
    """Use Blender's current EEVEE enum while accepting the historical name."""
    if requested != "BLENDER_EEVEE_NEXT":
        scene.render.engine = requested
        return requested
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        return "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
        return "BLENDER_EEVEE"


def _restore_render_state(scene: object, state: dict[str, Any]) -> None:
    scene.camera = state["camera"]
    scene.render.engine = state["engine"]
    scene.render.filepath = state["filepath"]
    scene.render.resolution_x = state["resolution_x"]
    scene.render.resolution_y = state["resolution_y"]
    scene.render.resolution_percentage = state["resolution_percentage"]
    scene.render.image_settings.file_format = state["file_format"]
    scene.render.image_settings.color_mode = state["color_mode"]
    scene.render.image_settings.color_depth = state["color_depth"]
    scene.render.image_settings.quality = state["quality"]
    scene.render.film_transparent = state["film_transparent"]
    if hasattr(scene.render, "dither_intensity"):
        scene.render.dither_intensity = state["dither_intensity"]
    scene.render.filter_size = state["filter_size"]
    scene.view_settings.view_transform = state["view_transform"]
    scene.view_settings.look = state["look"]
    scene.view_settings.exposure = state["exposure"]
    scene.view_settings.gamma = state["gamma"]
    if state["use_white_balance"] is not None:
        scene.view_settings.use_white_balance = state["use_white_balance"]
    if state["white_balance_temperature"] is not None:
        scene.view_settings.white_balance_temperature = state[
            "white_balance_temperature"
        ]
    if state["white_balance_tint"] is not None:
        scene.view_settings.white_balance_tint = state["white_balance_tint"]


def _instance_color(identifier: int) -> tuple[int, int, int]:
    if identifier <= 0:
        return (0, 0, 0)
    if identifier >= 4096:
        raise ValueError("Instance palette supports at most 4095 foreground IDs per scene")
    # A bijection over a 16^3 lattice; old palette collided every 200 IDs.
    code = (identifier * 1597) % 4096
    return ((code & 15)*17, ((code >> 4) & 15)*17, ((code >> 8) & 15)*17)


def _linear_rgba(color: tuple[int, int, int]) -> tuple[float, float, float, float]:
    return tuple(_srgb_to_linear(channel / 255.0) for channel in color) + (1.0,)


def _normalized_rgba(color: tuple[int, int, int]) -> tuple[float, float, float, float]:
    return tuple(channel / 255.0 for channel in color) + (1.0,)


def _srgb_to_linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _normalized_channel_to_byte(value: float) -> int:
    return max(0, min(255, int(round(max(0.0, min(1.0, float(value))) * 255.0))))
