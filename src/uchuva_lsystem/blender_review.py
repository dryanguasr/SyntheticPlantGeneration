"""Blender-side helpers for photoreal human-validation renders."""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .human_validation import HumanValidationCase, RenderQualityProfile


PREFLIGHT_VERSION = "1.0"


def configure_render_profile(
    profile: RenderQualityProfile,
    *,
    orientation: str,
) -> dict[str, Any]:
    """Apply a named review profile and report the actual engine/device."""
    import bpy

    scene = bpy.context.scene
    width, height = profile.resolution_for(orientation)
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = profile.image_format
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = profile.color_depth
    scene.render.film_transparent = False
    scene.render.filter_size = 1.5
    if hasattr(scene.render, "dither_intensity"):
        scene.render.dither_intensity = profile.dither_intensity
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = profile.motion_blur

    actual_engine = _set_engine(scene, profile.engine)
    device_report = {
        "requested": list(profile.preferred_devices),
        "selected": "GPU" if actual_engine != "CYCLES" else "CPU",
        "backend": actual_engine,
        "available": [],
        "fallback": actual_engine != profile.engine,
    }
    if actual_engine == "CYCLES":
        device_report = configure_cycles_device(profile.preferred_devices)
        cycles = scene.cycles
        cycles.samples = profile.samples
        if hasattr(cycles, "adaptive_min_samples"):
            cycles.adaptive_min_samples = profile.minimum_samples
        if hasattr(cycles, "adaptive_threshold"):
            cycles.adaptive_threshold = profile.noise_threshold
        if hasattr(cycles, "use_adaptive_sampling"):
            cycles.use_adaptive_sampling = profile.adaptive_sampling
        if hasattr(cycles, "use_denoising"):
            cycles.use_denoising = profile.denoising
        _set_enum_if_supported(cycles, "denoiser", profile.denoiser)
        _set_enum_if_supported(
            cycles,
            "denoising_input_passes",
            profile.denoising_input_passes,
        )
        _set_enum_if_supported(
            cycles,
            "denoising_prefilter",
            profile.denoising_prefilter,
        )
        _set_if_supported(cycles, "max_bounces", profile.max_bounces)
        _set_if_supported(cycles, "diffuse_bounces", profile.diffuse_bounces)
        _set_if_supported(cycles, "glossy_bounces", profile.glossy_bounces)
        _set_if_supported(
            cycles, "transmission_bounces", profile.transmission_bounces
        )
        _set_if_supported(
            cycles, "transparent_max_bounces", profile.transparent_bounces
        )
        _set_if_supported(
            cycles, "caustics_reflective", profile.reflective_caustics
        )
        _set_if_supported(
            cycles, "caustics_refractive", profile.refractive_caustics
        )
    else:
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            for name in ("taa_render_samples", "taa_samples"):
                if hasattr(eevee, name):
                    setattr(eevee, name, profile.samples)

    color_report = _configure_color_management(scene, profile)
    return {
        "profile": profile.to_dict(),
        "actual_engine": actual_engine,
        "device": device_report,
        "resolution": [width, height],
        "color_management": color_report,
        "available_memory_bytes": _available_memory_bytes(),
    }


def configure_cycles_device(preferred_devices: list[str]) -> dict[str, Any]:
    """Select OptiX, CUDA, or CPU without assuming a particular workstation."""
    import bpy

    optix_cache = Path(tempfile.gettempdir()) / "uchuva_optix_cache"
    optix_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("OPTIX_CACHE_PATH", str(optix_cache))
    scene = bpy.context.scene
    addon = bpy.context.preferences.addons.get("cycles")
    preferences = addon.preferences if addon is not None else None
    available: list[dict[str, Any]] = []
    if preferences is not None:
        try:
            preferences.get_devices()
        except (AttributeError, RuntimeError):
            pass
        available = [
            {
                "name": str(device.name),
                "type": str(device.type),
                "use": bool(device.use),
            }
            for device in preferences.devices
        ]

    for requested in preferred_devices:
        if requested == "CPU":
            scene.cycles.device = "CPU"
            return {
                "requested": list(preferred_devices),
                "selected": "CPU",
                "backend": "CPU",
                "available": available,
                "fallback": requested != preferred_devices[0],
            }
        if preferences is None:
            continue
        try:
            preferences.compute_device_type = requested
            preferences.get_devices()
        except (TypeError, RuntimeError):
            continue
        matching = [
            device
            for device in preferences.devices
            if str(device.type) == requested
        ]
        if not matching:
            continue
        for device in preferences.devices:
            device.use = device in matching
        scene.cycles.device = "GPU"
        return {
            "requested": list(preferred_devices),
            "selected": "GPU",
            "backend": requested,
            "available": [
                {
                    "name": str(device.name),
                    "type": str(device.type),
                    "use": bool(device.use),
                }
                for device in preferences.devices
            ],
            "fallback": requested != preferred_devices[0],
        }

    scene.cycles.device = "CPU"
    return {
        "requested": list(preferred_devices),
        "selected": "CPU",
        "backend": "CPU",
        "available": available,
        "fallback": True,
    }


def create_case_camera(
    case: HumanValidationCase,
    scene_data: Any,
    geometry_reports: list[dict[str, Any]],
) -> tuple[object, dict[str, Any]]:
    """Create a deterministic camera outside the measured canopy bounds."""
    import bpy

    from .blender_scene import create_annotation_camera

    target, height, radius = _case_bounds(case, scene_data, geometry_reports)
    camera = create_annotation_camera(
        profile_name=case.camera_profile,
        target=target,
        plant_height=height,
        scene_radius=radius,
        seed=int(scene_data.seed),
        name_suffix=case.case_id,
    )
    bpy.context.scene.camera = camera
    distance = math.dist(tuple(camera.location), target)
    report = {
        "profile": case.camera_profile,
        "target": [round(value, 5) for value in target],
        "location": [round(float(value), 5) for value in camera.location],
        "rotation_euler": [
            round(float(value), 7) for value in camera.rotation_euler
        ],
        "scene_radius": round(radius, 5),
        "plant_height": round(height, 5),
        "camera_distance": round(distance, 5),
        "outside_canopy_proxy": distance > radius,
        "lens_mm": round(float(camera.data.lens), 4),
        "fstop": round(float(camera.data.dof.aperture_fstop), 4),
    }
    if not report["outside_canopy_proxy"]:
        raise RuntimeError(
            f"{case.case_id}: fitted camera remains inside canopy proxy."
        )
    return camera, report


def lock_camera_to_report(
    camera: object,
    baseline_report: dict[str, Any],
    current_fit_report: dict[str, Any],
) -> dict[str, Any]:
    """Apply the accepted camera transform and verify it remains outside the canopy."""
    from mathutils import Vector

    location = tuple(float(value) for value in baseline_report["location"])
    target = tuple(float(value) for value in baseline_report["target"])
    camera.location = location
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = float(baseline_report["lens_mm"])
    camera.data.dof.aperture_fstop = float(baseline_report["fstop"])
    distance = math.dist(location, target)
    current_radius = float(current_fit_report["scene_radius"])
    report = {
        **current_fit_report,
        "target": [round(value, 5) for value in target],
        "location": [round(value, 5) for value in location],
        "rotation_euler": [
            round(float(value), 7) for value in camera.rotation_euler
        ],
        "camera_distance": round(distance, 5),
        "outside_canopy_proxy": distance > current_radius,
        "lens_mm": round(float(camera.data.lens), 4),
        "fstop": round(float(camera.data.dof.aperture_fstop), 4),
        "locked_from_baseline": True,
    }
    if not report["outside_canopy_proxy"]:
        raise RuntimeError(
            "Accepted camera transform is inside the candidate canopy proxy; "
            "the case must fail instead of silently reframing."
        )
    return report


def render_beauty_with_preflight(
    camera: object,
    output_path: str | Path,
    profile: RenderQualityProfile,
    *,
    orientation: str,
    locked_exposure: float | None = None,
) -> dict[str, Any]:
    """Measure exposure cheaply, adjust only EV, then render the final beauty."""
    import bpy

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.camera = camera
    preflight_path = path.with_name(f"{path.stem}_preflight.png")
    preflight = exposure_preflight(
        camera,
        preflight_path,
        locked_exposure=locked_exposure,
    )
    scene.render.resolution_x, scene.render.resolution_y = profile.resolution_for(
        orientation
    )
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = profile.image_format
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = profile.color_depth
    scene.render.filepath = str(path)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    elapsed = time.perf_counter() - started
    return {
        "path": str(path),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256(path) if path.is_file() else None,
        "elapsed_seconds": round(elapsed, 4),
        "preflight": preflight,
    }


def exposure_preflight(
    camera: object,
    output_path: str | Path,
    *,
    locked_exposure: float | None = None,
    maximum_steps: int = 6,
) -> dict[str, Any]:
    """Render a small deterministic frame and adjust exposure in 0.25 EV steps."""
    import bpy

    scene = bpy.context.scene
    previous = _capture_render_state(scene)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original_exposure = float(scene.view_settings.exposure)
    if locked_exposure is not None:
        scene.view_settings.exposure = float(locked_exposure)
    measurements: list[dict[str, Any]] = []
    try:
        scene.camera = camera
        scene.render.resolution_x = 320
        scene.render.resolution_y = 180
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        if scene.render.engine == "CYCLES":
            scene.cycles.samples = min(32, int(scene.cycles.samples))
            _set_if_supported(scene.cycles, "adaptive_min_samples", 8)
            _set_if_supported(scene.cycles, "adaptive_threshold", 0.04)
        for step in range(maximum_steps + 1):
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            statistics = _image_luminance_statistics(path)
            statistics["step"] = step
            statistics["exposure_ev"] = round(
                float(scene.view_settings.exposure), 4
            )
            measurements.append(statistics)
            if locked_exposure is not None:
                break
            median = statistics["median"]
            if 0.12 <= median <= 0.65:
                break
            adjustment = 0.25 if median < 0.12 else -0.25
            scene.view_settings.exposure += adjustment
        final = measurements[-1]
        warnings: list[str] = []
        if final["median"] < 0.08:
            warnings.append("severe_underexposure")
        if final["dark_clip_fraction"] > 0.45:
            warnings.append("excessive_dark_clipping")
        if final["bright_clip_fraction"] > 0.02:
            warnings.append("excessive_highlight_clipping")
        return {
            "version": PREFLIGHT_VERSION,
            "path": str(path),
            "bytes": path.stat().st_size if path.is_file() else 0,
            "sha256": _sha256(path) if path.is_file() else None,
            "locked": locked_exposure is not None,
            "original_exposure_ev": round(original_exposure, 4),
            "applied_exposure_ev": round(
                float(scene.view_settings.exposure), 4
            ),
            "step_size_ev": 0.25,
            "measurements": measurements,
            "warnings": warnings,
            "status": "warning" if warnings else "valid",
            "parameter_status": "engineering_heuristic",
        }
    finally:
        applied_exposure = float(scene.view_settings.exposure)
        _restore_render_state(scene, previous)
        scene.view_settings.exposure = applied_exposure


def render_auxiliary_diagnostics(
    camera: object,
    output_dir: str | Path,
    profile: RenderQualityProfile,
) -> dict[str, Any]:
    """Render a compact multilayer EXR and a flat-material diagnostic beauty."""
    import bpy

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if profile.engine != "CYCLES":
        return _render_standard_auxiliary_diagnostics(
            camera,
            directory,
            profile,
        )
    scene = bpy.context.scene
    view_layer = scene.view_layers[0]
    previous = _capture_render_state(scene)
    previous_engine = scene.render.engine
    previous_compositor = getattr(scene, "compositing_node_group", None)
    previous_override = view_layer.material_override
    pass_states = {
        name: getattr(view_layer, name)
        for name in (
            "use_pass_normal",
            "use_pass_diffuse_color",
        )
        if hasattr(view_layer, name)
    }
    cycles_layer = getattr(view_layer, "cycles", None)
    sample_pass_name = next(
        (
            name
            for name in ("pass_debug_sample_count", "use_pass_debug_sample_count")
            if cycles_layer is not None and hasattr(cycles_layer, name)
        ),
        None,
    )
    sample_pass_previous = (
        getattr(cycles_layer, sample_pass_name)
        if sample_pass_name is not None
        else None
    )
    denoising_store_previous = (
        getattr(cycles_layer, "denoising_store_passes")
        if cycles_layer is not None
        and hasattr(cycles_layer, "denoising_store_passes")
        else None
    )
    compositor_group = None
    generated_passes: list[str] = []
    try:
        scene.camera = camera
        scene.render.engine = "CYCLES"
        configure_cycles_device(["OPTIX", "CUDA", "CPU"])
        scene.render.resolution_x = 960
        scene.render.resolution_y = 540
        scene.render.resolution_percentage = 100
        scene.cycles.samples = min(profile.samples, 64)
        _set_if_supported(scene.cycles, "adaptive_min_samples", 16)
        _set_if_supported(scene.cycles, "adaptive_threshold", 0.02)
        for name in pass_states:
            setattr(view_layer, name, True)
        if sample_pass_name is not None:
            setattr(cycles_layer, sample_pass_name, True)
        if denoising_store_previous is not None:
            cycles_layer.denoising_store_passes = True

        compositor_group, generated_passes = _diagnostic_compositor(
            directory,
            view_layer.name,
        )
        required_passes = {
            "Combined",
            "Diffuse Color",
            "Normal",
            "Denoising Albedo",
            "Denoising Normal",
            "Debug Sample Count",
        }
        missing_passes = sorted(required_passes - set(generated_passes))
        if missing_passes:
            raise RuntimeError(
                "Cycles diagnostic passes are unavailable: "
                + ", ".join(missing_passes)
            )
        scene.compositing_node_group = compositor_group
        exr_path = directory / "diagnostic_passes.exr"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_depth = "8"
        scene.render.filepath = str(directory / ".diagnostic_combined.png")
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        exr_elapsed = time.perf_counter() - started
        temporary_combined = directory / ".diagnostic_combined.png"
        temporary_combined.unlink(missing_ok=True)
        if not exr_path.is_file():
            candidates = sorted(directory.glob("diagnostic_passes*.exr"))
            if candidates:
                candidates[0].replace(exr_path)
        if not exr_path.is_file():
            raise RuntimeError("Cycles did not produce the diagnostic EXR.")

        material = _flat_diagnostic_material()
        scene.compositing_node_group = previous_compositor
        view_layer.material_override = material
        flat_path = directory / "material_override.png"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        scene.render.filepath = str(flat_path)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        flat_elapsed = time.perf_counter() - started
        return {
            "multilayer_exr": _file_record(exr_path),
            "material_override": _file_record(flat_path),
            "passes": generated_passes,
            "elapsed_seconds": round(exr_elapsed + flat_elapsed, 4),
            "render_samples": min(profile.samples, 64),
        }
    finally:
        view_layer.material_override = previous_override
        for name, value in pass_states.items():
            setattr(view_layer, name, value)
        if sample_pass_name is not None:
            setattr(cycles_layer, sample_pass_name, sample_pass_previous)
        if denoising_store_previous is not None:
            cycles_layer.denoising_store_passes = denoising_store_previous
        scene.compositing_node_group = previous_compositor
        if compositor_group is not None and compositor_group.users == 0:
            bpy.data.node_groups.remove(compositor_group)
        scene.render.engine = previous_engine
        _restore_render_state(scene, previous)


def _render_standard_auxiliary_diagnostics(
    camera: object,
    directory: Path,
    profile: RenderQualityProfile,
) -> dict[str, Any]:
    """Render the useful flat-material pass without switching to Cycles."""
    import bpy

    scene = bpy.context.scene
    view_layer = scene.view_layers[0]
    previous = _capture_render_state(scene)
    previous_override = view_layer.material_override
    try:
        scene.camera = camera
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.render.resolution_x = min(profile.landscape_resolution[0], 960)
        scene.render.resolution_y = min(profile.landscape_resolution[1], 540)
        scene.render.resolution_percentage = 100
        material = _flat_diagnostic_material()
        view_layer.material_override = material
        flat_path = directory / "material_override.png"
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.color_depth = "8"
        scene.render.filepath = str(flat_path)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed = time.perf_counter() - started
        return {
            "status": "standard_engine_only",
            "multilayer_exr": None,
            "material_override": _file_record(flat_path),
            "passes": ["material_override"],
            "elapsed_seconds": round(elapsed, 4),
            "render_samples": profile.samples,
            "engine": "BLENDER_EEVEE_NEXT",
            "note": (
                "Cycles-only EXR/sample-count passes are deferred while the "
                "standard render policy is active."
            ),
        }
    finally:
        view_layer.material_override = previous_override
        _restore_render_state(scene, previous)


def compose_before_after(
    baseline_path: str | Path,
    candidate_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Create one neutral side-by-side comparison without external libraries."""
    paths = [Path(baseline_path), Path(candidate_path)]
    if not all(path.is_file() for path in paths):
        missing = [str(path) for path in paths if not path.is_file()]
        raise FileNotFoundError(f"Comparison inputs are missing: {missing}")
    return _compose_image_grid(
        paths,
        Path(output_path),
        columns=2,
        cell_width=960,
        cell_height=1080,
    )


def compose_suite_contact_sheet(
    comparison_paths: list[str | Path],
    output_path: str | Path,
) -> Path:
    """Compose the ten case comparisons in a fixed two-column contact sheet."""
    if len(comparison_paths) != 10:
        raise ValueError("The suite contact sheet requires exactly 10 comparisons.")
    return _compose_image_grid(
        [Path(item) for item in comparison_paths],
        Path(output_path),
        columns=2,
        cell_width=640,
        cell_height=360,
    )


def _case_bounds(
    case: HumanValidationCase,
    scene_data: Any,
    geometry_reports: list[dict[str, Any]],
) -> tuple[tuple[float, float, float], float, float]:
    positions = {
        item.plant_id: tuple(float(value) for value in item.position)
        for item in scene_data.plant_instances
    }
    reports = {str(item["plant_id"]): item for item in geometry_reports}
    center_x = sum(value[0] for value in positions.values()) / max(len(positions), 1)
    center_y = sum(value[1] for value in positions.values()) / max(len(positions), 1)
    height = max(
        (float(item.get("height", 0.0)) for item in geometry_reports),
        default=2.4,
    )
    radius = 0.5
    for plant_id, position in positions.items():
        canopy = float(
            reports.get(plant_id, {})
            .get("bounds_proxy", {})
            .get("canopy_radius", 0.5)
        )
        radius = max(
            radius,
            math.hypot(position[0] - center_x, position[1] - center_y) + canopy,
        )
    if case.camera_profile in {"real_close", "robot_close_oblique"}:
        foreground = next(
            (
                item
                for item in scene_data.plant_instances
                if item.role == "foreground"
            ),
            scene_data.plant_instances[0],
        )
        foreground_report = reports.get(foreground.plant_id, {})
        target = (
            float(foreground.position[0]),
            float(foreground.position[1]),
            max(0.45, float(foreground_report.get("height", height)) * 0.52),
        )
        radius = max(
            0.6,
            float(
                foreground_report.get("bounds_proxy", {}).get(
                    "canopy_radius", 0.6
                )
            ),
        )
    else:
        target = (center_x, center_y, max(0.45, height * 0.50))
    return target, max(height, 2.4), radius


def _configure_color_management(
    scene: object,
    profile: RenderQualityProfile,
) -> dict[str, Any]:
    requested_transform = profile.view_transform
    requested_look = profile.look
    try:
        scene.view_settings.view_transform = requested_transform
    except TypeError:
        requested_transform = str(scene.view_settings.view_transform)
    try:
        scene.view_settings.look = requested_look
    except TypeError:
        requested_look = str(scene.view_settings.look)
    scene.view_settings.gamma = 1.0
    if hasattr(scene.view_settings, "use_white_balance"):
        scene.view_settings.use_white_balance = True
    if hasattr(scene.view_settings, "white_balance_temperature"):
        scene.view_settings.white_balance_temperature = 6500.0
    if hasattr(scene.view_settings, "white_balance_tint"):
        scene.view_settings.white_balance_tint = 0.0
    return {
        "view_transform": requested_transform,
        "look": requested_look,
        "white_balance_temperature": 6500.0,
        "white_balance_tint": 0.0,
        "gamma": 1.0,
    }


def _set_engine(scene: object, requested: str) -> str:
    try:
        scene.render.engine = requested
        return requested
    except TypeError:
        if requested == "BLENDER_EEVEE_NEXT":
            scene.render.engine = "BLENDER_EEVEE"
            return "BLENDER_EEVEE"
        raise


def _set_if_supported(owner: object, name: str, value: Any) -> bool:
    if not hasattr(owner, name):
        return False
    try:
        setattr(owner, name, value)
        return True
    except (TypeError, ValueError):
        return False


def _set_enum_if_supported(owner: object, name: str, value: str) -> bool:
    return _set_if_supported(owner, name, value)


def _capture_render_state(scene: object) -> dict[str, Any]:
    cycles = getattr(scene, "cycles", None)
    state = {
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "color_depth": scene.render.image_settings.color_depth,
        "filepath": scene.render.filepath,
        "camera": scene.camera,
        "exposure": scene.view_settings.exposure,
    }
    if cycles is not None:
        for name in (
            "samples",
            "adaptive_min_samples",
            "adaptive_threshold",
            "use_adaptive_sampling",
            "use_denoising",
        ):
            if hasattr(cycles, name):
                state[f"cycles.{name}"] = getattr(cycles, name)
    return state


def _restore_render_state(scene: object, state: dict[str, Any]) -> None:
    scene.render.resolution_x = state["resolution_x"]
    scene.render.resolution_y = state["resolution_y"]
    scene.render.resolution_percentage = state["resolution_percentage"]
    scene.render.image_settings.file_format = state["file_format"]
    scene.render.image_settings.color_mode = state["color_mode"]
    scene.render.image_settings.color_depth = state["color_depth"]
    scene.render.filepath = state["filepath"]
    scene.camera = state["camera"]
    scene.view_settings.exposure = state["exposure"]
    cycles = getattr(scene, "cycles", None)
    if cycles is not None:
        for key, value in state.items():
            if key.startswith("cycles."):
                _set_if_supported(cycles, key.split(".", 1)[1], value)


def _image_luminance_statistics(path: Path) -> dict[str, float]:
    import bpy

    image = bpy.data.images.load(str(path), check_existing=False)
    try:
        pixels = list(image.pixels)
        luminance = [
            0.2126 * pixels[index]
            + 0.7152 * pixels[index + 1]
            + 0.0722 * pixels[index + 2]
            for index in range(0, len(pixels), 4)
        ]
        luminance.sort()
        count = max(len(luminance), 1)
        return {
            "median": round(_percentile(luminance, 0.50), 6),
            "p05": round(_percentile(luminance, 0.05), 6),
            "p95": round(_percentile(luminance, 0.95), 6),
            "dark_clip_fraction": round(
                sum(value <= 0.01 for value in luminance) / count, 6
            ),
            "bright_clip_fraction": round(
                sum(value >= 0.99 for value in luminance) / count, 6
            ),
        }
    finally:
        bpy.data.images.remove(image)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))
    return float(values[index])


def _file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": _sha256(path) if path.is_file() else None,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _flat_diagnostic_material() -> object:
    import bpy

    name = "Uchuva_HumanValidation_MaterialOverride"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.42, 0.42, 0.42, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.65
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = 0.0
        if "Normal" in bsdf.inputs:
            bsdf.inputs["Normal"].default_value = (0.0, 0.0, 0.0)
    return material


def _diagnostic_compositor(
    directory: Path,
    view_layer_name: str,
) -> tuple[object, list[str]]:
    import bpy

    group = bpy.data.node_groups.new(
        "Uchuva_HumanValidation_DiagnosticCompositor",
        "CompositorNodeTree",
    )
    nodes = group.nodes
    links = group.links
    render_layers = nodes.new("CompositorNodeRLayers")
    render_layers.layer = view_layer_name
    output = nodes.new("CompositorNodeOutputFile")
    output.directory = str(directory)
    output.file_name = "diagnostic_passes"
    output.format.file_format = "OPEN_EXR_MULTILAYER"
    output.format.color_depth = "32"
    output.save_as_render = False
    requested = (
        ("Image", "RGBA", "Combined"),
        ("Diffuse Color", "RGBA", "Diffuse Color"),
        ("Normal", "VECTOR", "Normal"),
        ("Debug Sample Count", "FLOAT", "Debug Sample Count"),
        ("Noisy Image", "RGBA", "Noisy Image"),
        ("Denoising Albedo", "RGBA", "Denoising Albedo"),
        ("Denoising Normal", "VECTOR", "Denoising Normal"),
    )
    generated_passes: list[str] = []
    for source_name, socket_type, output_name in requested:
        source = render_layers.outputs.get(source_name)
        if source is None:
            continue
        output.file_output_items.new(socket_type, output_name)
        links.new(source, output.inputs[output_name])
        generated_passes.append(output_name)
    return group, generated_passes


def _compose_image_grid(
    source_paths: list[Path],
    destination: Path,
    *,
    columns: int,
    cell_width: int,
    cell_height: int,
) -> Path:
    import bpy

    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = math.ceil(len(source_paths) / columns)
    width = columns * cell_width
    height = rows * cell_height
    canvas = [0.018, 0.018, 0.018, 1.0] * (width * height)
    for index, source_path in enumerate(source_paths):
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        image = bpy.data.images.load(str(source_path), check_existing=False)
        try:
            source_width, source_height = (int(value) for value in image.size)
            scale = min(
                cell_width / max(source_width, 1),
                cell_height / max(source_height, 1),
            )
            fit_width = max(1, round(source_width * scale))
            fit_height = max(1, round(source_height * scale))
            image.scale(fit_width, fit_height)
            pixels = list(image.pixels)
            # Blender exposes 16-bit PNG RGB values in scene-linear space but
            # ``Image.save`` writes a generated byte image without applying a
            # display transform. Convert those inputs back to sRGB so contact
            # sheets do not become artificially dark. Eight-bit PNG inputs
            # are already exposed as display-encoded values in Blender 5.1.
            if int(image.depth) > 32:
                for channel in range(0, len(pixels), 4):
                    pixels[channel] = _linear_to_srgb(pixels[channel])
                    pixels[channel + 1] = _linear_to_srgb(
                        pixels[channel + 1]
                    )
                    pixels[channel + 2] = _linear_to_srgb(
                        pixels[channel + 2]
                    )
            column = index % columns
            display_row = index // columns
            target_x = column * cell_width + (cell_width - fit_width) // 2
            target_y = (
                (rows - display_row - 1) * cell_height
                + (cell_height - fit_height) // 2
            )
            for row in range(fit_height):
                source_start = row * fit_width * 4
                source_end = source_start + fit_width * 4
                target_start = ((target_y + row) * width + target_x) * 4
                canvas[target_start : target_start + fit_width * 4] = pixels[
                    source_start:source_end
                ]
        finally:
            bpy.data.images.remove(image)
    output = bpy.data.images.new(
        "Uchuva_HumanValidation_ContactSheet",
        width=width,
        height=height,
        alpha=False,
        float_buffer=False,
    )
    try:
        output.pixels.foreach_set(canvas)
        output.file_format = "PNG"
        output.filepath_raw = str(destination)
        output.save()
    finally:
        bpy.data.images.remove(output)
    return destination


def _linear_to_srgb(value: float) -> float:
    value = max(0.0, min(1.0, float(value)))
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * (value ** (1.0 / 2.4)) - 0.055


def _available_memory_bytes() -> int | None:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return int(status.available_physical)
    except (AttributeError, OSError):
        return None
