"""Collision batching must preserve each transformed oriented triangle."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from group_cad_collision_meshes import concatenate, groups_for
from benchmark_cad_collision_grouping import verify_pair
from uchuva_gazebo.robot_kinematics import pose_identity, transform_point
from uchuva_gazebo.robot_mesh_geometry import _primitive_mesh, read_collision_obj


class CollisionGroupingTests(unittest.TestCase):
    def test_paired_benchmark_rejects_control_or_protected_geometry_changes(self):
        data={'provenance': {'source': 'original'}, 'physics': {'collision_detector': 'bullet'},
              'control': {'wheel_p': 30}, 'links': [
                  {'name': 'base_link', 'collisions': [{'name': 'a', 'geometry': {'type': 'mesh'}}]},
                  {'name': 'gripper_left_jaw', 'collisions': [{'name': 'pad', 'geometry': {'type': 'mesh'}}]},
                  {'name': 'wheel', 'collisions': [{'name': 'tire', 'geometry': {'type': 'cylinder', 'radius_m': .1}}]}]}
        source=SimpleNamespace(sha256='source',to_dict=lambda:copy.deepcopy(data))
        changed=copy.deepcopy(data);changed['provenance']['source']='grouped'
        changed['links'][0]['collisions']=[{'name':'group','geometry':{'type':'mesh'}}]
        grouped=SimpleNamespace(sha256='grouped',to_dict=lambda:copy.deepcopy(changed))
        manifest={'source_robot_spec_sha256':'source','robot_spec_sha256':'grouped'}
        verify_pair(source,grouped,manifest)
        changed['control']['wheel_p']=12
        with self.assertRaisesRegex(ValueError,'other physical'):
            verify_pair(source,grouped,manifest)
        changed['control']['wheel_p']=30
        changed['links'][1]['collisions'][0]['name']='altered'
        with self.assertRaisesRegex(ValueError,'protected'):
            verify_pair(source,grouped,manifest)
        changed['links'][1]=copy.deepcopy(data['links'][1])
        changed['links'][2]['collisions'][0]['geometry']['radius_m']=.12
        with self.assertRaisesRegex(ValueError,'primitive'):
            verify_pair(source,grouped,manifest)

    def fixture(self, root):
        mesh = _primitive_mesh({'type': 'box', 'size_m': [.02, .03, .04]})
        path = root/'box.obj'
        path.write_text(''.join('v '+' '.join(map(str, p))+'\n' for p in mesh.vertices)+
                        'vn 1 0 0\n'+''.join('f '+' '.join(f'{i+1}//1' for i in f)+'\n' for f in mesh.faces))
        geometry = {'type': 'mesh', 'uri': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'bound_parameters': {'/parameters/revision': 1}, 'scale': [1, 1, 1]}
        shapes = [{'name': f'part_{i}_bounds', 'pose': pose, 'geometry': copy.deepcopy(geometry)} for i, pose in enumerate([
            pose_identity(), {'xyz_m': [.1, -.02, .03], 'quaternion_xyzw': [0, 0, .6, .8]}])]
        return shapes, mesh, path

    def test_every_oriented_face_and_vertex_survives_transforms_and_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); shapes, source, path = self.fixture(root)
            before = path.read_bytes()
            bindings, report = concatenate(shapes, root, root/'group.obj')
            vertices, faces, normals, normal_faces = read_collision_obj(root/'group.obj')
            self.assertEqual(vertices, [tuple(transform_point(s['pose'], v)) for s in shapes for v in source.vertices])
            self.assertEqual(faces, list(source.faces)+[tuple(i+len(source.vertices) for i in f) for f in source.faces])
            self.assertEqual(report['triangles'], 2*len(source.faces))
            self.assertEqual(report['admitted_solid_components'], 2)
            self.assertLess(report['maximum_transform_roundoff_m'], 1e-15)
            self.assertEqual(report['maximum_storage_roundtrip_error_m'], 0)
            self.assertEqual(report['components'][1]['face_range_zero_based_half_open'], [12, 24])
            self.assertEqual(bindings, {'/parameters/revision': 1})
            self.assertEqual(path.read_bytes(), before)

    def test_protected_links_primitives_and_different_surfaces_are_not_grouped(self):
        with tempfile.TemporaryDirectory() as tmp:
            shapes, _, _ = self.fixture(Path(tmp))
            self.assertEqual(groups_for({'name': 'base_link', 'collisions': shapes}), [[0, 1]])
            for name in ('arm_wrist_roll', 'gripper_right_jaw'):
                self.assertEqual(groups_for({'name': name, 'collisions': shapes}), [])
            other = copy.deepcopy(shapes); other[1]['surface'] = {'mu': .3}
            self.assertEqual(groups_for({'name': 'base_link', 'collisions': other}), [])
            for row in other: row['surface'] = {'mu': .3, 'fdir1': [1, 0, 0]}
            self.assertEqual(groups_for({'name': 'base_link', 'collisions': other}), [])
            primitive = {'name': 'tire', 'pose': pose_identity(), 'geometry': {'type': 'cylinder', 'radius_m': .1, 'length_m': .05}}
            self.assertEqual(groups_for({'name': 'base_link', 'collisions': [primitive, *shapes]}), [[1, 2]])

    def test_hash_and_parameter_disagreement_block_concatenation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); shapes, _, _ = self.fixture(root)
            shapes[1]['geometry']['bound_parameters']['/parameters/revision'] = 2
            with self.assertRaisesRegex(ValueError, 'Inconsistent'):
                concatenate(shapes, root, root/'group.obj')
            shapes[1]['geometry']['bound_parameters']['/parameters/revision'] = 1
            shapes[1]['geometry']['sha256'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'hash'):
                concatenate(shapes, root, root/'group.obj')


if __name__ == '__main__':
    unittest.main()
