"""Compare structural revisions at locked camera and light, without training admission."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def axes(axis):
    yield axis
    for child in axis.get("child_axes", []):
        yield from axes(child)


def tree_counts(tree):
    # Read serialised evidence, rather than regenerating a tree during review.
    rows = [row for root_axis in tree["axes"] for row in axes(root_axis)]
    units = [n["reproductive_unit"] for a in rows for n in a["nodes"] if n.get("reproductive_unit")]
    return {"axes": len(rows), "leaves": sum(bool(n.get("leaf")) for a in rows for n in a["nodes"]),
            "reproductive_units": len(units), "fruits": sum(bool(u.get("fruit")) for u in units),
            "flowers": sum(u.get("stage") == "flower" for u in units),
            "calyces": sum(bool(u.get("calyx")) for u in units)}


def envelope_extent(folder, index):
    document = read(folder / f"plant_{index:02d}_envelopes.json")
    # Hidden fruit objects may have incomplete depsgraph bounds. Restrict this
    # visible-crown descriptor to stems and leaves, never use it as a collision test.
    rows = [r["bounds"] for r in document["objects"]
            if r["plant_id"] == f"calibration_{index:02d}" and r["semantic"] in {"stem", "leaf"} and not r["hidden_in_rgb"]]
    return [max(b["maximum"][i] for b in rows) - min(b["minimum"][i] for b in rows) for i in range(3)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    before, after = [root / "calibration" / s for s in [args.before, args.after]]
    for folder in [before, after]:
        completion = read(folder / "completion.json")
        assert completion["complete"] and completion["captures"] == 4
    old_profile, new_profile = [read(f / "profiles.json") for f in [before, after]]
    for key in ["materials", "lighting", "diagnostic_lights", "render", "color_management", "context"]:
        assert old_profile[key] == new_profile[key], key
    assert read(before / "source_snapshot/snapshot_manifest.json")["files"] == read(after / "source_snapshot/snapshot_manifest.json")["files"]
    out = after / "review"
    out.mkdir(exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
    small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    bold = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 30)
    panel = Image.new("RGB", (1440, 2400), "#f2f1ec")
    draw = ImageDraw.Draw(panel)
    draw.text((22, 16), "Copa: arquitectura anterior / nueva · cámara y apariencia fijas", font=bold, fill="#18372f")
    draw.text((22, 59), "Sin recorte adicional, zoom ni retoque. Frutos emergentes de los sitios nodales, sin cuota.", font=font, fill="#555555")
    records = []
    tree_entries = [{r["index"]: r for r in read(f / "plants.json")["plants"]} for f in [before, after]]
    for i in range(4):
        view = f"plant_{i:02d}_view0_LT"
        old, new = [read(f / view / "capture.json") for f in [before, after]]
        cameras = [read(f / view / "camera.json") for f in [before, after]]
        error = float(np.max(np.abs(np.asarray(cameras[0]["matrix_world"]) - np.asarray(cameras[1]["matrix_world"]))))
        assert error < 1e-6 and cameras[0]["intrinsic_matrix"] == cameras[1]["intrinsic_matrix"]
        assert old["effective_profile"] == new["effective_profile"]
        assert old["lighting_geometry"] == new["lighting_geometry"]
        assert old["light_target_source_sha256"] == new["light_target_source_sha256"]
        assert sha(before / f"plant_{i:02d}_environment.json") == sha(after / f"plant_{i:02d}_environment.json")
        record = {"plant": i, "camera_max_abs_difference": error, "lighting_inputs_and_source_equal": True,
                  "light_matrix_caveat": "These eight captures sampled matrix_world before depsgraph update. Equality of lighting is established by the same frozen interpreter, camera, light target hash and parameters; pre-update matrices are not independent observed-pose evidence. Future captures update the depsgraph first.",
                  "appearance_equal": True, "environment_record_equal": True, "training_allowed": False}
        for j, (folder, capture, label) in enumerate([(before, old, "Antes · v4"), (after, new, "Después · v5")]):
            for name, field in [("rgb.png", "rgb_sha256"), ("mask_calyx_crisp_v2.png", "mask_sha256")]:
                assert sha(folder / view / name) == capture[field]
            tree_entry = tree_entries[j][i]
            assert sha(tree_entry["path"]) == tree_entry["sha256"]
            counts = tree_counts(read(tree_entry["path"]))
            audit = read(folder / f"plant_{i:02d}_mesh_audit.json")
            record["before" if j == 0 else "after"] = dict(counts=counts,
                visible_stem_leaf_extent_blender_units=envelope_extent(folder, i),
                physical_collision_flags=audit["physical_collision_count"],
                clearance_flags=audit["clearance_violation_count"], rgb_sha256=capture["rgb_sha256"])
            x, y = 18 + j * 714, 104 + i * 566
            draw.text((x, y), f"Planta {i+1} · {label}", font=font, fill="#18372f")
            im = ImageOps.contain(Image.open(folder / view / "rgb.png").convert("RGB"), (690, 518))
            panel.paste(im, (x + (690 - im.width) // 2, y + 30))
            draw.text((x, y + 548), f'{counts["axes"]} ejes · {counts["leaves"]} hojas · {counts["fruits"]} frutos en el árbol', font=small, fill="#555555")
        records.append(record)
        # Cut the presentation canvas only; each underlying photograph/render
        # remains complete and uniformly scaled within its comparison panel.
        panel.crop((0, 104 + i * 566, 1440, 104 + (i + 1) * 566)).save(
            out / f"plant_{i:02d}_comparison.jpg", quality=95)
    panel.save(out / "comparacion_copas.jpg", quality=95)
    write(out / "verification.json", {"purpose": "fixed-camera structural review", "checks": records,
         "real_references": "training only; full photographs are not measurements of isolated whole plants",
         "human_review": "pending", "physical_admission": False})
    reference = root / "revisions/crown_feedback_20261026/real_full_frame_references.png"
    reference_link = f'<p><a href="{html.escape(reference.as_uri())}">Referencias reales de entrenamiento</a></p>' if reference.exists() else ""
    (out / "index.html").write_text('''<!doctype html><meta charset="utf-8"><title>Revisión de copa</title>
<style>body{background:#f2f1ec;color:#18372f;font:18px system-ui;max-width:1440px;margin:30px auto}img{width:100%}p{max-width:1000px}</style>
<h1>Revisión de arquitectura de la copa</h1><p>Comparación controlada: mismo encuadre, luz, materiales y vegetación del suelo.
Los nuevos frutos proceden del desarrollo nodal. No se cambió su tamaño ni se aplicó una cuota para componer la imagen.</p>
<p>Estos renders son diagnósticos: la revisión visual y la admisión física siguen pendientes. Más follaje no demuestra mejor desempeño del detector.</p>'''
        + reference_link + '<img src="comparacion_copas.jpg"><p><a href="verification.json">Conteos y verificaciones</a></p>', encoding="utf-8")
    write(out / "report_manifest.json", {"files": {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != "report_manifest.json"},
         "before_profiles_sha256": sha(before / "profiles.json"), "after_profiles_sha256": sha(after / "profiles.json")})
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
