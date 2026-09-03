"""Checks for the read-only evidence export, without training dependencies."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export_classical_augmentation_v2_review.py"
SPEC = importlib.util.spec_from_file_location("v2_review_export", SCRIPT)
export = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export)


class ReviewExportTests(unittest.TestCase):
    def test_allowlist_excludes_photos_labels_and_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "outputs/classical_augmentation_v2"
            for name in ("runs/test/args.yaml", "runs/test/results.csv", "runs/test/weights/model.pt",
                         "datasets/full/images/train/photo.jpg", "datasets/full/labels/train/a.txt",
                         "datasets/full/preview_contact_sheet.jpg", "datasets/full/manifests/derived_samples.jsonl"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"test")
            with patch.object(export, "ROOT", root), patch.object(export, "SOURCE", source):
                names = [p.name for p in export.selected_files()]
            self.assertIn("args.yaml", names)
            self.assertIn("preview_contact_sheet.jpg", names)
            self.assertIn("derived_samples.jsonl", names)
            self.assertNotIn("photo.jpg", names)
            self.assertNotIn("model.pt", names)
            self.assertNotIn("a.txt", names)

    def test_verifier_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "result.json"
            path.write_text("{}", encoding="utf-8")
            (root / "inventory.json").write_text(json.dumps({"files": [{
                "path": path.name, "bytes": 2, "sha256": export.sha256(path)}]}), encoding="utf-8")
            export.verify(root)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                export.verify(root)

    def test_credentials_stop_export_without_printing_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "environment.json"
            path.write_text(json.dumps({"url": "https://user:password@example.invalid"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "manual review required"):
                export.check_text(path)


if __name__ == "__main__":
    unittest.main()
