"""The preparation CLI exports checked inputs without inventing native PASS."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_robot_model import prepare


class RobotPreparationTests(unittest.TestCase):
    def test_proxy_preparation_exports_effective_configuration_without_native_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)/'robot'
            report=prepare('proxy_v1',destination)
            self.assertTrue(report['static_preparation_passed'],report)
            self.assertEqual(report['status'],'NO EJECUTADO')
            self.assertEqual(report['evidence_status']['harvest_mission'],'NO EJECUTADO')
            self.assertTrue((destination/'robot_resolved.json').is_file())
            self.assertTrue((destination/'model.sdf').is_file())
            self.assertIn('model.sdf',report['files_sha256'])
            with self.assertRaises(FileExistsError):prepare('proxy_v1',destination)

    def test_incomplete_profile_has_concrete_blocker_and_no_fake_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)/'blocked'
            report=prepare('cad_nominal_pending',destination)
            self.assertFalse(report['static_preparation_passed'])
            self.assertEqual(report['status'],'NO EJECUTADO')
            self.assertTrue(report['missing_evidence'])
            self.assertIn('Incomplete robot profile',report['blocker'])
            self.assertFalse((destination/'model.sdf').exists())
            self.assertTrue((destination/'preparation_report.json').is_file())


if __name__=='__main__':unittest.main()
