from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.validate_repository_context_graph import is_authoritative_evidence


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "docs/repository_context_graph.json"


class RepositoryContextGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))

    def test_node_ids_and_edge_references_are_valid(self) -> None:
        identifiers = [node["id"] for node in self.graph["nodes"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        known = set(identifiers)
        for edge in self.graph["edges"]:
            self.assertIn(edge["source"], known)
            self.assertIn(edge["target"], known)

    def test_rejects_generated_evidence(self) -> None:
        self.assertFalse(is_authoritative_evidence("outputs/run/report.json"))
        self.assertFalse(is_authoritative_evidence("generated_specs/item.json"))
        self.assertTrue(is_authoritative_evidence("src/uchuva_lsystem/morphology.py"))
        for owner in [*self.graph["nodes"], *self.graph["edges"]]:
            for evidence in owner.get("evidence", []):
                self.assertTrue(is_authoritative_evidence(evidence["path"]), evidence)

    def test_rejects_legacy_without_superseding_edge(self) -> None:
        superseding = {
            (edge["source"], edge["target"])
            for edge in self.graph["edges"]
            if edge["relation"] == "supersedes"
        }
        self.assertIn(("decision.morphology_first", "decision.legacy_prototype"), superseding)

    def test_rejects_external_and_noncanonical_authority_paths(self) -> None:
        for path in ("contributions/student/a.py", "legacy/prototype.py", "./outputs/a.json",
                     "Outputs\\a.json", "output/a.json", "src/../outputs/a.json",
                     "C:\\outside\\file.py", "/outside/file.py", "docs/drafts/note.md"):
            with self.subTest(path=path):
                self.assertFalse(is_authoritative_evidence(path))


if __name__ == "__main__":
    unittest.main()
