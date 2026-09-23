"""Reproducible, review-gated curation of unlabelled photos and videos.

Image similarity proposes relationships; it never certifies independent areas.
OpenCV and Pillow are existing optional tools, not core morphology dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import random
import shutil

import cv2
import numpy as np
from PIL import Image, ImageOps

VERSION = "1.0.0"
SEED = 20260922
RATIOS = {"train": .70, "val": .15, "test": .15}
MEDIA = {".jpg", ".jpeg", ".png", ".mp4", ".mov"}
# Selection heuristics, not botanical measurements. Flag only; do not reject.
CONFIG = {"sample_seconds": 1.0, "probe_seconds": .5,
          "change_mean_absolute": 18.0, "dhash_hamming": 4,
          "thumbnail_mae": 12.0, "photo_burst_seconds": 90,
          "jpeg_quality": 95, "seed": SEED}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".jsonl":
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    else:
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def read_rows(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def inventory(source, out):
    """Hash a stable source snapshot; never silently resume changed inputs."""
    rows = []
    for p in sorted(source.rglob("*")):
        if not p.is_file():
            continue
        before = p.stat()
        sha = digest(p)
        if (before.st_size, before.st_mtime_ns) != (p.stat().st_size, p.stat().st_mtime_ns):
            raise ValueError(f"Source changed while reading: {p}")
        relative = p.relative_to(source).as_posix()
        row = dict(source_id=hashlib.sha256(relative.encode()).hexdigest()[:16],
                   source=relative, sha256=sha, bytes=before.st_size,
                   kind="video" if p.suffix.lower() in {".mp4", ".mov"} else "photo",
                   device="unknown", capture_time="", status="readable")
        if p.suffix.lower() not in MEDIA:
            row.update(kind="reference", status="not_media")
        else:
            try:
                if row["kind"] == "photo":
                    with Image.open(p) as im:
                        exif = im.getexif()
                        row.update(width=im.width, height=im.height, orientation=int(exif.get(274, 1)),
                                   device=str(exif.get(272, "unknown")).strip("\x00"),
                                   capture_time=str(exif.get(36867, exif.get(306, ""))))
                        im.load()
                else:
                    cap = cv2.VideoCapture(str(p))
                    try:
                        if not cap.isOpened():
                            raise ValueError("Cannot open video")
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        row.update(width=int(cap.get(3)), height=int(cap.get(4)), fps=fps,
                                   frame_count=count, duration_estimate_seconds=count / fps if fps else None,
                                   orientation=cap.get(cv2.CAP_PROP_ORIENTATION_META),
                                   device="DJI_filename" if p.name.startswith("dji_") else "unknown_video")
                        ok, _ = cap.read()
                        if not ok:
                            raise ValueError("Cannot decode first frame")
                    finally:
                        cap.release()
            except Exception as error:
                row.update(status="unreadable", error=str(error))
        rows.append(row)
    target = out / "inventory.json"
    if target.exists():
        previous = {r["source"]: r["sha256"] for r in read_json(target)["files"]}
        current = {r["source"]: r["sha256"] for r in rows}
        if current != previous:
            change = dict(added=sorted(current.keys() - previous.keys()),
                          removed=sorted(previous.keys() - current.keys()),
                          modified=sorted(k for k in current.keys() & previous.keys() if current[k] != previous[k]))
            write_json(out / "input_changes.json", change)
            raise ValueError("Inputs changed. Use a new --version; see input_changes.json")
    value = dict(tool_version=VERSION, config=CONFIG, files=rows,
                 runtime=dict(opencv=cv2.__version__, numpy=np.__version__, pillow=Image.__version__))
    write_json(target, value)
    return rows


def image_features(rgb):
    small = cv2.resize(rgb, (32, 32), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    d = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (d[:, 1:] > d[:, :-1]).flatten()
    code = 0
    for bit in bits:
        code = (code << 1) | int(bit)
    # Common resolution for diagnostics only, never a quality rejection rule.
    inspection = cv2.resize(rgb, (256, 256), interpolation=cv2.INTER_AREA)
    sharpness = float(cv2.Laplacian(cv2.cvtColor(inspection, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())
    dark = float((gray < 12).mean())
    bright = float((gray > 243).mean())
    flags = []
    if sharpness < 40:
        flags.append("possible_blur_or_low_texture")
    if dark > .65 or bright > .65:
        flags.append("possible_extreme_exposure")
    return dict(dhash=f"{code:016x}", thumbnail=small.flatten().tolist(),
                sharpness=round(sharpness, 3), dark_fraction=round(dark, 3),
                bright_fraction=round(bright, 3), quality_flags=";".join(flags))


def candidates(source, out, files):
    """Decode sequentially; sample by decoder timestamps, retaining frame indices."""
    all_rows, errors = [], []
    cache = out / "candidates"
    cache.mkdir(parents=True, exist_ok=True)
    for number, src in enumerate(files):
        if src["status"] != "readable":
            if src["status"] == "unreadable":
                errors.append(src)
            continue
        sid = src["source_id"]
        shard = out / "source_records" / f"{sid}.json"
        if shard.exists():
            saved = read_json(shard)
            if saved["source_sha256"] != src["sha256"]:
                raise ValueError("Candidate cache source mismatch")
            if not all((out / r["candidate_path"]).exists() for r in saved["rows"]):
                raise ValueError("Incomplete candidate cache; use a new output version")
            all_rows.extend(saved["rows"])
            errors.extend(saved["errors"])
            continue
        path = source / src["source"]
        if digest(path) != src["sha256"]:
            raise ValueError(f"Source changed: {path}")
        records, source_errors = [], []

        def save(rgb, frame=None, timestamp=None, reason="photo", original=None):
            ident = f"{sid}_" + (f"f{frame:09d}" if frame is not None else "photo")
            target = cache / f"{ident}.jpg"
            if original:
                target = cache / f"{ident}{path.suffix.lower()}"
                shutil.copy2(path, target)
            else:
                Image.fromarray(rgb).save(target, quality=CONFIG["jpeg_quality"])
            thumb = out / "thumbnails" / f"{ident}.jpg"
            thumb.parent.mkdir(exist_ok=True)
            preview = Image.fromarray(rgb)
            preview.thumbnail((320, 240))
            preview.save(thumb, quality=80)
            records.append(dict(image_id=ident, source_id=sid, source=src["source"],
                                source_sha256=src["sha256"], kind=src["kind"], device=src["device"],
                                frame_index=frame, timestamp_seconds=timestamp, selection_reason=reason,
                                width=rgb.shape[1], height=rgb.shape[0],
                                candidate_path=target.relative_to(out).as_posix(),
                                sha256=digest(target), pixel_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                                **image_features(rgb)))
        try:
            if src["kind"] == "photo":
                with Image.open(path) as im:
                    oriented = ImageOps.exif_transpose(im).convert("RGB")
                    save(np.array(oriented), original=src["orientation"] == 1)
            else:
                cap = cv2.VideoCapture(str(path))
                cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
                index, next_probe, next_regular, previous_time = -1, 0., 0., -1.
                prior = None
                try:
                    while cap.grab():
                        index += 1
                        timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.
                        if not np.isfinite(timestamp) or (index > 0 and timestamp <= previous_time):
                            raise ValueError(f"Non-increasing decoder timestamp at frame {index}; manual decoder review required")
                        previous_time = timestamp
                        if timestamp + 1e-6 < next_probe:
                            continue
                        ok, frame = cap.retrieve()
                        if not ok:
                            source_errors.append(dict(source=src["source"], frame_index=index, status="unreadable_frame"))
                            next_probe += CONFIG["probe_seconds"]
                            continue
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        small = cv2.resize(rgb, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
                        change = float(np.abs(small - prior).mean()) if prior is not None else 0
                        regular = timestamp + 1e-6 >= next_regular
                        if regular or change >= CONFIG["change_mean_absolute"]:
                            save(rgb, index, round(timestamp, 6), "regular" if regular else "scene_change")
                        if regular:
                            next_regular = (int(timestamp / CONFIG["sample_seconds"]) + 1) * CONFIG["sample_seconds"]
                        next_probe = (int(timestamp / CONFIG["probe_seconds"]) + 1) * CONFIG["probe_seconds"]
                        prior = small
                    if src.get("frame_count", 0) > index + 2:
                        source_errors.append(dict(source=src["source"], status="incomplete_decode",
                                                  decoded_frames=index + 1, expected_frames=src["frame_count"]))
                finally:
                    cap.release()
        except Exception as error:
            source_errors.append(dict(source=src["source"], status="extraction_error", error=str(error)))
        if digest(path) != src["sha256"]:
            raise ValueError(f"Source changed during extraction: {path}")
        write_json(shard, dict(source_sha256=src["sha256"], rows=records, errors=source_errors))
        all_rows.extend(records)
        errors.extend(source_errors)
        print(f"[{number+1}/{len(files)}] {src['source']}: {len(records)} candidates", flush=True)
    write_rows(out / "candidates.jsonl", all_rows)
    write_json(out / "extraction_issues.json", errors)
    return all_rows


class Groups:
    def __init__(self, ids):
        self.parent = {x: x for x in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a, b):
        a, b = sorted((self.find(a), self.find(b)))
        self.parent[b] = a


def propose_review(out, files, rows):
    """Propose conservative source components and explicitly pending pair reviews."""
    groups = Groups([r["source_id"] for r in rows])
    photos = defaultdict(list)
    for src in files:
        if src["source_id"] not in groups.parent or src["kind"] != "photo":
            continue
        try:
            dt = datetime.strptime(src["capture_time"], "%Y:%m:%d %H:%M:%S")
            photos[src["device"]].append((dt, src["source_id"]))
        except ValueError:
            pass
    for sequence in photos.values():
        sequence.sort()
        for a, b in zip(sequence, sequence[1:]):
            if (b[0] - a[0]).total_seconds() <= CONFIG["photo_burst_seconds"]:
                groups.join(a[1], b[1])
    pairs = []
    features = [int(r["dhash"], 16) for r in rows]
    thumbs = np.array([r["thumbnail"] for r in rows], dtype=np.float32)
    for i, row in enumerate(rows):
        exact = row["pixel_sha256"]
        for j in range(i):
            other = rows[j]
            is_exact = exact == other["pixel_sha256"] or row["sha256"] == other["sha256"]
            if not is_exact and (features[i] ^ features[j]).bit_count() > CONFIG["dhash_hamming"]:
                continue
            mae = float(np.abs(thumbs[i] - thumbs[j]).mean())
            aspect_diff = abs(row["width"] / row["height"] - other["width"] / other["height"])
            if not is_exact and (mae > CONFIG["thumbnail_mae"] or aspect_diff > .08):
                continue
            groups.join(row["source_id"], other["source_id"])
            pairs.append(dict(left=other["image_id"], right=row["image_id"],
                              left_source=other["source_id"], right_source=row["source_id"],
                              hamming=(features[i] ^ features[j]).bit_count(), mae=round(mae, 3),
                              verdict="exact" if is_exact else (
                                  "same_source" if row["source_id"] == other["source_id"] else "pending")))
    source_review = []
    for src in files:
        sid = src["source_id"]
        if sid in groups.parent:
            source_review.append(dict(source_id=sid, source=src["source"],
                                      group_id="g_" + groups.find(sid), group_review="pending",
                                      rotation_cw=0, notes=""))
    review = []
    # Re-evaluate supplementary probes at an anti-aliased resolution. This also
    # supports older oversampled caches without discarding recoverable frames.
    temporal_reserve = set()
    previous = {}
    for row in rows:
        if row.get("kind") != "video":
            continue
        prior = previous.get(row["source_id"])
        if prior is not None and row["selection_reason"] == "scene_change":
            delta = row["timestamp_seconds"] - prior["timestamp_seconds"]
            change = float(np.abs(np.array(row["thumbnail"], dtype=float) - np.array(prior["thumbnail"], dtype=float)).mean())
            if delta <= CONFIG["probe_seconds"] + .15 and change < CONFIG["change_mean_absolute"]:
                temporal_reserve.add(row["image_id"])
        previous[row["source_id"]] = row
    # Direct-neighbour selection, not transitive components: A~B and B~C does
    # not imply A~C. This preserves slow zoom/pan changes in long sequences.
    neighbours = defaultdict(set)
    for pair in pairs:
        neighbours[pair["left"]].add(pair["right"])
        neighbours[pair["right"]].add(pair["left"])
    representatives, selected = {}, set()
    for row in sorted(rows, key=lambda r: (-r["sharpness"], r["image_id"])):
        if row["image_id"] in temporal_reserve:
            continue
        matches = sorted(neighbours[row["image_id"]] & selected)
        if matches:
            representatives[row["image_id"]] = matches[0]
        else:
            selected.add(row["image_id"])
    for row in rows:
        prior = representatives.get(row["image_id"], "")
        temporal = row["image_id"] in temporal_reserve
        review.append(dict(image_id=row["image_id"], selection="reserve" if prior or temporal else "include",
                           duplicate_of=prior or "", quality_review="pending", small="unknown",
                           medium="unknown", large="unknown", sin_objetivo_visible="unknown",
                           incierto="unknown", scale_review="pending",
                           notes="Sondeo intermedio sin cambio suficiente en miniatura antialias; recuperable." if temporal else (
                               "Reserva por semejanza directa; verificar antes de descartar." if prior else "")))
    for name, values in [("source_review.csv", source_review), ("image_review.csv", review), ("pair_review.csv", pairs)]:
        if not (out / name).exists():
            write_rows(out / name, values)
    if not (out / "pair_proposals.json").exists():
        write_json(out / "pair_proposals.json", pairs)
    return pairs


def assign_splits(records, seed=SEED):
    """Deterministic grouped allocation balancing total and device/kind counts."""
    grouped = defaultdict(list)
    for r in records:
        grouped[r["group_id"]].append(r)
    keys = sorted({r["kind"] + ":" + r["device"] for r in records})
    vectors = {g: np.array([len(rs)] + [sum(r["kind"] + ":" + r["device"] == k for r in rs) for k in keys]
                          + [sum(r.get(scale) == "yes" for r in rs) for scale in ["small", "medium", "large"]], dtype=float)
               for g, rs in grouped.items()}
    total = sum(vectors.values(), np.zeros(4 + len(keys)))
    rng = random.Random(seed)
    best = None
    for attempt in range(128):
        order = sorted(grouped)
        rng.shuffle(order)
        if attempt == 0:
            order.sort(key=lambda g: -len(grouped[g]))
        actual = {s: np.zeros_like(total) for s in RATIOS}
        assigned = {}
        for index, g in enumerate(order):
            empty = [s for s in RATIOS if s not in assigned.values()]
            choices = empty if len(order) - index == len(empty) else list(RATIOS)
            def score(split):
                return sum(float(np.sum(((actual[s] + (vectors[g] if s == split else 0) - ratio * total)
                                         / np.maximum(total, 1)) ** 2)) for s, ratio in RATIOS.items())
            choice = min(choices, key=score)
            assigned[g] = choice
            actual[choice] += vectors[g]
        loss = sum(float(np.sum(((actual[s] - ratio * total) / np.maximum(total, 1)) ** 2)) for s, ratio in RATIOS.items())
        # Prefer coverage of reviewed scales when at least three independent
        # groups contain them. Missing coverage still blocks freeze explicitly.
        for column in range(len(total) - 3, len(total)):
            if sum(vector[column] > 0 for vector in vectors.values()) >= 3:
                loss += 1000 * sum(actual[s][column] == 0 for s in RATIOS)
        if best is None or loss < best[0]:
            best = (loss, assigned)
    return best[1] if best else {}


def checked_review(out, rows):
    images = read_rows(out / "image_review.csv")
    sources = read_rows(out / "source_review.csv")
    if len({r["image_id"] for r in images}) != len(images) or {r["image_id"] for r in images} != {r["image_id"] for r in rows}:
        raise ValueError("Image review must contain each candidate exactly once")
    if len({r["source_id"] for r in sources}) != len(sources) or {r["source_id"] for r in sources} != {r["source_id"] for r in rows}:
        raise ValueError("Source review must contain each source exactly once")
    for r in images:
        if r["selection"] not in {"include", "reserve", "exclude"}:
            raise ValueError("Invalid selection")
        if r["scale_review"] not in {"pending", "reviewed"} or r["quality_review"] not in {"pending", "reviewed"}:
            raise ValueError("Invalid review state")
        for field in ["small", "medium", "large", "sin_objetivo_visible", "incierto"]:
            if r[field] not in {"yes", "no", "unknown"}:
                raise ValueError("Scale fields accept yes/no/unknown")
        if r["scale_review"] == "reviewed" and any(r[k] == "unknown" for k in ["small", "medium", "large", "sin_objetivo_visible", "incierto"]):
            raise ValueError("Reviewed scales must resolve unknown fields (use incierto=yes)")
        if r["sin_objetivo_visible"] == "yes" and any(r[k] == "yes" for k in ["small", "medium", "large"]):
            raise ValueError("No visible target conflicts with scale presence")
    for r in sources:
        if not r["group_id"] or r["group_review"] not in {"pending", "reviewed"} or r["rotation_cw"] not in {"0", "90", "180", "270"}:
            raise ValueError("Invalid source group review or rotation")
    return {r["image_id"]: r for r in images}, {r["source_id"]: r for r in sources}


def partition(out, rows):
    images, sources = checked_review(out, rows)
    groups = Groups([r["source_id"] for r in rows])
    by_name = {}
    for sid, r in sources.items():
        groups.join(sid, by_name.setdefault(r["group_id"], sid))
    pairs = read_rows(out / "pair_review.csv")
    proposals = read_json(out / "pair_proposals.json")
    expected = {(p["left"], p["right"]): p for p in proposals}
    if len(pairs) != len(expected) or {(p["left"], p["right"]) for p in pairs} != set(expected):
        raise ValueError("Pair review must resolve each proposed pair exactly once")
    for p in pairs:
        original = expected[p["left"], p["right"]]
        if any(p[key] != original[key] for key in ["left_source", "right_source"]):
            raise ValueError("Pair source identity changed")
        if original["verdict"] == "exact" and p["verdict"] != "exact":
            raise ValueError("Exact duplicates cannot be overridden")
        if p["verdict"] not in {"exact", "same_source", "pending", "same_scene", "duplicate", "different_scene"}:
            raise ValueError("Invalid pair verdict")
        if p["verdict"] == "same_source" and p["left_source"] != p["right_source"]:
            raise ValueError("same_source is reserved for pairs from one source")
        # Pending relationships are conservative grouping constraints, never split apart.
        if p["verdict"] != "different_scene":
            groups.join(p["left_source"], p["right_source"])
    # Review cannot override exact pixel equality.
    seen = {}
    for r in rows:
        groups.join(r["source_id"], seen.setdefault(r["pixel_sha256"], r["source_id"]))
    all_records = []
    for r in rows:
        record = {k: v for k, v in r.items() if k != "thumbnail"}
        record.update(images[r["image_id"]])
        record.update(group_id="g_" + groups.find(r["source_id"]),
                      proposed_area=sources[r["source_id"]]["group_id"],
                      group_review=sources[r["source_id"]]["group_review"],
                      rotation_cw=int(sources[r["source_id"]]["rotation_cw"]), split="")
        record.update(candidate_width=r["width"], candidate_height=r["height"])
        if record["rotation_cw"] in {90, 270}:
            record["width"], record["height"] = r["height"], r["width"]
        all_records.append(record)
    selected = [r for r in all_records if r["selection"] == "include"]
    policy_path = out / "preserved_splits.json"
    if policy_path.exists():
        assigned = read_json(policy_path)["groups"]
        if any(assigned.get(r["group_id"]) not in RATIOS for r in selected):
            raise ValueError("Preserved splits do not cover current groups; review grouping before repartitioning")
    else:
        assigned = assign_splits(selected)
    for r in all_records:
        r["split"] = assigned.get(r["group_id"], "")
    write_rows(out / "manifest.jsonl", all_records)
    write_rows(out / "manifest.csv", all_records)
    write_json(out / "split_assignment.json", dict(seed=SEED, ratios=RATIOS, groups=assigned))
    coverage = {}
    for split in RATIOS:
        subset = [r for r in selected if r["split"] == split]
        coverage[split] = dict(images=len(subset), groups=len({r["group_id"] for r in subset}),
                               fraction=len(subset) / max(len(selected), 1),
                               target_fraction=RATIOS[split],
                               deviation_percentage_points=round(100 * (len(subset) / max(len(selected), 1) - RATIOS[split]), 3),
                               by_device=dict(Counter(r["device"] for r in subset)),
                               by_kind=dict(Counter(r["kind"] for r in subset)),
                               scales={scale: dict(images=sum(r[scale] == "yes" for r in subset),
                                        groups=len({r["group_id"] for r in subset if r[scale] == "yes"}))
                                       for scale in ["small", "medium", "large"]},
                               scale_pending=sum(r["scale_review"] != "reviewed" for r in subset))
    blockers = []
    if any(r["group_review"] != "reviewed" for r in sources.values()):
        blockers.append("source_groups_pending")
    if any(p["verdict"] == "pending" for p in pairs):
        blockers.append("similarity_pairs_pending")
    if any(r["scale_review"] != "reviewed" or r["quality_review"] != "reviewed" for r in selected):
        blockers.append("image_review_pending")
    if any(not coverage[s]["images"] for s in RATIOS):
        blockers.append("insufficient_independent_groups")
    if any(coverage[s]["scales"][scale]["groups"] == 0 for s in RATIOS for scale in ["small", "medium", "large"]):
        blockers.append("scale_coverage_missing_or_unknown")
    extraction_issues = read_json(out / "extraction_issues.json")
    active_sources = {r["source"] for r in selected}
    if any(issue["source"] in active_sources for issue in extraction_issues):
        blockers.append("extraction_issues_require_review")
    report = dict(tool_version=VERSION, seed=SEED, config_profile="real_capture_curation_v1",
                  status="provisional" if blockers else "ready_to_freeze", blockers=blockers,
                  selected=len(selected), candidates=len(rows), splits=coverage,
                  selection=dict(Counter(r["selection"] for r in all_records)),
                  extraction_issue_count=len(extraction_issues),
                  by_source=dict(Counter(r["source"] for r in selected)),
                  group_sizes=dict(Counter(r["group_id"] for r in selected)),
                  pair_review=dict(Counter(p["verdict"] for p in pairs)),
                  limitations=["One capture day; no claim of cross-date/farm generalization.",
                               "Similarity is not proof of independence; human source review is required.",
                               "No detector, maturity inference or ground-truth labels were used."])
    write_json(out / "report.json", report)
    return all_records, report


def gallery(out, records):
    records = [r for r in records if r["selection"] != "exclude"]
    folder = out / "gallery"
    folder.mkdir(exist_ok=True)
    selected = [r for r in records if r["selection"] == "include"]
    for page, start in enumerate(range(0, len(selected), 100)):
        cards = []
        for r in selected[start:start + 100]:
            ident = r["image_id"]
            caption = html.escape(f"{ident} | {r['source']} | t={r['timestamp_seconds']} | {r['group_id']} | {r['split']} | {r['selection']} | rotation_cw={r['rotation_cw']} | {r['quality_flags']}")
            # Display corrected orientation without mutating immutable previews.
            style = f"transform:rotate({r['rotation_cw']}deg);max-width:240px;max-height:240px"
            cards.append(f'<figure><a href="../{r["candidate_path"]}"><div style="height:320px;display:flex;align-items:center;justify-content:center"><img style="{style}" loading="lazy" src="../thumbnails/{ident}.jpg"></div></a><figcaption>{caption}</figcaption></figure>')
        nav = " ".join(f'<a href="page_{p:03d}.html">{p+1}</a>' for p in range((len(selected)+99)//100))
        body = '<!doctype html><meta charset="utf-8"><title>Revisión provisional</title><style>body{font:15px sans-serif}main{display:flex;flex-wrap:wrap}figure{width:320px;margin:12px}img{max-width:320px}figcaption{overflow-wrap:anywhere}</style><h1>Revisión provisional — sin etiquetas</h1>' + nav + '<main>' + ''.join(cards) + '</main>' + nav
        (folder / f"page_{page:03d}.html").write_text(body, encoding="utf-8")
    by_source = defaultdict(list)
    for row in records:
        by_source[row["source_id"]].append(row)
    source_cards = []
    for sid, sequence in by_source.items():
        examples = [sequence[i] for i in sorted({0, len(sequence)//2, len(sequence)-1})]
        caption = html.escape(f"{sequence[0]['source']} | {sid} | {sequence[0]['group_id']} | {sequence[0]['split']} | export rotation_cw={sequence[0]['rotation_cw']}")
        thumbs = ''.join(f'<a href="../{r["candidate_path"]}"><img loading="lazy" src="../thumbnails/{r["image_id"]}.jpg"></a>' for r in examples)
        source_cards.append(f'<section><p>{caption}</p>{thumbs}</section>')
    (folder / "sources.html").write_text('<!doctype html><meta charset="utf-8"><h1>Fuentes: grupos y orientación pendientes</h1>' + ''.join(source_cards), encoding="utf-8")
    by_id = {r["image_id"]: r for r in records}
    pairs = read_rows(out / "pair_review.csv")
    pairs = [p for p in pairs if p["left"] in by_id and p["right"] in by_id]
    # Page suspicious cross-source relations first; within-source pairs follow.
    pairs.sort(key=lambda p: (p["left_source"] == p["right_source"], p["left"], p["right"]))
    for page, start in enumerate(range(0, len(pairs), 100)):
        body = []
        for p in pairs[start:start+100]:
            caption = html.escape(f"{p['left']} / {p['right']} | {p['verdict']} | H={p['hamming']} MAE={p['mae']}")
            thumbs = ''.join(f'<a href="../{by_id[p[k]]["candidate_path"]}"><img loading="lazy" src="../thumbnails/{p[k]}.jpg"></a>' for k in ["left", "right"])
            body.append(f'<section><p>{caption}</p>{thumbs}</section>')
        nav = ' '.join(f'<a href="pairs_{p:03d}.html">{p+1}</a>' for p in range((len(pairs)+99)//100))
        (folder / f"pairs_{page:03d}.html").write_text('<!doctype html><meta charset="utf-8"><h1>Pares por revisar</h1>' + nav + ''.join(body) + nav, encoding="utf-8")
    (out / "index.html").write_text('<!doctype html><meta charset="utf-8"><h1>Dataset provisional — revisión pendiente</h1><ul><li><a href="gallery/page_000.html">Imágenes seleccionadas</a></li><li><a href="manifest.csv">Manifiesto y reservas recuperables</a></li><li><a href="gallery/sources.html">Fuentes y grupos</a></li><li><a href="gallery/pairs_000.html">Pares similares</a></li><li><a href="LEEME.md">Instrucciones</a></li><li><a href="report.json">Informe de cobertura</a></li></ul>', encoding="utf-8")


def export(out, records):
    """Immutable delivery snapshots: reruns verify rather than overwrite images."""
    selected = [r for r in records if r["selection"] == "include"]
    for split in RATIOS:
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
    # Guard a partially completed export against changed reviews on resumption.
    signature = {name: digest(out / name) for name in ["inventory.json", "manifest.jsonl", "manifest.csv", "split_assignment.json", "source_review.csv", "image_review.csv", "pair_review.csv", "pair_proposals.json"]}
    if (out / "preserved_splits.json").exists():
        signature["preserved_splits.json"] = digest(out / "preserved_splits.json")
    state_path = out / "export_state.json"
    if state_path.exists() and read_json(state_path) != signature:
        raise ValueError("Review changed during export; fork a new version")
    write_json(state_path, signature)
    exported = []
    for r in selected:
        source = out / r["candidate_path"]
        target = out / "images" / r["split"] / source.name
        if target.exists():
            # A complete per-file receipt distinguishes finished files from an
            # interrupted copy. Unreceipted files may be safely overwritten.
            receipt = out / "export_receipts" / f"{r['image_id']}.json"
            if receipt.exists():
                saved = read_json(receipt)
                if digest(target) != saved["sha256"]:
                    raise ValueError("Previously exported image was modified")
                exported.append(saved)
                continue
        if r["rotation_cw"]:
            with Image.open(source) as im:
                im.rotate(-r["rotation_cw"], expand=True).save(target, quality=CONFIG["jpeg_quality"])
        else:
            shutil.copy2(source, target)
        exported.append(dict(image_id=r["image_id"], path=target.relative_to(out).as_posix(),
                             sha256=digest(target), group_id=r["group_id"], split=r["split"],
                             width=r["width"], height=r["height"], rotation_cw=r["rotation_cw"]))
        write_json(out / "export_receipts" / f"{r['image_id']}.json", exported[-1])
    write_rows(out / "export_manifest.jsonl", exported)


def verify(out):
    if (out / "FROZEN.json").exists():
        for name, sha in read_json(out / "FROZEN.json")["files"].items():
            if digest(out / name) != sha:
                raise ValueError(f"Frozen metadata changed: {name}")
    if (out / "export_state.json").exists():
        for name, sha in read_json(out / "export_state.json").items():
            if digest(out / name) != sha:
                raise ValueError("Delivered review changed; fork-review before editing")
    records = read_rows(out / "manifest.jsonl")
    exported = read_rows(out / "export_manifest.jsonl")
    selected = {r["image_id"]: r for r in records if r["selection"] == "include"}
    if len(exported) != len(selected) or {r["image_id"] for r in exported} != set(selected):
        raise ValueError("Export does not match selection")
    group_splits, pixel_splits = defaultdict(set), defaultdict(set)
    for row in exported:
        r = selected[row["image_id"]]
        if row["split"] != r["split"] or row["group_id"] != r["group_id"]:
            raise ValueError("Export metadata mismatch")
        if digest(out / row["path"]) != row["sha256"]:
            raise ValueError("Export content changed")
        with Image.open(out / row["path"]) as im:
            if im.size != (r["width"], r["height"]):
                raise ValueError("Export dimensions disagree with orientation")
        group_splits[r["group_id"]].add(r["split"])
        pixel_splits[r["pixel_sha256"]].add(r["split"])
    if any(len(s) > 1 for s in list(group_splits.values()) + list(pixel_splits.values())):
        raise ValueError("Cross-split group or exact duplicate")
    actual = {p.relative_to(out).as_posix() for p in (out / "images").rglob("*") if p.is_file()}
    if actual != {r["path"] for r in exported}:
        raise ValueError("Unexpected export files")
    result = dict(status="passed", images=len(exported), scope="structural_integrity_not_human_validation")
    write_json(out / "verification.json", result)
    return result


def write_handoff_readme(out):
    protocol = Path(__file__).resolve().parents[1] / "docs/guides/nuevo_dataset_real.md"
    if protocol.exists():
        report = read_json(out / "report.json")
        header = (f"# Entrega {out.name}\n\nEstado: **{report['status']}**. "
                  f"Imágenes propuestas: {report['selected']}; candidatos: {report['candidates']}.\n\n"
                  "Abrir `index.html` para revisar. No entrenar mientras existan pendientes. "
                  "Conservar esta versión; crear otra con `fork-review` antes de editar las tablas.\n\n"
                  f"En los ejemplos siguientes, sustituir las versiones por `{out.name}` "
                  "y un nombre nuevo para la siguiente revisión.\n\n---\n\n")
        (out / "LEEME.md").write_text(header + protocol.read_text(encoding="utf-8"), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["inventory", "candidates", "review", "partition", "export", "verify", "freeze", "run", "fork-review"])
    parser.add_argument("--source", type=Path, default=Path("Nuevo Dataset"))
    parser.add_argument("--output", type=Path, default=Path("outputs/new_real_dataset"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--from-version")
    args = parser.parse_args()
    if Path(args.version).name != args.version or args.version in {".", ".."}:
        parser.error("--version must be a single directory name")
    out = args.output.resolve() / args.version
    source = args.source.resolve()
    if out == source or out.is_relative_to(source):
        parser.error("Output must be outside source")
    if args.stage == "fork-review":
        if not args.from_version or Path(args.from_version).name != args.from_version or out.exists():
            parser.error("Provide existing --from-version and a new --version")
        old = args.output.resolve() / args.from_version
        out.mkdir(parents=True)
        for name in ["inventory.json", "candidates.jsonl", "extraction_issues.json", "source_review.csv", "image_review.csv", "pair_review.csv", "pair_proposals.json"]:
            shutil.copy2(old / name, out / name)
        if (old / "preserved_splits.json").exists():
            shutil.copy2(old / "preserved_splits.json", out / "preserved_splits.json")
        # Hard links only for immutable candidate/cache bytes; exported deliveries are copies.
        import os
        for name in ["candidates", "thumbnails", "source_records"]:
            shutil.copytree(old / name, out / name, copy_function=os.link)
        write_json(out / "parent_version.json", dict(version=args.from_version, inventory_sha256=digest(old / "inventory.json")))
        print(out)
        return
    if (out / "FROZEN.json").exists() and args.stage != "verify":
        raise ValueError("Frozen version is immutable; fork-review to a new version")
    if (out / "export_manifest.jsonl").exists() and args.stage not in {"verify", "freeze"}:
        raise ValueError("Delivered version is immutable; use fork-review")
    out.mkdir(parents=True, exist_ok=True)
    cv2.setNumThreads(2)
    if args.stage == "verify":
        print(json.dumps(verify(out)))
        return
    if args.stage == "freeze":
        records, report = partition(out, read_rows(out / "candidates.jsonl"))
        if report["blockers"]:
            raise ValueError(f"Cannot freeze: {report['blockers']}")
        verify(out)
        write_json(out / "FROZEN.json", dict(tool_version=VERSION, seed=SEED,
                   files={name: digest(out / name) for name in ["inventory.json", "manifest.jsonl", "manifest.csv", "export_manifest.jsonl", "source_review.csv", "image_review.csv", "pair_review.csv", "pair_proposals.json", "split_assignment.json", "report.json"]}))
        return
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")
    files = inventory(source, out)
    if args.stage == "inventory":
        return
    rows = candidates(source, out, files) if args.stage in {"run", "candidates"} else read_rows(out / "candidates.jsonl")
    if not rows:
        raise ValueError("No readable candidates; inspect inventory and extraction_issues.json")
    if args.stage == "candidates":
        return
    if args.stage in {"run", "review"}:
        propose_review(out, files, rows)
    if args.stage == "review":
        return
    records, report = partition(out, rows)
    gallery(out, records)
    if args.stage in {"run", "export"}:
        export(out, records)
        verify(out)
        write_handoff_readme(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
