"""Bounded COLMAP pilot; preserves each recovered component separately."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import pycolmap


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-features", type=int, default=4096)
    parser.add_argument("--fixed-intrinsics", type=float, nargs=4,
                        help="SIMPLE_RADIAL f,cx,cy,k from a previously recovered same-resolution camera")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    selected = json.loads((args.selection / "selection.json").read_text(encoding="utf-8"))
    rows = [r for r in selected["rows"] if r.get("selected")]
    image_path = (args.selection / "images").resolve()
    database = args.output / "database.db"
    sparse = args.output / "sparse"
    sparse.mkdir()
    reader = pycolmap.ImageReaderOptions()
    reader.camera_model = "SIMPLE_RADIAL"
    if args.fixed_intrinsics:
        reader.camera_params = ','.join(map(str,args.fixed_intrinsics))
    extraction = pycolmap.FeatureExtractionOptions()
    extraction.num_threads = 8
    extraction.max_image_size = max(r["width"] for r in rows)
    extraction.sift.max_num_features = args.max_features
    matching = pycolmap.FeatureMatchingOptions()
    matching.num_threads = 8
    matching.guided_matching = True
    mapping = pycolmap.IncrementalPipelineOptions()
    mapping.num_threads = 8
    mapping.random_seed = 20261001
    mapping.min_model_size = 5
    mapping.max_num_models = 5
    mapping.mapper.init_min_num_inliers = 50
    mapping.mapper.init_min_tri_angle = 4.0
    if args.fixed_intrinsics:
        mapping.ba_refine_focal_length = False
        mapping.ba_refine_principal_point = False
        mapping.ba_refine_extra_params = False
    report = dict(script_version="reconstruction-pilot/0.1", seed=20261001, parameter_preset="pilot_2h",
        pycolmap_version=pycolmap.__version__, has_cuda=pycolmap.has_cuda,
        input_sha256=selected["input"]["sha256"], images=len(rows),
        input_selection=str(args.selection), physical_scale="arbitrary_units",
        intrinsic_initialization=("Fixed SIMPLE_RADIAL from prior local component; not physical calibration" if args.fixed_intrinsics else
            "SIMPLE_RADIAL shared camera, focal prior from COLMAP default; refined by bundle adjustment; not physical calibration"),
        independent_evaluation=False, parameter_provenance="engineering_heuristic",
        options=dict(reader=reader.todict(), extraction=extraction.todict(), matching=matching.todict(), mapping=mapping.todict()),
        stages={}, components=[])
    write_json(args.output / "sfm_report.json", report)
    for name, operation in [
        ("feature_extraction", lambda: pycolmap.extract_features(database, image_path,
            camera_mode=pycolmap.CameraMode.SINGLE, reader_options=reader,
            extraction_options=extraction, device=pycolmap.Device.cuda)),
        ("exhaustive_matching", lambda: pycolmap.match_exhaustive(database,
            matching_options=matching, device=pycolmap.Device.cuda)),
        ("incremental_mapping", lambda: pycolmap.incremental_mapping(database, image_path, sparse, options=mapping)),
    ]:
        start = time.time()
        print(f"Starting {name}", flush=True)
        result = operation()
        report["stages"][name] = dict(seconds=time.time()-start, status="completed")
        write_json(args.output / "sfm_report.json", report)
    for model_id, model in result.items():
        folder = sparse / str(model_id)
        folder.mkdir(exist_ok=True)
        model.write(folder)
        model.write_text(folder)
        points = list(model.points3D.values())
        with (folder / "sparse_points.ply").open("w") as f:
            f.write(f"ply\nformat ascii 1.0\nelement vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
            for p in points:
                f.write(" ".join(map(str, [*p.xyz, *p.color])) + "\n")
        registered = []
        for image_id in model.reg_image_ids():
            image = model.images[image_id]
            registered.append(dict(image_id=image_id, image=image.name,
                camera_id=image.camera_id, center=image.projection_center().tolist(),
                cam_from_world=image.cam_from_world().matrix().tolist()))
        write_json(folder / "poses.json", dict(script_version=report["script_version"], seed=20261001,
            parameter_preset="pilot_2h", units="arbitrary", convention="COLMAP world to camera, camera +Z optical forward", images=registered))
        errors = [p.error for p in points]
        report["components"].append(dict(model_id=model_id, registered_images=model.num_reg_images(),
            points3D=model.num_points3D(), mean_reprojection_error_pixels=float(np.mean(errors)) if errors else None,
            median_reprojection_error_pixels=float(np.median(errors)) if errors else None,
            mean_track_length=model.compute_mean_track_length(),
            cameras=[dict(camera_id=k, model=c.model_name, width=c.width, height=c.height, params=c.params.tolist()) for k,c in model.cameras.items()],
            registered_names=sorted(i["image"] for i in registered),
            both_sides_alignment="not_validated", plant_completeness="not_validated"))
    report["status"] = "partial_sfm" if report["components"] else "failed_no_model"
    write_json(args.output / "sfm_report.json", report)
    print(json.dumps({k:v for k,v in report.items() if k not in {"options"}}), flush=True)
    return 0 if report["components"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
