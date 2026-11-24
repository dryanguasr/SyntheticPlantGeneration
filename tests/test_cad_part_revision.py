"""A leaf replacement must preserve mechanism state and recompute full inertia."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from apply_cad_part_revision import apply_revision
from prepare_cad_robot import aggregate_inertia


class CadPartRevisionTests(unittest.TestCase):
    def fixture(self):
        poses = [{'xyz_m': [0.01, 0.02, 0.03], 'quaternion_xyzw': [0, 0, .6, .8]},
                 {'xyz_m': [-.02, 0, .04], 'quaternion_xyzw': [0, 0, 0, 1]}]
        masses = [dict(mass_kg=m, center_of_mass_m=[.001, .002, -.003],
            xyz_moments_kg_m2=[.0002*m, .0003*m, .0004*m, .00001*m, .00002*m, .00003*m])
            for m in (.02, .01)]
        records = [dict(occurrence_id=str(i), occurrence_name_path=[str(i)], link='old_group',
                       link_T_document=poses[i], mass_properties=masses[i],
                       mesh_sha256=str(i)*64, source_sha256='a'*64) for i in range(2)]
        visuals = [dict(name=f'part_{i}', pose=poses[i], geometry={
            'type': 'mesh', 'uri': f'{i}.obj', 'sha256': str(i)*64, 'bound_parameters': {'/parameters/base_revision': 1}})
                   for i in range(2)]
        collisions = [{**copy.deepcopy(v), 'name': v['name']+'_bounds'} for v in visuals]
        data = dict(links=[dict(name='jaw', visuals=visuals, collisions=collisions,
            inertial=aggregate_inertia(list(zip(masses, poses))))], parameters={'base_revision': 1},
            parameter_metadata={}, provenance={'source': 'fixture', 'method': 'fixture'},
            joints=[{'name': 'unchanged'}], physics={'solver': 'unchanged'}, closures=[], control={'unchanged': 123})
        updated = copy.deepcopy(records[0])
        updated['mesh_sha256'] = 'c'*64
        updated['source_sha256'] = 'd'*64
        updated['mass_properties']['mass_kg'] = .015
        updated['mass_properties']['center_of_mass_m'] = [.004, -.003, .002]
        updated['mass_properties']['xyz_moments_kg_m2'] = [x*.75 for x in masses[0]['xyz_moments_kg_m2']]
        replacement = dict(full_robot_part_index=0, unchanged_L2_part_index=1,
                           original_import_record=copy.deepcopy(records[0]), replacement_import_record=updated)
        return data, {'parts': records}, replacement

    def apply(self, data, imported, replacement):
        return apply_revision(data, imported, replacement,
            {'uri': 'new.obj', 'sha256': 'c'*64}, {'uri': 'collision.obj', 'sha256': 'e'*64},
            {'status': 'derivado_de_CAD', 'source': 'fixture', 'revision': '1', 'method': 'fixture'})

    def test_rebuilds_entire_link_tensor_and_preserves_other_leaf(self):
        data, imported, replacement = self.fixture()
        snapshot = copy.deepcopy(data)
        result, report = self.apply(data, imported, replacement)
        self.assertEqual(data, snapshot)
        self.assertTrue(report['old_inertia_reconstructed_exactly'])
        self.assertAlmostEqual(report['native_leaf_mass_delta_kg'], -.005)
        expected = aggregate_inertia([(replacement['replacement_import_record']['mass_properties'],
                                      data['links'][0]['visuals'][0]['pose']),
                                     (imported['parts'][1]['mass_properties'], data['links'][0]['visuals'][1]['pose'])])
        self.assertEqual(result['links'][0]['inertial'], expected)
        self.assertEqual(result['links'][0]['visuals'][1], data['links'][0]['visuals'][1])
        for key in ('joints', 'physics', 'closures', 'control'):
            self.assertEqual(result[key], data[key])

    def test_rejects_stale_import_transform_or_unaccounted_mass(self):
        for mutation in ('record', 'placement', 'inertia'):
            data, imported, replacement = self.fixture()
            if mutation == 'record':
                replacement['original_import_record']['source_sha256'] = 'f'*64
            elif mutation == 'placement':
                replacement['replacement_import_record']['link_T_document']['xyz_m'][0] += .001
            else:
                data['links'][0]['inertial']['mass_kg'] += .001
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.apply(data, imported, replacement)

    def test_rejects_closure_mass_partition(self):
        data, imported, replacement = self.fixture()
        data['closures'] = [{'body': 'jaw', 'auxiliary': 'aux'}]
        with self.assertRaisesRegex(ValueError, 'mass-partitioned'):
            self.apply(data, imported, replacement)


if __name__ == '__main__':
    unittest.main()
