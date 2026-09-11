"""Two small EEVEE mask passes test visible boxes and true occlusion on a fixture.

Run with Blender --background --factory-startup --python-exit-code 1 --python
this_file. The spheres are annotation fixtures, not a botanical model.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_lsystem.blender_annotations import render_reproductive_annotations, tag_annotation_object
from uchuva_lsystem.annotation_contract import mask_visibility_metrics
from uchuva_lsystem.yolo_export import detections_from_mask_items


def main() -> None:
    start = time.perf_counter()
    output = ROOT / "outputs/audits/scientific_route_20260908/blender_smoke"
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(0, 0, 0))
    target = bpy.context.object
    tag_annotation_object(target, "calyx", plant_id="fixture", reproductive_id="unit1",
                          calyx_state="inflated_green")
    bpy.ops.object.camera_add(location=(0, 0, 6))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4
    bpy.context.scene.camera = camera
    for name in ("isolated", "occluded"):
        (output / name).mkdir(exist_ok=True)
    isolated = render_reproductive_annotations(camera, output / "isolated", width=128, height=128)
    base = detections_from_mask_items(isolated["items"], width=128, height=128)
    assert len(base) == 1, base
    # A leaf occluder covers the right half, without intersecting the sphere.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.65, 0, 2))
    occluder = bpy.context.object
    occluder.scale = (1.3, 3, 0.1)
    tag_annotation_object(occluder, "leaf", plant_id="fixture", organ_id="occluder")
    blocked = render_reproductive_annotations(camera, output / "occluded", width=128, height=128)
    detections = detections_from_mask_items(blocked["items"], width=128, height=128)
    assert len(detections) == 1 and detections[0].instance_id == base[0].instance_id
    before, after = base[0], detections[0]
    assert 0 < after.visible_pixels < before.visible_pixels
    assert after.bbox_xywh[2] < before.bbox_xywh[2]
    full = mask_visibility_metrics(before.visible_pixels, before.bbox_xywh[2] * before.bbox_xywh[3],
                                   isolated_pixels=before.visible_pixels)
    partial = mask_visibility_metrics(after.visible_pixels, after.bbox_xywh[2] * after.bbox_xywh[3],
                                      isolated_pixels=before.visible_pixels)
    assert full["mask_fill_ratio"] < 0.9 and full["occluded_fraction_in_frame"] == 0
    assert 0.3 < partial["occluded_fraction_in_frame"] < 0.7
    report = {"status": "passed", "purpose": "annotation_fixture_not_crop_validation",
              "blender": bpy.app.version_string, "python": sys.version,
              "elapsed_seconds": time.perf_counter() - start,
              "resolution": [128, 128], "mask_passes": 2,
              "isolated": {**before.to_dict(), **full},
              "occluded": {**after.to_dict(), **partial}}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
