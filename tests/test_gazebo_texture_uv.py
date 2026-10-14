"""Normals generation must preserve UV topology, including seams."""
import tempfile
from pathlib import Path
import unittest
from uchuva_gazebo.field import prepare_mesh_assets


class TextureUVTests(unittest.TestCase):
    def test_uv_indices_survive_normal_generation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'leaf.obj'
            p.write_text('o leaf\nv 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nvt 0 1\nvt 0.2 0.2\nf 1/1 2/2 3/3\nf 1/4 3/3 2/2\n')
            prepare_mesh_assets(d,[{'uri':'meshes/leaf.obj','color':[1,1,1,1]}],individual_material_files=True)
            result=p.read_text()
            self.assertIn('f 1/1/1 2/2/1 3/3/1',result)
            self.assertIn('f 1/4/2 3/3/2 2/2/2',result)
            self.assertEqual(sum(l.startswith('vt ') for l in result.splitlines()),4)

if __name__=='__main__':unittest.main()
