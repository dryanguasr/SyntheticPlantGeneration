"""Versioned contracts for synthetic-only calyx instance segmentation experiments."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

VERSION = 'calyx-segmentation-cycles/1.0'
CLASSES = ('pintona', 'madura', 'sobremadura')
GRADE_PRESETS = ('calyx_green_v0', 'calyx_green_v1', 'calyx_transition_v0',
                 'calyx_transition_v1', 'calyx_straw_v0', 'calyx_straw_v1', 'calyx_dry_v1')


def class_for_grade(grade):
    if type(grade) is not int or not 0 <= grade <= 6:
        raise ValueError('Expected synthetic grade 0..6')
    return 0 if grade <= 4 else 1 if grade == 5 else 2


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.partial')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    # Windows readers and antivirus may briefly deny atomic replacement.
    # Keep the original record intact and propagate persistent failures.
    import time
    for attempt in range(20):
        try:
            temp.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.1)


def check_deadline(root):
    if (Path(root)/'effective_budget.json').exists():
        from .execution_budget import remaining_seconds
        if remaining_seconds(root) <= 0:
            raise TimeoutError('Effective twelve-hour experiment budget exhausted')
        return
    record = json.loads((Path(root)/'run.json').read_text())
    if datetime.now(timezone.utc).timestamp() >= record['deadline_unix']:
        raise TimeoutError('Global twelve-hour experiment deadline reached')


def mask_polygon(mask):
    """Join exact contours with doubled bridges; verify against the lossless mask.

    No contour simplification or implicit component/hole removal. A failed
    rasterization rejects the image, never silently drops the instance.
    """
    import cv2
    import numpy as np
    contours, _ = cv2.findContours(mask.astype('uint8'), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError('Empty instance mask')
    contours = sorted((c.reshape(-1, 2) for c in contours), key=len, reverse=True)
    path = contours.pop(0)
    while contours:
        contour = contours.pop(0)
        distances = ((path[:, None, :].astype(float)-contour[None, :, :])**2).sum(2)
        left, right = np.unravel_index(distances.argmin(), distances.shape)
        loop = np.concatenate((contour[right:], contour[:right+1]))
        path = np.concatenate((path[:left+1], loop, path[left:]))
    while len(path) < 3:
        path = np.concatenate((path, path[-1:]))
    rebuilt = np.zeros(mask.shape, np.uint8)
    cv2.fillPoly(rebuilt, [path.astype(np.int32)], 1)
    union = np.count_nonzero(rebuilt.astype(bool) | mask.astype(bool))
    iou = np.count_nonzero(rebuilt.astype(bool) & mask.astype(bool))/union
    h, w = mask.shape
    normalized = (path.astype(float) + .05) / (w, h)
    return normalized, float(iou)


def group_seeds():
    return {'train': list(range(420100, 420118)), 'val': list(range(420118, 420124)),
            'development': list(range(420200, 420236)), 'final': list(range(420300, 420336))}


def assert_disjoint(groups):
    seen = set()
    for values in groups.values():
        if len(set(values)) != len(values) or seen.intersection(values):
            raise ValueError('Morphology leakage between groups')
        seen.update(values)
