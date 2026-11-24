"""Create an evidence-only full-frame v5/v6 contact review; never train or approve."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def tree_counts(tree: dict) -> dict:
    result = Counter()
    def visit(axes):
        for axis in axes:
            result["axes"] += 1
            for node in axis["nodes"]:
                result["nodes"] += 1
                result["leaves"] += bool(node.get("leaf"))
                unit = node.get("reproductive_unit")
                if unit:
                    result["reproductive_units"] += 1
                    result["flowers"] += unit["stage"] == "flower"
                    result["fruits"] += bool(unit.get("fruit"))
                    result["calyces"] += bool(unit.get("calyx"))
            visit(axis.get("child_axes", []))
    visit(tree["axes"])
    return dict(result)


def snapshot_signature(folder: Path) -> dict:
    lock = read(folder/"source_lock.json")
    snapshot = folder/"source_snapshot"
    for relative, expected in lock["sources"].items():
        if sha(snapshot/relative) != expected:
            raise ValueError(f"Changed captured source: {relative}")
    runner = snapshot/"scripts/render_appearance_calibration.py"
    if sha(runner) != lock["runner"]:
        raise ValueError(f"Changed capture runner: {runner}")
    manifest = snapshot/"snapshot_manifest.json"
    if manifest.exists():
        for relative, expected in read(manifest)["files"].items():
            if sha(snapshot/relative) != expected:
                raise ValueError(f"Changed snapshot asset/source: {relative}")
    if sha(folder/"profiles.json") != lock["profiles"]:
        raise ValueError(f"Changed capture profiles: {folder}")
    return {"runner":lock["runner"], "sources":lock["sources"], "assets":lock["assets"]}


def capture_comparability(before: dict, after: dict, camera_before: dict, camera_after: dict) -> list[str]:
    failures = []
    clean_camera = lambda camera: {k:v for k,v in camera.items() if k != "name"}
    if clean_camera(camera_before) != clean_camera(camera_after):
        failures.append("Las cámaras registradas no son exactamente iguales.")
    for key in ("effective_profile", "lighting_geometry", "light_target_source_sha256"):
        if key not in before or key not in after or before[key] != after[key]:
            failures.append(f"Metadatos distintos o ausentes: {key}.")
    identity = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
    for label, capture in (("antes",before),("después",after)):
        lights = capture.get("lighting_geometry", {})
        if not lights:
            failures.append(f"Falta geometría efectiva de luz {label}.")
        # This renderer positions an AREA fill away from the origin. Identity
        # metadata indicates the known pre-depsgraph-update capture defect.
        if any(v.get("type") == "AREA" and v.get("matrix_world") == identity for v in lights.values()):
            failures.append(f"La luz de relleno {label} conserva una matriz identidad sin actualizar.")
    return failures


def load_side(folder: Path) -> dict:
    signature = snapshot_signature(folder)
    plants = {int(r["index"]):r for r in read(folder/"plants.json")["plants"]}
    counts = {}
    for index, record in plants.items():
        path = Path(record["path"])
        if sha(path) != record["sha256"]:
            raise ValueError(f"Changed morphology: {path}")
        counts[index] = tree_counts(read(path))
    captures = {}
    for path in sorted(folder.glob("*/capture.json")):
        capture = read(path)
        if capture.get("kind") != "context":
            continue
        view = path.parent
        for name, key in (("rgb.png","rgb_sha256"),("mask_calyx_crisp_v2.png","mask_sha256")):
            if sha(view/name) != capture[key]:
                raise ValueError(f"Changed capture pixels: {view/name}")
        index = int(capture["plant_index"])
        if capture["morphology_sha256"] != plants[index]["sha256"]:
            raise ValueError(f"Capture does not match declared tree: {view}")
        annotations = read(view/"annotations.json")["items"]
        items = annotations.values() if isinstance(annotations,dict) else annotations
        visible = [r for r in items if r.get("semantic_class") == "calyx" and r.get("visible_pixels",0)>0
                   and len(r.get("bbox_xywh",[])) == 4 and min(r["bbox_xywh"][2:])>0]
        class_counts = Counter(str(capture["assignments"][r["instance_id"]]["class_id"]) for r in visible)
        mesh_path = folder/f"plant_{index:02d}_mesh_audit.json"
        ground_path = folder/f"plant_{index:02d}_ground_audit.json"
        mesh = read(mesh_path) if mesh_path.exists() else None
        ground = read(ground_path) if ground_path.exists() else None
        captures[capture["view_id"]] = dict(folder=view,capture=capture,camera=read(view/"camera.json"),
            morphology=counts[index],visible_annotations=len(visible),class_counts=dict(class_counts),
            mesh=mesh,ground=ground,environment=read(folder/f"plant_{index:02d}_environment.json"))
    if not captures:
        raise ValueError(f"No completed contextual captures: {folder}")
    return {"signature":signature,"captures":captures}


def physical_summary(side: dict) -> dict:
    mesh,ground = side["mesh"],side["ground"]
    strict = bool(mesh and mesh.get("tolerate_only_leaf_leaf") is True)
    full_ground = bool(ground and ground.get("version") == "plant-evaluated-terrain/2")
    issues = []
    if not strict:
        issues.append("Falta auditoría estricta de órganos.")
    if not full_ground:
        issues.append("Falta auditoría de suelo ampliada con frutos visibles e internos.")
    if full_ground:
        for semantic,field in (("fruit","fruits"),("calyx","calyces"),("leaf","leaves"),("flower","flowers")):
            actual = sum(r.get("semantic")==semantic for r in ground.get("objects",[]))
            if actual != side["morphology"].get(field,0):
                issues.append(f"Auditoría suelo: {actual} {semantic}; árbol: {side['morphology'].get(field,0)}. Revisar restos/duplicados/cobertura.")
    return dict(evidence_complete=not issues,issues=issues,
        physical_collisions=None if mesh is None else mesh["physical_collision_count"],
        clearance_violations=None if mesh is None else mesh["clearance_violation_count"],
        ground_physical_collisions=None if ground is None else ground["physical_collision_count"],
        ground_clearance_violations=None if ground is None else ground.get("clearance_violation_count"),
        ground_coverage_failures=None if ground is None else ground.get("coverage_failure_count"),
        physically_admitted=bool(not issues and mesh["status"]=="valid" and mesh["physical_collision_count"]==0
            and mesh["clearance_violation_count"]==0 and ground["status"]=="valid"
            and all(ground.get(k)==0 for k in ("physical_collision_count","clearance_violation_count","coverage_failure_count"))))


def full_frame_pair(before: Path, after: Path, destination: Path, title: str) -> None:
    from PIL import Image,ImageDraw,ImageFont,ImageOps
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path),22) if font_path.exists() else ImageFont.load_default()
    canvas = Image.new("RGB",(1940,790),(239,240,236))
    draw = ImageDraw.Draw(canvas)
    draw.text((15,10),title,fill=(25,30,25),font=font)
    for x,path,label in ((10,before,"Antes v5"),(980,after,"Después v6")):
        draw.text((x,42),label,fill=(25,30,25),font=font)
        with Image.open(path) as source:
            displayed=ImageOps.contain(source.convert("RGB"),(950,710),Image.Resampling.LANCZOS)
        canvas.paste(displayed,(x+(950-displayed.width)//2,75+(710-displayed.height)//2))
    canvas.save(destination)


def copy_references(manifest: Path, output: Path) -> list[dict]:
    records = read(manifest)
    if records.get("source_split") != "train":
        raise ValueError("References must be training only")
    folder = output/"references";folder.mkdir()
    copied = []
    for row in records["rows"]:
        if row.get("split") != "train" or row.get("domain") != "real":
            raise ValueError("Reference outside real train")
        path = Path(row["image"])
        if sha(path) != row["image_sha256"]:
            raise ValueError(f"Changed real reference: {path}")
        target = folder/f"row_{int(row['source_row']):04d}{path.suffix}"
        shutil.copy2(path,target)
        copied.append({"source_row":row["source_row"],"group_id":row["group_id"],"source":str(path),
                       "file":str(target),"sha256":sha(target),"source_sha256":row["image_sha256"]})
    return copied


def report(before: Path, after: Path, output: Path, references: Path | None = None) -> dict:
    if not all(p.is_absolute() for p in (before,after,output)):
        raise ValueError("Use absolute before, after and output directories")
    if output.exists():
        raise FileExistsError("Preserve prior evidence: choose a new report directory")
    a,b = load_side(before),load_side(after)
    failures = []
    if a["signature"] != b["signature"]:
        failures.append("Los snapshots de fuentes de render o assets difieren.")
    if a["captures"].keys() != b["captures"].keys():
        failures.append("Los identificadores de vistas no coinciden.")
    output.mkdir(parents=True)
    rows = []
    for view in sorted(a["captures"].keys() & b["captures"].keys()):
        left,right = a["captures"][view],b["captures"][view]
        pair_errors = capture_comparability(left["capture"],right["capture"],left["camera"],right["camera"])
        if left["environment"] != right["environment"]:
            pair_errors.append("El registro del contexto/terreno difiere.")
        failures.extend(f"{view}: {error}" for error in pair_errors)
        target=output/f"{view}_before_after.png"
        full_frame_pair(left["folder"]/"rgb.png",right["folder"]/"rgb.png",target,view)
        rows.append(dict(view_id=view,comparison_errors=pair_errors,image=str(target),
            before=dict(morphology=left["morphology"],visible_annotations=left["visible_annotations"],class_counts=left["class_counts"],physical=physical_summary(left)),
            after=dict(morphology=right["morphology"],visible_annotations=right["visible_annotations"],class_counts=right["class_counts"],physical=physical_summary(right))))
    refs = copy_references(references,output) if references else []
    result = dict(version="appearance-contact-comparison/1",before=str(before),after=str(after),
        visual_comparison_verified=not failures,comparison_failures=failures,rows=rows,references=refs,
        labels={"before":"Antes v5","after":"Después v6"},human_review="pending",training_eligible=False,
        image_transform="full frame preserved; fit resize only; no crop, color, exposure or geometric changes",
        limits=["Copa v5 y v6 son arquitecturas distintas; no se atribuye toda diferencia a reparación de poses.",
                "Contar capachos visibles no estima la carga completa de una planta real.",
                "Contactos de maleza/fondo y algunos órganos no forman parte del audit general; suelo ampliado es un contrato separado.",
                "Revisión visual y física, sin resultado de entrenamiento ni aprobación humana implícita."])
    write(output/"comparison.json",result)
    lines=["# Revisión de contactos: Antes v5 / Después v6","",
           f"Comparación de cámara, luz, contexto y fuentes: {'verificada' if not failures else 'NO verificada'}. Revisión humana pendiente; no habilita entrenamiento.",""]
    lines.extend(f"- {error}" for error in failures)
    lines.extend(["","| Vista | Cálices v5 / v6 | Anotaciones v5 / v6 | Pares físicos v5 / v6 | Separación v5 / v6 |","|---|---:|---:|---:|---:|"])
    for row in rows:
        left,right=row["before"],row["after"]
        lines.append(f"| {row['view_id']} | {left['morphology'].get('calyces',0)} / {right['morphology'].get('calyces',0)} | {left['visible_annotations']} / {right['visible_annotations']} | {left['physical']['physical_collisions']} / {right['physical']['physical_collisions']} | {left['physical']['clearance_violations']} / {right['physical']['clearance_violations']} |")
    for row in rows:
        lines.extend(["",f"![{row['view_id']}: Antes v5 / Después v6]({Path(row['image']).name})"])
        for side,label in (("before","Antes v5"),("after","Después v6")):
            phys=row[side]["physical"]
            lines.append(f"{label}: suelo — intersecciones {phys['ground_physical_collisions']}, déficit {phys['ground_clearance_violations']}, cobertura desconocida {phys['ground_coverage_failures']}. Admisión física con la evidencia disponible: {phys['physically_admitted']}.")
            lines.extend(f"- {issue}" for issue in phys["issues"])
    if refs:
        lines.extend(["","## Referencias reales de entrenamiento",""])
        lines.extend(f"- [Fila {r['source_row']} — {r['group_id']}](references/{Path(r['file']).name})" for r in refs)
    lines.extend(["","## Límites",""]+[f"- {limit}" for limit in result["limits"]])
    (output/"review.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    input_paths = []
    for folder in (before,after):
        input_paths.extend(p for p in folder.glob("*.json") if p.is_file())
        input_paths.extend(p for p in folder.glob("*/capture.json") if p.is_file())
        input_paths.extend(p for p in folder.glob("*/camera.json") if p.is_file())
        input_paths.extend(p for p in folder.glob("*/annotations.json") if p.is_file())
        input_paths.extend(Path(row["path"]) for row in read(folder/"plants.json")["plants"])
    if references:
        input_paths.append(references)
    write(output/"report_manifest.json",{"files":{str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()},
        "report_script_sha256":sha(Path(__file__)),"inputs":{str(p):sha(p) for p in input_paths}})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before",type=Path,required=True)
    parser.add_argument("--after",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--references",type=Path)
    args=parser.parse_args()
    result=report(args.before,args.after,args.output,args.references)
    print(args.output/"review.md")
    if not result["visual_comparison_verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
