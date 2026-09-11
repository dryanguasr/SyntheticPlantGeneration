"""Reader thread drains live streams independently of inference; one latest frame."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import threading
import time
from urllib.parse import urlsplit

import cv2

# OpenCV exposes FFmpeg options through the process environment. Serialize only
# decoder creation, restoring the environment before another file/live open.
_OPEN_LOCK = threading.Lock()


def open_capture(source, live=False):
    cap = cv2.VideoCapture()
    with _OPEN_LOCK:
        previous = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        try:
            if live and previous is None:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtmp_live;live|analyzeduration;500000|probesize;2048|fflags;nobuffer"
            params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_N_THREADS, 2]
            cap.open(str(source), cv2.CAP_FFMPEG, params)
        finally:
            if previous is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous
    return cap


def valid_rtmp(address):
    try:
        uri = urlsplit(address)
        return uri.scheme == "rtmp" and bool(uri.hostname) and uri.path not in ("", "/") and not uri.fragment and (uri.port is None or 0 < uri.port < 65536)
    except ValueError:
        return False


@dataclass(frozen=True)
class Frame:
    image: object
    number: int
    received_at: str
    monotonic: float
    media_time_ms: float | None


class VideoReader:
    def __init__(self, source, live=False):
        self.source, self.live = source, live
        if live and not valid_rtmp(source):
            raise ValueError("Usa rtmp://servidor:1935/ruta")
        self.latest = None
        self.error = None
        self.ended = False
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        cap = None
        try:
            cap = open_capture(self.source, self.live)
            if not cap.isOpened():
                raise OSError("No se pudo abrir el video. Comprueba la ruta, el servidor y el emisor RTMP.")
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = fps if 1 <= fps <= 240 else 30
            number = 0
            while not self.stop.is_set():
                if self.paused.is_set() and not self.live:
                    self.stop.wait(.05)
                    continue
                started = time.monotonic()
                ok, image = cap.read()
                if not ok:
                    if self.live:
                        raise OSError("RTMP desconectado. Pulsa Conectar RTMP para reintentar.")
                    self.ended = True
                    break
                number += 1
                media_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                self.latest = Frame(image, number, datetime.now(timezone.utc).isoformat(), time.monotonic(), media_ms if not self.live else None)
                if not self.live:
                    self.stop.wait(max(0, 1/fps - (time.monotonic()-started)))
        except Exception as error:
            self.error = str(error)
        finally:
            if cap:
                cap.release()

    def close(self):
        # The blocking read owns/release its decoder and is bounded by the timeout.
        self.stop.set()
