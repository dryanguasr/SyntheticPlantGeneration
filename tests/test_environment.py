"""Clear failures when the interpreter or pinned packages differ from requirements.txt."""

from __future__ import annotations

import importlib.metadata
import sys
import unittest

MINIMUM_PYTHON = (3, 11)
PINNED_ULTRALYTICS = "8.4.114"


class EnvironmentTests(unittest.TestCase):
    def test_python_version_supports_hashlib_file_digest(self):
        self.assertGreaterEqual(
            sys.version_info[:2], MINIMUM_PYTHON,
            f"Python {sys.version.split()[0]} no es compatible; el repositorio requiere "
            f"Python {'.'.join(map(str, MINIMUM_PYTHON))}+ (hashlib.file_digest).")

    def test_ultralytics_matches_reported_version(self):
        try:
            installed = importlib.metadata.version("ultralytics")
        except importlib.metadata.PackageNotFoundError:
            self.skipTest("ultralytics no instalado; usar pip install -r requirements.txt")
        self.assertEqual(
            installed, PINNED_ULTRALYTICS,
            f"Ultralytics {installed} cambia el emparejamiento de AP; los informes y "
            f"tests usan {PINNED_ULTRALYTICS} (pip install -r requirements.txt).")


if __name__ == "__main__":
    unittest.main()
