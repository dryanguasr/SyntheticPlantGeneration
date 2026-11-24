"""Package already computed results; never render, infer, track or train.

Run from the repository root with the existing training environment (OpenCV).
The output is a separate, immutable publication snapshot. The complete original
route JSONs are losslessly gzipped; compact JSONs only omit long change lists.
"""
from pathlib import Path
import csv
import gzip
import hashlib
import html
import json
import shutil
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "outputs/multiscale_dataset_20261020"
FLIGHT = REPO / "outputs/multiscale_flights_20261021"
FULL = FLIGHT / "full_routes_v1"
DEST = REPO / "docs/reports/campana_multiescala_20261021_parcial_v1"
PROVENANCE = []


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy(source, target):
    dest = DEST / target
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    assert sha(source) == sha(dest)
    PROVENANCE.append({"source": source.relative_to(REPO).as_posix(),
                       "published": dest.relative_to(DEST).as_posix(),
                       "source_sha256": sha(source), "transformation": "byte-identical"})
    return dest


def compact(value):
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items() if k != "changes"}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def make_package():
    if (DEST / "publication_manifest.json").exists():
        raise RuntimeError("Publication already sealed; create a new version instead.")
    DEST.mkdir(parents=True, exist_ok=True)
    for name in ["protocol.json", "campaign_manifest.json", "split_plan.json",
                 "training_readiness.json", "split_integrity_audit_v1.json",
                 "current_dataset_loader_check_v1.json", "native_augmentation_integration_check.json",
                 "evaluation_protocol_v1.json", "evaluation_delivery_audit_v1.json",
                 "detector_review_v1.json", "state.json"]:
        copy(DATA / name, "evidence/dataset/" + name)
    copy(DATA / "native_evaluation_v1/summary.json", "metrics/static_full_views.json")
    copy(DATA / "training_runs/training/results.csv", "metrics/training_results.csv")
    copy(DATA / "training_runs/training/args.yaml", "evidence/dataset/training_args.yaml")
    copy(DATA / "training_runs/training/weights/last.pt", "models/multiscale_last.pt")
    copy(REPO / "outputs/frozen_field_pilot_20261019/training_runs/training/weights/last.pt", "models/reference_last.pt")
    for name in ["protocol.json", "preparation_manifest.json", "launch_readiness_v1.json",
                 "preflight_delivery_v1.json", "preflight_report_v1.json", "sensor_protocol_v1.json",
                 "presentation_protocol_v1.json", "delivery_selection_plan_v1.json", "delivery_stage_state_v1.json"]:
        copy(FULL / name, "evidence/flights/" + name)
    for name in ["tracking_failure_diagnosis_v1.json", "historical_reprojection_recovery_review_v1.json"]:
        copy(FLIGHT / name, "evidence/diagnosis/" + name)
    copy(FULL / "route_preflight_overview_v1.png", "images/routes.png")
    for p in (DATA / "scale_review_v1").iterdir():
        if p.is_file():
            copy(p, "dataset_sample/" + p.name)
    # These are source snapshots for reading, not a standalone executable bundle.
    for parent, subdir, names in [
        (DATA, "dataset", ["train_multiscale.py", "native_raster_trainer.py", "evaluate_multiscale_v1.py"]),
        (FULL, "flights", ["infer_public_full_routes_v1.py", "track_public_full_routes_v1.py", "evaluate_full_routes_private_v1.py", "export_relative_sensors_v1.py", "marker_observation_contract_v1.py"]),
        (REPO / "scripts", "shared", ["multiscale_native_augmentation.py", "raster_segmentation_inference.py", "train_raster_segmentation.py", "track_continuous_predictions.py"]),
    ]:
        for name in names:
            copy(parent / name, "source_snapshot/" + subdir + "/" + name)
    for source in ["AGENTS.md", "docs/reports/dataset_multiescala_2026-10-20.md"]:
        copy(REPO / source, "evidence/context/" + Path(source).name)
    selection = read(FULL / "three_route_delivery_v1/selection_resolved_v1.json")
    copy(FULL / "three_route_delivery_v1/selection_resolved_v1.json", "evidence/flights/example_selection.json")
    routes = {}
    videos = []
    import cv2
    from PIL import Image, ImageDraw
    qa = REPO / "tmp/pdfs/video_review"
    qa.mkdir(parents=True, exist_ok=True)
    plan = read(FULL / "delivery_selection_plan_v1.json")
    for route in ["legacy", "vertical", "orbit"]:
        root = FULL / "flights" / route
        original = root / "evaluation_private_v1/summary.json"
        summary = read(original)
        routes[route] = compact(summary)
        write(DEST / f"metrics/{route}.json", routes[route])
        raw = original.read_bytes()
        gz = DEST / f"evidence/flights/{route}_full_evaluation.json.gz"
        gz.write_bytes(gzip.compress(raw, mtime=0))
        assert gzip.decompress(gz.read_bytes()) == raw
        PROVENANCE.append({"source": original.relative_to(REPO).as_posix(), "published": gz.relative_to(DEST).as_posix(), "source_sha256": sha(original), "transformation": "lossless gzip; original UTF-8 JSON"})
        for name in ["evaluation_arithmetic_review_v1.json", "validation_v1.json"]:
            copy(root / name, f"evidence/flights/{route}_{name}")
        if (root / "preliminary_visual_review_v1.json").exists():
            copy(root / "preliminary_visual_review_v1.json", f"evidence/flights/{route}_preliminary_visual_review_v1.json")
        for matrix in (root / "evaluation_private_v1").glob("confusion*.png"):
            copy(matrix, f"matrices/{route}/{matrix.name}")
        for rank, item in selection["selected"][route].items():
            frame = item["frame"]
            copy(root / f"tracking_new/frame_{frame:03d}.jpg", f"images/{route}_{rank}_{frame:03d}.jpg")
        v = root / "presentation_v1/video_verification.json"
        if v.exists():
            receipt = read(v)
            assert receipt["complete"] and receipt["decode_passed"]
            source = root / "presentation_v1/tracking_4fps_pip.mp4"
            assert sha(source) == receipt["video_sha256"]
            target = copy(source, f"videos/{route}_4fps_pip.mp4")
            copy(v, f"evidence/flights/{route}_video_verification.json")
            cap = cv2.VideoCapture(str(target))
            frame_count = 0
            selected = set(plan['routes'][route]['fixed_selected_frames_union'])
            cells = []
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame_count in selected:
                    im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    im.thumbnail((640, 360))
                    cell = Image.new("RGB", (640, 385), "white")
                    cell.paste(im, (0, 25))
                    ImageDraw.Draw(cell).text((8, 6), f"{route} | frame {frame_count}", fill="black")
                    cells.append(cell)
                frame_count += 1
            fps = cap.get(cv2.CAP_PROP_FPS)
            cap.release()
            assert frame_count == receipt["frames"] and abs(fps - 4) < 0.001
            for start in range(0, len(cells), 6):
                part = cells[start:start+6]
                sheet = Image.new("RGB", (1280, 385*((len(part)+1)//2)), "white")
                for j, cell in enumerate(part):
                    sheet.paste(cell, ((j%2)*640,(j//2)*385))
                sheet.save(qa/f"{route}_{start//6}.jpg")
            videos.append({"route": route, "file": target.relative_to(DEST).as_posix(), "frames_decoded":frame_count, "fps": fps, "duration_seconds":receipt["duration_seconds"], "sha256":sha(target), "visual_review":"pending"})
    # Preserve the previous three short diagnostic clips, including the camera failure.
    pilot = FLIGHT / "route_pilot_v1"
    for route in ["legacy", "vertical", "orbit"]:
        candidates = list((pilot / "flights" / route).rglob("tracking_4fps_pip.mp4"))
        for p in candidates:
            copy(p, f"videos/negative_pilot_{route}_{p.parent.name}.mp4")
    write(DEST / "publication_status.json", {
        "snapshot_utc":datetime.now(timezone.utc).isoformat(), "status":"partial",
        "dataset_training_static_evaluation":"complete", "full_routes_detection_tracking":"complete",
        "videos":videos, "orbit_pip_pending":not any(v['route']=='orbit' for v in videos),
        "metric_localization":"not executed; no new 3D accuracy available",
        "scientific_promotion":False,
        "scope":"Student-facing result archive, NOT an inference input directory. Evaluator truth in evidence must never feed the estimator.",
        "omitted_bulk_data":"Raw 384-view dataset, crop tensors, 627-frame captures and prediction caches remain local under outputs. Their manifests/hashes and complete evaluation JSONs are included; this is not a full dataset mirror.",
    })
    write(DEST / "provenance.json", PROVENANCE)
    # Keep the existing comparison and remap every local image into this package.
    import re
    report = (FULL / "three_route_delivery_v1/index.html").read_text(encoding="utf-8")
    def replace(match):
        attr, url = match.group(1), match.group(2)
        source = (FULL / "three_route_delivery_v1" / url).resolve()
        if not source.is_file():
            raise ValueError(f"Unresolved report link {url}")
        if source.suffix == '.json' and source.name == 'summary.json' and 'flights' in source.parts:
            # Existing report links point to summaries; portable compact copies preserve all metrics.
            route = source.parts[source.parts.index('flights')+1]
            dest = f"metrics/{route}.json"
        else:
            dest = 'report_assets/' + source.parent.parent.name + '_' + source.parent.name + '_' + source.name
            copy(source, dest)
        return f'{attr}="{dest}"'
    report = re.sub(r'(src|href)="([^"#]+)"', replace, report)
    # Existing comparison has no video elements. Add verified native media only.
    content = '<section><h2>Entrega parcial para las estudiantes</h2><p><a href="guia_estudiantes.pdf">Guía PDF</a> | <a href="README.md">Orientación y límites</a> | <a href="dataset_sample/index.html">Dataset con máscaras originales</a></p><p>La detección y el seguimiento de las tres rutas terminaron. La localización 3D sigue pendiente. El PiP orbital aún no se publica en este corte.</p>'
    for video in videos:
        content += f'<h3>{html.escape(video["route"])} - {video["duration_seconds"]} s</h3><video controls preload="metadata" style="width:100%;max-width:1000px" src="{video["file"]}"></video>'
    content += '</section>'
    report = report.replace('<body>', '<body>'+content, 1) if '<body>' in report else report + content
    (DEST / 'index.html').write_text(report, encoding='utf-8')
    write(DEST / "provenance.json", PROVENANCE)
    print(json.dumps({"package":str(DEST),"files":len(list(DEST.rglob('*'))),"videos":videos,"size_MiB":sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file())/2**20},indent=2))


if __name__ == "__main__":
    make_package()
