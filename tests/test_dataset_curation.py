"""Small generated media fixtures; no Blender, model or real test images."""
import csv
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from uchuva_dataset_curation import (inventory, candidates, propose_review, partition,
                                    assign_splits, export, verify, read_rows, write_rows, main, gallery)


class DatasetCurationTests(unittest.TestCase):
    def test_exclusion_preserves_splits_and_hides_gallery_image(self):
        rng = np.random.default_rng(42)
        for i in range(4):
            Image.fromarray(rng.integers(0, 256, (90, 120, 3), dtype=np.uint8)).save(self.source / f"{i}.jpg")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        propose_review(self.out, files, rows)
        before, _ = partition(self.out, rows)
        policy = {"groups": {r["group_id"]: r["split"] for r in before}}
        (self.out / "preserved_splits.json").write_text(json.dumps(policy), encoding="utf-8")
        review = read_rows(self.out / "image_review.csv")
        excluded = review[0]["image_id"]
        review[0]["selection"] = "exclude"
        write_rows(self.out / "image_review.csv", review)
        after, report = partition(self.out, rows)
        self.assertEqual(report["selected"], 3)
        self.assertEqual({r["image_id"]: r["split"] for r in before},
                         {r["image_id"]: r["split"] for r in after})
        gallery(self.out, after)
        self.assertTrue(all(excluded not in p.read_text(encoding="utf-8")
                            for p in (self.out / "gallery").glob("*.html")))
        policy["groups"] = {}
        (self.out / "preserved_splits.json").write_text(json.dumps(policy), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Preserved splits"):
            partition(self.out, rows)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.out = self.root / "out"
        self.source.mkdir()
        self.out.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_changed_input_cannot_resume(self):
        Image.new("RGB", (32, 32), "red").save(self.source / "a.jpg")
        inventory(self.source, self.out)
        Image.new("RGB", (32, 32), "blue").save(self.source / "a.jpg")
        with self.assertRaisesRegex(ValueError, "Inputs changed"):
            inventory(self.source, self.out)
        self.assertEqual(json.loads((self.out / "input_changes.json").read_text())["modified"], ["a.jpg"])

    def test_grouped_split_determinism_and_no_empty_split(self):
        rows = [dict(group_id=f"g{i//4}", kind="photo", device="phone") for i in range(60)]
        first = assign_splits(rows)
        self.assertEqual(first, assign_splits(list(reversed(rows))))
        self.assertEqual(set(first.values()), {"train", "val", "test"})

    def test_orientation_corrupt_and_recompressed_duplicates(self):
        rng = np.random.default_rng(7)
        pixels = rng.integers(0, 256, (100, 180, 3), dtype=np.uint8)
        exif = Image.Exif()
        exif[274] = 6
        Image.fromarray(pixels).save(self.source / "a.jpg", exif=exif, quality=95)
        # Both files decode to very similar oriented content, not identical bytes.
        Image.fromarray(pixels).save(self.source / "b.jpg", exif=exif, quality=85)
        (self.source / "broken.jpg").write_bytes(b"not an image")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        self.assertEqual(len(rows), 2)
        self.assertEqual((rows[0]["width"], rows[0]["height"]), (100, 180))
        pairs = propose_review(self.out, files, rows)
        self.assertTrue(pairs)
        records, report = partition(self.out, rows)
        self.assertEqual(len({r["group_id"] for r in records}), 1)
        self.assertIn("source_groups_pending", report["blockers"])
        self.assertEqual(report["selection"], {"include": 1, "reserve": 1})
        export(self.out, records)
        self.assertEqual(verify(self.out)["images"], 1)
        self.assertFalse((self.out / "labels").exists())

    def test_video_timestamps_and_whole_source_group(self):
        path = self.source / "sequence.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (96, 64))
        self.assertTrue(writer.isOpened())
        for i in range(30):
            frame = np.full((64, 96, 3), (i * 8) % 255, dtype=np.uint8)
            writer.write(frame)
        writer.release()
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        regular = [r for r in rows if r["selection_reason"] == "regular"]
        self.assertEqual([r["frame_index"] for r in regular], [0, 10, 20])
        self.assertEqual([r["timestamp_seconds"] for r in regular], [0., 1., 2.])
        self.assertGreater(len(rows), 3)  # half-second change probes retained
        propose_review(self.out, files, rows)
        records, _ = partition(self.out, rows)
        self.assertEqual(len({r["split"] for r in records}), 1)
        export(self.out, records)
        verify(self.out)
        exported = read_rows(self.out / "export_manifest.jsonl")
        (self.out / exported[0]["path"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "content changed"):
            verify(self.out)

    def test_review_validation(self):
        Image.new("RGB", (32, 32), "red").save(self.source / "a.jpg")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        propose_review(self.out, files, rows)
        review = read_rows(self.out / "image_review.csv")
        review[0]["scale_review"] = "reviewed"
        write_rows(self.out / "image_review.csv", review)
        with self.assertRaisesRegex(ValueError, "resolve unknown"):
            partition(self.out, rows)

    def test_pair_removal_cannot_hide_leakage(self):
        Image.new("RGB", (60, 40), "green").save(self.source / "a.jpg")
        Image.new("RGB", (60, 40), "green").save(self.source / "b.jpg")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        propose_review(self.out, files, rows)
        (self.out / "pair_review.csv").write_text("left,right\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "each proposed pair"):
            partition(self.out, rows)

    def test_review_rotation_and_resumable_export(self):
        Image.new("RGB", (60, 40), "green").save(self.source / "a.jpg")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        propose_review(self.out, files, rows)
        sources = read_rows(self.out / "source_review.csv")
        sources[0]["rotation_cw"] = "270"
        write_rows(self.out / "source_review.csv", sources)
        records, _ = partition(self.out, rows)
        export(self.out, records)
        export(self.out, records)
        self.assertEqual(verify(self.out)["images"], 1)
        self.assertEqual((records[0]["width"], records[0]["height"]), (40, 60))
        review = read_rows(self.out / "image_review.csv")
        review[0]["notes"] = "Changed after delivery"
        write_rows(self.out / "image_review.csv", review)
        with self.assertRaisesRegex(ValueError, "Delivered review changed"):
            verify(self.out)

    def test_variable_frame_rate_uses_decoder_timestamps(self):
        binaries = Path(__file__).resolve().parents[1] / "outputs/desktop/venv/Lib/site-packages/imageio_ffmpeg/binaries"
        ffmpeg = next(binaries.glob("ffmpeg*.exe"), None)
        if ffmpeg is None:
            self.skipTest("Optional existing FFmpeg fixture generator is unavailable")
        listing = []
        for i, duration in enumerate([.12, .56, .20, .80, 1.40]):
            path = self.root / f"frame{i}.png"
            Image.new("RGB", (96, 64), (i*45, 60, 30)).save(path)
            listing.extend([f"file '{path.as_posix()}'", f"duration {duration}"])
        listing.append(f"file '{path.as_posix()}'")
        concat = self.root / "frames.txt"
        concat.write_text("\n".join(listing), encoding="utf-8")
        subprocess.run([str(ffmpeg), "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(self.source / "vfr.mp4")], check=True)
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        cap = cv2.VideoCapture(str(self.source / "vfr.mp4"))
        actual, index = {}, 0
        while cap.grab():
            actual[index] = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            index += 1
        cap.release()
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertAlmostEqual(row["timestamp_seconds"], actual[row["frame_index"]], places=5)
        fps = files[0]["fps"]
        self.assertTrue(any(abs(r["timestamp_seconds"] - r["frame_index"] / fps) > .05 for r in rows))

    def test_slow_change_is_not_collapsed_by_transitive_similarity(self):
        rows, files = [], []
        for ident, value, sharpness in [("a", 40, 100), ("b", 50, 10), ("c", 60, 90)]:
            rows.append(dict(image_id=ident, source_id=ident, pixel_sha256=ident,
                             sha256=ident, dhash="0000000000000000", thumbnail=[value]*3072,
                             width=100, height=100, sharpness=sharpness))
            files.append(dict(source_id=ident, source=ident, kind="photo", capture_time="", device="test"))
        propose_review(self.out, files, rows)
        review = read_rows(self.out / "image_review.csv")
        self.assertEqual({r["image_id"] for r in review if r["selection"] == "include"}, {"a", "c"})

    def test_freeze_requires_review_and_detects_metadata_changes(self):
        rng = np.random.default_rng(27)
        for i in range(3):
            Image.fromarray(rng.integers(0,256,(90,120,3),dtype=np.uint8)).save(self.source/f"{i}.jpg")
        files = inventory(self.source, self.out)
        rows = candidates(self.source, self.out, files)
        propose_review(self.out, files, rows)
        argv = ["curation", "freeze", "--output", str(self.root), "--version", "out"]
        with patch.object(sys, "argv", argv), self.assertRaisesRegex(ValueError, "Cannot freeze"):
            main()
        self.assertFalse((self.out/"FROZEN.json").exists())
        sources = read_rows(self.out/"source_review.csv")
        for r in sources:
            r["group_review"] = "reviewed"
        write_rows(self.out/"source_review.csv", sources)
        images = read_rows(self.out/"image_review.csv")
        for r in images:
            r.update(scale_review="reviewed", quality_review="reviewed", small="yes", medium="yes", large="yes",
                     sin_objetivo_visible="no", incierto="no")
        write_rows(self.out/"image_review.csv", images)
        records, report = partition(self.out, rows)
        self.assertEqual(report["blockers"], [])
        export(self.out, records)
        with patch.object(sys, "argv", argv):
            main()
        self.assertTrue((self.out/"FROZEN.json").exists())
        verify(self.out)
        with (self.out/"manifest.csv").open("a", encoding="utf-8") as f:
            f.write("tampered\n")
        with self.assertRaisesRegex(ValueError, "Frozen metadata changed"):
            verify(self.out)


    def test_oversampled_low_change_probe_remains_recoverable(self):
        rows = []
        for ident, value, sharpness, time, reason in [
                ("a",40,10,0.,"regular"), ("b",41,100,.5,"scene_change"), ("c",90,15,1.,"regular")]:
            rows.append(dict(image_id=ident, source_id="video", pixel_sha256=ident,
                             sha256=ident, dhash="0000000000000000", thumbnail=[value]*3072,
                             width=100,height=100,sharpness=sharpness,kind="video",
                             timestamp_seconds=time,selection_reason=reason))
        propose_review(self.out,[dict(source_id="video",source="video.mp4",kind="video")],rows)
        review = {r["image_id"]: r for r in read_rows(self.out/"image_review.csv")}
        self.assertEqual(review["a"]["selection"],"include")
        self.assertEqual(review["b"]["selection"],"reserve")
        self.assertEqual(review["c"]["selection"],"include")
        self.assertIn("recuperable",review["b"]["notes"])


if __name__ == "__main__":
    unittest.main()
