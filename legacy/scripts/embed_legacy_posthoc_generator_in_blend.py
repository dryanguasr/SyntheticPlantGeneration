"""Embed a self-contained uchuva generator Text Block into a .blend file.

Run with Blender, for example:

    blender --background outputs/blends/uchuva_scene_seed_0.blend \
      --python scripts/embed_internal_blend_script.py

The resulting .blend contains a Text Block named
``RUN_UCHUVA_SCENE_INTERNAL.py`` that can regenerate the scene without importing
the local repository.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import zlib
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
DEFAULT_BLEND = REPO_ROOT / "outputs" / "blends" / "uchuva_scene_seed_0.blend"
DEFAULT_TEXT_NAME = "RUN_UCHUVA_SCENE_INTERNAL.py"
DEFAULT_ANNOTATION_TEXT_NAME = "RUN_UCHUVA_ANNOTATION_PILOT.py"
DEFAULT_DATASET_TEXT_NAME = "RUN_UCHUVA_DATASET_PILOT.py"

MODULE_FILES = {
    "__init__": REPO_ROOT / "src" / "uchuva_lsystem" / "__init__.py",
    "morphology": REPO_ROOT / "src" / "uchuva_lsystem" / "morphology.py",
    "parameters": REPO_ROOT / "src" / "uchuva_lsystem" / "parameters.py",
    "scene": REPO_ROOT / "src" / "uchuva_lsystem" / "scene.py",
    "collisions": REPO_ROOT / "src" / "uchuva_lsystem" / "collisions.py",
    "cultivation": REPO_ROOT / "src" / "uchuva_lsystem" / "cultivation.py",
    "texture_assets": REPO_ROOT / "src" / "uchuva_lsystem" / "texture_assets.py",
    "validation": REPO_ROOT / "src" / "uchuva_lsystem" / "validation.py",
    "grammar": REPO_ROOT / "src" / "uchuva_lsystem" / "grammar.py",
    "yolo_export": REPO_ROOT / "src" / "uchuva_lsystem" / "yolo_export.py",
    "blender_annotations": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_annotations.py",
    "blender_scene": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_scene.py",
    "blender_environment": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_environment.py",
    "blender_geometry": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_geometry.py",
    "exporters": REPO_ROOT / "src" / "uchuva_lsystem" / "exporters.py",
    "blender_pilot": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_pilot.py",
    "blender_dataset": REPO_ROOT / "src" / "uchuva_lsystem" / "blender_dataset.py",
    "domain_analysis": REPO_ROOT / "src" / "uchuva_lsystem" / "domain_analysis.py",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed a self-contained uchuva generator into a .blend file."
    )
    parser.add_argument(
        "--blend",
        type=Path,
        default=None,
        help="Blend file to update. Defaults to the currently loaded file or seed 0 output.",
    )
    parser.add_argument(
        "--output-blend",
        type=Path,
        default=None,
        help="Optional output .blend path. Defaults to updating the input file.",
    )
    parser.add_argument(
        "--text-name",
        default=DEFAULT_TEXT_NAME,
        help="Name of the internal runnable Text Block.",
    )
    parser.add_argument(
        "--annotation-text-name",
        default=DEFAULT_ANNOTATION_TEXT_NAME,
        help="Name of the internal annotation-pilot Text Block.",
    )
    parser.add_argument(
        "--dataset-text-name",
        default=DEFAULT_DATASET_TEXT_NAME,
        help="Name of the internal 200-image YOLO dataset Text Block.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Default embedded seed.")
    parser.add_argument(
        "--plant-count", type=int, default=10, help="Default embedded plant count."
    )
    parser.add_argument(
        "--neighbor-count",
        type=int,
        default=3,
        choices=[2, 3, 4],
        help="Default partial-neighbor count for the annotation pilot.",
    )
    parser.add_argument(
        "--preset",
        default="foreground_plant_with_neighbors",
        choices=[
            "single_plant_study",
            "foreground_plant_with_neighbors",
            "annotation_foreground_pilot",
            "row_canopy",
        ],
        help="Default embedded scene preset.",
    )
    parser.add_argument(
        "--collision-policy",
        default="canopy_permissive",
        choices=["canopy_permissive", "strict_base"],
        help="Default embedded collision policy.",
    )
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    bpy = _import_bpy()

    active_blend = Path(bpy.data.filepath) if bpy.data.filepath else None
    input_blend = args.blend or active_blend or DEFAULT_BLEND
    if input_blend and Path(input_blend).exists():
        input_blend = Path(input_blend)
        if not active_blend or active_blend.resolve() != input_blend.resolve():
            bpy.ops.wm.open_mainfile(filepath=str(input_blend))
    elif args.blend is not None:
        raise FileNotFoundError(f"Blend file not found: {args.blend}")

    module_sources = {
        name: path.read_text(encoding="utf-8") for name, path in MODULE_FILES.items()
    }
    runner = build_internal_runner(
        module_sources=module_sources,
        seed=args.seed,
        plant_count=args.plant_count,
        preset=args.preset,
        collision_policy=args.collision_policy,
    )
    _replace_text_block(bpy, args.text_name, runner)
    annotation_runner = build_internal_annotation_runner(
        module_sources=module_sources,
        seed=args.seed,
        neighbor_count=args.neighbor_count,
    )
    _replace_text_block(bpy, args.annotation_text_name, annotation_runner)
    dataset_runner = build_internal_dataset_runner(
        module_sources=module_sources,
        seed=args.seed,
    )
    _replace_text_block(bpy, args.dataset_text_name, dataset_runner)
    from uchuva_lsystem.blender_environment import ASSET_MANIFEST

    _replace_text_block(
        bpy,
        "ASSET_MANIFEST_CC0.json",
        json.dumps(ASSET_MANIFEST, ensure_ascii=False, indent=2) + "\n",
    )
    _replace_text_block(
        bpy,
        "README_UCHUVA_INTERNAL.txt",
        _build_readme_text(
            args.text_name,
            args.annotation_text_name,
            args.dataset_text_name,
            args.seed,
            args.plant_count,
            args.neighbor_count,
        ),
    )

    output_blend = args.output_blend or input_blend or DEFAULT_BLEND
    output_blend = Path(output_blend)
    output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    print(
        f"Embedded {args.text_name}, {args.annotation_text_name}, and "
        f"{args.dataset_text_name} into {output_blend}"
    )


def build_internal_runner(
    module_sources: dict[str, str],
    seed: int,
    plant_count: int,
    preset: str,
    collision_policy: str,
) -> str:
    payload = json.dumps(module_sources, ensure_ascii=False).encode("utf-8")
    encoded_sources = base64.b64encode(zlib.compress(payload, level=9)).decode("ascii")
    return dedent(
        f'''\
        """Self-contained uchuva scene generator embedded in this .blend.

        How to use:
        1. Open this Text Block in Blender's Text Editor.
        2. Adjust DEFAULT_* values below if needed.
        3. Press Run Script.

        The code below installs the embedded ``uchuva_lsystem`` modules into the
        current Blender Python session, regenerates the scene, and writes JSON
        reports into Text Blocks inside this .blend.
        """

        from __future__ import annotations

        import base64
        import json
        import sys
        import types
        import zlib


        DEFAULT_SEED = {seed}
        DEFAULT_PLANT_COUNT = {plant_count}
        DEFAULT_PRESET = {preset!r}
        DEFAULT_COLLISION_POLICY = {collision_policy!r}
        SAVE_BLEND_AFTER_GENERATION = False

        _EMBEDDED_MODULE_SOURCES_B64_ZLIB = {encoded_sources!r}
        _MODULE_EXECUTION_ORDER = [
            "morphology",
            "parameters",
            "scene",
            "collisions",
            "cultivation",
            "validation",
            "grammar",
            "texture_assets",
            "yolo_export",
            "blender_annotations",
            "blender_scene",
            "blender_environment",
            "blender_geometry",
            "exporters",
            "blender_pilot",
            "domain_analysis",
            "blender_dataset",
            "__init__",
        ]


        def generate_scene(
            seed: int = DEFAULT_SEED,
            plant_count: int = DEFAULT_PLANT_COUNT,
            preset: str = DEFAULT_PRESET,
            collision_policy: str = DEFAULT_COLLISION_POLICY,
        ):
            """Regenerate the uchuva cultivation scene in the current .blend."""
            _install_embedded_package()

            import bpy
            from uchuva_lsystem.blender_geometry import (
                audit_scene_mesh_collisions,
                build_geometry_from_morphology,
                create_cultivation_supports,
            )
            from uchuva_lsystem.blender_scene import (
                cleanup_scene,
                create_project_materials,
                setup_camera_and_lights,
                setup_render_settings,
            )
            from uchuva_lsystem.grammar import generate_morphology_tree
            from uchuva_lsystem.cultivation import adapt_cultivation_morphologies
            from uchuva_lsystem.scene import create_cultivation_scene
            from uchuva_lsystem.validation import (
                validate_cultivation_scene,
                validate_morphology_tree,
            )

            scene = create_cultivation_scene(
                seed=seed,
                preset_name=preset,
                plant_count=plant_count,
                collision_policy=collision_policy,
            )

            plants_by_id = {{
                instance.plant_id: generate_morphology_tree(
                    seed=instance.seed,
                    condition=instance.condition,
                )
                for instance in scene.plant_instances
            }}
            scene, plants_by_id, adaptation_report = adapt_cultivation_morphologies(
                scene, plants_by_id
            )

            cleanup_scene()
            materials = create_project_materials(seed=seed + 3000)
            geometry_reports = []
            morphology_reports = []
            max_height = 0.0

            for index, instance in enumerate(scene.plant_instances):
                plant = plants_by_id[instance.plant_id]
                morphology_report = validate_morphology_tree(plant)
                geometry_report = build_geometry_from_morphology(
                    plant,
                    materials,
                    instance_id=instance.plant_id,
                    instance_role=instance.role,
                    position=instance.position,
                    rotation_deg=instance.rotation_deg,
                    plant_scale=instance.scale,
                    add_ground=index == 0,
                )
                morphology_reports.append(
                    {{
                        "plant_id": instance.plant_id,
                        "seed": instance.seed,
                        "status": morphology_report["status"],
                        "summary": morphology_report["summary"],
                        "warnings": morphology_report["warnings"],
                    }}
                )
                geometry_reports.append(
                    {{
                        "plant_id": instance.plant_id,
                        "seed": instance.seed,
                        **geometry_report,
                    }}
                )
                max_height = max(max_height, geometry_report["height"])

            support_report = create_cultivation_supports(scene, materials, geometry_reports)
            mesh_collision_audit = audit_scene_mesh_collisions()

            scene.metadata["plant_morphology_reports"] = morphology_reports
            scene.metadata["geometry_reports"] = geometry_reports
            scene.metadata["cultivation_adaptation"] = adaptation_report
            scene.metadata["support_geometry"] = support_report
            scene.metadata["mesh_collision_audit"] = mesh_collision_audit
            scene_validation = validate_cultivation_scene(scene)
            scene.metadata["scene_validation_status"] = scene_validation["status"]

            _setup_scene_camera_and_lighting(scene, max_height)
            setup_render_settings()
            _write_text_block("uchuva_scene_report.json", _to_json(scene.to_dict()))
            _write_text_block("uchuva_validation_report.json", _to_json(scene_validation))
            bpy.context.scene["uchuva_generator_seed"] = seed
            bpy.context.scene["uchuva_generator_preset"] = preset
            bpy.context.scene["uchuva_validation_status"] = scene_validation["status"]

            if SAVE_BLEND_AFTER_GENERATION and bpy.data.filepath:
                bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

            print("Generated uchuva scene from embedded Text Block")
            print(f"Plant instances: {{len(scene.plant_instances)}}")
            print(f"Scene validation status: {{scene_validation['status']}}")
            return scene, scene_validation


        def _install_embedded_package() -> None:
            sources = json.loads(
                zlib.decompress(
                    base64.b64decode(_EMBEDDED_MODULE_SOURCES_B64_ZLIB)
                ).decode("utf-8")
            )
            package_name = "uchuva_lsystem"
            package = types.ModuleType(package_name)
            package.__file__ = "<blend text: uchuva_lsystem/__init__.py>"
            package.__package__ = package_name
            package.__path__ = []
            sys.modules[package_name] = package

            for module_name in _MODULE_EXECUTION_ORDER:
                source = sources[module_name]
                if module_name == "__init__":
                    module = package
                    filename = package.__file__
                else:
                    full_name = f"{{package_name}}.{{module_name}}"
                    module = types.ModuleType(full_name)
                    module.__file__ = f"<blend text: {{full_name}}.py>"
                    module.__package__ = package_name
                    sys.modules[full_name] = module
                    setattr(package, module_name, module)
                    filename = module.__file__
                exec(compile(source, filename, "exec"), module.__dict__)


        def _setup_scene_camera_and_lighting(scene, max_height: float) -> None:
            from uchuva_lsystem.blender_scene import setup_camera_and_lights

            positions = [instance.position for instance in scene.plant_instances]
            center_x = sum(position[0] for position in positions) / len(positions)
            center_y = sum(position[1] for position in positions) / len(positions)
            scene_radius = max(
                (
                    ((position[0] - center_x) ** 2 + (position[1] - center_y) ** 2)
                    ** 0.5
                    for position in positions
                ),
                default=2.0,
            ) + 1.5
            setup_camera_and_lights(
                plant_height=max(max_height, 2.4),
                target=(center_x, center_y, max_height * 0.48),
                seed=scene.seed,
                scene_radius=scene_radius,
            )
            scene.metadata["lighting"] = {{
                "mode": "distant_randomized_area_light",
                "seed": scene.seed,
                "scene_radius": round(scene_radius, 3),
            }}


        def _write_text_block(name: str, content: str) -> None:
            import bpy

            text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
            text.clear()
            text.write(content)


        def _to_json(data) -> str:
            return json.dumps(data, ensure_ascii=False, indent=2) + "\\n"


        generate_scene()
        '''
    )


def build_internal_annotation_runner(
    module_sources: dict[str, str],
    seed: int,
    neighbor_count: int,
) -> str:
    payload = json.dumps(module_sources, ensure_ascii=False).encode("utf-8")
    encoded_sources = base64.b64encode(zlib.compress(payload, level=9)).decode("ascii")
    execution_order = [
        "morphology",
        "parameters",
        "scene",
        "collisions",
        "cultivation",
        "texture_assets",
        "validation",
        "grammar",
        "yolo_export",
        "blender_annotations",
        "blender_scene",
        "blender_environment",
        "blender_geometry",
        "exporters",
        "blender_pilot",
        "blender_dataset",
        "__init__",
    ]
    return dedent(
        f'''\
        """Self-contained contextual uchuva annotation pilot.

        Run this Text Block in Blender. It reuses the CC0 images packed in this
        file and writes RGB, masks, and JSON reports next to the .blend.
        """

        from __future__ import annotations

        import base64
        import json
        import sys
        import types
        import zlib
        from pathlib import Path


        DEFAULT_SEED_START = {seed}
        DEFAULT_NEIGHBOR_COUNT = {neighbor_count}
        DEFAULT_WIDTH = 1280
        DEFAULT_HEIGHT = 960
        DEFAULT_CYCLES_SAMPLES = 64
        RENDER_RGB = True
        RENDER_CYCLES = True
        SAVE_BLEND_AFTER_GENERATION = False

        _EMBEDDED_MODULE_SOURCES_B64_ZLIB = {encoded_sources!r}
        _MODULE_EXECUTION_ORDER = {execution_order!r}


        def generate_annotation_scene(
            seed_start: int = DEFAULT_SEED_START,
            neighbor_count: int = DEFAULT_NEIGHBOR_COUNT,
            width: int = DEFAULT_WIDTH,
            height: int = DEFAULT_HEIGHT,
            cycles_samples: int = DEFAULT_CYCLES_SAMPLES,
        ):
            _install_embedded_package()
            import bpy
            from uchuva_lsystem.blender_pilot import generate_annotation_pilot

            if bpy.data.filepath:
                blend_path = Path(bpy.data.filepath)
                output_dir = blend_path.parent / f"uchuva_annotation_internal_seed_{{seed_start}}"
            else:
                output_dir = Path.cwd() / f"uchuva_annotation_internal_seed_{{seed_start}}"

            report = generate_annotation_pilot(
                seed_start=seed_start,
                neighbor_count=neighbor_count,
                output_dir=output_dir,
                output_blend=None,
                asset_dir=None,
                width=width,
                height=height,
                cycles_samples=cycles_samples,
                render_rgb=RENDER_RGB,
                render_cycles=RENDER_CYCLES,
            )
            if SAVE_BLEND_AFTER_GENERATION and bpy.data.filepath:
                bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
            print("Generated contextual uchuva annotation pilot from embedded code")
            print(f"Output directory: {{output_dir}}")
            print(f"Validation: {{report['annotation_validation']['status']}}")
            return report


        def _install_embedded_package() -> None:
            sources = json.loads(
                zlib.decompress(
                    base64.b64decode(_EMBEDDED_MODULE_SOURCES_B64_ZLIB)
                ).decode("utf-8")
            )
            package_name = "uchuva_lsystem"
            package = types.ModuleType(package_name)
            package.__file__ = "<blend text: uchuva_lsystem/__init__.py>"
            package.__package__ = package_name
            package.__path__ = []
            sys.modules[package_name] = package

            for module_name in _MODULE_EXECUTION_ORDER:
                source = sources[module_name]
                if module_name == "__init__":
                    module = package
                    filename = package.__file__
                else:
                    full_name = f"{{package_name}}.{{module_name}}"
                    module = types.ModuleType(full_name)
                    module.__file__ = f"<blend text: {{full_name}}.py>"
                    module.__package__ = package_name
                    sys.modules[full_name] = module
                    setattr(package, module_name, module)
                    filename = module.__file__
                exec(compile(source, filename, "exec"), module.__dict__)


        generate_annotation_scene()
        '''
    )


def build_internal_dataset_runner(
    module_sources: dict[str, str],
    seed: int,
) -> str:
    payload = json.dumps(module_sources, ensure_ascii=False).encode("utf-8")
    encoded_sources = base64.b64encode(zlib.compress(payload, level=9)).decode("ascii")
    execution_order = [
        "morphology",
        "parameters",
        "scene",
        "collisions",
        "cultivation",
        "texture_assets",
        "validation",
        "grammar",
        "yolo_export",
        "blender_annotations",
        "blender_scene",
        "blender_environment",
        "blender_geometry",
        "exporters",
        "blender_pilot",
        "blender_dataset",
        "__init__",
    ]
    return dedent(
        f'''\
        """Self-contained 200-image uchuva YOLO/MakeSense dataset generator.

        Run this Text Block in Blender. It uses the CC0 assets packed in this
        file and writes a resumable dataset next to the .blend.
        """

        from __future__ import annotations

        import base64
        import json
        import sys
        import types
        import zlib
        from pathlib import Path


        DEFAULT_SEED = {seed}
        DEFAULT_IMAGE_COUNT = 200
        DEFAULT_CAPTURES_PER_SCENE = 4
        DEFAULT_WIDTH = 1280
        DEFAULT_HEIGHT = 960
        DEFAULT_CYCLES_QA_COUNT = 12
        DEFAULT_CYCLES_SAMPLES = 64
        RESUME = True
        KEEP_MASKS = False

        _EMBEDDED_MODULE_SOURCES_B64_ZLIB = {encoded_sources!r}
        _MODULE_EXECUTION_ORDER = {execution_order!r}


        def generate_yolo_dataset(
            seed: int = DEFAULT_SEED,
            image_count: int = DEFAULT_IMAGE_COUNT,
            width: int = DEFAULT_WIDTH,
            height: int = DEFAULT_HEIGHT,
        ):
            _install_embedded_package()
            import bpy
            from uchuva_lsystem.blender_dataset import (
                DatasetConfig,
                generate_annotation_dataset,
            )

            if bpy.data.filepath:
                blend_path = Path(bpy.data.filepath)
                output_dir = blend_path.parent / f"uchuva_yolo_dataset_internal_seed_{{seed}}"
            else:
                output_dir = Path.cwd() / f"uchuva_yolo_dataset_internal_seed_{{seed}}"
            config = DatasetConfig(
                output_dir=output_dir,
                seed=seed,
                image_count=image_count,
                captures_per_scene=DEFAULT_CAPTURES_PER_SCENE,
                width=width,
                height=height,
                cycles_qa_count=DEFAULT_CYCLES_QA_COUNT,
                cycles_samples=DEFAULT_CYCLES_SAMPLES,
                asset_dir=None,
                resume=RESUME,
                keep_masks=KEEP_MASKS,
            )
            report = generate_annotation_dataset(config)
            print("Generated uchuva YOLO/MakeSense dataset from embedded code")
            print(f"Output directory: {{output_dir}}")
            print(f"Validation: {{report['status']}}")
            return report


        def _install_embedded_package() -> None:
            sources = json.loads(
                zlib.decompress(
                    base64.b64decode(_EMBEDDED_MODULE_SOURCES_B64_ZLIB)
                ).decode("utf-8")
            )
            package_name = "uchuva_lsystem"
            package = types.ModuleType(package_name)
            package.__file__ = "<blend text: uchuva_lsystem/__init__.py>"
            package.__package__ = package_name
            package.__path__ = []
            sys.modules[package_name] = package
            for module_name in _MODULE_EXECUTION_ORDER:
                source = sources[module_name]
                if module_name == "__init__":
                    module = package
                    filename = package.__file__
                else:
                    full_name = f"{{package_name}}.{{module_name}}"
                    module = types.ModuleType(full_name)
                    module.__file__ = f"<blend text: {{full_name}}.py>"
                    module.__package__ = package_name
                    sys.modules[full_name] = module
                    setattr(package, module_name, module)
                    filename = module.__file__
                exec(compile(source, filename, "exec"), module.__dict__)


        generate_yolo_dataset()
        '''
    )


def _build_readme_text(
    text_name: str,
    annotation_text_name: str,
    dataset_text_name: str,
    seed: int,
    plant_count: int,
    neighbor_count: int,
) -> str:
    return dedent(
        f"""\
        Generador interno de uchuva
        ===========================

        Este archivo .blend contiene el código del generador en el Text Block:

          {text_name}
          {annotation_text_name}
          {dataset_text_name}

        Para regenerar la escena:

        1. Cambia a Blender > Text Editor.
        2. Abre el Text Block {text_name}.
        3. Presiona Run Script.

        Valores por defecto embebidos:

        - seed: {seed}
        - plant_count: {plant_count}
        - annotation_neighbor_count: {neighbor_count}
        - preset: foreground_plant_with_neighbors
        - collision_policy: canopy_permissive

        El script escribe reportes JSON como Text Blocks internos:

        - uchuva_scene_report.json
        - uchuva_validation_report.json
        - uchuva_pilot_report.json
        - uchuva_pilot_validation.json

        Para generar el piloto contextual con RGB y anotaciones, ejecuta
        {annotation_text_name}. Los assets CC0 estan empaquetados en el .blend y
        su procedencia queda registrada en ASSET_MANIFEST_CC0.json.

        Para generar el dataset YOLO/MakeSense de 200 imagenes, ejecuta
        {dataset_text_name}. El proceso es reanudable y escribe data.yaml,
        labels.txt, manifest.jsonl y dataset_report.json junto al .blend.

        No requiere importar el repositorio local para generar la escena.
        """
    )


def _replace_text_block(bpy: object, name: str, content: str) -> None:
    text = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    text.clear()
    text.write(content)


def _import_bpy() -> object:
    try:
        import bpy
    except ModuleNotFoundError as exc:
        raise RuntimeError("This script must be run with Blender Python.") from exc
    return bpy


def _argv_after_blender_separator() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


if __name__ == "__main__":
    main()
