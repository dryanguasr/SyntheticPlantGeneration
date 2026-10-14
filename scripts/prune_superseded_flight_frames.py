"""Retira fotogramas de vuelos v1/v2, preservando videos, registros y muestras."""

import json
from pathlib import Path

from prune_historical_generated_data import ROOT, fingerprint


roots = [(ROOT / "outputs/gazebo" / name / "flight").resolve(strict=True)
         for name in ("low_pilot_v1", "low_pilot_v2")]
deleted = []
samples = []
protected = []
for root in roots:
    assert root.is_relative_to(ROOT / "outputs/gazebo")
    videos = list(root.glob("*.mp4"))
    assert videos, f"No hay video consolidado: {root}"
    protected.extend(p for p in root.iterdir() if p.is_file())
    for kind in ("rgb", "mask"):
        folder = root / kind
        files = sorted(p for p in folder.iterdir() if p.is_file()
                       and p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        retained = {files[i] for i in (0, len(files)//2, len(files)-1)} if files else set()
        samples.extend(sorted(retained))
        deleted.extend(p for p in files if p not in retained)
entries = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size}
           for p in deleted]
hashes = [{"path": p.relative_to(ROOT).as_posix(), "sha256": fingerprint(p)}
          for p in protected + samples]
record = ROOT / "outputs/archive/depuracion_vuelos_20261006"
record.mkdir(parents=True, exist_ok=True)
(record / "plan.json").write_text(json.dumps({"deleted": entries, "protected": hashes}), encoding="utf-8")
for path in deleted:
    resolved = path.resolve(strict=True)
    if not any(resolved.parent == root / kind for root in roots for kind in ("rgb", "mask")):
        raise RuntimeError(f"Ruta fuera de fotogramas antiguos: {path}")
for path in deleted:
    path.unlink()
for entry in hashes:
    if fingerprint(ROOT / entry["path"]) != entry["sha256"]:
        raise RuntimeError(f"Evidencia alterada: {entry['path']}")
for root in roots:
    (root / "FOTOGRAMAS_DEPURADOS.md").write_text(
        "# Vuelo histórico depurado\n\n"
        "Se conservan videos, registros y tres pares RGB/máscara de inicio, mitad y final. "
        "Los demás fotogramas se retiraron el 6 de octubre de 2026 por autorización del responsable. "
        "No se puede repetir la evaluación completa con las muestras restantes. "
        "La versión posterior low_pilot_v3 permanece disponible.\n", encoding="utf-8")
result = {"deleted_files": len(entries), "released_bytes": sum(e["bytes"] for e in entries),
          "verified_protected": len(hashes)}
(record / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
