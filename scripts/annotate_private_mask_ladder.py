"""Generate RGB-only MobileSAM drafts and seal explicit visual reviews."""
import argparse
from contextlib import closing
import math
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))

from uchuva_annotation_audit.masks import checked_runs, decode_mask, encode_mask, mask_bbox, mask_iou
from uchuva_annotation_audit.store import SessionLock, atomic_json, iou, now, read, sha


STATES = {'accept', 'uncertain', 'discard'}
COLORS = ('#22e3a0', '#ffd534', '#ff68b0', '#e8e9ec')
ABBREVIATIONS = ('P', 'M', 'S', '?')


def bounded_rectangle(box, size):
    w, h = size
    if len(box) != 4 or any(not math.isfinite(p) for p in box):
        raise ValueError('Invalid review rectangle')
    x1, y1, x2, y2 = box
    bounds = max(0, math.floor(x1)), max(0, math.floor(y1)), min(w, math.ceil(x2)), min(h, math.ceil(y2))
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError('Empty review rectangle')
    return bounds


def rectangle_mask(box, size):
    """Conservative exclusion only. No such rectangle is a training object."""
    x1, y1, x2, y2 = bounded_rectangle(box, size)
    mask = Image.new('L', size)
    mask.paste(255, (x1, y1, x2, y2))
    return encode_mask(mask)


def validate_binding(row, record):
    if record['id'] != row['id'] or record['image_sha256'] != row['image_sha256']:
        raise ValueError(f"Wrong draft for {row['id']}")
    if record['size'] != [row['width'], row['height']]:
        raise ValueError(f"Size mismatch for {row['id']}")


def make_annotation(row, draft, decision):
    validate_binding(row, draft)
    size = row['width'], row['height']
    candidates = {obj['id']: obj for obj in draft['candidates']}
    actions = decision['objects']
    if set(actions) != set(candidates) or not decision.get('scanned_rgb_and_overlay'):
        raise ValueError('Visual review must explicitly account for all candidates and both views')
    objects = []
    ignores = [rectangle_mask(box, size) for box in decision.get('ignore_boxes', [])]
    for ident, candidate in candidates.items():
        action = actions[ident]
        status = action['status']
        if status not in STATES:
            raise ValueError(f'Unknown visual decision: {status}')
        if status == 'discard':
            continue
        segmentation = action.get('segmentation', candidate['segmentation'])
        if status == 'uncertain':
            label = None
            if segmentation is None:
                ignores.append(rectangle_mask(candidate['prompt_box'], size))
                continue
        else:
            label = action['class_id']
            if type(label) is not int or label not in (0, 1, 2) or segmentation is None:
                raise ValueError('An accepted candidate requires a native mask and an explicit appearance class')
        checked_runs(segmentation, *size)
        objects.append(dict(id=ident, class_id=label, segmentation=segmentation,
                            bbox=mask_bbox(segmentation), bbox_source='native_mask_pixels',
                            provenance=dict(prompt_box=candidate['prompt_box'],
                                            source=candidate['source'],
                                            appearance_suggestion=candidate['suggested_class']),
                            note=str(action.get('note', ''))))
    for extra in decision.get('added_objects', []):
        ident = str(extra['id'])
        label = extra['class_id']
        if not ident or ident in candidates or any(item['id'] == ident for item in objects):
            raise ValueError('Duplicate or empty additional object identifier')
        if label is not None and (type(label) is not int or label not in (0, 1, 2)):
            raise ValueError('Invalid appearance class')
        segmentation = extra['segmentation']
        checked_runs(segmentation, *size)
        objects.append(dict(id=ident, class_id=label, segmentation=segmentation,
                            bbox=mask_bbox(segmentation), bbox_source='native_mask_pixels',
                            provenance={'source': 'assistant_visual_addition'}, note=str(extra.get('note', ''))))
    full = bool(decision.get('full_image_uncertain', False))
    empty = bool(decision.get('empty_confirmed', False))
    if full and (objects or ignores or empty):
        raise ValueError('A completely uncertain image cannot also contain supervision')
    if not objects and not ignores and not full and not empty:
        raise ValueError('An empty annotation needs explicit visual confirmation')
    if empty and (objects or ignores):
        raise ValueError('Confirmed empty is incompatible with any visible or uncertain region')
    return dict(id=row['id'], image_sha256=row['image_sha256'], size=draft['size'],
                review_state='assistant_visual_reviewed', visual_reviewed_at=now(),
                reviewer='Codex', objects=objects, ignore_regions=ignores,
                full_image_uncertain=full, empty_confirmed=empty,
                method='local_mobilesam_rgb_draft_then_assistant_visual_review',
                source_assets=draft['source_assets'], decisions_digest=decision.get('decision_digest'))


class DraftAnnotator:
    def __init__(self, plan):
        import torch
        from ultralytics import YOLO
        from ultralytics.models.sam import Predictor

        torch.set_num_threads(3)
        self.plan = plan
        self.assets = plan['annotation_assets']
        for item in self.assets.values():
            if sha(item['path']) != item['sha256']:
                raise ValueError('Frozen local annotation weight changed')
        self.detector = YOLO(self.assets['detector']['path'])
        self.sam = Predictor(overrides=dict(model=self.assets['mobile_sam']['path'],
                                             device='cpu', task='segment', mode='predict',
                                             imgsz=1024, conf=0.0, save=False, verbose=False))

    def detect(self, image):
        import numpy as np

        w, h = image.size
        tiles = [(0, 0, w, h)]
        if max(w, h) >= 1800:
            cw, ch = math.ceil(w * .64), math.ceil(h * .64)
            tiles.extend((x, y, x + cw, y + ch) for y in (0, h - ch) for x in (0, w - cw))
        hits = []
        for left, top, right, bottom in tiles:
            bgr = np.asarray(image.crop((left, top, right, bottom)))[:, :, ::-1].copy()
            boxes = self.detector.predict(bgr, device='cpu', imgsz=960, conf=.08,
                                          iou=.7, max_det=200, verbose=False)[0].boxes
            for box, score, label in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()):
                a, b, c, d = box
                if (left and a < 3) or (top and b < 3) or (right < w and c > right-left-3) or (bottom < h and d > bottom-top-3):
                    continue
                bounds = bounded_rectangle([a + left, b + top, c + left, d + top], (w, h))
                hits.append((score, bounds, int(label)))
        selected = []
        for score, box, label in sorted(hits, key=lambda hit: (-hit[0], hit[1], hit[2])):
            if all(iou(box, other[1]) < .62 for other in selected):
                selected.append((score, box, label))
        return selected

    def draft(self, row):
        import numpy as np
        import torch

        start = time.monotonic()
        if sha(row['image']) != row['image_sha256']:
            raise ValueError(f"RGB changed: {row['id']}")
        with Image.open(row['image']) as stream:
            image = stream.convert('RGB')
        if image.size != (row['width'], row['height']):
            raise ValueError(f"Unexpected RGB dimensions: {row['id']}")
        proposals = self.detect(image)
        candidates = []
        if proposals:
            self.sam.reset_image()
            bgr = np.asarray(image)[:, :, ::-1].copy()
            with torch.inference_mode():
                self.sam.set_image(bgr)
                for start_index in range(0, len(proposals), 4):
                    block = proposals[start_index:start_index+4]
                    result = self.sam(bboxes=[entry[1] for entry in block], multimask_output=False)[0]
                    masks = {} if result.masks is None else dict(zip(
                        map(int, result.boxes.cls.tolist()), result.masks.data.cpu().numpy(), strict=True))
                    for offset, (score, box, label) in enumerate(block):
                        candidate = dict(id=f'm{start_index+offset+1:03d}', suggested_class=label,
                                         detector_confidence=round(score, 6), prompt_box=list(box),
                                         source='historical_real_detector_rgb_box_to_mobilesam', segmentation=None)
                        pixels = masks.get(offset)
                        if pixels is not None:
                            mask = Image.fromarray((pixels > 0).astype('uint8') * 255)
                            if mask.size != image.size:
                                raise ValueError('MobileSAM did not return a native raster')
                            if mask.getbbox():
                                candidate['segmentation'] = encode_mask(mask)
                                candidate['bbox'] = mask_bbox(candidate['segmentation'])
                                candidate['largest_mask_overlap'] = max((mask_iou(candidate['segmentation'], other['segmentation'])
                                    for other in candidates if other['segmentation'] is not None
                                    and iou(candidate['bbox'], other['bbox']) > .35), default=0.)
                        candidates.append(candidate)
        return dict(id=row['id'], image_sha256=row['image_sha256'], size=list(image.size),
                    review_state='pending_assistant_visual_review', candidates=candidates,
                    source_assets=self.assets, seconds=round(time.monotonic()-start, 3))


def save_review_sheet(row, draft, target):
    """Show full RGB, an indexed overlay and native context crops in one private artifact."""
    import numpy as np

    with Image.open(row['image']) as base:
        image = base.convert('RGB')
    thumbnail = image.copy()
    thumbnail.thumbnail((800, 530), Image.Resampling.LANCZOS)
    tw, th = thumbnail.size
    candidates = draft['candidates']
    out = Image.new('RGB', (max(1600, 2*tw), th+54+math.ceil(len(candidates)/8)*155), '#172620')
    draw = ImageDraw.Draw(out)
    font = ImageFont.truetype('segoeui.ttf', 18)
    draw.text((8, 7), f"{row['id']} · RGB", font=font, fill='white')
    draw.text((tw+8, 7), 'Borrador de máscaras · sugerencias P / M / S', font=font, fill='white')
    overlay = thumbnail.copy()
    for obj in candidates:
        if obj['segmentation'] is None:
            continue
        opacity = decode_mask(obj['segmentation']).resize((tw, th), Image.Resampling.NEAREST)
        overlay.paste(COLORS[obj['suggested_class']], (0, 0, tw, th), opacity.point(lambda p: 70 if p else 0))
    out.paste(thumbnail, (0, 31))
    out.paste(overlay, (tw, 31))
    for index, obj in enumerate(candidates):
        x1, y1, x2, y2 = obj.get('bbox', obj['prompt_box'])
        x = max(0, min(tw-42, round(x1*tw/image.width)))
        y = max(0, min(th-18, round(y1*th/image.height)))
        color = COLORS[obj['suggested_class']] if obj['segmentation'] else COLORS[-1]
        draw.text((tw+x, 31+y), obj['id'][1:], font=font, fill=color, stroke_width=2, stroke_fill='#141514')
        padding = max(8, round(.18*max(x2-x1, y2-y1)))
        box = max(0, x1-padding), max(0, y1-padding), min(image.width, x2+padding), min(image.height, y2+padding)
        patch = image.crop(box)
        if obj['segmentation'] is not None:
            raw_mask = np.asarray(decode_mask(obj['segmentation']).crop(box))
            import cv2
            border = raw_mask ^ cv2.erode(raw_mask, np.ones((3, 3), np.uint8))
            patch.paste(color, (0, 0, *patch.size), Image.fromarray(border))
        patch.thumbnail((184, 124), Image.Resampling.LANCZOS)
        column, line = index % 8, index // 8
        left, top = column*200+7, th+54+line*155
        out.paste(patch, (left, top))
        draw.text((left, top+124), f"{obj['id']} · {ABBREVIATIONS[obj['suggested_class']]} {obj['detector_confidence']:.2f}", font=font, fill=color)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    out.save(temporary, format='JPEG', quality=92)
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    draft = sub.add_parser('draft')
    draft.add_argument('--through', type=int, required=True)
    seal = sub.add_parser('seal')
    seal.add_argument('decisions', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if root.parent != (REPO/'outputs').resolve() or not root.name.startswith('private_mask_ladder_'):
        raise ValueError('The annotation journal must stay in its dedicated private output tree')
    plan = read(root/'plan.json')
    rows = read(root/'private_inputs.json')['train']
    if args.action == 'seal':
        decisions = read(args.decisions)
        by_id = {row['id']: row for row in rows}
        records = []
        for ident, decision in decisions.items():
            record = read(root/'drafts'/f'{ident}.json')
            decision['decision_digest'] = sha(args.decisions)
            sealed = root/'annotations'/f'{ident}.json'
            if sealed.is_file():
                raise FileExistsError(sealed)
            records.append((sealed, make_annotation(by_id[ident], record, decision)))
        for sealed, annotation in records:
            atomic_json(sealed, annotation, exclusive=True)
        print(f'Sealed {len(records)} visually reviewed images', flush=True)
        return
    if not 1 <= args.through <= len(rows):
        raise ValueError('The draft range must be within the frozen inventory')
    with closing(SessionLock(root/'drafts.lock')):
        write_drafts(root, plan, rows[:args.through])


def write_drafts(root, plan, rows):
    model = None
    for row in rows:
        ident = row['id']
        target = root/'drafts'/f'{ident}.json'
        if target.exists():
            record = read(target)
        else:
            if model is None:
                model = DraftAnnotator(plan)
            record = model.draft(row)
            atomic_json(target, record, exclusive=True)
        validate_binding(row, record)
        if record['source_assets'] != plan['annotation_assets']:
            raise ValueError('Draft was produced with a different weight lock')
        preview = root/'visual_review'/f'{ident}.jpg'
        if not preview.exists():
            save_review_sheet(row, record, preview)
        print(ident, len(record['candidates']), record['seconds'], flush=True)


if __name__ == '__main__':
    main()
