"""Human selection hand-off, separate from partitions and synthetic labels.

Existing decoded candidates are a reusable cache, not the old visual selection.
All final decisions remain human. No detector, quality filtering or training.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageOps

from uchuva_dataset_curation import digest, read_json, read_rows, write_json, write_rows

VERSION = "annotation-packages/1.0"
CLASSES = {"0": "pintona", "1": "madura", "2": "sobremadura"}
STATES = {"pintona": [0, 1, 2], "madura": [3, 4], "sobremadura": [5, 6]}
DECISIONS = {"", "USAR", "NO USAR", "DUDOSA"}
PACKAGES = [f"P{i:02}" for i in range(1, 6)]


def sequence_key(r):
    return (r["group_id"], r["source"], r.get("frame_index") or 0, r["image_id"])


def sample_bank(rows, target, seed):
    """Retain all photos; systematic temporal subsampling of the decoded pool.

    Allocation is only the requested bank size, never a final annotation quota.
    Uniform quantiles per video avoid favouring the 488 historical representatives.
    """
    photos = [r for r in rows if r["kind"] == "photo"]
    videos = defaultdict(list)
    for r in rows:
        if r["kind"] == "video":
            if r.get("frame_index") is None or r.get("timestamp_seconds") is None:
                raise ValueError("Video candidate lacks decoder provenance")
            videos[r["source_id"]].append(r)
    if not len(photos) + len(videos) <= target <= len(rows):
        raise ValueError("Target must cover every photo and video source and fit available pool")
    # Temporal coverage, not quality or maturity scoring. Largest-remainder budget.
    duration = {s: max(r["timestamp_seconds"] for r in v) - min(r["timestamp_seconds"] for r in v) for s, v in videos.items()}
    counts = {s: 1 for s in videos}
    rng = random.Random(seed)
    tie = {s: rng.random() for s in sorted(videos)}
    for _ in range(target - len(photos) - len(videos)):
        s = max((s for s in videos if counts[s] < len(videos[s])),
                key=lambda s: (duration[s] / counts[s], tie[s]))
        counts[s] += 1
    chosen = list(photos)
    for s, v in sorted(videos.items()):
        v = sorted(v, key=lambda r: (r["timestamp_seconds"], r["frame_index"]))
        # Select actual decoder timestamps closest to uniform temporal positions.
        available = list(v)
        for t in np.linspace(v[0]["timestamp_seconds"], v[-1]["timestamp_seconds"], counts[s]):
            i = min(range(len(available)), key=lambda i: (abs(available[i]["timestamp_seconds"] - t), available[i]["frame_index"]))
            chosen.append(available.pop(i))
    return sorted(chosen, key=sequence_key)


def distribute(rows):
    """Keep groups whole where possible; split large groups into temporal blocks."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["group_id"]].append(r)
    limit = math.ceil(len(rows) / 5)
    blocks = []
    for gid, members in groups.items():
        members = sorted(members, key=sequence_key)
        parts = math.ceil(len(members) / limit)
        size = math.ceil(len(members) / parts)
        for i in range(0, len(members), size):
            blocks.append((gid, i // size, members[i:i + size]))
    assigned, loads = {}, Counter({p: 0 for p in PACKAGES})
    for gid, block, members in sorted(blocks, key=lambda b: (-len(b[2]), b[0], b[1])):
        package = min(PACKAGES, key=lambda p: (loads[p], p))
        for r in members:
            assigned[r["image_id"]] = (package, f"{gid}_review_{block:02}")
        loads[package] += len(members)
    return assigned


def partition_audit(rows, relations=()):
    """Check the parent pool as well as selected rows; no silent repartition."""
    conflicts = []
    for key in ("group_id", "source_id", "source_sha256", "pixel_sha256"):
        seen = defaultdict(set)
        for r in rows:
            if r.get(key):
                seen[r[key]].add(r["split"])
        conflicts.extend({"kind": key, "identity": k, "splits": sorted(s)}
                         for k, s in seen.items() if len(s) > 1)
    sources = defaultdict(set)
    for r in rows:
        sources[r["source_id"]].add(r["split"])
    for rel in relations:
        if rel["verdict"] != "different_scene":
            splits = sources[rel["left_source"]] | sources[rel["right_source"]]
            if len(splits) > 1:
                conflicts.append({"kind": "related_sources", "relation": rel, "splits": sorted(splits)})
    pending = sorted({r["group_id"] for r in rows if r.get("group_review") != "reviewed"})
    return {"conflicts": conflicts, "pending_groups": pending,
            "release_allowed": not conflicts and not pending,
            "scope": "Structural checks; clean hashes do not certify visual independence."}


def letterbox(rgb):
    h, w = rgb.shape[:2]
    scale = min(640 / w, 640 / h)
    nw, nh = round(w * scale), round(h * scale)
    left, top = (640 - nw) // 2, (640 - nh) // 2
    canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, {"width": w, "height": h, "scale_x": nw / w, "scale_y": nh / h,
                    "resized_width": nw, "resized_height": nh,
                    "left": left, "top": top, "right": 640 - nw - left, "bottom": 640 - nh - top}


def diagnose(parent, source, target, seed):
    rows = read_rows(parent / "manifest.jsonl")
    if len({r["image_id"] for r in rows}) != len(rows):
        raise ValueError("Parent IDs are not unique")
    chosen = sample_bank(rows, target, seed)
    files = read_json(parent / "inventory.json")["files"]
    missing = [r["source"] for r in files if not (source / r["source"]).is_file()]
    missing_cache = [r["image_id"] for r in chosen if not (parent / r["candidate_path"]).is_file()]
    relations = read_rows(parent / "pair_review.csv")
    result = {"parent_pool": len(rows), "bank": len(chosen), "kinds": dict(Counter(r["kind"] for r in chosen)),
              "sources": len({r["source_id"] for r in chosen}), "groups": len({r["group_id"] for r in chosen}),
              "splits": dict(Counter(r["split"] for r in chosen)), "missing_sources": missing,
              "missing_candidates": missing_cache, "partition_audit": partition_audit(rows, relations),
              "method": "All photos and uniform time coverage of cached decoder frames; no visual rejection.",
              "seed": seed, "source_root": str(source), "parent": str(parent)}
    return result, rows, chosen, files, relations


README = """# Revisar y anotar por tandas

1. Abra `index.html`. Compare la imagen original con su vista gris de 640.
2. Complete solo `seleccion.csv`: USAR, NO USAR o DUDOSA; vacío = pendiente.
3. Anote por tandas las instancias del capacho visible de la planta/rama de
   trabajo en primer plano, usando `imagenes/` (resolución original orientada).
   Delimite solo lo visible, sin completar partes ocultas ni incluir hojas,
   tallos o pedúnculos. Conserve oclusiones y bordes truncados identificables.
   No anote las vistas de 640 como nuevas muestras. No hay mínimo de píxeles:
   debe poder reconocer el capacho y delimitar su contorno visible.
4. Clases: pintona (estados 0–2), madura (3–4), sobremadura (5–6).
   Los IDs son 0, 1, 2 respectivamente; no son los estados del agricultor.
   No invente madurez por color; si duda, marque DUDOSA y conserve las máscaras.
5. Conserve nombres y devuelva la exportación sin modificar y `seleccion.csv`
   en `devolucion/`. USAR no certifica anotación completa ni ausencia de objetos.

Las cajas se derivarán de máscaras; no se pide otra anotación manual.
Revise con un compañero las primeras 5–10 anotaciones y después aproximadamente
10 % de cada lote y todas las DUDOSAS. Las cinco imágenes de `calibracion/`
son comunes: una identidad y una anotación final adjudicada por imagen.
No son cinco muestras diferentes ni obligan a segmentar todo el paquete.

`procedencia.csv` es de consulta. Paquete no equivale a train/val/test.
TEST es reservado para evaluación: no usar en calibración ni entrenamiento.
Las propuestas del piloto y los grupos requieren aprobación del coordinador.
"""


def make_gallery(folder, rows):
    pages = folder / "galeria"
    pages.mkdir()
    count = math.ceil(len(rows) / 40)
    for page in range(count):
        cards = []
        for r in rows[page * 40:(page + 1) * 40]:
            title = html.escape(f"{r['image_id']} | {r['source']} | frame={r['frame_index']} | t={r['timestamp_seconds']} | {r['group_id']} | {r['split']}" + (" — RESERVADO EVALUACIÓN" if r['split'] == 'test' else ''))
            cards.append(f'<article><img loading="lazy" width="280" height="280" src="../{r["preview_path"]}"><p>{title}</p><a href="../{r["image_path"]}">Original para anotar</a> · <a href="../{r["preview_path"]}">Vista 640</a></article>')
        nav = " ".join(f'<a href="pagina_{n:03}.html">{n + 1}</a>' for n in range(count))
        (pages / f"pagina_{page:03}.html").write_text('<!doctype html><meta charset="utf-8"><title>Revisión</title><style>body{font:16px sans-serif;margin:24px}main{display:flex;flex-wrap:wrap;gap:20px}article{width:300px;overflow-wrap:anywhere}img{object-fit:contain}nav a{padding:5px}</style><a href="../index.html">Inicio</a><nav>' + nav + '</nav><main>' + ''.join(cards) + '</main>', encoding="utf-8")
    (folder / "index.html").write_text('<!doctype html><meta charset="utf-8"><h1>Revisión ' + folder.name + '</h1><p>Una identidad: original para anotar y vista 640 para revisar.</p><ul><li><a href="galeria/pagina_000.html">Abrir galería</a></li><li><a href="seleccion.csv">Tabla de selección</a></li><li><a href="LEEME.md">Instrucciones</a></li><li><a href="procedencia.csv">Procedencia de consulta</a></li><li><a href="calibracion/referencias.csv">Cinco imágenes comunes de calibración</a></li></ul>', encoding="utf-8")


def pilot_references(rows, seed):
    rng = random.Random(seed)
    result = []
    for split, n in (("train", 40), ("val", 10)):
        by_group = defaultdict(list)
        for r in rows:
            if r["split"] == split and r["initial_decision"] != "NO USAR":
                by_group[r["group_id"]].append(r)
        for v in by_group.values():
            rng.shuffle(v)
        selected = []
        while len(selected) < n and any(by_group.values()):
            for gid in sorted(by_group):
                if by_group[gid] and len(selected) < n:
                    selected.append(by_group[gid].pop())
        for i, r in enumerate(selected):
            result.append({"image_id": r["image_id"], "package_id": r["package_id"], "group_id": r["group_id"],
                           "split": split, "role": "calibracion" if split == "train" and i < 5 else "semilla" if split == "train" else "validacion",
                           "status": "propuesta_pendiente", "image_path": f"paquetes/{r['package_id']}/{r['image_path']}"})
    return result


def generate(parent, source, out, target=4500, seed=20260925, guide=None):
    diagnostic, pool, chosen, files, relations = diagnose(parent, source, target, seed)
    if out.exists():
        raise ValueError("Delivery exists; use a new version")
    if diagnostic["missing_sources"] or diagnostic["missing_candidates"]:
        raise ValueError("Missing inputs; recover from original decoder/source before generation")
    # Validate every inventoried source before using historical provenance.
    for i, src in enumerate(files):
        if digest(source / src["source"]) != src["sha256"]:
            raise ValueError(f"Source hash changed: {src['source']}")
        if i % 100 == 0:
            print(f"Sources verified {i + 1}/{len(files)}", flush=True)
    out.mkdir(parents=True)
    write_json(out / "diagnostic.json", diagnostic)
    by_source = {r["source_id"]: r for r in files}
    assigned = distribute(chosen)
    records = []
    for p in PACKAGES:
        folder = out / "paquetes" / p
        for sub in ("imagenes", "vistas_640", "devolucion", "calibracion"):
            (folder / sub).mkdir(parents=True)
        (folder / "LEEME.md").write_text(README, encoding="utf-8")
        (folder / "devolucion" / "LEEME.md").write_text(
            "Coloque aquí la exportación original de anotaciones y seleccion.csv.\n"
            "Conserve las máscaras DUDOSAS y los nombres de imagen.\n", encoding="utf-8")
        if guide:
            shutil.copyfile(guide, folder / "Guia_seleccion_etiquetado_uchuva_4pag.pdf")
    for i, r in enumerate(chosen):
        package, block = assigned[r["image_id"]]
        folder = out / "paquetes" / package
        candidate = parent / r["candidate_path"]
        if digest(candidate) != r["sha256"]:
            raise ValueError(f"Candidate hash mismatch: {candidate}")
        name = r["image_id"] + candidate.suffix.lower()
        target_path = folder / "imagenes" / name
        with Image.open(candidate) as im:
            oriented = ImageOps.exif_transpose(im).convert("RGB")
            if r["rotation_cw"]:
                oriented = oriented.rotate(-r["rotation_cw"], expand=True)
                oriented.save(target_path, quality=95)
            else:
                shutil.copyfile(candidate, target_path)
        # Preview the exact delivered pixels, including any rotation re-encoding.
        with Image.open(target_path) as im:
            rgb = np.array(im.convert("RGB"))
        preview, transform = letterbox(rgb)
        preview_path = folder / "vistas_640" / (r["image_id"] + ".png")
        Image.fromarray(preview).save(preview_path)
        src = by_source[r["source_id"]]
        records.append({"image_id": r["image_id"], "filename": name,
                        "package_id": package, "primary_owner": package, "review_block": block,
                        "source_id": r["source_id"], "source": r["source"], "kind": r["kind"],
                        "source_sha256": src["sha256"], "frame_index": r["frame_index"],
                        "timestamp_seconds": r["timestamp_seconds"], "device": r["device"],
                        "group_id": r["group_id"], "split": r["split"], "group_review": r["group_review"],
                        "split_status": "inherited_provisional", "candidate_sha256": r["sha256"],
                        "pixel_sha256": r["pixel_sha256"], "delivered_sha256": digest(target_path),
                        "preview_sha256": digest(preview_path), "source_orientation": src.get("orientation"),
                        "orientation_applied": "EXIF transpose / video decoder auto in parent; then rotation_cw",
                        "rotation_cw": r["rotation_cw"], **transform,
                        "image_path": target_path.relative_to(folder).as_posix(),
                        "preview_path": preview_path.relative_to(folder).as_posix(),
                        "historical_selection": r["selection"], "historical_notes": r.get("notes", ""),
                        "initial_decision": "NO USAR" if r["selection"] == "exclude" else "",
                        "provenance_status": "source_hash_and_cached_frame_verified"})
        if (i + 1) % 100 == 0:
            print(f"Packaged {i + 1}/{len(chosen)}", flush=True)
    write_rows(out / "manifest.jsonl", records)
    write_rows(out / "manifest.csv", records)
    selected_ids = {r["image_id"] for r in records}
    write_rows(out / "bank_selection.csv", [{"image_id": r["image_id"], "in_bank": r["image_id"] in selected_ids,
               "historical_selection": r["selection"], "reason": "photo_or_temporal_sampling" if r["image_id"] in selected_ids else "outside_requested_bank_budget_preserved_in_parent"} for r in pool])
    write_rows(out / "relations.csv", relations)
    write_json(out / "partition_audit.json", diagnostic["partition_audit"])
    grouped = defaultdict(list)
    for r in records:
        grouped[r["group_id"]].append(r)
    write_rows(out / "groups.csv", [{"group_id": gid, "split": ";".join(sorted({r['split'] for r in v})),
                "review_status": "reviewed" if all(r["group_review"] == "reviewed" for r in v) else "pending",
                "candidates": len(v), "owners": ";".join(sorted({r['package_id'] for r in v})),
                "sources": ";".join(sorted({r['source_id'] for r in v})),
                "review_blocks": ";".join(sorted({r['review_block'] for r in v}))} for gid, v in sorted(grouped.items())])
    pilots = pilot_references(records, seed)
    write_rows(out / "piloto_sugerido.csv", pilots)
    by_id = {r["image_id"]: r for r in records}
    for package in PACKAGES:
        folder = out / "paquetes" / package
        subset = [r for r in records if r["package_id"] == package]
        write_rows(folder / "procedencia.csv", subset)
        write_rows(folder / "seleccion.csv", [{"image_id": r["image_id"], "decision": r["initial_decision"]} for r in subset])
        calibration = []
        for ref in pilots:
            if ref["role"] != "calibracion":
                continue
            r = by_id[ref["image_id"]]
            shutil.copyfile(out / ref["image_path"], folder / "calibracion" / r["filename"])
            calibration.append({**ref, "image_path": r["filename"], "primary_owner": r["package_id"], "not_an_additional_sample": True})
        write_rows(folder / "calibracion" / "referencias.csv", calibration)
        make_gallery(folder, subset)
    repo = Path(__file__).resolve().parents[1]
    campaign = {"version": VERSION, "campaign": out.name, "seed": seed, "target": target,
                "source_root_relative_to_repository": source.relative_to(repo).as_posix() if source.is_relative_to(repo) else str(source),
                "parent_relative_to_repository": parent.relative_to(repo).as_posix() if parent.is_relative_to(repo) else str(parent),
                "parent_manifest_sha256": digest(parent / "manifest.jsonl"), "parent_inventory_sha256": digest(parent / "inventory.json"),
                "method": diagnostic["method"], "new_decodes": 0, "reused_candidates": len(records),
                "classes": CLASSES, "farmer_states": STATES, "real_maturity_inferred": False,
                "preprocessing": "RGB 114 centered letterbox 640, INTER_LINEAR; no crop or mirror",
                "training_executed": False, "inference_executed": False, "status": "human_review_only",
                "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
                "code_sha256": {p: digest(repo / p) for p in ("src/uchuva_annotation_packages.py", "src/uchuva_dataset_curation.py", "scripts/prepare_annotation_packages.py")},
                "guide_sha256": digest(guide) if guide else None,
                "runtime": {"opencv": cv2.__version__, "pillow": Image.__version__, "numpy": np.__version__}}
    write_json(out / "campaign.json", campaign)
    (out / "LEEME.md").write_text("# Cinco paquetes de revisión\n\nAbra paquetes/P01 a P05 o reparta sus ZIP. Paquete no equivale a split.\n\n" + README + f"\nEl banco conserva exclusiones históricas NO USAR. Las reservas históricas quedan pendientes.\n{len(grouped)} grupos heredados requieren revisión de áreas/plantas entre dispositivos antes de liberar entrenamiento.\nConsulte groups.csv, partition_audit.json y piloto_sugerido.csv. Las propuestas son orientativas.\n", encoding="utf-8")
    (out / "zips").mkdir()
    for package in PACKAGES:
        folder = out / "paquetes" / package
        with zipfile.ZipFile(out / "zips" / (package + ".zip"), "x", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for path in sorted(folder.rglob("*")):
                if path.is_file():
                    z.write(path, package + "/" + path.relative_to(folder).as_posix())
        print(f"ZIP complete {package}", flush=True)
    return verify(out)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        self.paths.extend(v for k, v in attrs if k in {"href", "src"})


def relocate_zip(z, package, first_row):
    """Extract a complete archive to a temporary directory and check every link."""
    with tempfile.TemporaryDirectory(prefix="uchuva_portable_") as tmp:
        root = Path(tmp).resolve()
        if any(not (root / n).resolve().is_relative_to(root) for n in z.namelist()):
            raise ValueError('Unsafe ZIP path')
        z.extractall(tmp)
        relocated = root / package
        for page in relocated.rglob('*.html'):
            links = Links()
            links.feed(page.read_text(encoding='utf-8'))
            for link in links.paths:
                path = (page.parent / link).resolve()
                if not path.is_relative_to(relocated) or not path.is_file():
                    raise ValueError('Relocated gallery link broken')
        with Image.open(relocated / first_row['preview_path']) as im:
            im.load()
            if im.size != (640, 640):
                raise ValueError('Relocated preview unreadable')


def verify_portability(out):
    """Supplement an existing pixel/hash audit without decoding every image again."""
    rows = read_rows(out / 'manifest.jsonl')
    csv_rows = [{k: '' if v is None else str(v) for k, v in r.items()} for r in rows]
    if read_rows(out / 'manifest.csv') != csv_rows:
        raise ValueError('Master CSV/JSONL disagreement')
    checks = []
    for package in PACKAGES:
        subset = [r for r in rows if r['package_id'] == package]
        folder = out / 'paquetes' / package
        if read_rows(folder / 'procedencia.csv') != [r for r in csv_rows if r['package_id'] == package]:
            raise ValueError('Package provenance differs from master')
        archive = out / 'zips' / (package + '.zip')
        with zipfile.ZipFile(archive) as z:
            expected = {package + '/' + p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}
            if set(z.namelist()) != expected or len(z.namelist()) != len(expected):
                raise ValueError('ZIP membership differs')
            relocate_zip(z, package, subset[0])
        checks.append(dict(package=package, zip_sha256=digest(archive), full_extraction=True, gallery_links=True))
        print(f'Full relocation verified {package}', flush=True)
    result = dict(ok=True, scope='Complete ZIP relocation and CSV/master correspondence; complements pixel/hash verification',
                  manifest_sha256=digest(out/'manifest.jsonl'), packages=checks,
                  validator_sha256=digest(Path(__file__)))
    write_json(out / 'verification_portability.json', result)
    return result


def verify(out):
    rows = read_rows(out / "manifest.jsonl")
    ids = [r["image_id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate master ID")
    bank = read_rows(out / "bank_selection.csv")
    if {r["image_id"] for r in bank if r["in_bank"] == "True"} != set(ids):
        raise ValueError("Bank coverage mismatch")
    pilots = read_rows(out / "piloto_sugerido.csv")
    lookup = {r["image_id"]: r for r in rows}
    if any(lookup[p["image_id"]]["split"] == "test" for p in pilots):
        raise ValueError("Test in pilot")
    report, delivered = [], []
    for package in PACKAGES:
        folder = out / "paquetes" / package
        subset = [r for r in rows if r["package_id"] == package]
        provenance = read_rows(folder / "procedencia.csv")
        selection = read_rows(folder / "seleccion.csv")
        expected = {r["image_id"] for r in subset}
        # CSV is a portable representation of the exact master, not a second authority.
        expected_csv = [{k: '' if v is None else str(v) for k, v in r.items()} for r in subset]
        if provenance != expected_csv:
            raise ValueError("Package provenance differs from master metadata")
        if {r['image_id'] for r in provenance} != expected or {r['image_id'] for r in selection} != expected or len(selection) != len(expected):
            raise ValueError("Package ownership mismatch")
        if any(set(r) != {"image_id", "decision"} or r["decision"] not in DECISIONS for r in selection):
            raise ValueError("Invalid selection table")
        calibration = read_rows(folder / "calibracion" / "referencias.csv")
        if {r['image_id'] for r in calibration} != {r['image_id'] for r in pilots if r['role'] == 'calibracion'}:
            raise ValueError("Calibration identity mismatch")
        for ref in calibration:
            if digest(folder / 'calibracion' / ref['image_path']) != lookup[ref['image_id']]['delivered_sha256']:
                raise ValueError("Calibration copy differs")
        if {p.name for p in (folder / 'imagenes').iterdir()} != {r['filename'] for r in subset}:
            raise ValueError("Extra/missing primary images")
        for r in subset:
            if r['primary_owner'] != package:
                raise ValueError("Owner mismatch")
            for key, sha in (("image_path", "delivered_sha256"), ("preview_path", "preview_sha256")):
                if digest(folder / r[key]) != r[sha]:
                    raise ValueError(f"Hash mismatch {r['image_id']}")
            with Image.open(folder / r["image_path"]) as im:
                if im.size != (r["width"], r["height"]) or im.getexif().get(274, 1) != 1:
                    raise ValueError("Delivered orientation/dimension mismatch")
                rgb = np.array(im.convert("RGB"))
            with Image.open(folder / r["preview_path"]) as im:
                preview = np.array(im.convert("RGB"))
            expected_preview, t = letterbox(rgb)
            if any(r[k] != v for k, v in t.items()) or preview.shape != (640, 640, 3):
                raise ValueError("Letterbox transform mismatch")
            if not np.array_equal(expected_preview, preview):
                raise ValueError("Preview pixels do not match delivered image")
            mask = np.ones((640, 640), dtype=bool)
            mask[r['top']:r['top'] + r['resized_height'], r['left']:r['left'] + r['resized_width']] = False
            if np.any(preview[mask] != 114):
                raise ValueError("Padding is not RGB 114")
        for page in folder.rglob("*.html"):
            links = Links()
            links.feed(page.read_text(encoding="utf-8"))
            for link in links.paths:
                path = (page.parent / link).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file():
                    raise ValueError(f"Nonportable gallery link {link}")
        with zipfile.ZipFile(out / "zips" / (package + ".zip")) as z:
            disk = {package + "/" + p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file()}
            if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(disk):
                raise ValueError("ZIP membership mismatch")
            for name, path in disk.items():
                h = hashlib.sha256()
                with z.open(name) as f:
                    for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                        h.update(chunk)
                if h.hexdigest() != digest(path):
                    raise ValueError("ZIP bytes differ")
            relocate_zip(z, package, subset[0])
        delivered.extend(r["image_id"] for r in subset)
        report.append({"package": package, "candidates": len(subset), "photos": sum(r['kind'] == 'photo' for r in subset),
                       "frames": sum(r['kind'] == 'video' for r in subset), "groups": len({r['group_id'] for r in subset}),
                       "splits": dict(Counter(r['split'] for r in subset)), "zip_bytes": (out / 'zips' / (package + '.zip')).stat().st_size})
        print(f"Verified {package}: {len(subset)}", flush=True)
    if Counter(delivered) != Counter(ids):
        raise ValueError("Exact union failed")
    audit = partition_audit(rows, read_rows(out / "relations.csv"))
    master_csv = read_rows(out / "manifest.csv")
    if master_csv != [{k: '' if v is None else str(v) for k, v in r.items()} for r in rows]:
        raise ValueError("Master CSV/JSONL disagreement")
    result = {"ok": True, "candidates": len(rows), "packages": report, "partition_audit": audit,
              "zip_all_members_hash_checked": True, "relocation": "All five ZIPs fully extracted outside workspace; all gallery links checked",
              "training_ready": False}
    write_json(out / "verification.json", result)
    return result


def validate_geometry(segmentation, dimensions):
    """Accept multipart polygons or lossless uncompressed COCO RLE; no filling holes."""
    w, h = dimensions
    if isinstance(segmentation, dict):
        counts = segmentation.get("counts")
        if segmentation.get("size") != [h, w] or not isinstance(counts, list):
            raise ValueError("RLE requires explicit size and uncompressed counts; preserve other formats raw")
        if not counts or any(type(n) is not int or n < 0 for n in counts) or sum(counts) != w * h:
            raise ValueError("Invalid RLE counts")
    elif isinstance(segmentation, list) and segmentation:
        for polygon in segmentation:
            if not isinstance(polygon, list) or len(polygon) < 6 or len(polygon) % 2:
                raise ValueError("Polygon needs at least three coordinate pairs")
            for i, value in enumerate(polygon):
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= (w if i % 2 == 0 else h):
                    raise ValueError("Invalid polygon coordinate")
    else:
        raise ValueError("Unsupported segmentation; raw return preserved for explicit adapter")


def import_returns(campaign, incoming, output):
    """Preserve raw normalized returns, validate identity; never silently release.

    JSON contract is documented in docs/guides/paquetes_anotacion_trazables.md.
    Geometry remains in declared coordinates, with exact inverse letterbox metadata.
    Null maturity and DUDOSA are preserved, not mapped to a class or negative.
    """
    if not incoming.is_dir():
        raise ValueError("Incoming directory is missing")
    if output.resolve().is_relative_to(incoming.resolve()):
        raise ValueError("Import output must be outside the raw incoming tree")
    if output.exists():
        raise ValueError("Import output exists; use another version")
    output.mkdir(parents=True)
    shutil.copytree(incoming, output / "raw")
    rows = read_rows(campaign / "manifest.jsonl")
    master = {r["image_id"]: r for r in rows}
    errors, preserved, selections = [], [], defaultdict(list)
    for path in sorted(incoming.rglob("seleccion.csv")):
        for item in read_rows(path):
            if set(item) != {"image_id", "decision"} or item['image_id'] not in master or item['decision'] not in DECISIONS:
                errors.append({"file": str(path.relative_to(incoming)), "error": "Invalid selection identity/columns/decision"})
            else:
                selections[item['image_id']].append({**item, "raw_return": path.relative_to(incoming).as_posix()})
    for path in sorted(incoming.rglob("*.json")):
        try:
            doc = read_json(path)
            if doc.get("classes") != CLASSES:
                raise ValueError("Class meanings mismatch; mono capacho ID 0 is not pintona")
            for item in doc["images"]:
                r = master.get(item["image_id"])
                if r is None:
                    raise ValueError("Unknown image ID")
                representation = item.get("representation")
                if representation not in {"original", "640"}:
                    raise ValueError("Explicit annotation representation required")
                expected_name = r["filename"] if representation == "original" else Path(r["preview_path"]).name
                name = item["filename"]
                if name != expected_name and doc.get("filename_to_image_id", {}).get(name) != r["image_id"]:
                    raise ValueError("Renamed file requires explicit identity mapping")
                dimensions = [r["width"], r["height"]] if representation == "original" else [640, 640]
                if item.get("dimensions") != dimensions:
                    raise ValueError("Dimension mismatch")
                expected_hash = r["delivered_sha256"] if representation == "original" else r["preview_sha256"]
                if item.get("image_sha256") != expected_hash:
                    raise ValueError("Image hash mismatch or recomposition: manual reconciliation required")
                if item.get("decision", "") not in DECISIONS:
                    raise ValueError("Invalid human decision")
                instances = item.get("instances", [])
                if not isinstance(instances, list):
                    raise ValueError("Instances must be a list")
                for inst in instances:
                    cls = inst.get("class_id")
                    if cls is not None and (type(cls) is not int or str(cls) not in CLASSES):
                        raise ValueError("Invalid maturity class; use null if unknown")
                    if not inst.get("segmentation"):
                        raise ValueError("Instance missing geometry")
                    validate_geometry(inst['segmentation'], dimensions)
                decisions = {d['decision'] for d in selections[item['image_id']]} | ({item['decision']} if 'decision' in item else set())
                decisions.discard('')
                # Never discard contradictory returns. DUDOSA is conservative pending.
                decision = 'DUDOSA' if len(decisions) > 1 else next(iter(decisions), '')
                item = {**item, 'decision': decision, 'selection_conflict': len(decisions) > 1}
                complete = item.get("annotation_complete") is True
                pending = (item.get("decision") != "USAR" or not complete or
                           any(i.get("class_id") is None for i in instances) or not instances)
                preserved.append({**item, "split": r["split"], "group_id": r["group_id"],
                                  "returned_split_ignored": item.get("split"), "raw_return": path.relative_to(incoming).as_posix(),
                                  "review_pending": pending, "negative_confirmed": False,
                                  "inverse_letterbox": {k: r[k] for k in ("scale_x", "scale_y", "left", "top")},
                                  "geometry_coordinates": representation, "training_approved": False})
        except (KeyError, ValueError, TypeError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
    repetitions = Counter(i["image_id"] for i in preserved)
    for i in preserved:
        if repetitions[i["image_id"]] > 1:
            i["review_pending"] = True
            i["adjudication_required"] = True
    write_json(output / "preserved_returns.json", preserved)
    write_json(output / "preserved_selections.json", dict(selections))
    audit = partition_audit(rows, read_rows(campaign / "relations.csv"))
    result = {"errors": errors, "preserved_image_returns": len(preserved),
              "unique_images": len(repetitions), "adjudication_required": sorted(k for k, v in repetitions.items() if v > 1),
              "raw_files_preserved": len([p for p in (output / 'raw').rglob('*') if p.is_file()]),
              "geometry_format": "multipart polygons or uncompressed COCO RLE, in declared coordinates",
              "partition_audit": audit, "training_release_allowed": False,
              "note": "Raw returns preserved; coordinator must adjudicate and validate masks before a separate release."}
    write_json(output / "import_report.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("diagnose", "generate", "verify", "portability", "import"))
    p.add_argument("--parent", type=Path, default=Path("outputs/new_real_dataset/captura_20260912_v6"))
    p.add_argument("--source", type=Path, default=Path("Nuevo Dataset"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--target", type=int, default=4500)
    p.add_argument("--seed", type=int, default=20260925)
    p.add_argument("--guide", type=Path)
    p.add_argument("--incoming", type=Path)
    p.add_argument("--campaign", type=Path)
    a = p.parse_args()
    if a.mode == "diagnose":
        result = diagnose(a.parent, a.source, a.target, a.seed)[0]
    elif a.mode == "generate":
        result = generate(a.parent.resolve(), a.source.resolve(), a.output.resolve(), a.target, a.seed, a.guide)
    elif a.mode == "verify":
        result = verify(a.output)
    elif a.mode == "portability":
        result = verify_portability(a.output)
    else:
        if not a.incoming or not a.campaign:
            p.error("import requires --incoming and --campaign")
        result = import_returns(a.campaign, a.incoming, a.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
