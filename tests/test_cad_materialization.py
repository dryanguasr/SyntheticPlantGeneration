import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("materialize_robot_cad", Path(__file__).resolve().parents[1]/"scripts/materialize_robot_cad.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MaterializationTests(unittest.TestCase):
    def test_same_size_existing_file_is_not_new_revision_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root/"part.ipt"
            target.write_bytes(b"old")
            with patch.object(MODULE.urllib.request, "urlopen") as network:
                result = MODULE.materialize({"path": "part.ipt", "id": "new_revision", "size": 3,
                                             "download_url": "private_url"}, root)
                network.assert_not_called()
            self.assertEqual(result["status"], "existing_unverified")
            self.assertNotIn("sha256", result)
            self.assertNotIn("download_url", result)
            self.assertEqual(target.read_bytes(), b"old")

    def test_parent_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                MODULE.materialize({"path": "../part.ipt", "size": 1}, Path(directory).resolve())


if __name__ == "__main__":
    unittest.main()
