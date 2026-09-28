import math
import unittest
from pathlib import Path
import tempfile
from uchuva_gazebo.field import build_world, cylinder_collision, prepare_mesh_assets
from uchuva_lsystem.sparse_pilot import create_sparse_scene, marker_specs
import xml.etree.ElementTree as ET


class GazeboFieldTests(unittest.TestCase):
    def test_obj_batch_preserves_faces_and_adds_outward_normals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'plant.obj'
            path.write_text('o leaf\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
            meshes = [{'uri':'meshes/plant.obj','color':(.1,.4,.02,1)}]
            prepare_mesh_assets(folder, meshes)
            first = path.read_text()
            self.assertIn('vn 0 0 1\nf 1//1 2//1 3//1', first)
            self.assertEqual(len([s for s in first.splitlines() if s.startswith('o ')]), 1)
            self.assertIn('Kd 0.1 0.4 0.02', (Path(folder)/'surface.mtl').read_text())
            prepare_mesh_assets(folder, meshes)
            self.assertEqual(first,path.read_text())

    def test_field_keeps_marker_fronts_scale_and_camera_topics(self):
        markers = marker_specs(create_sparse_scene(7))
        patterns = {str(m['id']): [[1]*6 for _ in range(6)] for m in markers}
        root = build_world([], markers, patterns, [])
        visuals = {v.attrib['name']:v for v in root.findall('.//visual')}
        self.assertEqual(len([v for v in visuals if v.endswith('_backing')]), 72)
        for spec in markers:
            sign = spec['normal_world'][1]
            pose = [float(v) for v in visuals[f"marker_{spec['id']}_0_0"].findtext('pose').split()]
            center = spec['center_world_m']
            self.assertGreater(sign*(pose[1]-center[1]), 0)
            # First bit appears top-left when seen from the printed side.
            self.assertGreater(sign*(pose[0]-center[0]), 0)
            self.assertGreater(pose[2], center[2])
        self.assertEqual({s.findtext('topic') for s in root.findall('.//sensor')},
                         {'/uchuva/overview/image','/uchuva/drone_camera/image'})
        self.assertEqual(len(root.findall('.//collision')), 73)

    def test_rejects_duplicate_ids_and_malformed_patterns(self):
        marker = marker_specs(create_sparse_scene(7))[0]
        with self.assertRaises(ValueError):
            build_world([], [marker], {'0':[[1]]}, [])
        with self.assertRaises(ValueError):
            build_world([], [marker, marker], {'0':[[0]*6 for _ in range(6)]}, [])

    def test_cylinder_local_z_reaches_endpoints(self):
        link = ET.Element('link')
        cylinder_collision(link, 'test', (1,2,3), (4,6,3), .1)
        pose = [float(v) for v in link.findtext('collision/pose').split()]
        length = float(link.findtext('collision/geometry/cylinder/length'))
        self.assertAlmostEqual(length, 5)
        direction = (math.cos(pose[5])*math.sin(pose[4]),math.sin(pose[5])*math.sin(pose[4]),math.cos(pose[4]))
        for i,value in enumerate((4,6,3)):
            self.assertAlmostEqual(pose[i]+direction[i]*length/2,value,places=7)
        with self.assertRaises(ValueError):
            cylinder_collision(link, 'bad', (0,0,0),(0,0,0),.1)


if __name__ == '__main__':
    unittest.main()
