"""Export paired detection/instance segmentation and evaluate calibrated ArUco poses."""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import shutil

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"src"))
from uchuva_lsystem.sparse_pilot import VERSION, CLASSES, class_for_grade


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def numpy_rle(mask):
    pixels = mask.ravel(order="F").astype(bool)
    boundaries = np.flatnonzero(np.r_[True, pixels[1:] != pixels[:-1], True])
    counts = np.diff(boundaries).tolist()
    if pixels[0]:
        counts.insert(0,0)
    return {"size": list(mask.shape), "counts": counts}


def evaluate_aruco(rgb, metadata):
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100), params)
    corners, identifiers, rejected = detector.detectMarkers(cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY))
    observations = {}
    unexpected = []
    known = {m["id"]: m for m in metadata["markers"]}
    K = np.array(metadata["K"], np.float64)
    ids = [] if identifiers is None else identifiers.ravel()
    counts = Counter(int(i) for i in ids)
    for quad, raw_id in zip(corners, ids):
        identifier = int(raw_id)
        if identifier not in known:
            unexpected.append(identifier)
            continue
        expected = known[identifier]
        half = expected["side_m"]/2
        object_points = np.array([[-half,half,0],[half,half,0],[half,-half,0],[-half,-half,0]], np.float64)
        image_points = quad.reshape(4,2).astype(np.float64)
        solved = cv2.solvePnPGeneric(object_points, image_points, K, np.zeros(5), flags=cv2.SOLVEPNP_IPPE_SQUARE)
        candidates = []
        truth = np.array(expected["T_camera_marker_m"])
        for rvec, tvec in zip(solved[1], solved[2]):
            rotation = cv2.Rodrigues(rvec)[0]
            depths = (rotation @ object_points.T + tvec)[2]
            if np.min(depths) <= 0:
                continue
            projected = cv2.projectPoints(object_points, rvec, tvec, K, np.zeros(5))[0].reshape(4,2)
            error = float(np.sqrt(np.mean(np.sum((projected-image_points)**2, axis=1))))
            angular = math.degrees(math.acos(np.clip((np.trace(rotation @ truth[:3,:3].T)-1)/2, -1, 1)))
            candidates.append({"reprojection_rmse_px": error,
                               "translation_error_m": float(np.linalg.norm(tvec.ravel()-truth[:3,3])),
                               "rotation_error_deg": angular, "rvec": rvec.ravel().tolist(), "tvec_m": tvec.ravel().tolist()})
        candidates.sort(key=lambda c:c["reprojection_rmse_px"])
        observations[identifier] = {"detected": True, "duplicate_id": counts[identifier]>1,
            "corners_px": image_points.tolist(), "pose_candidates": candidates,
            "selected_by": "lowest_reprojection_not_ground_truth", "selected": candidates[0] if candidates else None,
            "ambiguous": len(candidates)>1 and abs(candidates[1]["reprojection_rmse_px"]-candidates[0]["reprojection_rmse_px"]) < .25}
    return {"markers": [{"id": m["id"], "face": m["face"], "plant_id": m["plant_id"],
                          "in_frame": m["in_frame"], "front_facing": m["front_facing"],
                          **observations.get(m["id"], {"detected": False, "reason": "not_detected_visibility_not_assumed"})}
                         for m in metadata["markers"]], "unexpected_ids": unexpected, "rejected_candidates": len(rejected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--partial", action="store_true", help="Export completed captures for diagnosis, never label complete")
    args = parser.parse_args()
    root = args.root.resolve()
    def capture_order(path):
        c = json.loads(path.read_text(encoding="utf-8"))["capture"]
        return (path.parent.parent.name, {"front":0,"back":1}[c["face"]],
                {"close":0,"mid":1,"far":2}[c["distance_band"]], c["height_band"])
    paths = sorted(root.glob("scene_*/*/capture.json"),key=capture_order)
    expected_count = json.loads((root/"config.json").read_text(encoding="utf-8"))["capture_count"]
    if not args.partial and len(paths) != expected_count:
        raise ValueError(f"Expected {expected_count} captures, got {len(paths)}")
    if not args.partial:
        projection = json.loads((root/"mask_projection_report.json").read_text(encoding="utf-8"))
        if projection["status"] != "passed":
            raise ValueError("Mask projection check failed")
        for path in paths:
            if projection["capture_sha256"].get(path.relative_to(root).as_posix()) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(f"Missing or stale mask projection check: {path}")
    out = root/("exports_partial" if args.partial else "exports")
    out.mkdir(exist_ok=False)
    for name in ("detection", "monoclass", "previews", "aruco"):
        (out/name).mkdir()
    for name in ("detection", "monoclass"):
        (out/name/"images").mkdir()
        (out/name/"labels").mkdir()
    categories = [{"id": i+1, "name": name, "yolo_class_id": i} for i,name in enumerate(CLASSES)]
    coco = {"info": {"version": VERSION, "annotation_target": "visible_calyx", "agronomic_validation": "pending",
                      "category_id_convention": "COCO 1..4, YOLO 0..3"}, "images": [], "annotations": [], "categories": categories}
    inventory, exclusions, counts, tiles = [], [], Counter(), []
    rgb_tiles=[]
    for image_id, path in enumerate(paths, 1):
        data = json.loads(path.read_text(encoding="utf-8"))
        folder = path.parent
        name = f"{folder.parent.name}_{folder.name}"
        rgb = cv2.imread(str(folder/"rgb.png"))
        mask = cv2.cvtColor(cv2.imread(str(folder/Path(data["mask"]["path"]).name)), cv2.COLOR_BGR2RGB)
        codes = (mask[:,:,0].astype(np.uint32)<<16) | (mask[:,:,1].astype(np.uint32)<<8) | mask[:,:,2]
        height,width = mask.shape[:2]
        if rgb.shape[:2] != (height,width):
            raise ValueError("RGB/mask dimensions differ")
        preview, segment = rgb.copy(), rgb.copy()
        for directory in ("detection", "monoclass"):
            target_image = out/directory/"images"/f"{name}.png"
            try:
                os.link(folder/"rgb.png",target_image)
            except OSError:
                shutil.copy2(folder/"rgb.png",target_image)
        image_record = {"id": image_id, "file_name": f"detection/images/{name}.png",
                        "width": width, "height": height, "scene_id": data["scene_id"]}
        coco["images"].append(image_record)
        centers = {v["instance_id"]:v for v in data["geometry"]["capachos"]}
        yolo, mono, instance_records = [], [], []
        palette = data["mask"]["palette"]
        if len(set(tuple(c) for c in palette.values())) != len(palette):
            raise ValueError("Aliased instance palette")
        for identifier, record in data["mask"]["items"].items():
            instance_id = record.get("instance_id")
            if identifier == "0" or instance_id not in centers:
                continue
            if not record.get("visible_pixels", 0):
                exclusions.append({"image_id":image_id,"instance_id":instance_id,"reason":"no_visible_pixels"})
                continue
            color = palette[identifier]
            binary = codes == ((color[0]<<16) | (color[1]<<8) | color[2])
            ys,xs = np.nonzero(binary)
            pixels = int(len(xs))
            if pixels != record["visible_pixels"]:
                raise ValueError(f"Mask pixel count mismatch for {instance_id}")
            if not pixels:
                exclusions.append({"image_id":image_id,"instance_id":instance_id,"reason":"no_visible_pixels"})
                continue
            x,y = int(xs.min()),int(ys.min())
            w,h = int(xs.max())-x+1,int(ys.max())-y+1
            if pixels < 24 or min(w,h) < 6:
                exclusions.append({"image_id":image_id,"instance_id":instance_id,"reason":"below_shared_size_threshold","visible_pixels":pixels})
                continue
            grade = centers[instance_id]["synthetic_reference_grade"]
            cls = class_for_grade(grade)
            annotation = {"id": len(coco["annotations"])+1, "image_id":image_id, "category_id":cls+1,
                "bbox":[x,y,w,h], "area":pixels, "iscrowd":0, "segmentation":numpy_rle(binary),
                "instance_id":instance_id, "synthetic_reference_grade":grade,
                "mask_instance_id":int(identifier),
                "class_source":"simulated_grade_user_grouping", "agronomic_maturity":None,
                "human_validation":"pending", "truncated":x==0 or y==0 or x+w==width or y+h==height}
            if sum(annotation["segmentation"]["counts"][1::2]) != pixels:
                raise ValueError("RLE area differs from master mask")
            coco["annotations"].append(annotation)
            values = f"{(x+w/2)/width:.8f} {(y+h/2)/height:.8f} {w/width:.8f} {h/height:.8f}"
            yolo.append(f"{cls} {values}")
            mono.append(f"0 {values}")
            color = ((70,190,60),(30,210,210),(30,130,245),(160,70,180))[cls]
            cv2.rectangle(preview,(x,y),(x+w-1,y+h-1),color,2)
            cv2.putText(preview,CLASSES[cls],(x,max(12,y-3)),cv2.FONT_HERSHEY_SIMPLEX,.4,color,1)
            segment[binary] = (segment[binary]*.45 + np.array(color)*.55).astype(np.uint8)
            counts[CLASSES[cls]] += 1
            scale = min(640/width,640/height)
            instance_records.append({"annotation_id":annotation["id"],"instance_id":instance_id,"class_id":cls,
                                     "bbox_at_640":[x*scale+(640-width*scale)/2,y*scale+(640-height*scale)/2,w*scale,h*scale]})
        for directory, lines in (("detection",yolo),("monoclass",mono)):
            (out/directory/"labels"/f"{name}.txt").write_text("\n".join(lines)+("\n" if lines else ""),encoding="utf-8")
        cv2.imwrite(str(out/"previews"/f"{name}_boxes.jpg"),preview)
        cv2.imwrite(str(out/"previews"/f"{name}_segments.jpg"),segment)
        pose_report = evaluate_aruco(rgb, data["geometry"])
        write(out/"aruco"/f"{name}.json", {"capture":data["capture"], **pose_report})
        aruco_preview = rgb.copy()
        for marker in pose_report["markers"]:
            if not marker.get("detected"):
                continue
            corners = np.array(marker["corners_px"],np.float32).reshape(1,4,2)
            cv2.aruco.drawDetectedMarkers(aruco_preview,[corners],np.array([[marker["id"]]],np.int32))
            if marker.get("selected"):
                pose = marker["selected"]
                cv2.drawFrameAxes(aruco_preview,np.array(data["geometry"]["K"]),np.zeros(5),
                                 np.array(pose["rvec"]),np.array(pose["tvec_m"]),.05,2)
        cv2.imwrite(str(out/"previews"/f"{name}_aruco.jpg"),aruco_preview)
        inventory.append({"image":image_record, "capture":data["capture"],"instances":instance_records,
                          "capture_metadata":path.relative_to(root).as_posix(),
                          "rgb_sha256":hashlib.sha256((folder/"rgb.png").read_bytes()).hexdigest(),
                          "mask_sha256":hashlib.sha256((folder/Path(data["mask"]["path"]).name).read_bytes()).hexdigest()})
        tile = cv2.resize(preview,(320,240))
        cv2.putText(tile,name,(5,18),cv2.FONT_HERSHEY_SIMPLEX,.36,(255,255,255),1)
        tiles.append(tile)
        rgb_tile=cv2.resize(rgb,(320,240))
        cv2.rectangle(rgb_tile,(0,0),(319,24),(20,20,20),-1)
        cv2.putText(rgb_tile,name,(5,18),cv2.FONT_HERSHEY_SIMPLEX,.36,(255,255,255),1)
        rgb_tiles.append(rgb_tile)
        print(f"EXPORT {image_id}/{len(paths)} {name} instances={len(instance_records)}",flush=True)
    write(out/"instances_coco.json",coco)
    detection = {**coco,"annotations":[{k:v for k,v in a.items() if k!="segmentation"} for a in coco["annotations"]]}
    write(out/"detection_coco.json",detection)
    write(out/"manifest.json",inventory)
    write(out/"exclusions.json",exclusions)
    write(out/"dataset_contract.json", {"version":VERSION, "yolo_classes":dict(enumerate(CLASSES)),
        "monoclass_classes":{"0":"calyx"},"split_status":"unassigned_inspection_pilot",
        "group_key":"scene_id", "segmentation_format":"COCO_uncompressed_RLE",
        "mask_source":"capture.json mask.path + palette",
        "paired_instances":True,"agronomic_validation":"pending"})
    audits = {}
    for audit_path in sorted(root.glob("scene_*/mesh_audit.json")):
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audits[audit_path.parent.name] = {key:audit[key] for key in
            ("status","physical_collision_count","clearance_violation_count")}
    physically_valid = len(audits)==4 and all(a["status"]=="valid" for a in audits.values())
    write(out/"summary.json",{"version":VERSION,"capture_count":len(paths),"class_counts":dict(counts),
                             "status":"partial" if args.partial else
                                "technical_export_complete_visual_review_pending" if physically_valid else
                                "inspection_only_physical_review_required",
                             "mesh_audits":audits,"training_eligible":False,
                             "training_status":"not_run","scene_group_split_required":True})
    if tiles:
        while len(tiles)%6:
            tiles.append(np.zeros_like(tiles[0]))
            rgb_tiles.append(np.zeros_like(rgb_tiles[0]))
        cv2.imwrite(str(out/"contact_sheet.jpg"),np.vstack([np.hstack(tiles[i:i+6]) for i in range(0,len(tiles),6)]))
        cv2.imwrite(str(out/"contact_sheet_rgb.jpg"),np.vstack([np.hstack(rgb_tiles[i:i+6]) for i in range(0,len(rgb_tiles),6)]))
    print(out)


if __name__ == "__main__":
    main()
