"""Offline export processes every decoded frame, unlike the live latest-frame preview."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

import cv2

from .vision import VisionEngine
from .video import open_capture


def export_video(source, directory, assets, settings, selected, cancel, progress):
    capture_id = "video_" + uuid4().hex
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pending = directory / ("." + capture_id + ".pending")
    final = directory / capture_id
    pending.mkdir()
    cap = open_capture(source)
    writer = None
    try:
        if not cap.isOpened():
            raise OSError("No se pudo abrir el video")
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not 1 <= fps <= 240:
            raise ValueError("Frecuencia de video desconocida; no se exportará con tiempos inventados")
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width % 2 or height % 2:
            raise ValueError("La exportación MP4 requiere dimensiones pares")
        video_name = capture_id + ".mp4"
        jsonl_name = capture_id + ".jsonl"
        writer = cv2.VideoWriter(str(pending / video_name), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise OSError("No se pudo crear el MP4")
        engine = VisionEngine(assets)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        count = 0
        with (pending / jsonl_name).open("w", encoding="utf-8") as records:
            while not cancel.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                count += 1
                image, result = engine.analyze(frame, settings, count, "file", selected,
                                               media_time_ms=cap.get(cv2.CAP_PROP_POS_MSEC))
                if selected is None:
                    selected = result["reference"]["selected_id"]
                if image.shape[:2] != (height, width):
                    raise ValueError("El video cambia de dimensiones")
                result["capture_id"] = capture_id
                result["output_frame_index"] = count - 1
                result["output_time_ms"] = (count - 1) * 1000 / fps
                writer.write(image)
                records.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
                if count % 10 == 0:
                    progress(f"Exportando: {count}/{total or '?'} fotogramas")
        if cancel.is_set():
            raise InterruptedError("Exportación cancelada")
        if count == 0 or (total > 0 and count < total):
            raise OSError("Video vacío o decodificación incompleta")
        writer.release(); writer = None
        with (pending / video_name).open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = dict(schema_version="1.4", capture_id=capture_id, video_name=video_name,
                        records_name=jsonl_name, video_sha256=digest, frames=count, fps=fps,
                        model_sha256=engine.model_hash, exported_at=datetime.now(timezone.utc).isoformat(),
                        audio_included=False, timing="constant_frame_rate_from_source_fps",
                        records="one JSON line per output frame, zero-based output_frame_index")
        (pending / (capture_id + ".json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        pending.rename(final)
        return final
    finally:
        cap.release()
        if writer:
            writer.release()
        if pending.exists():
            shutil.rmtree(pending)
