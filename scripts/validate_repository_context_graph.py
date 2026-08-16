"""Validate the evidence-backed repository context graph.

The graph is intentionally stored as plain JSON and this validator uses only
the Python standard library so it can run outside Blender and without adding a
runtime dependency to the plant generator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


GRAPH_RELATIVE_PATH = Path("docs/repository_context_graph.json")
ALLOWED_NODE_TYPES = {
    "subsystem",
    "entrypoint",
    "artifact",
    "test",
    "constraint",
    "decision",
}
ALLOWED_RELATIONS = {
    "depends_on",
    "produces",
    "validates",
    "tests",
    "configures",
    "must_preserve",
    "supersedes",
}
GENERATED_PREFIXES = ("outputs/", "generated_specs/")
PURE_MODULE_IDS = {
    "module.morphology",
    "module.parameters",
    "module.phenology",
    "module.texture_assets",
    "module.grammar",
    "module.scene",
    "module.cultivation",
    "module.collisions",
    "module.validation",
    "module.exporters",
    "module.human_validation",
    "module.yolo_export",
    "module.domain_analysis",
    "module.composition_calibration",
    "module.detection_diagnostics",
    "module.hybrid_experiments",
    "module.hybrid_training",
    "module.photometric_calibration",
    "module.spatial_calibration",
}
BLENDER_MODULE_IDS = {
    "module.blender_annotations",
    "module.blender_dataset",
    "module.blender_environment",
    "module.blender_geometry",
    "module.blender_pilot",
    "module.blender_review",
    "module.blender_scene",
}
REQUIRED_NODE_IDS = {
    "decision.morphology_first",
    "decision.legacy_prototype",
    "constraint.original_dataset_immutable",
    "constraint.closed_calyx_hidden_fruit",
    "constraint.collision_taxonomy",
    "constraint.reproducible_seeds",
    "artifact.morphology_tree",
    "artifact.blender_scene",
    "artifact.yolo_dataset",
    "artifact.domain_report",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _safe_repo_path(repo_root: Path, raw_path: str) -> Path | None:
    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    resolved = (repo_root / relative).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return resolved


def _validate_evidence(
    evidence: Any,
    *,
    owner: str,
    repo_root: Path,
    errors: list[str],
) -> None:
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{owner}: evidence must be a non-empty list.")
        return

    for index, item in enumerate(evidence):
        label = f"{owner}.evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: evidence entry must be an object.")
            continue
        raw_path = item.get("path")
        locator = item.get("locator")
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"{label}: path must be a non-empty string.")
            continue
        normalized = raw_path.replace("\\", "/")
        if normalized.startswith(GENERATED_PREFIXES):
            errors.append(f"{label}: generated output cannot be authoritative evidence.")
            continue
        resolved = _safe_repo_path(repo_root, raw_path)
        if resolved is None:
            errors.append(f"{label}: path must remain relative to the repository.")
            continue
        if not resolved.is_file():
            errors.append(f"{label}: evidence file does not exist: {raw_path}")
            continue
        if not isinstance(locator, str) or not locator:
            errors.append(f"{label}: locator must be a non-empty string.")
            continue
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{label}: evidence file is not UTF-8 text: {raw_path}")
            continue
        if locator not in text:
            errors.append(f"{label}: locator not found in {raw_path}: {locator!r}")


def validate_graph_data(
    graph: Any,
    *,
    repo_root: Path,
    graph_path: Path,
) -> dict[str, Any]:
    """Validate an already parsed graph and return a serializable report."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(graph, dict):
        return _report(graph_path, [], [], ["Graph root must be a JSON object."], [])

    required_root = {"schema_version", "project", "nodes", "edges"}
    missing_root = sorted(required_root - set(graph))
    if missing_root:
        errors.append(f"Missing root fields: {', '.join(missing_root)}")
    if graph.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'.")

    project = graph.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object.")
        project = {}

    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        errors.append("nodes must be a list.")
        nodes = []
    edges = graph.get("edges")
    if not isinstance(edges, list):
        errors.append("edges must be a list.")
        edges = []

    node_ids: list[str] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    represented_paths: set[str] = set()
    for index, node in enumerate(nodes):
        owner = f"nodes[{index}]"
        if not isinstance(node, dict):
            errors.append(f"{owner}: node must be an object.")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"{owner}: id must be a non-empty string.")
            continue
        node_ids.append(node_id)
        if node_id in node_by_id:
            errors.append(f"Duplicate node id: {node_id}")
        else:
            node_by_id[node_id] = node
        if node.get("type") not in ALLOWED_NODE_TYPES:
            errors.append(f"{node_id}: unsupported node type {node.get('type')!r}.")
        for field in ("label", "summary"):
            if not isinstance(node.get(field), str) or not node[field].strip():
                errors.append(f"{node_id}: {field} must be a non-empty string.")
        paths = node.get("paths")
        if not isinstance(paths, list) or not paths:
            errors.append(f"{node_id}: paths must be a non-empty list.")
        else:
            for raw_path in paths:
                if not isinstance(raw_path, str) or not raw_path:
                    errors.append(f"{node_id}: every path must be a non-empty string.")
                    continue
                resolved = _safe_repo_path(repo_root, raw_path)
                if resolved is None:
                    errors.append(f"{node_id}: path escapes repository: {raw_path}")
                elif not resolved.exists():
                    errors.append(f"{node_id}: path does not exist: {raw_path}")
                represented_paths.add(raw_path.replace("\\", "/"))
        _validate_evidence(
            node.get("evidence"), owner=node_id, repo_root=repo_root, errors=errors
        )

    duplicate_ids = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    if duplicate_ids:
        errors.append(f"Node ids are not unique: {', '.join(duplicate_ids)}")

    missing_required = sorted(REQUIRED_NODE_IDS - set(node_by_id))
    if missing_required:
        errors.append(f"Missing required nodes: {', '.join(missing_required)}")

    normalized_edges: list[tuple[str, str, str]] = []
    for index, edge in enumerate(edges):
        owner = f"edges[{index}]"
        if not isinstance(edge, dict):
            errors.append(f"{owner}: edge must be an object.")
            continue
        source = edge.get("source")
        relation = edge.get("relation")
        target = edge.get("target")
        if source not in node_by_id:
            errors.append(f"{owner}: unknown source node {source!r}.")
        if target not in node_by_id:
            errors.append(f"{owner}: unknown target node {target!r}.")
        if relation not in ALLOWED_RELATIONS:
            errors.append(f"{owner}: unsupported relation {relation!r}.")
        if isinstance(source, str) and isinstance(relation, str) and isinstance(target, str):
            normalized_edges.append((source, relation, target))
        _validate_evidence(
            edge.get("evidence"), owner=owner, repo_root=repo_root, errors=errors
        )

    if len(normalized_edges) != len(set(normalized_edges)):
        errors.append("Graph contains duplicate edges.")

    public_modules = {
        path.relative_to(repo_root).as_posix()
        for path in (repo_root / "src/uchuva_lsystem").glob("*.py")
    }
    missing_modules = sorted(public_modules - represented_paths)
    if missing_modules:
        errors.append(f"Public modules missing from graph: {', '.join(missing_modules)}")

    pipeline = project.get("primary_pipeline")
    if not isinstance(pipeline, list) or len(pipeline) < 2:
        errors.append("project.primary_pipeline must list at least two node ids.")
    else:
        unknown_pipeline = [item for item in pipeline if item not in node_by_id]
        if unknown_pipeline:
            errors.append(
                "project.primary_pipeline references unknown nodes: "
                + ", ".join(map(str, unknown_pipeline))
            )
        connected_pairs = {
            frozenset((source, target)) for source, _relation, target in normalized_edges
        }
        for left, right in zip(pipeline, pipeline[1:]):
            if frozenset((left, right)) not in connected_pairs:
                errors.append(f"Pipeline steps are not connected: {left} -> {right}")

    edge_set = set(normalized_edges)
    if (
        "decision.morphology_first",
        "supersedes",
        "decision.legacy_prototype",
    ) not in edge_set:
        errors.append("The morphology-first architecture must supersede the legacy prototype.")

    immutable_node = node_by_id.get("constraint.original_dataset_immutable", {})
    if "inmutable" not in str(immutable_node.get("summary", "")).lower():
        errors.append("The original dataset constraint must explicitly state that it is immutable.")
    if (
        "module.domain_analysis",
        "must_preserve",
        "constraint.original_dataset_immutable",
    ) not in edge_set:
        errors.append("Domain analysis must preserve original dataset immutability.")

    for constraint_id in (
        "constraint.closed_calyx_hidden_fruit",
        "constraint.collision_taxonomy",
        "constraint.reproducible_seeds",
    ):
        if not any(
            relation == "must_preserve" and target == constraint_id
            for _source, relation, target in normalized_edges
        ):
            errors.append(f"No subsystem preserves required constraint: {constraint_id}")

    for source, relation, target in normalized_edges:
        if relation == "depends_on" and source in PURE_MODULE_IDS and target in BLENDER_MODULE_IDS:
            errors.append(
                f"Pure module cannot depend on Blender subsystem: {source} -> {target}"
            )

    legacy_node = node_by_id.get("decision.legacy_prototype", {})
    legacy_text = f"{legacy_node.get('label', '')} {legacy_node.get('summary', '')}".lower()
    if "no autoritativo" not in legacy_text:
        errors.append("Legacy prototype must be explicitly marked as non-authoritative.")

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for evidence in node.get("evidence", []):
            if isinstance(evidence, dict):
                path = str(evidence.get("path", "")).replace("\\", "/")
                if path.startswith(GENERATED_PREFIXES):
                    errors.append(
                        f"{node.get('id')}: generated output used as authoritative evidence."
                    )

    return _report(graph_path, nodes, edges, errors, warnings, public_modules)


def _report(
    graph_path: Path,
    nodes: list[Any],
    edges: list[Any],
    errors: list[str],
    warnings: list[str],
    public_modules: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "valid" if not errors else "invalid",
        "graph_path": str(graph_path),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "covered_public_modules": len(public_modules or set()),
        "errors": errors,
        "warnings": warnings,
    }


def validate_graph(
    repo_root: Path | None = None,
    graph_path: Path | None = None,
) -> dict[str, Any]:
    """Load and validate the repository graph without mutating the workspace."""
    active_root = (repo_root or _repo_root()).resolve()
    active_graph_path = graph_path or (active_root / GRAPH_RELATIVE_PATH)
    try:
        graph = json.loads(active_graph_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _report(active_graph_path, [], [], ["Context graph file does not exist."], [])
    except json.JSONDecodeError as exc:
        return _report(
            active_graph_path,
            [],
            [],
            [f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"],
            [],
        )
    return validate_graph_data(
        graph,
        repo_root=active_root,
        graph_path=active_graph_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate docs/repository_context_graph.json."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete machine-readable validation report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate_graph()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"Repository context graph: {report['status']} "
            f"({report['node_count']} nodes, {report['edge_count']} edges, "
            f"{report['covered_public_modules']} public modules)"
        )
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
        for error in report["errors"]:
            print(f"ERROR: {error}")
    return 0 if report["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
