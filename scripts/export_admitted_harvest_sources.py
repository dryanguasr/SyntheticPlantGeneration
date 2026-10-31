"""Freeze admitted morphology and its source interpreter's poses for harvesting.

Run with plain Python. The explicitly selected source checkout is read-only;
all artifacts are written to a new output folder outside that checkout. This
does not generate new plants, launch Blender, or repeat source mesh audits.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path)
    parser.add_argument("--plant-files", required=True, type=Path, nargs="+")
    parser.add_argument("--source-units-per-metre", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source_repo.resolve()
    output = args.output.resolve()
    if output == source or source in output.parents:
        parser.error("Output must be outside the read-only source checkout")
    if output.exists():
        parser.error("Output already exists; preserve frozen source exports")
    if not 0 < args.source_units_per_metre < float("inf"):
        parser.error("A finite positive source unit conversion is required")
    if not (source / "src/uchuva_lsystem/collisions.py").is_file():
        parser.error("Source checkout lacks its morphology interpreter")
    sys.path.insert(0, str(source / "src"))
    from uchuva_lsystem.collisions import build_scene_proxies
    from uchuva_lsystem.morphology import Plant
    from uchuva_lsystem.scene import CultivationScene, PlantInstance
    from uchuva_gazebo.admitted_plants import build_admitted_plant_bundle

    sources = {str(path.relative_to(source)).replace("\\", "/"): sha(path)
               for package in ("uchuva_lsystem", "uchuva_gazebo")
               for path in sorted((source / "src" / package).glob("*.py"))}
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for path in args.plant_files:
        path = path.resolve()
        raw = path.read_bytes()
        plant = Plant.from_dict(json.loads(raw))
        folder = path.parent
        audit_names = {"mesh": "final_independent_mesh.json", "ground": "ground.json", "orientation": "orientation.json"}
        admission = read(folder / "admission.json")
        audits = {name: read(folder / filename) for name, filename in audit_names.items()}
        # Reuse the source's anatomy, reversibility and evidence checks. This
        # verifies supplied evidence; it is deliberately not a fresh mesh audit.
        bundle = build_admitted_plant_bundle(plant, admission, audits,
            metres_per_scene_unit=1 / args.source_units_per_metre, lod=1)
        measured_scale = audits["ground"].get("metres_per_blender_unit")
        if measured_scale is None or abs(measured_scale - 1 / args.source_units_per_metre) > 1e-7:
            raise ValueError("Explicit source units disagree with the ground audit")
        local_id = "source"
        scene = CultivationScene("harvest_source", "frozen_admitted_poses", plant.seed,
            plant_instances=[PlantInstance(local_id, plant.seed)])
        proxies = build_scene_proxies(scene, {local_id: plant})
        target = output / f"seed_{plant.seed}"
        target.mkdir(exist_ok=False)
        (target / "plant.json").write_bytes(raw)
        (target / "admission.json").write_bytes((folder / "admission.json").read_bytes())
        catalog = dict(schema_version="uchuva.harvest_proxy_catalog/1", seed=plant.seed,
            parameter_preset=plant.parameter_preset, source_plant_id=local_id,
            morphology_sha256=hashlib.sha256(raw).hexdigest(), source_morphology_path=str(path),
            source_repo=str(source), source_units_per_metre=args.source_units_per_metre,
            source_files_sha256=sources,
            exporter_sha256=sha(Path(__file__).resolve()),
            admission=admission, admission_sha256=sha(folder / "admission.json"),
            audit_sha256={name: sha(folder / filename) for name, filename in audit_names.items()},
            static_evidence=bundle["static_evidence"],
            spatial_admission_verification=bundle["spatial_admission_verification"],
            limitations=bundle["limitations"], proxies=[asdict(proxy) for proxy in proxies])
        write(target / "proxy_catalog.json", catalog)
        record = dict(seed=plant.seed, morphology_file=str(target / "plant.json"),
            proxy_catalog_file=str(target / "proxy_catalog.json"),
            morphology_sha256=catalog["morphology_sha256"],
            proxy_catalog_sha256=sha(target / "proxy_catalog.json"),
            counts=admission["counts"], proxy_count=len(proxies))
        records.append(record)
        print(json.dumps(record), flush=True)
    if any(sha(source / relative) != digest for relative, digest in sources.items()):
        raise RuntimeError("Source interpreter changed during catalog preparation")
    write(output / "manifest.json", dict(schema_version="uchuva.harvest_sources/1",
        source_repo=str(source), source_units_per_metre=args.source_units_per_metre,
        source_files_sha256=sources, plants=records,
        policy="byte-identical admitted trees; source poses; no generation or new mesh audit"))


if __name__ == "__main__":
    main()
