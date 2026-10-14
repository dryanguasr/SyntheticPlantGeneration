"""Retira intermediarios recuperables conservando originales y cierres recientes."""

import argparse
import json
from pathlib import Path

from prune_historical_generated_data import ROOT, fingerprint


RECORD = ROOT / "outputs/archive/depuracion_reciente_20261006"
CURATION = ROOT / "outputs/new_real_dataset/captura_20260912_v6"
MESH_ROOTS = [
    ROOT / "outputs/gazebo" / name / "meshes"
    for name in ("field_v1", "field_v2", "low_pilot_v1", "low_pilot_v2",
                 "dense_crowns_v3", "dense_crowns_v3_lod")
] + [
    ROOT / "outputs/segmentation_cycles_20261002" / name / "meshes"
    for name in ("development_field_batched", "development_field_light_batched",
                 "development_field_light", "development_field_cycle1_full",
                 "development_field_cycle1_lod", "development_field_fitted",
                 "development_field_fitted_batched")
]
DEPTH_ROOTS = [
    ROOT / "outputs/reconstruction/pilot_20261001_improved" / name / "stereo"
    for name in ("mvs", "mvs_return")
]


def plan():
    files = []
    sources = {}
    with (CURATION / "candidates.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            source = (ROOT / "Nuevo Dataset" / row["source"]).resolve(strict=True)
            if not source.is_relative_to((ROOT / "Nuevo Dataset").resolve()):
                raise RuntimeError("Fuente fuera del dataset original")
            expected = row["source_sha256"]
            if source in sources and sources[source] != expected:
                raise RuntimeError(f"Hashes de fuente inconsistentes: {source}")
            sources[source] = expected
            candidate = (CURATION / row["candidate_path"]).resolve(strict=True)
            if not candidate.is_relative_to((CURATION / "candidates").resolve()):
                raise RuntimeError("Candidato fuera del directorio previsto")
            files.append(candidate)
    for source, expected in sources.items():
        if fingerprint(source) != expected:
            raise RuntimeError(f"Original no coincide con su registro: {source}")
    for root in MESH_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.is_file()
                         and p.suffix.lower() in {".dae", ".obj", ".ply"})
    for root in DEPTH_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*.bin") if p.is_file())
    files = sorted(set(files))
    entries = []
    for path in files:
        stat = path.stat()
        entries.append({"path": path.relative_to(ROOT).as_posix(),
                        "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    protected = []
    for root in (CURATION / "images", CURATION / "images_640x640"):
        protected.extend(p for p in root.rglob("*") if p.is_file())
    for root in (ROOT / "outputs/segmentation_cycles_20261002",
                 ROOT / "outputs/localization_pilot_20261005",
                 ROOT / "outputs/reconstruction"):
        protected.extend(p for p in root.rglob("*") if p.is_file()
                         and p.suffix in {".md", ".csv", ".json", ".pt", ".mp4", ".blend"})
    payload = {"candidates": entries,
               "verified_originals": [{"path": p.relative_to(ROOT).as_posix(),
                                       "sha256": h} for p, h in sources.items()],
               "protected": [{"path": p.relative_to(ROOT).as_posix(),
                              "sha256": fingerprint(p)} for p in sorted(set(protected))]}
    RECORD.mkdir(parents=True, exist_ok=True)
    (RECORD / "plan.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"files": len(entries), "GiB": sum(e["bytes"] for e in entries)/1024**3,
                      "verified_originals": len(sources), "protected": len(payload["protected"])}))


def apply():
    payload = json.loads((RECORD / "plan.json").read_text(encoding="utf-8"))
    roots = [(CURATION / "candidates").resolve()] + [p.resolve() for p in MESH_ROOTS + DEPTH_ROOTS]
    paths = []
    for entry in payload["candidates"]:
        path = (ROOT / entry["path"]).resolve(strict=True)
        if not any(path.is_relative_to(root) for root in roots):
            raise RuntimeError(f"Fuera del alcance: {path}")
        stat = path.stat()
        if stat.st_size != entry["bytes"] or stat.st_mtime_ns != entry["mtime_ns"]:
            raise RuntimeError(f"Archivo cambiado: {path}")
        paths.append(path)
    for entry in payload["verified_originals"]:
        if not (ROOT / entry["path"]).is_file():
            raise RuntimeError("Original ya no está disponible")
    for path in paths:
        path.unlink()
    for entry in payload["protected"]:
        if fingerprint(ROOT / entry["path"]) != entry["sha256"]:
            raise RuntimeError(f"Entregable alterado: {entry['path']}")
    result = {"deleted_files": len(paths),
              "released_bytes": sum(e["bytes"] for e in payload["candidates"]),
              "verified_protected": len(payload["protected"])}
    (RECORD / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    apply() if args.apply else plan()
