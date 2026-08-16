from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from uchuva_lsystem.spatial_calibration import derive_spatially_calibrated_dataset


class SpatialCalibrationTests(unittest.TestCase):
    def test_calibration_excludes_real_test_and_preserves_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split in ("train", "val", "test"):
                _write_example(real, split, "real", "0 0.5 0.5 0.3 0.3\n", real_layout=True)
                _write_example(synthetic, split, "synthetic", "0 0.5 0.5 0.1 0.1\n")
            source_image = synthetic / "images" / "train" / "synthetic.jpg"
            source_bytes = source_image.read_bytes()

            report = derive_spatially_calibrated_dataset(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "derived",
            )

            self.assertEqual(report["real_splits_used"], ["train", "val"])
            self.assertEqual(report["synthetic_fit_splits_used"], ["train"])
            self.assertNotIn("test", report["real_splits_used"])
            self.assertEqual(source_bytes, source_image.read_bytes())
            derived_fields = (
                root / "derived" / "labels" / "train" / "synthetic.txt"
            ).read_text(encoding="utf-8").split()
            self.assertGreater(float(derived_fields[3]), 0.1)
            self.assertGreater(float(derived_fields[4]), 0.1)
            self.assertTrue((root / "derived" / "spatial_calibration.json").is_file())
            self.assertEqual(report["image_count"], 3)

    def test_refuses_real_test_for_fitting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "real train/val only"):
                derive_spatially_calibrated_dataset(
                    real_root=root / "real",
                    synthetic_root=root / "synthetic",
                    output_root=root / "derived",
                    real_splits=("train", "test"),
                )


def _write_example(
    root: Path,
    split: str,
    stem: str,
    label: str,
    *,
    real_layout: bool = False,
) -> None:
    image_folder = "IMAGENES" if real_layout else "images"
    label_folder = "LABELS" if real_layout else "labels"
    image_path = root / image_folder / split / f"{stem}.jpg"
    label_path = root / label_folder / split / f"{stem}.txt"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 40), (40, 120, 40)).save(image_path, quality=100)
    label_path.write_text(label, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
