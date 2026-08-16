#!/usr/bin/env python3
"""Ejecuta E0, E1 y E2 con multiples semillas; reanuda corridas incompletas."""
from __future__ import annotations
import argparse, csv, hashlib, json, platform, sys, traceback
from datetime import datetime, timezone
from pathlib import Path
import torch, yaml
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[3]
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MODEL_SHA256 = "0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1"
EXPERIMENTS = {
    "E0": ("real_only", ROOT / "data/semifield_v1", (1062, 109, 109)),
    "E1": ("occ_light_strong", ROOT / "data/working/dataset_E1_occ_light_strong", (2124, 109, 109)),
    "E2": ("occ_light_soft", ROOT / "data/working/dataset_E2_occ_light_soft", (2124, 109, 109)),
}

def seeds_arg(text):
    values = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            first, last = map(int, part.split("-", 1)); values.extend(range(first, last + 1))
        elif part: values.append(int(part))
    if not values or len(values) != len(set(values)) or min(values) < 0:
        raise argparse.ArgumentTypeError("Use semillas unicas >= 0; ejemplo: 1-30")
    return values

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest().upper()

def validate_dataset(code):
    _, root, expected = EXPERIMENTS[code]
    result, errors = {"experiment": code, "path": str(root), "splits": {}}, []
    for split, count in zip(("train", "val", "test"), expected, strict=True):
        image_dir, label_dir = root / "images" / split, root / "labels" / split
        if not image_dir.is_dir() or not label_dir.is_dir():
            errors.append(f"{code}/{split}: faltan directorios"); continue
        images = {p.stem: p for p in image_dir.iterdir() if p.suffix.lower() in EXTS}
        labels = {p.stem: p for p in label_dir.glob("*.txt")}
        if len(images) != count or len(labels) != count:
            errors.append(f"{code}/{split}: images={len(images)}, labels={len(labels)}, esperado={count}")
        if set(images) != set(labels): errors.append(f"{code}/{split}: pares imagen-etiqueta incorrectos")
        objects = 0
        for label in labels.values():
            for number, line in enumerate(label.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip(): continue
                fields = line.split()
                try:
                    valid = len(fields) == 5 and int(fields[0]) == 0
                    coords = [float(value) for value in fields[1:]]
                    valid = valid and all(0 <= v <= 1 for v in coords) and coords[2] > 0 and coords[3] > 0
                except (ValueError, IndexError): valid = False
                if not valid:
                    errors.append(f"Etiqueta YOLO invalida: {label}:{number}"); break
                objects += 1
        result["splits"][split] = {"images": len(images), "labels": len(labels), "objects": objects}
    if errors: raise RuntimeError("\n".join(errors[:30]))
    return result

def make_yaml(code, directory):
    directory.mkdir(parents=True, exist_ok=True); output = directory / f"data_{code}.yaml"
    payload = {"path": EXPERIMENTS[code][1].as_posix(), "train": "images/train",
               "val": "images/val", "test": "images/test", "names": {0: "uchuva"}}
    output.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"); return output

def is_complete(run, epochs):
    results = run / "results.csv"
    if not results.exists(): return False
    with results.open(encoding="utf-8-sig", newline="") as stream: return len(list(csv.DictReader(stream))) >= epochs

def log_state(project, code, seed, run, action, status, message=""):
    path = project / "execution_state.csv"; exists = path.exists()
    fields = ["timestamp_utc", "experiment", "seed", "run", "action", "status", "message"]
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        if not exists: writer.writerow(fields)
        writer.writerow([datetime.now(timezone.utc).isoformat(), code, seed, run, action, status, message])

def train_one(code, seed, args, project, data_yaml):
    scenario = EXPERIMENTS[code][0]; name = f"{code}_{scenario}_yolo11n_640_e{args.epochs}_seed{seed:02d}"
    run, last = project / name, project / name / "weights/last.pt"
    if is_complete(run, args.epochs): print(f"[OMITIDO] {name}: completo"); return
    action = "resume" if last.exists() else "new"
    print(f"\n{'=' * 70}\n{action.upper()} {name}\n{'=' * 70}"); log_state(project, code, seed, name, action, "started")
    try:
        if last.exists(): YOLO(str(last)).train(resume=True)
        else:
            YOLO(str(args.model)).train(
                data=str(data_yaml), epochs=args.epochs, imgsz=640, batch=args.batch,
                device=args.device, workers=args.workers, rect=True, cache=False,
                optimizer="AdamW", lr0=0.001, lrf=0.01, weight_decay=0.0005,
                patience=args.epochs, seed=seed, deterministic=True, amp=args.amp,
                val=True, plots=True, save=True, save_period=args.save_period,
                hsv_h=0.0, hsv_s=0.0, hsv_v=0.0, degrees=0.0, translate=0.0,
                scale=0.0, shear=0.0, perspective=0.0, flipud=0.0, fliplr=0.0,
                bgr=0.0, mosaic=0.0, mixup=0.0, cutmix=0.0, copy_paste=0.0,
                close_mosaic=0, project=str(project), name=name, exist_ok=False)
        log_state(project, code, seed, name, action, "complete")
    except BaseException as error:
        log_state(project, code, seed, name, action, "failed", f"{type(error).__name__}: {error}")
        traceback.print_exc(); raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", nargs="+", choices=EXPERIMENTS, default=list(EXPERIMENTS))
    parser.add_argument("--seeds", type=seeds_arg, default=list(range(1, 30)) + [42])
    parser.add_argument("--epochs", type=int, default=50); parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4); parser.add_argument("--device", default="0")
    parser.add_argument("--save-period", type=int, default=5); parser.add_argument("--amp", action="store_true")
    parser.add_argument("--model", type=Path, default=ROOT / "models/pretrained/yolo11n.pt")
    parser.add_argument("--project", type=Path, default=ROOT / "runs/detect/experiments/training/yolo11n_multiseed_v1")
    parser.add_argument("--dry-run", action="store_true"); args = parser.parse_args()
    args.model, args.project = args.model.resolve(), args.project.resolve()
    if not args.model.is_file(): raise FileNotFoundError(f"Falta {args.model}")
    if sha256(args.model) != MODEL_SHA256: raise RuntimeError("SHA256 de yolo11n.pt no coincide")
    if args.device != "cpu" and not torch.cuda.is_available(): raise RuntimeError("CUDA no disponible")
    print("Validando datasets..."); reports = [validate_dataset(code) for code in args.experiments]
    yamls = {code: make_yaml(code, args.project / "runtime_configs") for code in args.experiments}
    args.project.mkdir(parents=True, exist_ok=True)
    serial_args = {**vars(args), "model": str(args.model), "project": str(args.project)}
    environment = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "platform": platform.platform(), "torch": torch.__version__, "cuda": torch.version.cuda,
        "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        "arguments": serial_args, "model_sha256": sha256(args.model), "datasets": reports}
    (args.project / "execution_environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    print(f"Plan: {len(args.seeds)} semillas x {len(args.experiments)} experimentos = {len(args.seeds)*len(args.experiments)} corridas")
    print(f"Orden emparejado: {' -> '.join(args.experiments)} por cada semilla")
    if args.dry_run: print("DRY RUN correcto; no se entreno ningun modelo."); return
    for seed in args.seeds:
        for code in args.experiments: train_one(code, seed, args, args.project, yamls[code])

if __name__ == "__main__": main()
