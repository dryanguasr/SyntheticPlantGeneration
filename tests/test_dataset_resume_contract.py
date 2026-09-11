import json
from pathlib import Path
import tempfile
import unittest

from uchuva_lsystem.blender_dataset import DatasetConfig, generate_annotation_dataset


class DatasetResumeContractTests(unittest.TestCase):
    def test_changed_configuration_fails_before_metadata_write_or_blender(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = DatasetConfig(output_dir=root)
            original = json.dumps(old.to_dict())
            (root / "generation_config.json").write_text(original)
            (root / "manifest.jsonl").write_text("historical record\n")
            changed = DatasetConfig(output_dir=root, resume=True, phenology_model="legacy_independent")
            with self.assertRaisesRegex(ValueError, "phenology_model"):
                generate_annotation_dataset(changed)
            self.assertEqual((root / "generation_config.json").read_text(), original)
            self.assertEqual((root / "manifest.jsonl").read_text(), "historical record\n")
            self.assertFalse((root / "data.yaml").exists())

    def test_missing_configuration_is_not_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.jsonl").write_text("historical record\n")
            with self.assertRaisesRegex(ValueError, "without generation_config"):
                generate_annotation_dataset(DatasetConfig(output_dir=root, resume=True))
            self.assertFalse((root / "generation_config.json").exists())


if __name__ == "__main__":
    unittest.main()
