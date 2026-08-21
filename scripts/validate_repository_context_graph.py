"""Validate repository-context graph structure and evidence using stdlib only."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = REPO_ROOT / "docs/repository_context_graph.json"
GENERATED_EVIDENCE_PREFIXES = ("outputs/", "generated_specs/", "tmp/")


def is_authoritative_evidence(relative_path: str) -> bool:
    """Return false when generated output cannot be authoritative evidence."""
    normalized = relative_path.replace("\\", "/")
    return not normalized.startswith(GENERATED_EVIDENCE_PREFIXES)


def main() -> None:
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    ids = [node.get("id") for node in nodes]
    errors = []
    if len(ids) != len(set(ids)):
        errors.append("duplicate node ids")
    known = set(ids)
    for node in nodes:
        for relative in node.get("paths", []):
            if not (REPO_ROOT / relative).exists():
                errors.append(f"missing node path {node['id']}: {relative}")
        errors.extend(_validate_evidence(node.get("evidence", []), node["id"]))
    for index, edge in enumerate(edges):
        if edge.get("source") not in known:
            errors.append(f"edge {index}: unknown source {edge.get('source')}")
        if edge.get("target") not in known:
            errors.append(f"edge {index}: unknown target {edge.get('target')}")
        errors.extend(_validate_evidence(edge.get("evidence", []), f"edge {index}"))
    if errors:
        raise SystemExit("\n".join(errors[:100]))
    print(f"VALID nodes={len(nodes)} edges={len(edges)} graph={GRAPH_PATH}")


def _validate_evidence(items, owner: str):
    errors = []
    for item in items:
        relative, locator = item.get("path"), item.get("locator")
        if relative and not is_authoritative_evidence(relative):
            errors.append(f"{owner}: generated output cannot be authoritative evidence: {relative}")
            continue
        path = REPO_ROOT / relative if relative else None
        if path is None or not path.is_file():
            errors.append(f"{owner}: missing evidence path {relative}")
            continue
        if locator and locator not in path.read_text(encoding="utf-8-sig", errors="replace"):
            errors.append(f"{owner}: locator not found in {relative}: {locator}")
    return errors


if __name__ == "__main__":
    main()
