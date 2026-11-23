"""Geometric winding repair must preserve every native coordinate and normal."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts"))
from repair_inventor_mesh_winding import repair_mesh_bytes


class NativeFacetRepairTests(unittest.TestCase):
    def test_reversed_and_collapsed_faces_preserve_native_data(self):
        prefix = b"# Native example\r\nv 0 0 0\r\nv 1 0 0\r\nv 0 1 0\r\nvn 0 0 1\r\n"
        original = prefix+b"f 1//1 3//1 2//1\r\nf 1//1 1//1 2//1\r\n"
        output, report = repair_mesh_bytes(original)
        self.assertEqual(output, prefix+b"f 1//1 2//1 3//1\r\n")
        self.assertEqual(report["reversed_faces"], 1)
        self.assertEqual(report["removed_degenerate_triangles"], 1)
        self.assertEqual(report["derived_triangles"], 1)
        self.assertNotEqual(report["original_sha256"], report["derived_sha256"])
        self.assertEqual(repair_mesh_bytes(output)[0], output)

    def test_correct_winding_is_byte_identical(self):
        original = b"v 0 0 0\nv 1 0 0\nv 0 1 0\nvn 0 0 1\nf 1//1 2//1 3//1\n"
        output, report = repair_mesh_bytes(original)
        self.assertEqual(output, original)
        self.assertEqual(report["changes"], [])

    def test_invalid_normal_index_is_rejected(self):
        with self.assertRaises(ValueError):
            repair_mesh_bytes(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nvn 0 0 1\nf 1//2 2//1 3//1\n")


if __name__ == "__main__":
    unittest.main()
