"""Summarize measured pilot artifacts without converting failed audits into acceptance."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    summary = read(root/"exports/summary.json")
    integrity = read(root/"exports/integrity_report.json")
    projection = read(root/"mask_projection_report.json")
    files = [p for p in root.rglob("*") if p.is_file()]
    unique_files = { (p.stat().st_dev,p.stat().st_ino):p.stat().st_size for p in files }
    storage = {"logical_bytes":sum(p.stat().st_size for p in files),
               "unique_file_bytes":sum(unique_files.values()),
               "scope":"pilot root including preserved diagnostics; hard links deduplicated"}
    lines = ["# Piloto disperso: entrega técnica para inspección", "",
             f"{summary['capture_count']} imágenes; cuatro escenas de 36 arbustos; dos alturas y tres distancias.",
             "Detección YOLO/COCO y segmentación COCO RLE del capacho visible, con las mismas cuatro clases.",
             "", "**Piloto de inspección; entrenamiento no autorizado en esta entrega.** Consultar los conflictos físicos en la tabla de auditorías.",
             "La integridad de etiquetas y la validez física son comprobaciones independientes.", "",
             "## Artefactos", "", "- [Hoja de contacto RGB](exports/contact_sheet_rgb.jpg)","- [Hoja de contacto con cajas](exports/contact_sheet.jpg)",
             "- [Segmentación COCO](exports/instances_coco.json)","- [Detección COCO](exports/detection_coco.json)",
             "- [Integridad](exports/integrity_report.json)","- [Manifiesto](exports/manifest.json)","",
             "- [Control geométrico de máscaras](mask_projection_report.json)", "",
             "Cada carpeta conserva `cultivation.blend` para auditoría y `capture_geometry.blend` para abrir/renderizar con menor consumo.", "",
             "El RGB usa EEVEE y la identidad Workbench sin antialiasing, con fondo transparente convertido a ID 0.",
             "Los pases EEVEE de identidad iniciales mezclaban colores en bordes; sus exportaciones fallidas se conservan",
             "en el piloto histórico v4 (`exports_eevee_diagnostic/`). La igualdad RLE/máscara no detectaba ese defecto de la máscara maestra.",
             f"El control independiente verificó {projection['visible_instances_checked']} límites proyectados; "
             f"excepciones por plano cercano: {len(projection['skipped'])}.", "",
             "## Escenas y coste medido", "",
             "La memoria registrada es RAM del proceso Blender; no incluye una medición separada de VRAM. Los tiempos y picos corresponden a fases supervisadas e incluyen los intentos fallidos conservados; no miden el tiempo humano ni todas las verificaciones posteriores.", "",
             "| Escena | Colisiones físicas | Separaciones insuficientes | Tiempo (s) | Pico RAM (GiB) |",
             "|---|---:|---:|---:|---:|"]
    scenes = []
    gap_notes=[]
    for folder in sorted(root.glob("scene_*")):
        audit = read(folder/"mesh_audit.json")
        resources = read(folder/"resources.json")
        gaps=[round(b["seconds"]-a["seconds"],3) for phase in resources.get("phases",[resources])
              for a,b in zip(phase.get("samples",[]),phase.get("samples",[])[1:])
              if b["seconds"]-a["seconds"]>10]
        scene_link=f"[{folder.name}]({folder.name}/capture_geometry.blend) · [original]({folder.name}/cultivation.blend)" if (folder/"capture_geometry.blend").exists() else f"[{folder.name}]({folder.name}/cultivation.blend)"
        lines.append(f"| {scene_link} | {audit['physical_collision_count']} | "
                     f"{audit['clearance_violation_count']} | {resources['elapsed_seconds']:.1f} | "
                     f"{resources['peak_working_set_bytes']/1024**3:.2f} |")
        scenes.append({"scene":folder.name,"physical_collisions":audit['physical_collision_count'],
                       "clearance_violations":audit['clearance_violation_count'],
                       "leaf_mesh_intersections":audit['soft_occupancy_intersection_count'],
                       "seconds":resources['elapsed_seconds'],"peak_ram_bytes":resources['peak_working_set_bytes'],
                       "monitoring_gaps_over_10_seconds":gaps})
        if gaps:
            gap_notes.append(f"Registro temporal de {folder.name}: intervalos sin muestras de {gaps} s; el tiempo total no equivale a cómputo continuo.")
    lines += ["",*gap_notes]
    lines += ["",f"Intersecciones geométricas con hojas: {sum(s['leaf_mesh_intersections'] for s in scenes)}. "
              "Se registran como ocupación blanda sin validación física; no son oclusiones visuales medidas en imagen."]
    repair_seconds = sum(read(p)["seconds"] for p in root.glob("scene_*/mask_repair.json"))
    drone_heights = [read(p)["capture"]["height_m"] for p in root.glob("scene_*/*close_drone/capture.json")]
    lines += ["", f"Reprocesado de máscaras: {repair_seconds:.1f} s adicionales; memoria de ese pase no muestreada.",
              f"Almacenamiento con diagnósticos conservados: {storage['unique_file_bytes']/1024**3:.2f} GiB "
              f"sin duplicar enlaces duros ({storage['logical_bytes']/1024**3:.2f} GiB lógicos).",
              f"Alturas de dron ejecutadas: {', '.join(f'{h:.3f}' for h in drone_heights)} m; cosechador: 0,400 m.",
              "Las alturas se calculan sobre el arbusto objetivo de cada escena; ambas caras comparten ese objetivo.",
              "El 50 % se calcula sobre la altura de ejes reportada por el intérprete (proxy de altura del arbusto); no sobre la silueta foliar. La escala necesita contraste con mediciones del cultivo."]
    lines += ["", "## Etiquetas", "",f"Instancias por vista verificadas: {integrity['instances_checked']}.",
              "Cada instancia repetida en otra vista vuelve a contarse; no son frutos independientes.","",
              "| Clase | Anotaciones |","|---|---:|"]
    for name in ("verde","pintona","madura","sobremadura"):
        count=summary["class_counts"].get(name,0)
        lines.append(f"| {name} | {count} |")
    if (root/"density_comparison.json").exists():
        density=read(root/"density_comparison.json")
        lines += ["", "## Densidad de las copas", "",
                  f"Comparación de {density['plants']} plantas con v4: "
                  f"{density['ratios']['leaves']:.2f} veces más hojas y {density['ratios']['axes']:.2f} veces más ejes.",
                  "Las posiciones de los 36 arbustos por escena permanecen iguales.",
                  "Los tamaños e inclinaciones foliares se ajustaron cualitativamente con fotos de train; no son mediciones de campo.",
                  "[Detalle por planta](density_comparison.json). Ocho iteraciones locales; búsqueda exhaustiva de poses omitida",
                  "y declarada en los JSON. La auditoría de mallas y el bloqueo de entrenamiento permanecen activos."]
    lines += ["", "Grados simulados: 0–1 verde, 2–4 pintona, 5 madura y 6 sobremadura.",
              "La agrupación es aproximada y no valida madurez agronómica real por apariencia del capacho.",
              "", "## ArUco", "",
              "72 IDs únicos DICT_4X4_100 por escena; frente y atrás de cada planta, lado negro 10 cm.",
              "Las placas tienen reverso opaco sin patrón; cada escena incluye ambas caras del mismo arbusto objetivo.",
              f"Comprobaciones de respaldo opaco: {projection.get('opaque_marker_reverse_rays_checked',0)} rayos. "
              f"Vistas con IDs detectados incompatibles con la cara: {len(integrity.get('marker_detection_warnings',[]))}.",
              "Errores calculados para poses detectadas; proyección dentro del cuadro no garantiza visibilidad.","",
              "| Cara / distancia / altura | Poses | Frente/en cuadro sin detectar | Error mediano traslación (cm) | Error mediano rotación (°) | Ambiguas |",
              "|---|---:|---:|---:|---:|---:|"]
    groups = defaultdict(list)
    misses = defaultdict(int)
    unexpected = []
    for path in sorted((root/"exports/aruco").glob("*.json")):
        report = read(path)
        capture = report["capture"]
        key = (capture["face"],capture["distance_band"],capture["height_band"])
        groups[key].extend(m for m in report["markers"] if m.get("selected"))
        misses[key] += sum(m["in_frame"] and m["front_facing"] and not m["detected"] for m in report["markers"])
        unexpected.extend(report["unexpected_ids"])
    pose_summary = []
    for key,rows in sorted(groups.items()):
        translation = statistics.median(r["selected"]["translation_error_m"] for r in rows)*100 if rows else None
        rotation = statistics.median(r["selected"]["rotation_error_deg"] for r in rows) if rows else None
        ambiguity = sum(r["ambiguous"] for r in rows)
        t = f"{translation:.2f}" if translation is not None else "—"
        r = f"{rotation:.2f}" if rotation is not None else "—"
        lines.append(f"| {' / '.join(key)} | {len(rows)} | {misses[key]} | {t} | {r} | {ambiguity} |")
        pose_summary.append({"stratum":key,"poses":len(rows),"median_translation_cm":translation,
                             "median_rotation_deg":rotation,"ambiguous":ambiguity,
                             "front_in_frame_not_detected_occlusion_unknown":misses[key]})
    lines += ["",f"IDs inesperados detectados: {unexpected}.","",
              "No se reconstruyó profundidad de capachos desde RGB: se exportaron referencias geométricas conocidas.",
              "", "## Límites y siguiente paso", "",
              "Corregir cruces residuales de hilos/órganos y separaciones insuficientes, repetir la auditoría de mallas",
              "y revisar fidelidad visual antes de presupuestar entrenamiento. Los reportes conservan nombres de",
              "objetos e identidades de planta para reproducir cada conflicto. No se relajaron los umbrales físicos.",
              "En `scene_02/front_far_drone` y `scene_02/back_mid_drone`, hojas próximas a cámara tapan parte importante del encuadre; se conservan como casos de oclusión visual para revisión.",
              "No se entrenó ni evaluó ningún detector sobre el test histórico o sobre el dataset nuevo.",
              "Las particiones de entrenamiento quedan sin asignar; las vistas de cada escena deberán mantenerse juntas.","",
              "Los hashes de código adjuntos son una instantánea de cierre, no un lock retrospectivo de las ejecuciones."]
    (root/"INFORME.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    sources = list((ROOT/"src/uchuva_lsystem").glob("*.py")) + list((ROOT/"scripts").glob("*sparse*.py"))
    provenance = {"kind":"post_run_source_snapshot_not_execution_lock",
        "git_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "source_sha256":{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (root/"source_snapshot.json").write_text(json.dumps(provenance,indent=2),encoding="utf-8")
    (root/"measured_summary.json").write_text(json.dumps({"scenes":scenes,"poses":pose_summary,
        "unexpected_ids":unexpected,"integrity":integrity,"mask_projection":projection,
        "storage":storage,"mask_repair_seconds":repair_seconds,"classes":summary["class_counts"]},indent=2),encoding="utf-8")
    print(root/"INFORME.md")


if __name__=="__main__": main()
