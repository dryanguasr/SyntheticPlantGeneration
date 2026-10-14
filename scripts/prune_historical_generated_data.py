"""Depuración autorizada: conserva evidencia y elimina datos históricos pesados."""

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "outputs/experiments",
    ROOT / "outputs/classical_augmentation_v2/datasets",
    ROOT / "outputs/classical_augmentation_v2/runs",
)
RECORD = ROOT / "outputs/archive/depuracion_20261006"
CUTOFF = datetime(2026, 9, 1).timestamp()


def fingerprint(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plan():
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode("utf-8").split("\0"))
    groups = defaultdict(list)
    checkpoints = []
    evidence = []
    for target in TARGETS:
        for path in target.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
            if stat.st_mtime >= CUTOFF:
                continue
            if (path.suffix.lower() == ".jpg"
                    and path.parent.name in {"train", "val", "test"}
                    and path.parent.parent.name == "images"):
                groups[path.parent].append(path)
            elif (path.suffix == ".pt" and path.parent.name == "weights"
                  and (path.name == "last.pt"
                       or re.fullmatch(r"epoch\d+\.pt", path.name))
                  and (path.parent / "best.pt").is_file()):
                checkpoints.append(path)
            elif (path.suffix.lower() in {".md", ".csv", ".json", ".yaml", ".pt"}
                  and stat.st_size < 100 * 1024 * 1024):
                evidence.append(path)
    candidates = checkpoints[:]
    samples = []
    for folder, files in sorted(groups.items()):
        ordered = sorted(files)
        samples.extend(ordered[:3])
        candidates.extend(ordered[3:])
    entries = []
    for path in sorted(candidates):
        relative = path.relative_to(ROOT).as_posix()
        if relative in tracked:
            raise RuntimeError(f"Candidato versionado: {relative}")
        stat = path.stat()
        entries.append({"path": relative, "bytes": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns})
    payload = {
        "created": datetime.now().isoformat(),
        "scope": "Imágenes derivadas anteriores a septiembre y checkpoints redundantes",
        "warning": "Los datasets depurados quedan incompletos; sus manifiestos y métricas son evidencia histórica, no datasets entrenables.",
        "candidates": entries,
        "samples": [p.relative_to(ROOT).as_posix() for p in samples],
        "evidence": [{"path": p.relative_to(ROOT).as_posix(),
                      "sha256": fingerprint(p)} for p in evidence],
    }
    RECORD.mkdir(parents=True, exist_ok=True)
    (RECORD / "plan.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"files": len(entries),
                      "GiB": sum(e["bytes"] for e in entries) / 1024**3,
                      "samples": len(samples), "evidence": len(evidence),
                      "plan": str(RECORD / "plan.json")}))


def apply():
    payload = json.loads((RECORD / "plan.json").read_text(encoding="utf-8"))
    candidates = payload["candidates"]
    # Validate every exact path and unchanged file before any deletion.
    paths = []
    for entry in candidates:
        path = (ROOT / entry["path"]).resolve(strict=True)
        if not any(path.is_relative_to(t.resolve()) for t in TARGETS):
            raise RuntimeError(f"Ruta fuera del alcance: {path}")
        stat = path.stat()
        if stat.st_size != entry["bytes"] or stat.st_mtime_ns != entry["mtime_ns"]:
            raise RuntimeError(f"Archivo cambiado después del inventario: {path}")
        paths.append(path)
    for path in paths:
        path.unlink()
    for relative in payload["samples"]:
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"Muestra ausente: {relative}")
    for entry in payload["evidence"]:
        if fingerprint(ROOT / entry["path"]) != entry["sha256"]:
            raise RuntimeError(f"Evidencia alterada: {entry['path']}")
    if any(p.exists() for p in paths):
        raise RuntimeError("Quedan candidatos sin eliminar")
    result = {"deleted_files": len(paths),
              "released_bytes": sum(e["bytes"] for e in candidates),
              "preserved_samples": len(payload["samples"]),
              "verified_evidence": len(payload["evidence"])}
    (RECORD / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


def mark_retired():
    payload = json.loads((RECORD / "plan.json").read_text(encoding="utf-8"))
    roots = {(ROOT / p).parents[2] for p in payload["samples"]}
    for root in roots:
        (root / "DATASET_DEPURADO.md").write_text(
            "# Dataset histórico depurado — 6 de octubre de 2026\n\n"
            "Se retiró la mayoría de las imágenes para liberar espacio, por autorización del responsable. "
            "Se conservan muestras, etiquetas, manifiestos y configuraciones históricas. "
            "Este directorio ya no es un dataset completo: no entrenar ni reevaluar con sus muestras "
            "como si correspondieran al protocolo original. Regenerar/restaurar las imágenes antes de reutilizarlo.\n\n"
            "Inventario de lo eliminado: outputs/archive/depuracion_20261006/plan.json. "
            "Los informes y los pesos best.pt se conservaron.\n", encoding="utf-8")
    print(json.dumps({"marked_datasets": len(roots)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--mark", action="store_true")
    args = parser.parse_args()
    mark_retired() if args.mark else (apply() if args.apply else plan())
