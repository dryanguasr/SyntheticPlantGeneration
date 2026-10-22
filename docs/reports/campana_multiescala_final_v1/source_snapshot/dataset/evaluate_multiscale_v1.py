"""Resumable full-view native-raster evaluation, derived from frozen evaluate_native.py.

Inference receives RGB only. Original rasters enter the private evaluator after
prediction persistence. Both checkpoints use exactly the same 640/448 pipeline.
"""
import argparse
import collections
import datetime
import gc
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
import time

import numpy as np
import psutil
from PIL import Image, ImageDraw

VERSION = "multiscale-full-view-evaluator/1"
CLASSES = ["pintona", "madura", "sobremadura"]
COLORS = [(70, 200, 100), (255, 188, 35), (175, 90, 215)]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def memory_guard(minimum=3.0):
    free = psutil.virtual_memory().available / 2**30
    if free < minimum:
        raise RuntimeError(f"RAM early stop: {free:.3f} GiB free < {minimum}")
    return free


def tile_boxes(width, height, size=640, stride=448):
    if min(width, height) < size:
        raise ValueError("Current protocol requires native image dimensions >=640")
    def axis(limit):
        return sorted(set([*range(0, limit-size+1, stride), limit-size]))
    return [[x, y, x+size, y+size] for y in axis(height) for x in axis(width)]


def compact(mask, label, x=0, y=0):
    yy, xx = np.nonzero(mask)
    if not len(xx):
        return None
    x1, x2, y1, y2 = int(xx.min()), int(xx.max())+1, int(yy.min()), int(yy.max())+1
    return dict(label=dict(label), bbox=[x+x1, y+y1, x+x2, y+y2],
                area=len(xx), mask=mask[y1:y2, x1:x2].astype(bool, copy=True))


def intersection(a, b):
    ax, ay, az, aw = a["bbox"]; bx, by, bz, bw = b["bbox"]
    x1, y1, x2, y2 = max(ax,bx), max(ay,by), min(az,bz), min(aw,bw)
    if x1 >= x2 or y1 >= y2:
        return 0
    return int(np.logical_and(a["mask"][y1-ay:y2-ay,x1-ax:x2-ax],
                              b["mask"][y1-by:y2-by,x1-bx:x2-bx]).sum())


def deduplicate(candidates):
    """Same class-agnostic exact mask NMS as frozen field_roi_patch_pilot.py."""
    kept = []
    for item in sorted(candidates, key=lambda r: -r["label"]["confidence"]):
        duplicate = False
        for previous in kept:
            n = intersection(item, previous)
            if n/max(1,item["area"]+previous["area"]-n) > .45 or n/max(1,min(item["area"],previous["area"])) > .75:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return kept


def save_predictions(folder, stem, predictions, binding):
    """Commit data first and JSON last; only paired/hash-verified files resume."""
    folder.mkdir(parents=True, exist_ok=True)
    binary = folder / (stem + ".npz")
    temporary = binary.with_suffix(".npz.tmp")
    metadata, arrays, offset = [], [], 0
    for item in predictions:
        packed = np.packbits(item["mask"].ravel())
        arrays.append(packed)
        metadata.append(dict(**item["label"], bbox=item["bbox"], area=item["area"],
                             offset=offset, packed_bytes=len(packed)))
        offset += len(packed)
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, packed=np.concatenate(arrays) if arrays else np.zeros(0, np.uint8))
    temporary.replace(binary)
    record = dict(binding=binding, predictions=metadata, binary_sha256=sha(binary),
                  inference_uses_ground_truth=False)
    write(folder / (stem + ".json"), record)
    return record


def load_predictions(folder, stem, binding):
    record = read(folder / (stem + ".json"))
    if record["binding"] != binding:
        raise ValueError("Prediction provenance/config mismatch: " + stem)
    binary = folder / (stem + ".npz")
    if sha(binary) != record["binary_sha256"]:
        raise ValueError("Prediction payload hash mismatch: " + stem)
    with np.load(binary, allow_pickle=False) as archive:
        packed = archive["packed"]
    result = []
    for item in record["predictions"]:
        x1,y1,x2,y2 = item["bbox"]; count = (y2-y1)*(x2-x1)
        mask = np.unpackbits(packed[item["offset"]:item["offset"]+item["packed_bytes"]], count=count).reshape(y2-y1,x2-x1).astype(bool)
        if int(mask.sum()) != item["area"]:
            raise ValueError("Prediction area mismatch: " + stem)
        result.append(dict(label={k:v for k,v in item.items() if k not in ("bbox","area","offset","packed_bytes")},
                           bbox=item["bbox"], area=item["area"], mask=mask))
    return result


def summarize(cm):
    tp = int(np.trace(cm[:3,:3])); fp = int(cm[:,:3].sum())-tp; fn = int(cm[:3,:].sum())-tp
    per_class = {}
    for cls, name in enumerate(CLASSES):
        ctp=int(cm[cls,cls]);cfp=int(cm[:,cls].sum())-ctp;cfn=int(cm[cls,:].sum())-ctp
        per_class[name]=dict(tp=ctp,fp=cfp,fn=cfn,precision=ctp/max(1,ctp+cfp),
                            recall=ctp/max(1,ctp+cfn),f1=2*ctp/max(1,2*ctp+cfp+cfn))
    return dict(tp=tp,fp=fp,fn=fn,precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn),
                f1=2*tp/max(1,2*tp+fp+fn),confusion=cm.tolist(),
                rows="truth",columns="prediction",classes=CLASSES+["background/unmatched"],per_class=per_class)


def confusion(native, truth, predictions, eligible_only=False):
    eligible = {i for i,t in enumerate(truth) if not eligible_only or
                (t["pixels"] >= 100 and min(t["bbox"][2]-t["bbox"][0],t["bbox"][3]-t["bbox"][1]) >= 8)}
    remaining = set(eligible); small = set(range(len(truth)))-eligible
    cm = np.zeros((4,4),dtype=np.int64); ignored = 0
    for prediction in sorted(predictions, key=lambda p:-p["label"]["confidence"]):
        x1,y1,x2,y2 = prediction["bbox"]
        values = native[y1:y2,x1:x2][prediction["mask"]]
        histogram = np.bincount(values.astype(np.int64), minlength=max([t["mask_id"] for t in truth],default=0)+1)
        def iou(k):
            t=truth[k]; n=int(histogram[t["mask_id"]]); return n/max(1,prediction["area"]+t["pixels"]-n)
        pairs = [(iou(k), k) for k in remaining]
        if pairs and max(pairs)[0] >= .5:
            _,k=max(pairs);remaining.remove(k);cm[truth[k]["class_id"],prediction["label"]["class_id"]]+=1
        elif small and max(iou(k) for k in small) >= .5:
            ignored += 1
        else:
            cm[3,prediction["label"]["class_id"]]+=1
    for k in remaining:
        cm[truth[k]["class_id"],3]+=1
    return dict(**summarize(cm),ignored_small_predictions=ignored,truth_total=len(truth),
                truth_in_scope=len(eligible),truth_excluded_small=len(small))


def infer_rgb(model, rgb, torch):
    """RGB-only; no row, instance identity, camera truth or annotation inputs."""
    candidates = []; minimum = memory_guard()
    for tile, (x1,y1,x2,y2) in enumerate(tile_boxes(rgb.shape[1],rgb.shape[0])):
        minimum = min(minimum,memory_guard())
        result = model.predict(rgb[y1:y2,x1:x2,::-1].copy(),imgsz=960,rect=False,
            conf=.25,iou=.7,retina_masks=True,max_det=300,device=0,verbose=False,
            augment=False,agnostic_nms=False)[0]
        if result.masks is not None:
            masks = result.masks.data.cpu().numpy()
            if masks.shape[1:] != (y2-y1,x2-x1):
                raise ValueError("retina_masks did not preserve native tile dimensions")
            for mask,cls,score in zip(masks,result.boxes.cls.cpu().tolist(),result.boxes.conf.cpu().tolist()):
                item=compact(mask.astype(bool),dict(class_id=int(cls),confidence=float(score),tile=tile),x1,y1)
                if item: candidates.append(item)
            del masks
        del result
        torch.cuda.empty_cache();minimum=min(minimum,memory_guard())
    return deduplicate(candidates),minimum


def preflight(root, protocol):
    """No GPU imports until completed training and bound provenance pass."""
    training = root/"training_runs/training"
    execution = read(training/"execution_summary.json")
    updates = [json.loads(line) for line in (training/"parameter_updates.jsonl").read_text().splitlines()]
    expected = read(root/"protocol.json")["training_epochs"]
    if len(updates) != expected or updates[-1]["epoch"] != expected or execution["optimizer_steps"] <= 0:
        raise ValueError("Training has not completed the predeclared epochs with real optimizer updates")
    if not all(u["epoch_steps"] > 0 and u["changed_tensors"] > 0 for u in updates):
        raise ValueError("Missing real parameter update in at least one epoch")
    weights = {"reference": Path(protocol["reference_weight"]), "new": training/"weights/last.pt"}
    weight_hashes = {k:sha(v) for k,v in weights.items()}
    if weight_hashes["reference"] != protocol["reference_sha256"]:
        raise ValueError("Frozen reference checkpoint changed")
    if weight_hashes["new"] == weight_hashes["reference"]:
        raise ValueError("New and reference weights are byte-identical")
    for name,expected_hash in protocol["bound_files"].items():
        if sha(root/name) != expected_hash:
            raise ValueError("Evaluation source/contract changed: " + name)
    audit=read(root/"split_integrity_audit_v1.json")
    if audit["status"] != "PASS" or audit["errors"]:
        raise ValueError("Split audit not passed")
    return weights,weight_hashes


def overlay(rgb, items, title):
    array=rgb.copy();locations=[]
    for item in items:
        x1,y1,x2,y2=item["bbox"];mask=item["mask"];color=np.asarray(COLORS[item["label"]["class_id"]])
        region=array[y1:y2,x1:x2];region[mask]=(region[mask]*.55+color*.45).astype(np.uint8)
        locations.append((x1,y1,item["label"]))
    image=Image.fromarray(array);draw=ImageDraw.Draw(image)
    for x,y,label in locations:
        text=str(label["class_id"])
        if "confidence" in label:text+=f":{label['confidence']:.2f}"
        draw.text((x,y),text,fill="white",stroke_width=1,stroke_fill="black")
    final=Image.new("RGB",(image.width,image.height+32),(25,32,40));final.paste(image,(0,32))
    ImageDraw.Draw(final).text((12,9),title,fill="white")
    return final


def ground_truth_items(native, truth):
    result=[]
    for item in truth:
        x1,y1,x2,y2=item["bbox"]
        result.append(dict(label=dict(class_id=item["class_id"]),bbox=item["bbox"],
                           mask=native[y1:y2,x1:x2]==item["mask_id"],area=item["pixels"]))
    return result


def report(root,protocol,run_binding,rows):
    output=root/"native_evaluation_v1";aggregates={};records={}
    for model in ("reference","new"):
        records[model]={}
        aggregates[model]={}
        for row in rows:
            stem=Path(row["image"]).stem;prediction_dir=output/model/"predictions"
            binding=dict(run_binding=run_binding,model=model,rgb_sha256=row["rgb_sha256"],image=row["image"])
            predictions=load_predictions(prediction_dir,stem,binding)
            native=np.asarray(Image.open(root/"dataset"/row["mask"]))
            if sha(root/"dataset"/row["mask"])!=row["raster_sha256"]:raise ValueError("Truth mask changed")
            metrics={mode:confusion(native,row["instances"],predictions,mode=="eligible") for mode in ("all","eligible")}
            record=dict(image=row["image"],split=row["split"],distance_bin=row["camera_sample"]["distance_bin"],
                        native_mask_sha256=row["raster_sha256"],metrics=metrics,predictions=len(predictions))
            records[model][row["image"]]=record
            write(output/model/"metrics"/(stem+".json"),record)
        for split in ("val","test"):
            aggregates[model][split]={}
            for distance in ("all_distances","near","middle","far"):
                subset=[r for r in records[model].values() if r["split"]==split and (distance=="all_distances" or r["distance_bin"]==distance)]
                aggregates[model][split][distance]={}
                for mode in ("all","eligible"):
                    cm=sum((np.asarray(r["metrics"][mode]["confusion"]) for r in subset),np.zeros((4,4),dtype=np.int64))
                    aggregates[model][split][distance][mode]=dict(**summarize(cm),images=len(subset),
                        ignored_small_predictions=sum(r["metrics"][mode]["ignored_small_predictions"] for r in subset),
                        truth_total=sum(r["metrics"][mode]["truth_total"] for r in subset),
                        truth_in_scope=sum(r["metrics"][mode]["truth_in_scope"] for r in subset),
                        truth_excluded_small=sum(r["metrics"][mode]["truth_excluded_small"] for r in subset))
    write(output/"summary.json",dict(version=VERSION,run_binding=run_binding,models=aggregates,
        limitations=protocol["limitations"],complete=True))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matrices=[]
    for split in ("val","test"):
        for mode in ("all","eligible"):
            fig,axes=plt.subplots(2,4,figsize=(19,10))
            for ri,model in enumerate(("reference","new")):
                for ci,distance in enumerate(("all_distances","near","middle","far")):
                    ax=axes[ri,ci];cm=np.asarray(aggregates[model][split][distance][mode]["confusion"])
                    ax.imshow(cm,cmap="Blues");ax.set_title(f"{model} / {distance}")
                    ax.set_xticks(range(4),CLASSES+["sin pareja"],rotation=35,ha="right")
                    ax.set_yticks(range(4),CLASSES+["sin pareja"])
                    ax.set_xlabel("Predicción");ax.set_ylabel("Verdad")
                    for y in range(4):
                        for x in range(4):ax.text(x,y,str(cm[y,x]),ha="center",va="center",color="white" if cm[y,x]>cm.max()/2 else "black")
            fig.suptitle(f"{split} / {mode}: vistas completas, máscaras nativas, conf .25 / IoU .5")
            fig.tight_layout();name=f"confusion_{split}_{mode}.png";fig.savefig(output/name,dpi=130);plt.close(fig);matrices.append(name)
    by_image={r["image"]:r for r in rows};previews=[]
    for image in protocol["representative_images"]:
        row=by_image[image];stem=Path(image).stem;rgb=np.asarray(Image.open(root/"dataset"/image).convert("RGB"))
        native=np.asarray(Image.open(root/"dataset"/row["mask"]))
        panels=[overlay(rgb,ground_truth_items(native,row["instances"]),"Verdad: máscaras raster originales")]
        for model in ("reference","new"):
            binding=dict(run_binding=run_binding,model=model,rgb_sha256=row["rgb_sha256"],image=image)
            predictions=load_predictions(output/model/"predictions",stem,binding)
            panels.append(overlay(rgb,predictions,model+" — misma inferencia 640/448"))
        combined=Image.new("RGB",(sum(p.width for p in panels),panels[0].height))
        x=0
        for panel in panels:combined.paste(panel,(x,0));x+=panel.width
        relative="examples/"+stem+".jpg";(output/"examples").mkdir(exist_ok=True)
        combined.save(output/relative,quality=94);previews.append(dict(image=image,preview=relative,split=row["split"],distance=row["camera_sample"]["distance_bin"]))
    write(output/"representative_examples.json",dict(selection="Predeclared image order, independent of predictions and test performance",examples=previews))
    table=['<h2>Métricas comparables</h2><table><thead><tr><th>Partición</th><th>Distancia</th><th>Alcance</th><th>P ref.</th><th>R ref.</th><th>F1 ref.</th><th>P nuevo</th><th>R nuevo</th><th>F1 nuevo</th></tr></thead><tbody>']
    for split in ("val","test"):
        for distance in ("all_distances","near","middle","far"):
            for mode in ("all","eligible"):
                values=[f"{100*aggregates[model][split][distance][mode][metric]:.2f}%" for model in ("reference","new") for metric in ("precision","recall","f1")]
                table.append('<tr>'+''.join('<td>'+v+'</td>' for v in [split,distance,mode]+values)+'</tr>')
    table.append('</tbody></table>')
    page=['<meta charset="utf-8"><title>Comparación multiescala</title><style>body{background:#18232b;color:white;font:16px Arial;margin:24px}img{width:100%;height:auto}pre{white-space:pre-wrap}a{color:#8ed2ff}table{border-collapse:collapse}td,th{padding:9px;border:1px solid #526270}td{text-align:right}tr:nth-child(even){background:#243541}</style>',
          '<h1>Referencia congelada frente al modelo multiescala</h1><p>Misma inferencia640/stride448, entrada960, confianza0,25 e IoU nativo0,5. Prueba de desarrollo históricamente inspeccionada. Las columnas de ejemplos contienen verdad original, referencia y nuevo modelo; vistas completas sin seleccionar esquinas.</p>',
          '<p>Las escalas corresponden a la distancia cámara–punto de mira del encuadre; los vecinos pueden estar a otras distancias. Eligible: al menos100píxeles visibles y lado mínimo8; criterio de ingeniería, no límite universal YOLO. Se reportan también omisiones pequeñas y cobertura.</p>',
          '<p>Máximo300detecciones por parche en ambos modelos. Hay parches con más de300objetos verdaderos; este techo puede limitar recuperación en escenas densas. Se conserva predeclarado, sin ajustarlo usando prueba.</p>',
          ''.join(table),'<details><summary>Métricas completas, por clase y cobertura</summary><pre>'+html.escape(json.dumps(aggregates,indent=2))+'</pre></details>']
    for name in matrices:page.append(f'<a href="{name}"><img src="{name}" loading="lazy"></a>')
    for item in previews:page.append('<h2>'+html.escape(item["image"])+'</h2><a href="'+item["preview"]+'"><img src="'+item["preview"]+'" loading="lazy"></a>')
    (output/"comparison.html").write_text("\n".join(page),encoding="utf-8")
    write(output/"state.json",dict(stage="comparison_complete",pid=None,models=2,images_per_model=len(rows),report="comparison.html",scientific_promotion=False))


def cpu_test(root):
    native=np.zeros((30,40),np.uint16);native[2:14,3:15]=1;native[20:22,25:27]=2
    truth=[dict(mask_id=1,class_id=0,pixels=144,bbox=[3,2,15,14]),dict(mask_id=2,class_id=2,pixels=4,bbox=[25,20,27,22])]
    correct=compact(native==1,dict(class_id=0,confidence=.9,tile=0))
    wrong=compact(native==1,dict(class_id=1,confidence=.9,tile=0))
    tiny=compact(native==2,dict(class_id=2,confidence=.8,tile=0))
    assert confusion(native,truth,[correct,tiny])["tp"]==2
    a=confusion(native,truth,[wrong,tiny]);assert (a["tp"],a["fp"],a["fn"])==(1,1,1)
    a=confusion(native,truth,[correct,tiny],True);assert (a["tp"],a["ignored_small_predictions"],a["truth_excluded_small"])==(1,1,1)
    a=confusion(native,truth,[],True);assert (a["tp"],a["fn"])==(0,1)
    assert len(deduplicate([correct,wrong,tiny]))==2
    assert tile_boxes(1280,720)==[[0,0,640,640],[448,0,1088,640],[640,0,1280,640],[0,80,640,720],[448,80,1088,720],[640,80,1280,720]]
    # Load only the pure frozen NMS function: no Ultralytics/GPU import side effects.
    import ast
    frozen=root.parent/"frozen_field_pilot_20261019/frozen/scripts/field_roi_patch_pilot.py"
    tree=ast.parse(frozen.read_text(encoding="utf-8"))
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="deduplicate")
    namespace={"np":np};exec(compile(ast.Module(body=[function],type_ignores=[]),str(frozen),"exec"),namespace)
    rng=np.random.default_rng(640448);candidates=[];full_candidates=[]
    for i in range(24):
        mask=np.zeros((30,40),bool);x,y=int(rng.integers(0,25)),int(rng.integers(0,15));mask[y:y+12,x:x+12]=True
        label=dict(class_id=i%3,confidence=float(rng.random()),tile=i)
        candidates.append(compact(mask,label));full_candidates.append((mask,label))
    expected=[label["tile"] for mask,label in namespace["deduplicate"](full_candidates)]
    assert expected==[item["label"]["tile"] for item in deduplicate(candidates)]
    with tempfile.TemporaryDirectory(prefix="multiscale_eval_cpu_", dir=root) as temp:
        folder=Path(temp).resolve()
        assert folder.is_relative_to(root.resolve()) and folder.name.startswith("multiscale_eval_cpu_")
        binding=dict(cpu_test=True,model="dummy",rgb_sha256="dummy")
        save_predictions(folder,"test",[correct,tiny],binding);restored=load_predictions(folder,"test",binding)
        assert all(np.array_equal(a["mask"],b["mask"]) and a["bbox"]==b["bbox"] for a,b in zip([correct,tiny],restored))
        try:load_predictions(folder,"test",dict(cpu_test=False))
        except ValueError:pass
        else:raise AssertionError("Mismatched cache accepted")
        save_predictions(folder,"empty",[],binding);assert load_predictions(folder,"empty",binding)==[]
        payload=folder/"test.npz";payload.write_bytes(payload.read_bytes()+b"corrupt")
        try:load_predictions(folder,"test",binding)
        except ValueError:pass
        else:raise AssertionError("Corrupt cache accepted")
        overlay(np.zeros((30,40,3),np.uint8),[correct,tiny],"dummy").save(folder/"preview.png")
        # End-to-end CPU report fixture: six tiny synthetic views, no real model.
        fixture=folder/"fixture";(fixture/"dataset").mkdir(parents=True)
        rows=[];run_binding=dict(cpu_fixture=True);preview_images=[]
        for split in ("val","test"):
            for distance in ("near","middle","far"):
                stem=split+"_"+distance;image=stem+".png";mask_name=stem+"_mask.png"
                Image.fromarray(np.zeros((30,40,3),np.uint8)).save(fixture/"dataset"/image)
                Image.fromarray(native).save(fixture/"dataset"/mask_name)
                row=dict(image=image,mask=mask_name,split=split,camera_sample=dict(distance_bin=distance),
                         instances=truth,rgb_sha256=sha(fixture/"dataset"/image),raster_sha256=sha(fixture/"dataset"/mask_name))
                rows.append(row);preview_images.append(image)
                for model,values in (("reference",[wrong,tiny]),("new",[correct,tiny])):
                    binding=dict(run_binding=run_binding,model=model,rgb_sha256=row["rgb_sha256"],image=image)
                    save_predictions(fixture/"native_evaluation_v1"/model/"predictions",stem,values,binding)
        report(fixture,dict(representative_images=preview_images,limitations=["CPU dummy fixture, not model results"]),run_binding,rows)
        result=read(fixture/"native_evaluation_v1/summary.json")
        assert result["models"]["new"]["test"]["all_distances"]["all"]["tp"]==6
        assert result["models"]["reference"]["test"]["all_distances"]["all"]["fp"]==3
        assert len(list((fixture/"native_evaluation_v1").glob("confusion_*.png")))==4
        assert (fixture/"native_evaluation_v1/comparison.html").exists()
    result=dict(passed=True,version=VERSION,tests=["perfect masks", "wrong class is FP+FN", "eligible small ignore", "missed eligible object", "class-agnostic NMS", "compact NMS agrees with frozen implementation", "six full-frame tiles", "cache roundtrip", "cache binding rejection", "payload corruption rejection", "empty predictions", "overlay without GPU", "complete CPU fixture report with strata/matrices/examples"],
                gpu_imported=False,evaluator_sha256=sha(Path(__file__)),protocol_sha256=sha(root/"evaluation_protocol_v1.json"))
    write(root/"evaluation_cpu_check_v1.json",result);print(json.dumps(result),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument("--stage",choices=("all","infer","report","cpu-test"),default="all")
    parser.add_argument("--model",choices=("both","reference","new"),default="both")
    parser.add_argument("--limit-images",type=int,default=0,help="Bound new inferences for resumable jobs; default all")
    args=parser.parse_args();root=args.root.resolve()
    if args.stage=="cpu-test":cpu_test(root);return
    protocol=read(root/"evaluation_protocol_v1.json");weights,weight_hashes=preflight(root,protocol)
    rows=[r for r in read(root/"dataset/raster_manifest.json")["images"] if r["split"] in ("val","test")]
    if [r["image"] for r in rows]!=protocol["evaluation_images"]:raise ValueError("Evaluation view set changed")
    output=root/"native_evaluation_v1";output.mkdir(exist_ok=True)
    run_binding=dict(evaluator_sha256=sha(Path(__file__)),protocol_sha256=sha(root/"evaluation_protocol_v1.json"),
                     manifest_sha256=sha(root/"dataset/raster_manifest.json"),weights=weight_hashes)
    identity=output/"run_binding.json"
    if identity.exists() and read(identity)!=run_binding:raise ValueError("Existing evaluation bindings changed; preserve old outputs")
    write(identity,run_binding)
    lock=output/"evaluation.lock"
    if lock.exists():
        old=read(lock)
        if psutil.pid_exists(old["pid"]):raise RuntimeError("Evaluator PID already exists; inspect identity before recovery")
        lock.rename(output/("stale_lock_"+str(time.time_ns())+".json"))
    with lock.open("x") as stream:json.dump(dict(pid=os.getpid(),created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),stream)
    try:
        if args.stage in ("all","infer"):
            import torch
            from ultralytics import YOLO
            torch.set_num_threads(4)
            new_count=0
            for name in ("reference","new") if args.model=="both" else (args.model,):
                model=None;folder=output/name/"predictions"
                for row in rows:
                    stem=Path(row["image"]).stem;binding=dict(run_binding=run_binding,model=name,rgb_sha256=row["rgb_sha256"],image=row["image"])
                    rgb_path=root/"dataset"/row["image"]
                    if sha(rgb_path)!=row["rgb_sha256"]:raise ValueError("RGB source changed")
                    if (folder/(stem+".json")).exists():load_predictions(folder,stem,binding);continue
                    if model is None:
                        memory_guard(6.5);model=YOLO(weights[name]);assert list(model.names.values())==CLASSES
                    rgb=np.asarray(Image.open(rgb_path).convert("RGB"));predictions,min_free=infer_rgb(model,rgb,torch)
                    save_predictions(folder,stem,predictions,binding);new_count+=1
                    write(output/"state.json",dict(stage="infer",pid=os.getpid(),model=name,image=row["image"],
                        completed_model=len(list(folder.glob("*.json"))),planned_model=len(rows),min_free_host_gib=min_free))
                    print(name,stem,len(predictions),flush=True);del predictions,rgb;gc.collect()
                    if args.limit_images and new_count>=args.limit_images:return
                if model is not None:del model;gc.collect();torch.cuda.empty_cache()
        if args.stage in ("all","report"):
            if args.model!="both":raise ValueError("Combined report requires --model both")
            report(root,protocol,run_binding,rows)
    finally:
        lock.unlink(missing_ok=True)


if __name__=="__main__":main()
