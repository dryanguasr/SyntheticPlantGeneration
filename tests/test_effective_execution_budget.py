import json
from pathlib import Path
import tempfile
import unittest
from uchuva_lsystem.execution_budget import remaining_seconds,awake_seconds
from uchuva_lsystem.segmentation_cycles import check_deadline


class EffectiveBudgetTests(unittest.TestCase):
    def test_sleep_or_old_calendar_deadline_does_not_consume_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'run.json').write_text(json.dumps({'deadline_unix':0}))
            (root/'effective_budget.json').write_text(json.dumps({'limit_seconds':43200,'historical_execution_seconds':3600}))
            (root/'execution_jobs').mkdir()
            (root/'execution_jobs'/'job.json').write_text(json.dumps({'awake_elapsed_seconds':20,'started_utc':'1999-01-01'}))
            self.assertEqual(remaining_seconds(root),39580)
            check_deadline(root)
            (root/'execution_jobs'/'job.json').write_text(json.dumps({'awake_elapsed_seconds':40000}))
            with self.assertRaises(TimeoutError):check_deadline(root)

    def test_awake_clock_is_monotonic(self):
        first=awake_seconds();self.assertGreaterEqual(awake_seconds(),first)

    def test_preparation_time_includes_jobs_without_double_charging(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'effective_budget.json').write_text(json.dumps({'limit_seconds':43200,'historical_execution_seconds':3600}))
            (root/'controller_sessions').mkdir();(root/'execution_jobs').mkdir()
            (root/'controller_sessions'/'session.json').write_text(json.dumps({
                'started_utc':'2026-10-03T16:00:00','ended_utc':'2026-10-03T17:00:00',
                'state':'complete','awake_elapsed_seconds':3600}))
            (root/'execution_jobs'/'covered.json').write_text(json.dumps({
                'started_utc':'2026-10-03T16:15:00','ended_utc':'2026-10-03T16:30:00',
                'awake_elapsed_seconds':900}))
            (root/'execution_jobs'/'later.json').write_text(json.dumps({
                'started_utc':'2026-10-03T18:00:00','ended_utc':'2026-10-03T18:10:00',
                'awake_elapsed_seconds':600}))
            self.assertEqual(remaining_seconds(root),35400)


if __name__=='__main__':unittest.main()
