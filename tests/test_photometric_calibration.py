from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageStat

from uchuva_lsystem.photometric_calibration import derive_photometrically_calibrated_dataset


class PhotometricCalibrationTests(unittest.TestCase):
    def test_calibration_uses_no_real_test_and_preserves_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            synthetic = root / "synthetic"
            for split in ("train", "val", "test"):
                _write_image(real / "IMAGENES" / split / "real.jpg", (160, 170, 120))
                _write_image(synthetic / "images" / split / "synthetic.jpg", (50, 80, 40))
                label = synthetic / "labels" / split / "synthetic.txt"
                label.parent.mkdir(parents=True, exist_ok=True)
                label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            source_bytes = (synthetic / "images" / "train" / "synthetic.jpg").read_bytes()
            report = derive_photometrically_calibrated_dataset(
                real_root=real,
                synthetic_root=synthetic,
                output_root=root / "derived",
            )
            self.assertEqual(report["real_splits_used"], ["train", "val"])
            self.assertNotIn("test", report["real_splits_used"])
            self.assertEqual(
                (root / "derived" / "labels" / "test" / "synthetic.txt").read_text(encoding="utf-8"),
                "0 0.5 0.5 0.2 0.2\n",
            )
            self.assertEqual(
                source_bytes,
                (synthetic / "images" / "train" / "synthetic.jpg").read_bytes(),
            )
            with Image.open(root / "derived" / "images" / "train" / "synthetic.jpg") as image:
                self.assertGreater(sum(ImageStat.Stat(image).mean), 300.0)


def _write_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path, quality=100)


if __name__ == "__main__":
    unittest.main()
