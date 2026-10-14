"""Inspect only the exact configured recording and preserve its source bytes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from uchuva_dataset_curation import digest, write_json
from uchuva_reconstruction import VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    expected = config["source_expected_basename"]
    name = config.get("source_confirmed_basename", expected)
    if name != expected and not config.get("alternate_authorization"):
        raise ValueError("A different basename requires explicit user authorization")
    matches = [p for p in (ROOT / "Nuevo Dataset").rglob("*") if p.is_file() and p.name == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {name}; found {len(matches)}. No substitution allowed.")
    source = matches[0]
    before = source.stat()
    args.output.mkdir(parents=True, exist_ok=False)
    inspection = args.output / "inspection"
    inspection.mkdir()
    cv2.setNumThreads(2)
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise ValueError("Cannot decode source")
        fps = cap.get(cv2.CAP_PROP_FPS)
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps <= 0 or count <= 0:
            raise ValueError("Invalid video duration metadata")
        manifest = dict(script_version=VERSION, seed=config["seed"],
            parameter_preset=config["parameter_preset"], source_relative=source.relative_to(ROOT).as_posix(),
            expected_filename=expected, confirmed_filename=name, authorization=config.get("alternate_authorization"),
            bytes=before.st_size, sha256=digest(source), fps=fps, frame_count=count,
            duration_seconds=count/fps, width=int(cap.get(3)), height=int(cap.get(4)),
            orientation=cap.get(cv2.CAP_PROP_ORIENTATION_META),
            budget_start_epoch=config["budget_start_epoch"], deadline_epoch=config["deadline_epoch"])
        write_json(args.output / "input_manifest.json", manifest)
        sheet = Image.new("RGB", (1280, 1632), "#171b21")
        draw = ImageDraw.Draw(sheet)
        rows = []
        for i, target in enumerate(np.linspace(0, max(0, count/fps-1), 32)):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(target)*1000)
            ok, frame = cap.read()
            if not ok:
                rows.append(dict(sample=i, requested_seconds=float(target), status="decode_failed"))
                continue
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            image = Image.fromarray(cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_BGR2RGB))
            filename = f"sample_{i:02d}_{timestamp:08.2f}.jpg"
            image.save(inspection / filename)
            x, y = i%4*320, i//4*204
            sheet.paste(image, (x, y))
            draw.text((x+5, y+183), f"{i:02d} | {timestamp:.2f} s", fill="white")
            rows.append(dict(sample=i, requested_seconds=float(target), decoder_seconds=timestamp, image=filename))
        write_json(args.output / "inspection_samples.json", dict(script_version=VERSION,
            seed=config["seed"], parameter_preset=config["parameter_preset"], samples=rows))
        sheet.save(args.output / "contact_sheet.jpg")
    finally:
        cap.release()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during inspection")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
