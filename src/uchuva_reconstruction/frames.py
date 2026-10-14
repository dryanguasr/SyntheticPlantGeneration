"""Motion-adaptive pilot frames with decoder timestamps and explicit provenance."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from uchuva_dataset_curation import digest, write_json
from . import VERSION


def motion_between(a, b):
    corners = cv2.goodFeaturesToTrack(a, maxCorners=500, qualityLevel=.015, minDistance=8)
    if corners is None or len(corners) < 20:
        return None, 0
    moved, status, _ = cv2.calcOpticalFlowPyrLK(a, b, corners, None)
    if moved is None:
        return None, 0
    back, reverse, _ = cv2.calcOpticalFlowPyrLK(b, a, moved, None)
    if back is None:
        return None, 0
    good = (status.ravel() == 1) & (reverse.ravel() == 1)
    good &= np.linalg.norm(back.reshape(-1, 2) - corners.reshape(-1, 2), axis=1) < 1.5
    if good.sum() < 20:
        return None, int(good.sum())
    shifts = np.linalg.norm(moved.reshape(-1, 2)[good] - corners.reshape(-1, 2)[good], axis=1)
    return float(np.median(shifts)), int(good.sum())


def select_frames(root, manifest_path, output, start, end, step=1., long_side=960,
                  motion_pixels=18., max_gap=4.):
    """Probe regularly, retain by tracked displacement, sharpness and max gap.

    All thresholds are engineering heuristics at 480-pixel analysis resolution.
    Maximum-gap frames are retained even when blurry to expose possible bridges.
    No frame is labelled as an independent evaluation view by this selector.
    """
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    source = (root / manifest["source_relative"]).resolve()
    if not source.is_relative_to(root / "Nuevo Dataset"):
        raise ValueError("Input must stay under Nuevo Dataset")
    if (not 0 <= start < end <= manifest["duration_seconds"] or step <= 0 or max_gap < step
            or not 320 <= long_side <= 3840 or motion_pixels <= 0):
        raise ValueError("Invalid sampling interval")
    if source.stat().st_size != manifest["bytes"] or digest(source) != manifest["sha256"]:
        raise ValueError("Input differs from the inspected manifest")
    output.mkdir(parents=True, exist_ok=False)
    images = output / "images"
    images.mkdir()
    cv2.setNumThreads(2)
    cv2.setRNGSeed(20261001)
    cap = cv2.VideoCapture(str(source))
    rows, selected = [], []
    previous = None
    last_time = None
    try:
        for target in np.arange(start, end + .001, step):
            cap.set(cv2.CAP_PROP_POS_MSEC, float(target) * 1000)
            ok, frame = cap.read()
            if not ok:
                rows.append({"requested_seconds": float(target), "status": "decode_failed"})
                continue
            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            h, w = frame.shape[:2]
            analysis = cv2.cvtColor(cv2.resize(frame, (480, round(h * 480 / w))), cv2.COLOR_BGR2GRAY)
            sharpness = float(cv2.Laplacian(analysis, cv2.CV_64F).var())
            motion, tracks = (None, 0) if previous is None else motion_between(previous, analysis)
            reason = ("first" if previous is None else "max_gap_bridge" if timestamp-last_time >= max_gap-.05
                      else "tracking_lost_bridge" if motion is None else "motion" if motion >= motion_pixels
                      else "redundant")
            keep = reason != "redundant"
            # Preserve uncertain bridge frames rather than hiding a coverage gap.
            if sharpness < 35 and reason == "motion":
                keep, reason = False, "blur_deferred"
            row = {"requested_seconds": float(target), "decoder_seconds": timestamp,
                   "source_frame_index": int(cap.get(cv2.CAP_PROP_POS_FRAMES))-1,
                   "sharpness_laplacian_480": sharpness, "median_flow_pixels_480": motion,
                   "valid_tracks": tracks, "selected": keep, "reason": reason,
                   "exposure_mean_480": float(analysis.mean()), "split": "pilot_reconstruction"}
            if keep:
                scale = long_side / max(h, w)
                resized = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
                name = f"frame_{row['source_frame_index']:06d}_{timestamp:010.3f}.jpg"
                # imencode also supports Unicode Windows input/output paths reliably.
                ok, encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 95])
                if not ok:
                    raise RuntimeError("JPEG encoding failed")
                (images / name).write_bytes(encoded.tobytes())
                row.update(image=name, width=resized.shape[1], height=resized.shape[0],
                           resize_scale=scale, sha256=digest(images / name))
                selected.append(row)
                previous, last_time = analysis, timestamp
            rows.append(row)
            if len(rows) % 30 == 0:
                print(f"Probed {len(rows)} frames; retained {len(selected)}; time {timestamp:.1f}s", flush=True)
    finally:
        cap.release()
    write_json(output / "selection.json", {"script_version": VERSION, "seed": 20261001,
        "parameter_preset": "pilot_2h", "input": manifest, "rows": rows,
        "config": dict(start=start, end=end, probe_step=step, long_side=long_side,
                       motion_pixels=motion_pixels, max_gap=max_gap, thresholds="engineering_heuristic"),
        "selected_count": len(selected), "independent_evaluation": False})
    # Paginated contact sheets, with every selected image represented.
    for page, offset in enumerate(range(0, len(selected), 40)):
        subset = selected[offset:offset+40]
        sheet = Image.new("RGB", (1280, ((len(subset)+3)//4)*204), "#151b22")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(subset):
            with Image.open(images / row["image"]) as im:
                thumb = im.resize((320, 180))
                x, y = (i%4)*320, (i//4)*204
                sheet.paste(thumb, (x, y))
                draw.text((x+4, y+183), f"{offset+i:03d} | {row['decoder_seconds']:.2f}s | {row['reason']}", fill="white")
        sheet.save(output / f"selected_{page:02d}.jpg")
    print(f"Selected {len(selected)} of {len(rows)} frames", flush=True)
