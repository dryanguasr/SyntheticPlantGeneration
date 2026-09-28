"""Independently verify every exported box/RLE against its retained master mask."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from uchuva_lsystem.sparse_pilot import class_for_grade


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    out = root/"exports"
    coco = read(out/"instances_coco.json")
    boxes = read(out/"detection_coco.json")
    manifest = read(out/"manifest.json")
    expected_count = read(root/"config.json")["capture_count"]
    assert len(manifest)==len(coco["images"])==expected_count
    assert len(boxes["annotations"])==len(coco["annotations"])
    groups = Counter(m["image"]["scene_id"] for m in manifest)
    assert len(groups)==4 and set(groups.values())=={expected_count//4}
    if expected_count == 48:
        combinations = {(face,distance,height) for face in ("front","back")
                        for distance in ("close","mid","far") for height in ("drone","harvester")}
        for scene_id in groups:
            rows = [m for m in manifest if m["image"]["scene_id"]==scene_id]
            assert {(m["capture"]["face"],m["capture"]["distance_band"],m["capture"]["height_band"]) for m in rows}==combinations
            assert len({m["capture"]["target_plant_id"] for m in rows})==1
    annotations = {a["id"]:a for a in coco["annotations"]}
    checked = 0
    scene_class_counts={}
    scene_heights={}
    case_examples={"truncated":[],"disconnected_visible_components":[],"background_plant":[]}
    marker_detection_warnings=[]
    for a,b in zip(coco["annotations"],boxes["annotations"]):
        assert {k:v for k,v in a.items() if k!="segmentation"}==b
    for row in manifest:
        metadata = read(root/row["capture_metadata"])
        folder = (root/row["capture_metadata"]).parent
        assert hashlib.sha256((folder/"rgb.png").read_bytes()).hexdigest()==row["rgb_sha256"]
        assert hashlib.sha256((folder/Path(metadata["mask"]["path"]).name).read_bytes()).hexdigest()==row["mask_sha256"]
        master = cv2.cvtColor(cv2.imread(str(folder/Path(metadata["mask"]["path"]).name)),cv2.COLOR_BGR2RGB)
        codes = (master[:,:,0].astype(np.uint32)<<16) | (master[:,:,1].astype(np.uint32)<<8) | master[:,:,2]
        height,width = master.shape[:2]
        name = Path(row["image"]["file_name"]).stem
        if expected_count == 48:
            pose_report = read(out/"aruco"/f"{name}.json")
            detected = [m for m in pose_report["markers"] if m["detected"]]
            # A wrongly decoded ID is a detector failure, not proof that a
            # printed reverse was rendered. Geometry has an independent ray test.
            inconsistent=[m["id"] for m in detected if not m["front_facing"]]
            if inconsistent:
                marker_detection_warnings.append({"capture":name,"backfacing_ids":inconsistent})
        yolo = [list(map(float,line.split())) for line in (out/"detection"/"labels"/f"{name}.txt").read_text().splitlines()]
        mono = [list(map(float,line.split())) for line in (out/"monoclass"/"labels"/f"{name}.txt").read_text().splitlines()]
        assert len(yolo)==len(mono)==len(row["instances"])
        markers = metadata["geometry"]["markers"]
        capachos={item["instance_id"]:item for item in metadata["geometry"]["capachos"]}
        assert sorted(m["id"] for m in markers)==list(range(72))
        assert all(m["side_m"]==.1 for m in markers)
        if row["capture"]["height_band"]=="harvester":
            assert abs(row["capture"]["height_m"]-.4)<1e-8
        else:
            scene_id=row["image"]["scene_id"]
            if scene_id not in scene_heights:
                payload=read(folder.parent/"input.json")
                geometry=read(folder.parent/"geometry.json")
                scene_heights[scene_id]={plant["plant_id"]:report["height"]/8 for plant,report in zip(
                    payload["scene"]["plant_instances"],geometry["reports"])}
            assert abs(row["capture"]["height_m"]-scene_heights[scene_id][row["capture"]["target_plant_id"]]/2)<1e-6
        for instance, detection, single in zip(row["instances"],yolo,mono):
            annotation = annotations[instance["annotation_id"]]
            assert annotation["instance_id"]==instance["instance_id"]
            cls = class_for_grade(annotation["synthetic_reference_grade"])
            scene_class_counts.setdefault(row["image"]["scene_id"],Counter())[cls]+=1
            assert cls==instance["class_id"]==int(detection[0])==annotation["category_id"]-1
            assert single[0]==0 and single[1:]==detection[1:]
            rle = annotation["segmentation"]
            assert rle["size"]==[height,width] and sum(rle["counts"])==height*width
            decoded = np.repeat((np.arange(len(rle["counts"]))%2).astype(bool),rle["counts"]).reshape((height,width),order="F")
            color = metadata["mask"]["palette"][str(annotation["mask_instance_id"])]
            expected = codes==((color[0]<<16) | (color[1]<<8) | color[2])
            assert np.array_equal(decoded,expected), annotation["instance_id"]
            ys,xs = np.nonzero(decoded)
            box = [int(xs.min()),int(ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)]
            assert box==annotation["bbox"] and len(xs)==annotation["area"]
            x,y,w,h = box
            is_truncated=x==0 or y==0 or x+w==width or y+h==height
            assert annotation["truncated"]==is_truncated
            example={"image":name,"instance_id":annotation["instance_id"]}
            if is_truncated and not case_examples["truncated"]:
                case_examples["truncated"].append(example)
            if capachos[annotation["instance_id"]]["plant_id"]!=row["capture"]["target_plant_id"] and not case_examples["background_plant"]:
                case_examples["background_plant"].append(example)
            if not case_examples["disconnected_visible_components"]:
                components,_=cv2.connectedComponents(decoded[y:y+h,x:x+w].astype(np.uint8),connectivity=8)
                if components>2:
                    case_examples["disconnected_visible_components"].append({**example,"components":components-1})
            np.testing.assert_allclose(detection[1:],[(x+w/2)/width,(y+h/2)/height,w/width,h/height],atol=1e-8,rtol=0)
            checked += 1
        print("VERIFIED",name,len(row["instances"]),flush=True)
    assert set(a["category_id"] for a in annotations.values())=={1,2,3,4}
    assert all(set(counts)=={0,1,2,3} for counts in scene_class_counts.values())
    report = {"status":"passed","captures":expected_count,"scenes":4,"instances_checked":checked,
              "marker_detection_warnings":marker_detection_warnings,
              "scene_class_counts_yolo_ids":scene_class_counts,
              "case_examples":case_examples,
              "exclusion_reasons":dict(Counter(item["reason"] for item in read(out/"exclusions.json"))),
              "checks":"RLE/master pixel equality, boxes, classes, hashes, pairing, groups, ArUco IDs and camera height",
              "physical_acceptance":"separate_mesh_audits_not_overridden"}
    (out/"integrity_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__": main()
