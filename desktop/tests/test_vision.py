import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from uchuva_aruco.vision import Settings, VisionEngine, mapping, project, grid_lines, resolve
from uchuva_aruco.storage import save_capture
from uchuva_aruco.video import valid_rtmp

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "mobile/android/app/src/main/assets"


class GeometryTests(unittest.TestCase):
    def test_dictionary_selection_preserves_historical_default(self):
        self.assertEqual(Settings().dictionary, "DICT_4X4_50")
        self.assertEqual(Settings(dictionary="DICT_4X4_100").dictionary, "DICT_4X4_100")
        with self.assertRaises(ValueError):
            Settings(dictionary="unknown")
    def test_signs_scale_rotation_and_perspective(self):
        corners = np.array([[100, 100], [200, 100], [200, 200], [100, 200]], float)
        self.assertAlmostEqual(project(mapping(corners, 10), [250, 50])["x"], 10)
        self.assertAlmostEqual(project(mapping(corners, 10), [250, 50])["y"], 10)
        self.assertAlmostEqual(project(mapping(corners, 20), [250, 50])["distance"], 20 * 2**.5)
        for p in (corners, np.roll(corners, 1, axis=0), np.array([[80, 90], [250, 100], [200, 250], [110, 220]], float)):
            h = mapping(p, 10)
            for corner, expected in zip(p, [(-5, 5), (5, 5), (5, -5), (-5, -5)]):
                actual = project(h, corner)
                np.testing.assert_allclose([actual["x"], actual["y"]], expected, atol=1e-5)
            inv = np.linalg.inv(h)
            pixel = cv2.perspectiveTransform(np.array([[[8., 12.]]]), inv)[0, 0]
            actual = project(h, pixel)
            np.testing.assert_allclose([actual["x"], actual["y"]], [8, 12], atol=1e-5)

    def test_grid_extends_to_frame_edges(self):
        h = mapping([[100, 100], [200, 100], [200, 200], [100, 200]], 10)
        lines = grid_lines(h, 10, 1280, 720)
        self.assertGreater(len(lines), 10)
        self.assertTrue(any(max(a[1], b[1]) == 719 for a, b, _ in lines))
        for a, b, _ in lines:
            for x, y in (a, b):
                self.assertTrue(-1e-6 <= x <= 1279.00001 and -1e-6 <= y <= 719.00001)

    def test_invalid_reference_is_independent(self):
        p = [[100, 100], [200, 100], [200, 200], [100, 200]]
        markers = [{"id": i, "corners_px": p} for i in [0, 0, 1]]
        refs, _ = resolve(markers, 10, 0)
        self.assertEqual([r["state"] for r in refs], ["ambiguous", "ambiguous", "valid"])
        refs, _ = resolve(markers[2:], None, 0)
        self.assertEqual(refs[0]["state"], "size_unconfirmed")
        self.assertIsNone(mapping([[0, 0], [1, 0], [2, 0], [3, 0]], 10))
        for value in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                Settings(value)

    def test_rtmp_address(self):
        self.assertTrue(valid_rtmp("rtmp://127.0.0.1:1935/neo"))
        for address in ("https://youtube.com", "rtmp://host", "rtmp://host:90000/neo", "rtmp://host:0/neo"):
            self.assertFalse(valid_rtmp(address))

    def test_capture_pair_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            image = np.full((200, 300, 3), 120, np.uint8)
            result = {"schema_version": "1.4", "frame_id": 17, "detections": []}
            saved = save_capture(Path(directory), image, result)
            metadata = json.loads(next(saved.glob("*.json")).read_text())
            self.assertEqual(metadata["frame_id"], 17)
            self.assertEqual(metadata["image_sha256"], hashlib.sha256(next(saved.glob("*.jpg")).read_bytes()).hexdigest())
            self.assertNotIn("capture_id", result)
            with patch("uchuva_aruco.storage.json.dumps", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    save_capture(Path(directory), image, result)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)


@unittest.skipUnless((ASSETS / "detector.onnx").exists(), "Prepare model assets first")
class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = VisionEngine(ASSETS)

    def test_validation_fixture_parity(self):
        folder = ROOT / "mobile/android/app/src/androidTest/assets"
        if not (folder / "mobile_validation_fixture.png").exists():
            self.skipTest("Validation fixture not prepared")
        image = cv2.imread(str(folder / "mobile_validation_fixture.png"))
        expected = json.loads((folder / "mobile_validation_fixture.json").read_text())
        _, result = self.engine.analyze(image, Settings(10))
        self.assertEqual(len(result["detections"]), len(expected["detections"]))
        for actual, reference in zip(result["detections"], expected["detections"]):
            np.testing.assert_allclose(actual["box_xyxy_px"], reference["box"], atol=.1)
            self.assertAlmostEqual(actual["confidence"], reference["confidence"], delta=.001)

    def test_markers_and_unconfirmed_size(self):
        image = np.full((480, 640, 3), 255, np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for marker_id, x in ((0, 40), (1, 350)):
            marker = cv2.aruco.generateImageMarker(dictionary, marker_id, 160)
            image[40:200, x:x+160] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        annotated, result = self.engine.analyze(image, Settings())
        self.assertEqual({r["marker_id"] for r in result["references"]}, {0, 1})
        self.assertTrue(all(r["state"] == "size_unconfirmed" for r in result["references"]))
        self.assertFalse(np.array_equal(image, annotated))

    def test_pilot_dictionary_detects_id_71(self):
        image = np.full((480,640,3),255,np.uint8)
        marker = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100),71,160)
        image[100:260,100:260] = cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
        _, result = self.engine.analyze(image,Settings(10,dictionary="DICT_4X4_100"))
        self.assertEqual(result["reference"]["dictionary"],"DICT_4X4_100")
        self.assertEqual([m["marker_id"] for m in result["references"]],[71])

    def test_detection_has_metric_positions_for_both_markers(self):
        image = np.full((480, 640, 3), 255, np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        for marker_id, x in ((0, 40), (1, 350)):
            image[40:200, x:x+160] = cv2.cvtColor(cv2.aruco.generateImageMarker(dictionary, marker_id, 160), cv2.COLOR_GRAY2BGR)
        class Session:
            def run(self, *_):
                return [np.array([[[300, 380, 350, 430, .9, 0]]], np.float32)]
        with patch.object(self.engine, "session", Session()):
            _, confirmed = self.engine.analyze(image, Settings(10))
            _, unknown = self.engine.analyze(image, Settings())
        positions = confirmed["detections"][0]["positions_by_marker"]
        self.assertEqual([p["marker_id"] for p in positions], [0, 1])
        self.assertTrue(all(p["position_cm"] is not None for p in positions))
        self.assertGreater(positions[0]["position_cm"]["x"], 0)
        self.assertLess(positions[1]["position_cm"]["x"], 0)
        self.assertTrue(all(p["position_cm"]["y"] < 0 for p in positions))
        self.assertTrue(all(p["position_cm"] is None for p in unknown["detections"][0]["positions_by_marker"]))
        self.assertIsNone(unknown["reference"]["side_cm"])


if __name__ == "__main__":
    unittest.main()
