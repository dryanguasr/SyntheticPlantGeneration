"""Exercise Tk callbacks without requiring a human to operate the desktop."""
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest

import cv2
import numpy as np

from uchuva_aruco.app import Application
from uchuva_aruco.vision import Settings

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "nt", "Windows GUI smoke test")
class ApplicationTests(unittest.TestCase):
    def test_local_video_preview_save_and_disconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "input.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 5, (640, 480))
            frame = np.full((480, 640, 3), 230, np.uint8)
            for _ in range(15):
                writer.write(frame)
            writer.release()
            root = tk.Tk()
            root.withdraw()
            app = Application(root, ROOT / "mobile/android/app/src/main/assets")
            app.settings = Settings(10)
            app.save_directory = folder / "captures"
            try:
                app.connect(str(source), False)
                deadline = time.monotonic()+10
                while app.snapshot is None and time.monotonic()<deadline:
                    root.update(); time.sleep(.03)
                self.assertIsNotNone(app.snapshot, app.status.get())
                self.assertEqual(app.snapshot[1]["source"]["kind"], "file")
                app.pause()
                self.assertTrue(app.reader.paused.is_set())
                app.save()
                deadline = time.monotonic()+5
                while not list(app.save_directory.glob("*/*.json")) and time.monotonic()<deadline:
                    root.update(); time.sleep(.03)
                self.assertEqual(len(list(app.save_directory.glob("*/*.json"))), 1)
                app.disconnect()
                self.assertIsNone(app.snapshot)
            finally:
                app.close()
