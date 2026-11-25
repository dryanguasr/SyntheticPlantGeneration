"""Prepare firmware/drv8833_wifi for Arduino without copying the snapshot into Git.

1. Verifies drv8833_ros.ino against contributions/physalisharvest.provenance.json
   and writes it, byte for byte after LF normalisation, as drv8833_core.h.
2. If wifi_config.h is missing, creates it with a random token and WPA2 key.

Both outputs are ignored by Git. Nothing is uploaded to the board.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "contributions/physalisharvest.provenance.json"
SKETCH = "firmware/bench_2wd/drv8833_ros/drv8833_ros.ino"
TARGET = "firmware/drv8833_wifi"


def verified_sketch(root: Path) -> bytes:
    provenance = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    entry = next((item for item in provenance["files"] if item["path"] == SKETCH), None)
    if entry is None:
        raise ValueError(f"{SKETCH} no figura en el manifiesto de procedencia")
    payload = (root / provenance["snapshot_path"] / SKETCH).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise ValueError(f"{SKETCH} no coincide con su SHA-256 de procedencia")
    return payload


def write_core(root: Path) -> Path:
    payload = verified_sketch(root)
    header = (
        "// GENERADO por scripts/prepare_drv8833_wifi.py; no editar ni versionar.\n"
        f"// Origen: contributions/physalisharvest/{SKETCH}\n"
        f"// SHA-256: {hashlib.sha256(payload).hexdigest()}\n"
        "#pragma once\n"
    ).encode("ascii")
    core = root / TARGET / "drv8833_core.h"
    core.write_bytes(header + payload)
    return core


def write_config(root: Path, station_ssid: str | None, station_password: str | None) -> Path | None:
    config = root / TARGET / "wifi_config.h"
    if config.exists():
        return None
    example = (root / TARGET / "wifi_config.example.h").read_text(encoding="utf-8")
    replacements = {
        '#define BRIDGE_TOKEN "cambia-este-token"': f'#define BRIDGE_TOKEN "{secrets.token_urlsafe(24)}"',
        '#define AP_PASSWORD "cambia-esta-clave"': f'#define AP_PASSWORD "{secrets.token_urlsafe(12)}"',
    }
    if station_ssid:
        for value in (station_ssid, station_password or ""):
            if '"' in value or "\\" in value:
                raise ValueError("El SSID y la clave no pueden contener comillas ni barras invertidas")
        replacements['#define WIFI_SSID ""'] = f'#define WIFI_SSID "{station_ssid}"'
        replacements['#define WIFI_PASSWORD ""'] = f'#define WIFI_PASSWORD "{station_password or ""}"'
    for old, new in replacements.items():
        if old not in example:
            raise ValueError(f"wifi_config.example.h cambió; falta {old!r}")
        example = example.replace(old, new)
    config.write_text(example, encoding="utf-8", newline="\n")
    return config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssid", help="Red existente (modo estación). Sin ella: punto de acceso.")
    parser.add_argument("--password", help="Clave de la red existente")
    args = parser.parse_args()
    core = write_core(ROOT)
    print(f"Núcleo verificado: {core.relative_to(ROOT)}")
    config = write_config(ROOT, args.ssid, args.password)
    if config:
        print(f"Configuración nueva con token y clave aleatorios: {config.relative_to(ROOT)}")
    else:
        print("wifi_config.h ya existe; no se modificó")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
