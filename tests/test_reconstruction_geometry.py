"""Keep analytical COLMAP points distinct from incompatible PLY representations."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from uchuva_reconstruction.geometry import read_colmap_points, write_colmap_points


class ReconstructionGeometryTests(unittest.TestCase):
    def test_point_roundtrip_preserves_normals_and_color(self):
        dtype=[(n,'<f4') for n in ('x','y','z','nx','ny','nz')]+[(n,'u1') for n in ('red','green','blue')]
        points=np.zeros(2,dtype=dtype);points['x']=[-2,3];points['nz']=1;points['green']=[17,200]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cloud.ply';write_colmap_points(path,points)
            np.testing.assert_array_equal(points,read_colmap_points(path))
            path.write_bytes(path.read_bytes()[:-3])
            with self.assertRaisesRegex(ValueError,'Truncated'):read_colmap_points(path)

    def test_gaussian_properties_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'splats.ply'
            path.write_bytes(b'ply\nformat binary_little_endian 1.0\nelement vertex 1\nproperty float x\nproperty float opacity\nend_header\n')
            with self.assertRaisesRegex(ValueError,'Gaussian'):read_colmap_points(path)


if __name__=='__main__':unittest.main()
