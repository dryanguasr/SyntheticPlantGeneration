"""Pure package/integration checks. These do not execute the simulator."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from uchuva_gazebo.harvest_pilot import build_pilot, load_verified_package, read_config, write_package


class HarvestPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = read_config()
        cls.bundle = build_pilot(cls.config)

    def test_world_contains_physical_robot_and_separate_fruits(self):
        world = ET.fromstring(self.bundle['sdf']).find('world')
        manifest = self.bundle['manifest']
        self.assertEqual(len(manifest['plants']), 3)
        self.assertEqual(len(manifest['fruits']), 6)
        models = {m.get('name'): m for m in world.findall('model')}
        for fruit in manifest['fruits']:
            self.assertEqual(models[fruit['model']].findtext('static'), 'false')
            self.assertEqual(models[fruit['parent_model']].findtext('static'), 'true')
            self.assertIsNotNone(models[fruit['model']].find('link/inertial'))
        plugin = world.find("plugin[@name='uchuva::HarvestSystem']")
        self.assertEqual(len(plugin.findall('fruit')), 6)
        self.assertEqual(plugin.findtext('tool_link'), 'tool_link')
        self.assertEqual(len(models['harvester'].findall('joint')), 9)
        self.assertEqual(len(models['collection_bin'].findall('link/collision')), 5)
        self.assertEqual(manifest['validation']['physical_harvest'], 'pending_gazebo')
        for name, model in models.items():
            if name != 'harvester':
                self.assertTrue(all(c.findtext('surface/contact/collide_bitmask') == '65535'
                                    for c in model.findall('.//collision')))

    def test_plugin_cut_coordinates_are_local_and_roundtrip_world(self):
        world = ET.fromstring(self.bundle['sdf']).find('world')
        plugin = world.find("plugin[@name='uchuva::HarvestSystem']")
        inventory = {f['id']: f for f in self.bundle['manifest']['fruits']}
        for item in plugin.findall('fruit'):
            fruit = inventory[item.get('id')]
            relative = [float(v) for v in item.findtext('cut_point').split()]
            for actual, expected in zip([a + b for a, b in zip(relative, fruit['center_world_m'])], fruit['cut_point_world_m']):
                self.assertAlmostEqual(actual, expected, places=8)

    def test_package_relocation_checksums_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'initial'
            with patch('uchuva_gazebo.harvest_pilot.build_pilot', return_value=deepcopy(self.bundle)):
                manifest = write_package(path, self.config)
            relocated = Path(temp) / 'relocated'
            path.rename(relocated)
            loaded = load_verified_package(relocated)
            self.assertEqual(loaded['fruits'], manifest['fruits'])
            with patch('uchuva_gazebo.harvest_pilot.build_pilot', return_value=deepcopy(self.bundle)):
                with self.assertRaises(FileExistsError):
                    write_package(relocated, self.config)
            mesh = next(iter(self.bundle['meshes']))
            with (relocated / mesh).open('a') as stream:
                stream.write('# changed\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                load_verified_package(relocated)

    def test_manifest_cannot_request_files_outside_package(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'package'
            with patch('uchuva_gazebo.harvest_pilot.build_pilot', return_value=deepcopy(self.bundle)):
                manifest = write_package(path, self.config)
            manifest['files_sha256']['../private-input.txt'] = 'not-a-digest'
            (path / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'escaped'):
                load_verified_package(path)

    def test_all_waypoints_reachable_and_unreachable_robot_fails_preparation(self):
        mission = self.bundle['manifest']['mission']
        self.assertEqual(len(mission['targets']), 6)
        for target in mission['targets']:
            self.assertEqual(target['workspace_check'], 'passed')
            self.assertEqual(target['collision_and_dynamic_validation'], 'pending_gazebo')
        small_robot = deepcopy(self.config)
        small_robot['robot'] = {'upper_arm_m': .08, 'forearm_m': .08, 'tool_length_m': .03}
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'must_not_exist'
            with self.assertRaises(ValueError):
                write_package(output, small_robot)
            self.assertFalse(output.exists())

    def test_model_interface_topics_and_sources_are_reproducible(self):
        second = build_pilot(self.config)
        self.assertEqual(self.bundle['sdf'], second['sdf'])
        self.assertEqual(self.bundle['meshes'], second['meshes'])
        self.assertEqual(self.bundle['manifest'], second['manifest'])
        self.assertNotIn('import gz', Path(__import__('uchuva_gazebo.harvest_pilot', fromlist=['x']).__file__).read_text())
        for name in self.bundle['manifest']['robot']['arm_joint_names']:
            self.assertIn(f'/harvester/arm/{name}/cmd_pos', self.bundle['bridge'])
        self.assertIn('ROS_TO_GZ', self.bundle['bridge'])


if __name__ == '__main__':
    unittest.main()
