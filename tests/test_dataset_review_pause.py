from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from uchuva_lsystem.nodal_automation import write
import complete_optimized_dataset as controller


class ReviewPauseTests(unittest.TestCase):
    def test_active_review_pause_prevents_prepare_and_process_launch(self):
        with TemporaryDirectory(dir=ROOT/'outputs') as folder:
            root=Path(folder);write(root/'pause_requested.json',dict(active=True))
            with patch.object(controller,'prepare') as prepare,patch.object(controller.subprocess,'Popen') as launch:
                controller.run(root/'source',root)
                prepare.assert_not_called();launch.assert_not_called()

    def test_archived_or_explicitly_released_pause_is_inactive(self):
        with TemporaryDirectory(dir=ROOT/'outputs') as folder:
            root=Path(folder);self.assertFalse(controller.review_pause_active(root))
            write(root/'pause_requested.json',dict(active=False))
            self.assertFalse(controller.review_pause_active(root))


if __name__=='__main__':unittest.main()
