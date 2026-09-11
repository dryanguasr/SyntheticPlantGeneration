"""A capture directory appears only after its image and JSON are complete."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

import cv2


def save_capture(directory: Path, image, result):
    capture_id = datetime.now(timezone.utc).strftime("uchuva_%Y%m%d_%H%M%S_") + uuid4().hex[:12]
    directory.mkdir(parents=True, exist_ok=True)
    pending = directory / ("." + capture_id + ".pending")
    final = directory / capture_id
    pending.mkdir()
    try:
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not ok:
            raise OSError("No se pudo codificar la imagen")
        data = encoded.tobytes()
        image_name, json_name = capture_id + ".jpg", capture_id + ".json"
        (pending / image_name).write_bytes(data)
        metadata = deepcopy(result)
        metadata.update(capture_id=capture_id, image_name=image_name, json_name=json_name,
                        image_relative_path=f"{capture_id}/{image_name}", json_relative_path=f"{capture_id}/{json_name}",
                        image_sha256=hashlib.sha256(data).hexdigest())
        (pending / json_name).write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        pending.rename(final)
        return final
    except Exception:
        shutil.rmtree(pending, ignore_errors=True)
        raise
