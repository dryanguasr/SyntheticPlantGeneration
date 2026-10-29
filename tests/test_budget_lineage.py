import json
from pathlib import Path
import tempfile
import unittest
from uchuva_lsystem.budget_lineage import verify_frozen_inputs
from uchuva_lsystem.nodal_automation import sha


class AuthorizedBudgetLineageTests(unittest.TestCase):
    def test_only_exact_authorized_extension_preserves_the_original_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=dict(awake_started_seconds=10,excluded_intervals=[],limit_active_seconds=28800)
            previous=root/'previous.json';previous.write_text(json.dumps(old))
            budget=root/'budget.json';budget.write_text(json.dumps(dict(old,limit_active_seconds=30000+28800)))
            approval=root/'approval.json';approval.write_text(json.dumps(dict(previous_active_seconds=30000)))
            record=dict(previous_budget=str(previous),previous_sha256=sha(previous),current_sha256=sha(budget),authorization=str(approval),authorization_sha256=sha(approval))
            lineage=root/'authorized_budget_revision.json';lineage.write_text(json.dumps(record));locked={str(budget):sha(previous)}
            self.assertEqual(verify_frozen_inputs(root,locked),[])
            altered=dict(old,limit_active_seconds=30000+28801);budget.write_text(json.dumps(altered))
            self.assertEqual(verify_frozen_inputs(root,locked),[str(budget)])
            record['current_sha256']=sha(budget);lineage.write_text(json.dumps(record))
            self.assertEqual(verify_frozen_inputs(root,locked),[str(budget)])
            budget.write_text(json.dumps(dict(old,awake_started_seconds=11,limit_active_seconds=30000+28800)))
            record['current_sha256']=sha(budget);lineage.write_text(json.dumps(record))
            self.assertEqual(verify_frozen_inputs(root,locked),[str(budget)])
