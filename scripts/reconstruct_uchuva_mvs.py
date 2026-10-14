"""Small COLMAP MVS on a recovered component; keep dense and visual outputs distinct."""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import pycolmap


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--views", type=int, default=16)
    parser.add_argument("--size", type=int, default=640)
    parser.add_argument("--image-list", type=Path, help="Optional newline-delimited registered image names")
    parser.add_argument("--fuse-only", action="store_true", help="Reuse completed depth maps after an export failure")
    args = parser.parse_args()
    if args.fuse_only:
        report_path = args.output / "mvs_report.json"
        report = json.loads(report_path.read_text())
        if "patch_match" not in report["stages"]:
            raise ValueError("No completed PatchMatch stage to reuse")
        options = pycolmap.StereoFusionOptions()
        options.num_threads = 4
        options.max_image_size = args.size
        options.min_num_pixels = 3
        options.cache_size = 2
        options.use_cache = True
        start = time.time()
        result = pycolmap.stereo_fusion(args.output / "fused.ply", args.output,
            input_type="geometric", options=options, output_type="ply")
        report["fusion_recovery"] = dict(seconds=time.time()-start, status="completed",
            note="Original fusion computed points but TXT denotes a COLMAP directory; corrected PLY output type without repeating PatchMatch",
            points3D=result.num_points3D())
        report["status"] = "partial_dense_geometry_unscaled"
        report_path.write_text(json.dumps(report,indent=2))
        print(json.dumps(report["fusion_recovery"]))
        return
    args.output.mkdir(parents=True, exist_ok=False)
    model = pycolmap.Reconstruction(args.model)
    names = sorted(model.images[i].name for i in model.reg_image_ids())
    if args.image_list:
        requested=set(args.image_list.read_text().splitlines())
        names=[name for name in names if name in requested]
        if len(names)<3:
            raise ValueError('Fewer than three requested images are registered')
    indices = sorted(set(np.linspace(0, len(names)-1, min(args.views, len(names)), dtype=int)))
    names = [names[i] for i in indices]
    # image_names limits exported JPEGs but does not prune the sparse model.
    # Prune a copy first so automatic source selection cannot reference absent JPEGs.
    for image_id in list(model.reg_image_ids()):
        image = model.images[image_id]
        if image.name not in names:
            model.deregister_frame(image.frame_id)
    subset = args.output / "input_sparse_subset"
    subset.mkdir()
    model.write(subset)
    undistort = pycolmap.UndistortCameraOptions()
    undistort.max_image_size = args.size
    patch = pycolmap.PatchMatchOptions()
    patch.max_image_size = args.size
    patch.cache_size = 2
    patch.num_threads = 1
    patch.gpu_index = "0"
    patch.num_iterations = 3
    patch.num_samples = 10
    patch.geom_consistency = True
    fusion = pycolmap.StereoFusionOptions()
    fusion.num_threads = 4
    fusion.max_image_size = args.size
    fusion.min_num_pixels = 3
    fusion.cache_size = 2
    fusion.use_cache = True
    report = dict(script_version="reconstruction-pilot/0.1", seed=20261001, parameter_preset="pilot_2h",
        pycolmap_version=pycolmap.__version__, model=str(args.model), images=str(args.images),
        selected_views=names, units="arbitrary", measured_physical_scale=False,
        image_list=str(args.image_list) if args.image_list else None,
        parameter_provenance="engineering_heuristic", stages={},
        options=dict(undistort=undistort.todict(), patch=patch.todict(), fusion=fusion.todict()))
    def save():
        (args.output / "mvs_report.json").write_text(json.dumps(report, indent=2, default=str))
    save()
    operations = [
        ("undistort", lambda: pycolmap.undistort_images(args.output, subset, args.images,
            image_names=names, num_patch_match_src_images=min(8,len(names)-1),
            undistort_options=undistort, num_threads=4)),
        ("patch_match", lambda: pycolmap.patch_match_stereo(args.output, options=patch)),
        ("fusion", lambda: pycolmap.stereo_fusion(args.output / "fused.ply", args.output,
            input_type="geometric", options=fusion, output_type="ply")),
    ]
    for name, operation in operations:
        start = time.time()
        print(f"Starting {name}", flush=True)
        operation()
        report["stages"][name] = dict(seconds=time.time()-start, status="completed")
        save()
    report["status"] = "partial_dense_geometry_unscaled"
    save()
    print(json.dumps(report, default=str), flush=True)


if __name__ == "__main__":
    main()
