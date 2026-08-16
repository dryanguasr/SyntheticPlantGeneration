"""Render the seven fixed diagnostic views for one A--F scene variant.

Run with Blender, for example:

```
blender --background --python scripts/render_structural_diagnostics.py -- \
  --seed 1 --model-variant E_plus_contact_policy_clearance
```
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_geometry import (
    audit_scene_mesh_collisions,
    build_diagnostic_proxy_geometry,
    build_geometry_from_morphology,
    create_cultivation_supports,
)
from uchuva_lsystem.blender_scene import (
    cleanup_scene,
    create_material,
    create_project_materials,
    save_blend_file,
    setup_camera_and_lights,
    setup_render_settings,
)
from uchuva_lsystem.cultivation import generate_cultivation_morphologies
from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.grammar import generate_morphology_tree
from uchuva_lsystem.parameters import get_morphology_parameters
from uchuva_lsystem.scene import create_cultivation_scene
from uchuva_lsystem.support import build_continuous_trellis


DIAGNOSTIC_MODES = (
    "skeleton",
    "branch_order",
    "plant_id",
    "leaf_scale_correction",
    "contacts",
    "global",
    "close",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--model-variant",
        default="E_plus_contact_policy_clearance",
        choices=(
            "A_baseline_independent",
            "B_morphology_calibrated",
            "C_plus_structural_support",
            "D_plus_synchronous_multi_plant",
            "E_plus_contact_policy_clearance",
            "F_plus_space_colonization_optional",
        ),
    )
    parser.add_argument("--plant-count", type=int, default=20)
    parser.add_argument(
        "--plant-limit",
        type=int,
        default=None,
        help="Optional smoke-test limit; omit for the required full 20-plant scene.",
    )
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--save-blend", action="store_true")
    parser.add_argument(
        "--geometry-mode",
        choices=("proxy", "full"),
        default="proxy",
        help="Proxy mode is the economical structural diagnostic; full is production geometry.",
    )
    parser.add_argument(
        "--mesh-audit",
        action="store_true",
        help="Run the expensive evaluated-mesh intersection/clearance audit.",
    )
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    import bpy
    from mathutils import Vector

    args = parse_args()
    output_dir = args.output_dir or (
        REPO_ROOT
        / "outputs"
        / "diagnostic_renders"
        / args.model_variant
        / f"seed_{args.seed}"
    )
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    preset = (
        "dense_staked_crop"
        if args.model_variant == "A_baseline_independent"
        else "dense_trellis_synchronous"
    )
    morphology_preset = (
        "initial_migration_manual_guess"
        if args.model_variant == "A_baseline_independent"
        else "trained_trellis"
    )
    parameters = get_morphology_parameters(morphology_preset)
    cultivation_scene = create_cultivation_scene(
        args.seed,
        preset,
        plant_count=args.plant_count,
        collision_policy=(
            "canopy_permissive"
            if args.model_variant == "A_baseline_independent"
            else "contact_policy_clearance"
        ),
    )
    if args.plant_limit is not None:
        if args.plant_limit < 1:
            raise ValueError("--plant-limit must be positive")
        cultivation_scene.plant_instances = cultivation_scene.plant_instances[
            : args.plant_limit
        ]
        if cultivation_scene.support_system is not None:
            cultivation_scene.support_system = build_continuous_trellis(
                cultivation_scene.plant_instances,
                seed=args.seed,
            )
        allowed = {
            item.plant_id for item in cultivation_scene.plant_instances
        }
        cultivation_scene.supports = [
            item
            for item in cultivation_scene.supports
            if item.plant_id in allowed
        ]
    potentials = {
        instance.plant_id: generate_morphology_tree(
            instance.seed,
            params=parameters,
            condition=instance.condition,
        )
        for instance in cultivation_scene.plant_instances
    }
    cultivation_scene, plants, growth_report = generate_cultivation_morphologies(
        cultivation_scene,
        parameters,
        args.model_variant,
        potential_plants=potentials,
    )

    cleanup_scene()
    materials = create_project_materials(seed=args.seed + 3000)
    geometry_reports: list[dict[str, Any]] = []
    maximum_height = 0.0
    if args.geometry_mode == "proxy":
        report = build_diagnostic_proxy_geometry(
            cultivation_scene,
            plants,
            materials,
            add_ground=True,
        )
        geometry_reports.append(report)
        maximum_height = float(report["height"])
        support_report = {
            "support_system_mode": (
                cultivation_scene.support_system.mode
                if cultivation_scene.support_system is not None
                else "individual_stakes"
            ),
            "rendered_from_clearance_proxies": True,
        }
    else:
        for index, instance in enumerate(cultivation_scene.plant_instances):
            report = build_geometry_from_morphology(
                plants[instance.plant_id],
                materials,
                instance_id=instance.plant_id,
                instance_role=instance.role,
                position=instance.position,
                rotation_deg=instance.rotation_deg,
                plant_scale=instance.scale,
                add_ground=index == 0,
            )
            geometry_reports.append({"plant_id": instance.plant_id, **report})
            maximum_height = max(maximum_height, float(report["height"]))
        support_report = create_cultivation_supports(
            cultivation_scene,
            materials,
            geometry_reports,
        )
    mesh_audit = (
        audit_scene_mesh_collisions()
        if args.mesh_audit
        else {
            "status": "not_run",
            "reason": "economical_diagnostic_render",
        }
    )
    center_x = sum(item.position[0] for item in cultivation_scene.plant_instances) / len(
        cultivation_scene.plant_instances
    )
    center_y = sum(item.position[1] for item in cultivation_scene.plant_instances) / len(
        cultivation_scene.plant_instances
    )
    radius = max(
        math.hypot(item.position[0] - center_x, item.position[1] - center_y)
        for item in cultivation_scene.plant_instances
    ) + 1.5
    target = (center_x, center_y, maximum_height * 0.48)
    camera, _ = setup_camera_and_lights(
        plant_height=max(maximum_height, 2.4),
        target=target,
        seed=args.seed,
        scene_radius=radius,
    )
    setup_render_settings(args.width, args.height)
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.film_transparent = False

    palette = _diagnostic_materials()
    objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type in {"MESH", "CURVE", "SURFACE"}
    ]
    original_state = {
        obj.name: {
            "hide_render": obj.hide_render,
            "materials": list(obj.data.materials),
        }
        for obj in objects
    }
    collision_names = {
        item[key]
        for item in (
            mesh_audit.get("physical_collisions", [])
            + mesh_audit.get("clearance_violations", [])
        )
        for key in ("object_a", "object_b")
        if item.get(key)
    }
    rendered: dict[str, str] = {}
    original_camera_location = camera.location.copy()
    original_camera_rotation = camera.rotation_euler.copy()
    for mode in DIAGNOSTIC_MODES:
        _restore_object_state(objects, original_state)
        camera.location = original_camera_location.copy()
        camera.rotation_euler = original_camera_rotation.copy()
        if mode == "close":
            camera.location = Vector(target) + (
                original_camera_location - Vector(target)
            ) * 0.56
            _look_at(camera, target)
        elif mode != "global":
            _apply_diagnostic_style(
                objects,
                mode,
                palette,
                collision_names=collision_names,
            )
        path = output_dir / f"{mode}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered[mode] = str(path)

    _restore_object_state(objects, original_state)
    if args.save_blend:
        save_blend_file(output_dir / "diagnostic_scene.blend")
    manifest = {
        "schema_version": "1.0",
        "seed": args.seed,
        "model_variant": args.model_variant,
        "preset": preset,
        "morphology_preset": morphology_preset,
        "geometry_mode": args.geometry_mode,
        "camera_contract": "fixed_by_seed_across_structural_variants",
        "lighting_contract": "fixed_by_seed_across_structural_variants",
        "rendered": rendered,
        "growth_report": growth_report,
        "support_report": support_report,
        "mesh_collision_audit": mesh_audit,
    }
    export_json(manifest, output_dir / "diagnostic_manifest.json")
    print(json.dumps({"rendered": rendered}, ensure_ascii=False, indent=2))


def _diagnostic_materials() -> dict[str, object]:
    colors = {
        "black": (0.015, 0.015, 0.015, 1.0),
        "grey": (0.18, 0.18, 0.18, 1.0),
        "white": (0.82, 0.82, 0.82, 1.0),
        "red": (0.85, 0.03, 0.02, 1.0),
        "orange": (0.95, 0.28, 0.02, 1.0),
        "yellow": (0.95, 0.78, 0.03, 1.0),
        "green": (0.03, 0.65, 0.12, 1.0),
        "cyan": (0.02, 0.72, 0.86, 1.0),
        "blue": (0.04, 0.18, 0.78, 1.0),
        "violet": (0.52, 0.08, 0.78, 1.0),
    }
    return {
        key: create_material(
            f"Uchuva_Diagnostico_{key}",
            value,
            roughness=0.72,
        )
        for key, value in colors.items()
    }


def _apply_diagnostic_style(
    objects: list[object],
    mode: str,
    palette: dict[str, object],
    *,
    collision_names: set[str],
) -> None:
    for obj in objects:
        semantic = str(obj.get("uchuva_semantic_class", "background"))
        role = str(obj.get("uchuva_plant_role", ""))
        plant_id = str(obj.get("uchuva_plant_id", ""))
        if mode == "skeleton":
            obj.hide_render = semantic not in {"stem"} and role != "support"
            _replace_material(obj, palette["white"] if semantic == "stem" else palette["cyan"])
        elif mode == "branch_order":
            order = int(obj.get("uchuva_axis_order", -1))
            key = {0: "green", 1: "yellow", 2: "orange", 3: "violet"}.get(
                order,
                "grey",
            )
            _replace_material(obj, palette[key])
        elif mode == "plant_id":
            key = ("red", "orange", "yellow", "green", "cyan", "blue", "violet")[
                _stable_index(plant_id, 7)
            ]
            _replace_material(obj, palette[key])
        elif mode == "leaf_scale_correction":
            if semantic != "leaf":
                _replace_material(obj, palette["grey"])
            else:
                adjustment = float(
                    obj.get("uchuva_orientation_adjustment_deg", 0.0)
                )
                key = (
                    "green"
                    if adjustment < 8.0
                    else "yellow"
                    if adjustment < 25.0
                    else "orange"
                    if adjustment < 50.0
                    else "red"
                )
                _replace_material(obj, palette[key])
        elif mode == "contacts":
            if obj.name in collision_names:
                key = "red"
            elif role == "support":
                key = "cyan"
            elif float(obj.get("uchuva_orientation_adjustment_deg", 0.0)) > 0.5:
                key = "orange"
            else:
                key = "grey"
            _replace_material(obj, palette[key])


def _restore_object_state(objects: list[object], state: dict[str, Any]) -> None:
    for obj in objects:
        original = state[obj.name]
        obj.hide_render = original["hide_render"]
        obj.data.materials.clear()
        for material in original["materials"]:
            obj.data.materials.append(material)


def _replace_material(obj: object, material: object) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _stable_index(value: str, count: int) -> int:
    return int.from_bytes(
        hashlib.sha256(value.encode("utf-8")).digest()[:4],
        "big",
    ) % count


def _look_at(camera: object, target: tuple[float, float, float]) -> None:
    from mathutils import Vector

    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


if __name__ == "__main__":
    main()
