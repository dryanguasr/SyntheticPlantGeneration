"""Frozen RGB-only variable-length full-route inference; no truth, pose, identity or metric inputs.

Only the validated public package, model checkpoint and frozen inference helper
are read. The helper's evaluator/report functions are never called.
"""
import argparse
import datetime
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

import numpy as np
import psutil
from PIL import Image

VERSION = "public-full-route-inference/1"
CAMPAIGN = Path(__file__).resolve().parent
DATASET = CAMPAIGN.parents[1] / "multiscale_dataset_20261020"
WEIGHT = DATASET / "training_runs/training/weights/last.pt"
WEIGHT_SHA = "9c660824319f2c436321d2545cf9b267348c7be64d7780a396d8382555eb05cd"
HELPER = DATASET / "evaluate_multiscale_v1.py"
HELPER_SHA = "111f4359578dae14adaef24626b82bc94b644efef82d1b4076d54a7906b34527"
SETTINGS = dict(patch_size=640, stride=448, input_size=960, confidence=.25,
    prediction_nms_iou=.7, max_det_per_tile=300, merge_mask_iou=.45,
    merge_intersection_over_smaller=.75, exhaustive_full_frame=True,
    ground_truth_used=False, tracking_performed=False, evaluation_performed=False)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def write(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(data,indent=2),encoding="utf-8");temp.replace(path)


def checked_path(root, name):
    relative=Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Public path must be relative and contained")
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError("Public path escapes package")
    return path


def validate_public(public, admission_path):
    """Consume only a sanitized allowlist receipt, never the private validator."""
    frames=read(public/"frames.json")
    calibration=read(public/"calibration.json")
    marker=read(public/"marker_dimensions.json")
    admission=read(admission_path)
    if set(admission)!={"version","passed","public_files"} or admission["version"]!="public-inference-admission/1":
        raise ValueError("Receipt contains unexpected fields or wrong schema")
    if admission["passed"] is not True:raise ValueError("Public export admission has not passed")
    if not isinstance(frames,list):raise ValueError("Public frames must be a list")
    if set(calibration)!={"width","height","intrinsic_matrix","distortion_coefficients","camera_model"}:
        raise ValueError("Public calibration contains unexpected/nonintrinsic fields")
    if set(marker)!={"dictionary","coded_side_m","board_side_m"}:
        raise ValueError("Marker metadata contains unexpected fields")
    if marker["dictionary"]!="DICT_4X4_50" or not 0<float(marker["coded_side_m"])<=float(marker["board_side_m"]):
        raise ValueError("Invalid physical marker dimensions")
    allowed={"frames.json","calibration.json","marker_dimensions.json"}
    if not frames:raise ValueError("A public route needs at least one frame")
    if (calibration["width"],calibration["height"])!=(1280,720):raise ValueError("Unexpected RGB dimensions")
    K=np.asarray(calibration["intrinsic_matrix"],dtype=float)
    if K.shape!=(3,3) or not np.isfinite(K).all() or K[0,0]<=0 or K[1,1]<=0:raise ValueError("Invalid public intrinsics")
    distortion=np.asarray(calibration["distortion_coefficients"],dtype=float)
    if distortion.shape!=(5,) or not np.isfinite(distortion).all():raise ValueError("Invalid distortion coefficients")
    previous=None;inference_frames=[]
    for index,row in enumerate(frames):
        if set(row)!={"stamp_ns","filename","rgb_sha256"}:raise ValueError("Unexpected/private frame fields")
        if type(row["stamp_ns"]) is not int or row["stamp_ns"]<0:raise ValueError("Invalid timestamp")
        if previous is not None and row["stamp_ns"]-previous!=250000000:raise ValueError("Expected consecutive4Hz times")
        previous=row["stamp_ns"]
        if row["filename"]!=str(row["stamp_ns"])+".png":raise ValueError("Filename must encode only observed timestamp")
        path=checked_path(public,"rgb/"+row["filename"])
        if path.suffix.lower()!=".png" or sha(path)!=row["rgb_sha256"]:raise ValueError("RGB filename/hash mismatch")
        with Image.open(path) as image:
            if image.size!=(1280,720) or image.mode!="RGB":raise ValueError("Wrong public RGB format")
        allowed.add(path.relative_to(public).as_posix())
        inference_frames.append(dict(row,frame=index,filename="rgb/"+row["filename"]))
    present={p.relative_to(public).as_posix() for p in public.rglob("*") if p.is_file()}
    if present!=allowed:raise ValueError("Unexpected or missing public files: "+str(sorted(present^allowed)))
    if any(p.is_symlink() for p in public.rglob("*")):raise ValueError("Public package cannot contain symlinks")
    public_files={name:sha(checked_path(public,name)) for name in sorted(allowed)}
    if admission["public_files"]!=public_files:raise ValueError("Public admission hashes do not match package")
    return inference_frames,dict(admission_sha256=sha(admission_path),public_files=public_files)


def helper_module():
    if sha(HELPER)!=HELPER_SHA:raise ValueError("Frozen RGB inference helper changed")
    if sha(WEIGHT)!=WEIGHT_SHA:raise ValueError("Frozen checkpoint changed")
    spec=importlib.util.spec_from_file_location("public_rgb_inference_helper",HELPER)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    return helper


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--public",type=Path,required=True)
    parser.add_argument("--admission",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--check-only",action="store_true")
    parser.add_argument("--limit-frames",type=int,default=0)
    args=parser.parse_args();public=args.public.resolve();output=args.output.resolve()
    if output.is_relative_to(public):raise ValueError("Predictions must stay outside immutable public package")
    if args.limit_frames<0:raise ValueError("Frame limit cannot be negative")
    frames,package_binding=validate_public(public,args.admission.resolve());helper=helper_module()
    run_binding=dict(version=VERSION,runner_sha256=sha(Path(__file__)),helper_sha256=HELPER_SHA,
        weight_sha256=WEIGHT_SHA,public_package=package_binding,settings=SETTINGS)
    if args.check_only:
        print(json.dumps(dict(passed=True,frames=len(frames),run_binding=run_binding,gpu_used=False)),flush=True)
        return
    output.mkdir(parents=True,exist_ok=True)
    binding_path=output/"run_binding.json"
    if binding_path.exists() and read(binding_path)!=run_binding:raise ValueError("Existing output has different provenance; preserve it")
    write(binding_path,run_binding)
    lock=output/"inference.lock"
    if lock.exists():
        old=read(lock)
        if psutil.pid_exists(old["pid"]):raise RuntimeError("Another runner PID exists; inspect before recovery")
        lock.rename(output/("stale_lock_"+str(time.time_ns())+".json"))
    with lock.open("x") as stream:json.dump(dict(pid=os.getpid(),created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),stream)
    model=None;torch=None;new_frames=0;records=[]
    try:
        for row in frames:
            stem=f"frame_{row['frame']:03d}";binding=dict(run_binding=run_binding,frame=row["frame"],stamp_ns=row["stamp_ns"],rgb_sha256=row["rgb_sha256"])
            folder=output/"predictions"
            if (folder/(stem+".json")).exists():
                predictions=helper.load_predictions(folder,stem,binding)
            else:
                if model is None:
                    helper.memory_guard(6.5)
                    import torch as torch_module
                    from ultralytics import YOLO
                    torch=torch_module;torch.set_num_threads(4);model=YOLO(WEIGHT)
                    if list(model.names.values())!=helper.CLASSES:raise ValueError("Checkpoint class contract mismatch")
                rgb=np.asarray(Image.open(checked_path(public,row["filename"])).convert("RGB"))
                predictions,free=helper.infer_rgb(model,rgb,torch)
                helper.save_predictions(folder,stem,predictions,binding);new_frames+=1
                write(output/"state.json",dict(stage="public_rgb_inference",pid=os.getpid(),frame=row["frame"],min_free_host_gib=free,frames_planned=len(frames)))
            records.append(dict(frame=row["frame"],stamp_ns=row["stamp_ns"],predictions=len(predictions),cache=str(Path("predictions")/(stem+".json"))))
            print(stem,len(predictions),flush=True);del predictions;gc.collect()
            if args.limit_frames and new_frames>=args.limit_frames:
                write(output/"state.json",dict(stage="bounded_partial",pid=None,frames_completed=len(records),frames_planned=len(frames)));return
        # Completion is inference only. Tracking and truth evaluation are separate.
        write(output/"summary.json",dict(version=VERSION,complete=True,frames=records,run_binding=run_binding,
            inference_only=True,tracking_performed=False,evaluation_performed=False,ground_truth_used=False))
        write(output/"state.json",dict(stage="public_inference_complete",pid=None,frames_completed=len(frames),frames_planned=len(frames)))
    except BaseException as exc:
        write(output/"state.json",dict(stage="public_inference_failure",pid=None,error=repr(exc),previous_caches_preserved=True));raise
    finally:
        if model is not None:del model;gc.collect();torch.cuda.empty_cache()
        lock.unlink(missing_ok=True)


if __name__=="__main__":main()
