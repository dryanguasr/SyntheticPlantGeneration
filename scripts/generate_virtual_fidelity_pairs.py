"""Render 12 paired historical-v1 versus virtual-fidelity-v2 comparisons in Blender."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from uchuva_lsystem.blender_annotations import camera_metadata, render_rgb_image
from uchuva_lsystem.blender_dataset import (
    _build_dataset_scene,
    _morphology_params_for_target,
)
from uchuva_lsystem.blender_environment import apply_lighting_profile
from uchuva_lsystem.blender_review import compose_before_after
from uchuva_lsystem.blender_scene import save_blend_file, setup_render_settings
from uchuva_lsystem.exporters import export_json
from uchuva_lsystem.blender_scene import create_annotation_camera


CAMERA_PROFILES = ("real_context", "real_mid", "real_close")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, default=12)
    return parser.parse_args(_argv_after_blender_separator())


def main() -> None:
    args = parse_args()
    v1_root = args.v1_dataset.resolve()
    output = args.output_dir.resolve()
    asset_dir = (
        args.asset_dir.resolve()
        if args.asset_dir is not None and args.asset_dir.is_absolute()
        else (REPO_ROOT / args.asset_dir).resolve()
        if args.asset_dir is not None
        else None
    )
    output.mkdir(parents=True, exist_ok=True)
    records = _read_jsonl(v1_root / "manifest.jsonl")
    records = [record for record in records if record.get("split") == "train"]
    quota = {camera: args.count // len(CAMERA_PROFILES) for camera in CAMERA_PROFILES}
    for camera in CAMERA_PROFILES[: args.count % len(CAMERA_PROFILES)]:
        quota[camera] += 1
    accepted_counts: Counter[str] = Counter()
    accepted = []
    rejected = []
    setup_render_settings(width=1280, height=960)
    for record in records:
        camera_profile = str(record.get("camera_profile"))
        if camera_profile not in quota or accepted_counts[camera_profile] >= quota[camera_profile]:
            continue
        target = dict(record["composition_target"])
        params = _morphology_params_for_target(target)
        build = _build_dataset_scene(
            scene_seed=int(record["scene_seed"]),
            neighbor_count=int(record["neighbor_count"]),
            phenology_profile=str(record["phenology_profile"]),
            asset_dir=asset_dir,
            composition_target=target,
            morphology_params=params,
            phenology_model="literature_cohort_v1",
            background_style="layered_understory_v2",
        )
        collision_count = int(
            build["scene_validation"]["summary"]["physical_collision_count"]
        )
        if collision_count or build["open_calyx_count"] or build["visible_hidden_fruit_count"]:
            rejected.append(
                {
                    "scene_seed": record["scene_seed"],
                    "camera_profile": camera_profile,
                    "physical_collision_count": collision_count,
                    "open_calyx_count": build["open_calyx_count"],
                    "visible_hidden_fruit_count": build["visible_hidden_fruit_count"],
                }
            )
            continue
        pair_index = len(accepted)
        pair_dir = output / f"pair_{pair_index:02d}_seed_{record['scene_seed']}"
        pair_dir.mkdir(parents=True, exist_ok=True)
        capture_seed = int(record["capture_seed"])
        apply_lighting_profile(str(record["lighting_profile"]), capture_seed)
        retry = int(record.get("capture_pose_retry", 0))
        camera = create_annotation_camera(
            profile_name=camera_profile,
            target=build["target"],
            plant_height=float(build["plant_height"]),
            scene_radius=float(build["scene_radius"]),
            seed=capture_seed + retry * 104729,
            name_suffix=f"paired_{pair_index:02d}",
        )
        _lock_camera(camera, record["camera"])
        frame = record["frame"]
        sensor = dict(record["sensor_profile"])
        candidate_path = pair_dir / "v2_candidate.jpg"
        render_rgb_image(
            camera,
            candidate_path,
            width=int(frame["width"]),
            height=int(frame["height"]),
            engine="BLENDER_EEVEE_NEXT",
            image_format="JPEG",
            **sensor,
        )
        baseline_source = v1_root / record["image_path"]
        comparison_path = compose_before_after(
            baseline_source,
            candidate_path,
            pair_dir / "v1_v2_comparison.png",
        )
        validation_path = export_json(
            build["scene_validation"], pair_dir / "v2_scene_validation.json"
        )
        morphology_path = export_json(
            build["morphology_reports"], pair_dir / "v2_morphology_summaries.json"
        )
        pair_record = {
            "pair_index": pair_index,
            "scene_seed": int(record["scene_seed"]),
            "capture_seed": capture_seed,
            "camera_profile": camera_profile,
            "lighting_profile": record["lighting_profile"],
            "phenology_profile": record["phenology_profile"],
            "same_camera_matrix": camera_metadata(
                camera, int(frame["width"]), int(frame["height"])
            )["matrix_world"] == record["camera"]["matrix_world"],
            "same_lighting_seed": True,
            "same_sensor_profile": True,
            "v1_source": _file_record(baseline_source, root=REPO_ROOT),
            "v2_candidate": _file_record(candidate_path, root=output),
            "comparison": _file_record(comparison_path, root=output),
            "validation": _file_record(Path(validation_path), root=output),
            "morphology_summaries": _file_record(Path(morphology_path), root=output),
            "physical_collision_count": collision_count,
            "open_calyx_count": build["open_calyx_count"],
            "visible_hidden_fruit_count": build["visible_hidden_fruit_count"],
            "interpretation": (
                "The left image is the archived v1 render. The right image reruns the same scene/capture seed, exact camera matrix, lighting profile, and sensor profile with v2 morphology/background."
            ),
        }
        export_json(pair_record, pair_dir / "pair_manifest.json")
        accepted.append(pair_record)
        accepted_counts[camera_profile] += 1
        save_blend_file(output / "representative_v2.blend")
        if len(accepted) >= args.count:
            break
    report = {
        "version": "1.0.0-archived-v1-versus-v2-paired",
        "status": "valid" if len(accepted) == args.count else "incomplete",
        "requested_pair_count": args.count,
        "accepted_pair_count": len(accepted),
        "camera_profile_counts": dict(sorted(accepted_counts.items())),
        "render_engine": "BLENDER_EEVEE_NEXT",
        "cycles_qa_count": 0,
        "pairs": accepted,
        "rejections": rejected,
    }
    export_json(report, output / "paired_comparison_report.json")
    print(output / "paired_comparison_report.json")
    if report["status"] != "valid":
        raise RuntimeError(f"Only {len(accepted)} of {args.count} pairs were accepted.")


def _lock_camera(camera: Any, report: dict[str, Any]) -> None:
    from mathutils import Matrix

    camera.matrix_world = Matrix(report["matrix_world"])
    camera.data.lens = float(report["lens_mm"])
    camera.data.sensor_width = float(report["sensor_width_mm"])
    camera.data.clip_start = float(report["clip_start"])
    camera.data.clip_end = float(report["clip_end"])
    camera.data.dof.use_dof = bool(report.get("depth_of_field", {}).get("enabled_for_rgb", True))
    camera.data.dof.aperture_fstop = float(report.get("depth_of_field", {}).get("fstop", 4.5))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def _file_record(path: Path, *, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display_path = str(resolved.relative_to(root.resolve()))
    except ValueError:
        display_path = str(resolved)
    return {
        "path": display_path,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "bytes": resolved.stat().st_size,
    }


def _argv_after_blender_separator() -> list[str]:
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return sys.argv[1:]


if __name__ == "__main__":
    main()
