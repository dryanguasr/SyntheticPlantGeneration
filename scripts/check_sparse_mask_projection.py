"""Check mask identities against independent projected Blender object bounds."""
import argparse
from collections import defaultdict
import json
import hashlib
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scenes",type=int,nargs="+",help="Diagnostic subset; does not write the final export gate")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    root = args.root.resolve()
    checked, skipped, hashes, reverse_checks = 0, [], {}, 0
    for folder in sorted(root.glob("scene_*")):
        if args.scenes is not None and int(folder.name.rsplit("_",1)[1]) not in args.scenes:continue
        bpy.ops.wm.open_mainfile(filepath=str(folder / "cultivation.blend"))
        scene = bpy.context.scene
        print("WORKBENCH_STATE", {k:getattr(scene.display.shading,k,None) for k in ("show_object_outline","show_xray","show_backface_culling")},flush=True)
        payload=json.loads((folder/"input.json").read_text(encoding="utf-8"))
        depsgraph=bpy.context.evaluated_depsgraph_get()
        for marker in payload["markers"]:
            if marker.get("printed_faces") != "outward_only":
                continue  # Historical pilot without opaque reverses.
            normal=Vector(marker["normal_world"])
            center=Vector(marker["center_world_m"])*8.0
            thickness=marker["backing_thickness_m"]*8.0
            backing=scene.objects[f"aruco_{marker['id']}_opaque_backing"]
            evaluated=backing.evaluated_get(depsgraph)
            inverse=evaluated.matrix_world.inverted()
            up=Vector((0,0,1)); right=up.cross(normal)
            half=marker["side_m"]*8.0*.45
            for x,y in ((0,0),(-half,-half),(-half,half),(half,-half),(half,half)):
                point=center+right*x+up*y
                origin=point-normal*(thickness+.001*8.0)
                hit,location,_,_=evaluated.ray_cast(inverse@origin,inverse.to_3x3()@normal,distance=thickness+.002*8.0)
                assert hit, (folder.name,marker["id"],"missing opaque backing")
                assert (evaluated.matrix_world@location-(point-normal*thickness)).length < 1e-4
                reverse_checks += 1
        objects = defaultdict(list)
        for obj in scene.objects:
            if obj.get("uchuva_semantic_class") == "calyx" and not obj.hide_render:
                objects[obj["uchuva_reproductive_instance_id"]].append(obj)
        for path in sorted(folder.glob("*/capture.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
            camera = bpy.data.objects[path.parent.name]
            for key, item in data["mask"]["items"].items():
                if key == "0" or not item["visible_pixels"]:
                    continue
                identity = item["instance_id"]
                assert identity in objects, identity
                points = [world_to_camera_view(scene, camera, obj.matrix_world @ Vector(corner))
                          for obj in objects[identity] for corner in obj.bound_box]
                if any(p.z <= camera.data.clip_start for p in points):
                    skipped.append([folder.name, path.parent.name, identity, "near_plane_intersection"])
                    continue
                x, y, w, h = item["bbox_xywh"]
                left, right = min(p.x for p in points)*1280, max(p.x for p in points)*1280
                top, bottom = (1-max(p.y for p in points))*960, (1-min(p.y for p in points))*960
                assert x >= left-2 and x+w <= right+2 and y >= top-2 and y+h <= bottom+2, (
                    folder.name, path.parent.name, identity, item["bbox_xywh"], [left,top,right,bottom])
                checked += 1
    result = {"status":"passed", "visible_instances_checked":checked, "skipped":skipped,
              "opaque_marker_reverse_rays_checked":reverse_checks,
              "capture_sha256":hashes,
              "method":"mask bounds contained in projected calyx object bounds; two pixel raster tolerance",
              "limitation":"Does not certify silhouette completeness or photorealism."}
    report_name="mask_projection_report.json" if args.scenes is None else "mask_projection_subset_report.json"
    (root/report_name).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result),flush=True)


if __name__ == "__main__": main()
