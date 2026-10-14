"""Elimina solamente discos e instantáneas del AVD de pruebas del proyecto."""

import json
from pathlib import Path

from prune_historical_generated_data import ROOT


avd = (ROOT / "outputs/mobile/toolchain/avd/uchuva_api29.avd").resolve(strict=True)
assert avd.is_relative_to(ROOT / "outputs/mobile/toolchain/avd")
assert (avd / "config.ini").is_file()
apk_files = list((ROOT / "outputs/mobile/apk").glob("*.apk"))
assert apk_files, "No hay APK conservado para reinstalar"
files = sorted(p for p in avd.rglob("*") if p.is_file()
               and (p.suffix in {".img", ".qcow2"}
                    or p.is_relative_to(avd / "snapshots")))
entries = [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size}
           for p in files]
record = ROOT / "outputs/archive/depuracion_emulador_20261006"
record.mkdir(parents=True, exist_ok=True)
(record / "plan.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
for path in files:
    if not path.resolve(strict=True).is_relative_to(avd):
        raise RuntimeError(f"Ruta fuera del AVD: {path}")
for path in files:
    path.unlink()
assert (avd / "config.ini").is_file()
assert all(p.is_file() for p in apk_files)
result = {"deleted_files": len(files), "released_bytes": sum(e["bytes"] for e in entries)}
(record / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
(avd / "AVD_DEPURADO.md").write_text(
    "# Emulador de pruebas depurado\n\n"
    "Se retiraron discos de usuario y snapshots el 6 de octubre de 2026. "
    "Se conservan configuración, SDK y APK. Recrear el AVD e instalar el APK "
    "para volver a ejecutar las pruebas; los datos internos del emulador anterior se descartaron.\n",
    encoding="utf-8")
print(json.dumps(result))
