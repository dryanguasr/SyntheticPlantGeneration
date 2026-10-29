import json
from pathlib import Path
import tempfile
import unittest
from scripts.resume_spatial_dataset import verify_bank,archive_incomplete
from uchuva_lsystem.nodal_automation import sha


class FrozenDatasetResumeTests(unittest.TestCase):
    def test_changed_sources_or_incomplete_pool_cannot_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);bank=root/'dataset';bank.mkdir();source=root/'input';source.write_text('frozen')
            (bank/'source_lock.json').write_text(json.dumps(dict(files={str(source):sha(source)})))
            (bank/'pool_lock.json').write_text(json.dumps(dict(plants=[])))
            with self.assertRaises(ValueError):verify_bank(root)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'Incompatible'):verify_bank(root)

    def test_only_new_uncommitted_scene_data_can_be_archived(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();bank=root/'dataset'
            for name in ['scene_001','scene_002','scene_003']:(bank/'scenes'/name).mkdir(parents=True)
            v=bank/'views/scene_003_view_000';v.mkdir(parents=True);(v/'rgb.png').write_bytes(b'partial')
            archive_incomplete(root,bank,{'scene_001'},[dict(scene_id='scene_002')],root/'archive')
            self.assertTrue((bank/'scenes/scene_001').exists());self.assertTrue((bank/'scenes/scene_002').exists())
            self.assertFalse((bank/'scenes/scene_003').exists());self.assertTrue((root/'archive/views/scene_003_view_000/rgb.png').exists())
