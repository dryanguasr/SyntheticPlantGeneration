from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.validate_repository_context_graph import (
    validate_graph,
    validate_graph_data,
)


class RepositoryContextGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.graph_path = cls.repo_root / "docs/repository_context_graph.json"
        cls.graph = json.loads(cls.graph_path.read_text(encoding="utf-8"))

    def _validate_copy(self, graph: dict) -> dict:
        return validate_graph_data(
            graph,
            repo_root=self.repo_root,
            graph_path=self.graph_path,
        )

    def test_repository_graph_is_valid(self) -> None:
        report = validate_graph(self.repo_root, self.graph_path)
        self.assertEqual(report["status"], "valid", report["errors"])
        self.assertEqual(report["covered_public_modules"], 34)

    def test_all_public_modules_are_represented(self) -> None:
        represented = {
            path
            for node in self.graph["nodes"]
            for path in node["paths"]
            if path.startswith("src/uchuva_lsystem/")
        }
        expected = {
            path.relative_to(self.repo_root).as_posix()
            for path in (self.repo_root / "src/uchuva_lsystem").glob("*.py")
        }
        self.assertEqual(represented & expected, expected)

    def test_primary_pipeline_is_connected_and_complete(self) -> None:
        expected = [
            "module.parameters",
            "module.phenology",
            "module.grammar",
            "module.morphology",
            "module.scene",
            "module.support",
            "module.growth",
            "module.spatial",
            "module.cultivation",
            "module.collisions",
            "module.validation",
            "module.blender_geometry",
            "module.blender_scene",
            "module.blender_annotations",
            "module.yolo_export",
            "module.blender_dataset",
            "module.domain_analysis",
        ]
        self.assertEqual(self.graph["project"]["primary_pipeline"], expected)
        connected = {
            frozenset((edge["source"], edge["target"]))
            for edge in self.graph["edges"]
        }
        for left, right in zip(expected, expected[1:]):
            self.assertIn(frozenset((left, right)), connected)

    def test_graph_serialization_is_deterministic(self) -> None:
        first = json.dumps(
            self.graph, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        second_graph = json.loads(self.graph_path.read_text(encoding="utf-8"))
        second = json.dumps(
            second_graph, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        self.assertEqual(hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest())
        self.assertNotIn("generated_at", self.graph)

    def test_agents_file_points_to_the_context_graph(self) -> None:
        agents = (self.repo_root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("docs/repository_context_graph.json", agents)
        self.assertIn("`AGENTS.md` remains the prescriptive authority", agents)

    def test_rejects_schema_duplicate_id_and_unknown_endpoint(self) -> None:
        graph = copy.deepcopy(self.graph)
        graph["schema_version"] = "9.9"
        graph["nodes"].append(copy.deepcopy(graph["nodes"][0]))
        graph["edges"].append(
            {
                "source": "module.grammar",
                "relation": "depends_on",
                "target": "module.does_not_exist",
                "evidence": [
                    {"path": "src/uchuva_lsystem/grammar.py", "locator": "def generate_morphology_tree"}
                ],
            }
        )
        report = self._validate_copy(graph)
        joined = "\n".join(report["errors"])
        self.assertEqual(report["status"], "invalid")
        self.assertIn("schema_version", joined)
        self.assertIn("Duplicate node id", joined)
        self.assertIn("unknown target node", joined)

    def test_rejects_mutable_original_dataset(self) -> None:
        graph = copy.deepcopy(self.graph)
        for node in graph["nodes"]:
            if node["id"] == "constraint.original_dataset_immutable":
                node["summary"] = "Dataset Original puede modificarse durante el analisis."
                break
        report = self._validate_copy(graph)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("immutable" in item for item in report["errors"]))

    def test_rejects_pure_module_dependency_on_blender(self) -> None:
        graph = copy.deepcopy(self.graph)
        graph["edges"].append(
            {
                "source": "module.morphology",
                "relation": "depends_on",
                "target": "module.blender_geometry",
                "evidence": [
                    {"path": "AGENTS.md", "locator": "Keep Blender-specific code separate"}
                ],
            }
        )
        report = self._validate_copy(graph)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(
            any("Pure module cannot depend on Blender" in item for item in report["errors"])
        )

    def test_rejects_legacy_without_superseding_edge(self) -> None:
        graph = copy.deepcopy(self.graph)
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if not (
                edge["source"] == "decision.morphology_first"
                and edge["relation"] == "supersedes"
                and edge["target"] == "decision.legacy_prototype"
            )
        ]
        report = self._validate_copy(graph)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("must supersede" in item for item in report["errors"]))

    def test_rejects_generated_evidence(self) -> None:
        graph = copy.deepcopy(self.graph)
        graph["nodes"][0]["evidence"].append(
            {"path": "outputs/specs/morphology_tree_seed_0.json", "locator": "seed"}
        )
        report = self._validate_copy(graph)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(
            any("generated output" in item.lower() for item in report["errors"])
        )

    def test_json_cli_report_is_machine_readable(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(self.repo_root / "scripts/validate_repository_context_graph.py"),
                "--json",
            ],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "valid")


if __name__ == "__main__":
    unittest.main()
