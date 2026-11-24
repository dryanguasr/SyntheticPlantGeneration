"""Prepare train-only references, explicit visual profiles and new calibration trees."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from uchuva_lsystem.appearance_profiles import initial_profiles, component_seed, canonical_hash


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path.exists():
        if read(path) != data:
            raise FileExistsError(f"Preserve previous evidence: {path}")
        return
    path.write_text(content, encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_references(root):
    import cv2
    import numpy as np
    source = REPO / "outputs/union_real_pilot_20261022"
    records = [r for r in read(source / "manifest.json")["records"] if r["status"] == "included"]
    rows = []
    for r in records:
        image, label = source / r["image"], source / r["label"]
        assert sha(image) == r["sha256"] and sha(label) == r["label_sha256"]
        rows.append(dict(source_row=r["source_row"], image=str(image.resolve()), label=str(label.resolve()),
                         image_sha256=r["sha256"], label_sha256=r["label_sha256"],
                         group_id=r["group_id"], split=r["split"], domain="real", file=r["file"]))
    assert Counter(r["split"] for r in rows) == {"train":461, "val":88, "test":94}
    write_new(root / "real_manifest.json", {"records":rows, "test_status":"development_previously_consulted"})
    train = {r["file"]:r for r in rows if r["split"] == "train"}
    raw = REPO / "outputs/datasets/union_anotadas_20261021_v1/source_latest.ndjson"
    annotations = {}
    with raw.open(encoding="utf-8") as stream:
        for line in stream:
            r = json.loads(line)
            if r.get("file") in train: annotations[r["file"]] = r
    instances, backgrounds = [], []
    for index, (filename, row) in enumerate(train.items()):
        image = cv2.imread(row["image"])
        if image is None: raise ValueError(row["image"])
        h, w = image.shape[:2]; scale = min(1., 640 / max(w,h))
        small = cv2.resize(image, (round(w*scale),round(h*scale)))[:,:,::-1]
        hh, ww = small.shape[:2]; union = np.zeros((hh,ww),np.uint8)
        segments = annotations[filename]["annotations"]["segments"]
        labels = Path(row["label"]).read_text().splitlines()
        assert len(segments) == len(labels), (filename, len(segments),len(labels))
        for number, segment in enumerate(segments):
            class_id = int(segment[0]); coords = np.asarray(segment[1:]).reshape(-1,2)
            mask = np.zeros((hh,ww),np.uint8)
            cv2.fillPoly(mask,[np.rint(coords*[ww,hh]).astype(np.int32)],1)
            union |= mask
            pixels = small[mask.astype(bool)].astype(float)/255
            if not len(pixels): continue
            lum = pixels @ np.array([.2126,.7152,.0722])
            saturation = (pixels.max(1)-pixels.min(1))/np.maximum(pixels.max(1),1e-6)
            lo,hi = coords.min(0),coords.max(0)
            instances.append(dict(source_row=row["source_row"],image=row["image"],group_id=row["group_id"],
                instance_index=number,class_id=class_id,bbox=[float(lo[0]*w),float(lo[1]*h),float((hi[0]-lo[0])*w),float((hi[1]-lo[1])*h)],
                min_side_960=float(min((hi-lo)*[w,h])*960/max(w,h)),
                srgb_median=np.median(pixels,axis=0).tolist(), luminance_median=float(np.median(lum)),
                luminance_p10=float(np.quantile(lum,.1)),luminance_p90=float(np.quantile(lum,.9)),
                saturation_median=float(np.median(saturation)),contrast=float(np.std(lum)),
                clipped_dark_fraction=float((lum<.02).mean()),clipped_light_fraction=float((lum>.98).mean()),
                measurement="human polygon rasterized at longest side <=640; camera sRGB, not reflectance"))
        outside = small[~union.astype(bool)].astype(float)/255
        backgrounds.append(dict(source_row=row["source_row"],luminance_median=float(np.median(outside@np.array([.2126,.7152,.0722]))) if len(outside) else None,
                                measurement="outside annotated capachos; includes leaves and context"))
        if index % 75 == 0: print("REFERENCE",index,"/",len(train),flush=True)
    summary={str(c):{key:np.quantile([r[key] for r in instances if r["class_id"]==c],[.1,.5,.9]).tolist()
                    for key in ("min_side_960","luminance_median","saturation_median","contrast")} for c in range(3)}
    selection=[]; used=set()
    for c in range(3):
        choices=[r for r in instances if r["class_id"]==c and r["min_side_960"]>=32]
        choices.sort(key=lambda r:r["luminance_median"])
        for label,q in [("oscura",.1),("central",.5),("clara",.9)]:
            target=choices[round(q*(len(choices)-1))]
            selection.append(dict(target,review_role=label));used.add((target['source_row'],target['instance_index']))
        # A small, low-contrast example is a review candidate, not a relabeling decision.
        target=min((r for r in choices if (r['source_row'],r['instance_index']) not in used),key=lambda r:r['contrast'])
        selection.append(dict(target,review_role="bajo contraste; revisar ambigüedad"))
    write_new(root/"references/real_instances.json",{"instances":instances,"backgrounds":backgrounds,"by_class":summary,
        "selection":selection,"source_split":"train","source_sha256":sha(raw),"test_images_read":False,
        "note":"Split follows the cleaned union manifest, not the original filename directory."})
    write_new(root/"profiles.json",initial_profiles())
    asset_root=REPO/"assets/textures/current"
    manifest=read(asset_root/"manifest.json")
    assets={str(p.resolve()):sha(p) for p in sorted(asset_root.glob("*.png"))}
    assert assets
    write_new(root/"texture_assets.json",{"manifest":str(asset_root/"manifest.json"),"manifest_sha256":sha(asset_root/"manifest.json"),
                                         "files":assets,"generator_version":manifest.get("version",manifest.get("generator_version")),"fallback_allowed":False})


def prepare_trees(root, round_name="round_01"):
    from uchuva_lsystem.grammar import generate_morphology_tree
    from uchuva_lsystem.validation import validate_morphology_tree
    from uchuva_lsystem.appearance_profiles import CLASSES
    from uchuva_lsystem.parameters import get_morphology_parameters
    if Path(round_name).name!=round_name:raise ValueError('Round must be a single directory name')
    profiles=read(root/'profiles.json')
    parameters=get_morphology_parameters(profiles['plant_preset'])
    if 'plant_parameters_sha256' in profiles:
        assert canonical_hash(parameters)==profiles['plant_parameters_sha256'],'Plant profile changed'
    round_dir=root/'calibration'/round_name
    write_new(round_dir/'profiles.json',profiles)
    refs=read(root/"references/real_instances.json"); counts=Counter(r['class_id'] for r in refs['instances'])
    total=sum(counts.values()); thresholds=[counts[0]/total,(counts[0]+counts[1])/total]
    records=[]
    def axes(items):
        for a in items:
            yield a
            yield from axes(a.child_axes)
    for index in range(4):
        seed=2026102600+index
        plant=generate_morphology_tree(seed,preset_name=profiles['plant_preset'],phenology_model="literature_cohort_v1")
        assigned=[]
        for axis in axes(plant.axes):
            for node in axis.nodes:
                u=node.reproductive_unit
                if u is None or u.calyx is None:continue
                number=component_seed(seed,"appearance",u.id)/2**32
                c=0 if number<thresholds[0] else 1 if number<thresholds[1] else 2
                grade=[3,5,6][c]
                u.synthetic_reference_grade=grade
                u.calyx.material_key=["calyx_transition_v1","calyx_straw_v1","calyx_dry_v1"][c]
                u.provenance["appearance_pilot"]={"class_id":c,"class_name":CLASSES[c],"basis":"synthetic appearance assignment", "human_validation":"pending","agronomic_maturity":None}
                assigned.append(dict(unit_id=u.id,class_id=c,grade=grade))
        if not assigned:raise ValueError(f"Calibration plant {seed} has no calyx; preserve and diagnose")
        path=round_dir/f"plants/plant_{index:02d}.json"
        write_new(path,plant.to_dict());validation=validate_morphology_tree(plant,stage="generated")
        write_new(path.with_name(path.stem+"_validation.json"),validation)
        records.append(dict(index=index,seed=seed,path=str(path.resolve()),sha256=sha(path),assignments=assigned,
                            parameter_hash=plant.metadata.get('effective_parameters_sha256')))
    write_new(round_dir/"plants.json",{"plants":records,"training_eligible":False,"review":"pending"})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--stage',choices=['references','trees'],required=True)
    p.add_argument('--round',default='round_01')
    a=p.parse_args()
    if a.stage=='references':prepare_references(a.root.resolve())
    else:prepare_trees(a.root.resolve(),a.round)
