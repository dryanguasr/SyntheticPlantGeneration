"""Local RTMP smoke fixture; no drone, external video service or test-set data.

Run with outputs/desktop/venv/Scripts/python.exe; imageio-ffmpeg==0.6.0 is a
test-only dependency. --hold-seconds keeps the publisher alive for Android tests.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))

import cv2
import imageio_ffmpeg
import numpy as np

from uchuva_aruco.video import VideoReader
from uchuva_aruco.vision import Settings, VisionEngine
from uchuva_aruco.storage import save_capture
from uchuva_aruco.export_video import export_video


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    out = ROOT / "outputs/desktop/rtmp-test"
    out.mkdir(parents=True, exist_ok=True)
    image = np.full((480, 640, 3), 240, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for mid, x in ((0, 30), (1, 350)):
        patch = cv2.aruco.generateImageMarker(dictionary, mid, 160)
        image[30:190, x:x+160] = cv2.cvtColor(patch, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(image, (70, 320), (180, 410), (30, 140, 210), -1)
    cv2.imwrite(str(out / "fixture.png"), image)
    config = (ROOT / "desktop/mediamtx.yml").read_text().replace("rtmpAddress: :1935", "rtmpAddress: 127.0.0.1:1935")
    (out / "server.yml").write_text(config)
    server = publisher = reader = None
    with (out / "server.log").open("w") as server_log, (out / "publisher.log").open("w") as publisher_log:
        try:
            server = subprocess.Popen([str(ROOT / "outputs/desktop/server/mediamtx.exe"), str(out / "server.yml")], stdout=server_log, stderr=server_log)
            time.sleep(1)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            publisher = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-re", "-loop", "1", "-i", str(out / "fixture.png"),
                                          "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-r", "10", "-g", "10",
                                          "-f", "flv", "rtmp://127.0.0.1:1935/neo"], stdout=publisher_log, stderr=publisher_log)
            deadline = time.monotonic() + 15
            while "is publishing" not in (out / "server.log").read_text() and time.monotonic() < deadline:
                time.sleep(.1)
            if server.poll() is not None or publisher.poll() is not None:
                raise RuntimeError("Local publisher/server failed; inspect fixture logs")
            reader = VideoReader("rtmp://127.0.0.1:1935/neo", True)
            deadline = time.monotonic()+20
            while reader.latest is None and not reader.error and time.monotonic()<deadline:
                time.sleep(.1)
            if reader.latest is None:
                raise AssertionError(reader.error or "RTMP timeout")
            frame = reader.latest
            assets = ROOT / "mobile/android/app/src/main/assets"
            engine = VisionEngine(assets)
            annotated, result = engine.analyze(frame.image, Settings(10), frame.number, "rtmp", received_at=frame.received_at)
            assert {m["id"] for m in result["markers"]} == {0, 1}
            saved = save_capture(out / "captures", annotated, result)
            metadata = json.loads(next(saved.glob("*.json")).read_text())
            assert metadata["image_sha256"] == hashlib.sha256(next(saved.glob("*.jpg")).read_bytes()).hexdigest()
            # Export a short local MP4 and check every output frame against its JSONL index.
            source = out / "short.mp4"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 480))
            for _ in range(6):
                writer.write(image)
            writer.release()
            exported = export_video(source, out, assets, Settings(10), None, threading.Event(), print)
            records = [json.loads(line) for line in next(exported.glob("*.jsonl")).read_text().splitlines()]
            assert [r["output_frame_index"] for r in records] == list(range(6))
            assert all(len(r["references"]) == 2 for r in records)
            cap = cv2.VideoCapture(str(next(exported.glob("*.mp4"))))
            assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 6
            cap.release()
            print("RTMP_READY: decoded 640x480, two markers, capture hash and six-frame video export verified", flush=True)
            initial_number = reader.latest.number
            continuity_deadline = time.monotonic() + 8
            while time.monotonic() < continuity_deadline:
                assert reader.error is None, reader.error
                time.sleep(.1)
            assert reader.latest.number > initial_number + 20, "Reader must continue draining the live stream"
            deadline = time.monotonic()+args.hold_seconds
            while time.monotonic()<deadline:
                time.sleep(.5)
            publisher.terminate(); publisher.wait(timeout=5); publisher = None
            deadline = time.monotonic()+10
            while not reader.error and time.monotonic()<deadline:
                time.sleep(.1)
            assert reader.error, "Disconnect must become an error, not an empty detection"
            report = dict(status="passed", source="local_ffmpeg_fixture_not_drone", resolution=[640,480],
                          marker_ids=[0,1], capture_sha256=metadata["image_sha256"],
                          analysis_ms=result["analysis_ms"], exported_frames=len(records), disconnect_detected=True)
            (out / "report.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
        finally:
            if reader:
                reader.close()
            for process in (publisher, server):
                if process and process.poll() is None:
                    process.terminate(); process.wait(timeout=5)


if __name__ == "__main__":
    main()
