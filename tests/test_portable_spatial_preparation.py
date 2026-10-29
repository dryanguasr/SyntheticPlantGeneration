from pathlib import Path
import tempfile
import unittest
from scripts.prepare_spatial_plant_pool import prepare
from uchuva_lsystem.nodal_automation import read,sha


class PortableSpatialPreparationTests(unittest.TestCase):
    def test_new_run_has_frozen_configuration_and_no_historical_paths_or_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=prepare(Path(tmp)/'new',73,'blender',.5,900)
            config=read(root/'config.json');lock=read(root/'source_lock.json')
            self.assertFalse(config['previews']);self.assertTrue(config['automatic_spatial_admission'])
            self.assertEqual(read(root/'queue.json'),[dict(seed=73,origin='fresh_seed_portable_queue')])
            self.assertEqual(read(root/'budget.json')['limit_active_seconds'],1800)
            self.assertTrue(all(sha(p)==h for p,h in lock['inputs'].items()))
            self.assertFalse((root/'controller_identity.json').exists())
            with self.assertRaises(FileExistsError):prepare(root,73,'blender')
