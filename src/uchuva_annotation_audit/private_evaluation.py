"""Native-mask metrics for the private real-image ladder.

Precision is sampled at 101 recall points. Matching is confidence-ordered and
one-to-one at each IoU threshold. Unresolvable pixels are evaluation ignores;
they cannot hide a prediction overlapping a resolved reference.
"""

from dataclasses import dataclass
from collections import Counter

import numpy as np

from .masks import VERSION as RLE_VERSION, checked_runs

CLASS_NAMES = ('Pintona', 'Madura', 'Sobremadura')
MASK_IOUS = tuple(round(level / 100, 2) for level in range(50, 100, 5))
AREA_BANDS = ('small', 'medium', 'large')


def occupied_intervals(rle, width, height):
    counts, _, _ = checked_runs(rle, width, height)
    edges = np.r_[0, np.cumsum(counts, dtype=np.int64)]
    intervals = np.column_stack((edges[:-1][1::2], edges[1:][1::2]))
    return intervals[intervals[:, 0] < intervals[:, 1]]


def union_intervals(intervals):
    if not len(intervals):
        return np.empty((0, 2), dtype=np.int64)
    intervals = np.asarray(intervals, np.int64)
    intervals = intervals[np.argsort(intervals[:, 0], kind='stable')]
    running_ends = np.maximum.accumulate(intervals[:, 1])
    boundaries = np.flatnonzero(intervals[1:, 0] > running_ends[:-1]) + 1
    return np.column_stack((intervals[np.r_[0, boundaries], 0],
                            running_ends[np.r_[boundaries - 1, len(intervals) - 1]]))


def interval_prefix(intervals):
    return np.r_[0, np.cumsum(intervals[:, 1] - intervals[:, 0], dtype=np.int64)]


def intersection_pixels(intervals, prefix, other):
    if not len(intervals) or not len(other):
        return 0
    endpoints = other.ravel()
    index = np.searchsorted(intervals[:, 1], endpoints, side='right')
    # Evaluate the foreground integral at both endpoints of each interval.
    extra = np.maximum(0, endpoints - intervals[np.minimum(index, len(intervals) - 1), 0])
    integral = prefix[index] + np.where(index < len(intervals), extra, 0)
    return int(np.sum(integral[1::2] - integral[::2]))


def native_prediction_rle(mask, width, height):
    """Undo square letterbox and restore nearest binary pixels without a full canvas."""
    mask_height, mask_width = mask.shape
    if not mask_height or not mask_width:
        raise ValueError('Empty model mask grid')
    gain = min(mask_width / width, mask_height / height)
    content_width, content_height = round(width * gain), round(height * gain)
    left = round((mask_width - content_width) / 2 - .1)
    top = round((mask_height - content_height) / 2 - .1)
    content = mask[top:top + content_height, left:left + content_width].astype(bool, copy=False)
    ys, xs = np.nonzero(content)
    if not len(xs):
        return None

    def projected_edges(indices, native_size, grid_size):
        first = (int(indices.min()) * native_size + grid_size - 1) // grid_size
        end = ((int(indices.max()) + 1) * native_size + grid_size - 1) // grid_size
        return first, np.arange(first, end, dtype=np.int64) * grid_size // native_size

    x, sampled_x = projected_edges(xs, width, content_width)
    y, sampled_y = projected_edges(ys, height, content_height)
    foreground = content[np.ix_(sampled_y, sampled_x)]
    rows, boundaries = np.nonzero(np.diff(np.pad(foreground, ((0, 0), (1, 1))), axis=1))
    if not len(boundaries):
        return None
    linear_edges = (rows + y) * width + boundaries + x
    runs = union_intervals(linear_edges.reshape(-1, 2))
    heights = np.diff(np.r_[0, runs.ravel(), width * height]).tolist()
    return {'version': RLE_VERSION, 'size': [height, width], 'counts': heights}


def _bbox(intervals, width):
    starts = intervals[:, 0]
    final = intervals[:, 1] - 1
    first_y, first_x = np.divmod(starts, width)
    last_y, last_x = np.divmod(final, width)
    crosses_row = np.any(first_y != last_y)
    return (0 if crosses_row else int(first_x.min()), int(first_y.min()),
            width if crosses_row else int(last_x.max()) + 1, int(last_y.max()) + 1)


def _area_band(area, width, height, input_size):
    effective = area * (input_size / max(width, height)) ** 2
    return AREA_BANDS[0] if effective < 32 ** 2 else AREA_BANDS[1] if effective < 96 ** 2 else AREA_BANDS[2]


@dataclass(frozen=True)
class EvalImage:
    image_id: str
    group_id: str
    target_classes: np.ndarray
    target_bands: tuple
    target_ids: tuple
    prediction_classes: np.ndarray
    prediction_bands: tuple
    scores: np.ndarray
    overlap: np.ndarray
    prediction_ignore: np.ndarray


def prepare_image(row, annotation, predictions, input_size):
    width, height = row['width'], row['height']
    targets = []
    ref_rles = list(annotation.get('ignore_regions', []))
    for obj in annotation['objects']:
        if obj['class_id'] is None:
            ref_rles.append(obj['segmentation'])
        else:
            targets.append(obj)
    target_intervals = [occupied_intervals(obj['segmentation'], width, height) for obj in targets]
    pred_intervals = [occupied_intervals(obj['segmentation'], width, height) for obj in predictions]
    ignore = union_intervals(np.concatenate([occupied_intervals(rle, width, height) for rle in ref_rles], axis=0)) if ref_rles else union_intervals([])
    ignore_prefix = interval_prefix(ignore)
    target_boxes = np.asarray([_bbox(runs, width) for runs in target_intervals], dtype=np.int64).reshape(-1, 4)
    target_area = np.asarray([interval_prefix(runs)[-1] for runs in target_intervals])
    overlap = np.zeros((len(predictions), len(targets)), dtype=np.float32)
    ignored = np.zeros(len(predictions), dtype=bool)
    pred_areas = []
    for j, pred in enumerate(pred_intervals):
        pred_prefix = interval_prefix(pred)
        pred_area = pred_prefix[-1]
        pred_areas.append(pred_area)
        x1, y1, x2, y2 = _bbox(pred, width)
        nearby = np.flatnonzero((target_boxes[:, 0] < x2) & (target_boxes[:, 1] < y2)
                                & (target_boxes[:, 2] > x1) & (target_boxes[:, 3] > y1))
        for k in nearby:
            # The area ratio bounds the maximum attainable intersection-over-union.
            if min(pred_area, target_area[k]) < .5 * max(pred_area, target_area[k]):
                continue
            inter = intersection_pixels(pred, pred_prefix, target_intervals[k])
            overlap[j, k] = inter / (pred_area + target_area[k] - inter)
        ignored[j] = 2 * intersection_pixels(ignore, ignore_prefix, pred) >= pred_area
    return EvalImage(
        row['id'], row['group_id'],
        np.asarray([obj['class_id'] for obj in targets], dtype=np.int8),
        tuple(_area_band(a, width, height, input_size) for a in target_area),
        tuple(obj['id'] for obj in targets),
        np.asarray([obj['class_id'] for obj in predictions], dtype=np.int8),
        tuple(_area_band(a, width, height, input_size) for a in pred_areas),
        np.asarray([obj['score'] for obj in predictions], dtype=np.float64), overlap, ignored,
    )


def _scores_across(images, class_id=None):
    records = []
    for i, image in enumerate(images):
        eligible = range(len(image.scores)) if class_id is None else np.flatnonzero(image.prediction_classes == class_id)
        records.extend((float(image.scores[j]), i, int(j)) for j in eligible)
    return sorted(records, key=lambda entry: (-entry[0], entry[1], entry[2]))


def sampled_precision(tp, support):
    if not support:
        return None
    if not len(tp):
        return 0.0
    cumulative = np.cumsum(tp, dtype=np.int64)
    recall = cumulative / support
    precision = cumulative / np.arange(1, len(cumulative) + 1)
    envelope = np.r_[np.maximum.accumulate(precision[::-1])[::-1], 0.0]
    return float(np.mean(envelope[np.searchsorted(recall, np.linspace(0., 1., 101), side='left')]))


def average_precisions(images, class_id=None, band=None):
    target_scope = []
    band_scope = []
    for image in images:
        classes = image.target_classes
        same_class = np.ones(len(classes), dtype=bool) if class_id is None else classes == class_id
        bands = np.ones(len(classes), dtype=bool) if band is None else np.asarray(image.target_bands, dtype=object) == band
        target_scope.append(same_class & bands)
        band_scope.append(same_class & ~bands)
    support = sum(int(np.sum(include)) for include in target_scope)
    scores = _scores_across(images, class_id)
    threshold_results = []
    if support:
        for threshold in MASK_IOUS:
            used = [~include.copy() for include in target_scope]
            true_positives = []
            for _, i, p in scores:
                image = images[i]
                overlaps = image.overlap[p]
                available = np.where(used[i], -1.0, overlaps)
                if len(available) and float(available.max()) + 1e-7 >= threshold:
                    used[i][int(available.argmax())] = True
                    true_positives.append(True)
                    continue
                if band is not None and (image.prediction_bands[p] != band or np.any(overlaps[band_scope[i]] + 1e-7 >= threshold)):
                    continue
                if image.prediction_ignore[p] and not np.any(overlaps + 1e-7 >= threshold):
                    continue
                true_positives.append(False)
            threshold_results.append(sampled_precision(true_positives, support))
    return {'support': support, 'ap50_95': float(np.mean(threshold_results)) if support else None,
            'ap50': threshold_results[0] if support else None}


def ap_summary(images):
    by_class = {name: average_precisions(images, class_id) for class_id, name in enumerate(CLASS_NAMES)}
    supported = [entry for entry in by_class.values() if entry['support']]
    return {
        'image_count': len(images), 'supported_classes': len(supported), 'by_class': by_class,
        'macro_ap50_95': float(np.mean([entry['ap50_95'] for entry in supported])) if supported else None,
        'macro_ap50': float(np.mean([entry['ap50'] for entry in supported])) if supported else None,
        'class_agnostic': average_precisions(images),
    }


def operating_events(images):
    """Confidence-order geometry pairing, independent of semantic class."""
    matched = [np.zeros(len(image.target_classes), dtype=bool) for image in images]
    for score, i, p in _scores_across(images):
        overlaps = images[i].overlap[p]
        available = np.where(matched[i], -1.0, overlaps)
        if len(available) and float(available.max()) >= .5:
            target = int(available.argmax())
            matched[i][target] = True
        elif images[i].prediction_ignore[p] and not np.any(overlaps >= .5):
            continue
        else:
            target = None
        yield score, i, p, target


def choose_threshold(images, events):
    support = np.bincount(np.concatenate([im.target_classes for im in images]), minlength=3)
    if not np.any(support):
        raise ValueError('Validation has no resolved ground-truth instance')
    predicted = np.zeros(3, dtype=int)
    true_positives = np.zeros(3, dtype=int)
    best_score, best_threshold = -1., 1.0
    for ix, (score, i, p, target) in enumerate(events):
        pred = int(images[i].prediction_classes[p])
        predicted[pred] += 1
        if target is not None and images[i].target_classes[target] == pred:
            true_positives[pred] += 1
        if ix + 1 < len(events) and events[ix + 1][0] == score:
            continue
        supported = support > 0
        macro = float(np.mean(2 * true_positives[supported] / (predicted[supported] + support[supported])))
        if macro > best_score:
            best_score, best_threshold = macro, score
    return best_threshold


def operating_summary(images, events, threshold):
    """Return fully counted errors, including no detection and background FPs."""
    confusion = np.zeros((4, 4), dtype=int)
    sob_errors = []
    matched = [set() for _ in images]
    for score, i, p, target in events:
        if score < threshold:
            break
        image = images[i]
        actual = 3 if target is None else int(image.target_classes[target])
        pred = int(image.prediction_classes[p])
        confusion[actual, pred] += 1
        if target is not None:
            matched[i].add(target)
        if 2 in (actual, pred):
            kind = 'correct' if actual == pred else ('background_fp' if target is None else 'confusion')
            sob_errors.append({'kind': kind, 'id': image.image_id, 'group_id': image.group_id,
                               'actual': CLASS_NAMES[actual] if actual < 3 else 'Background',
                               'predicted': CLASS_NAMES[pred], 'prediction_index': p, 'score': score,
                               'target_id': image.target_ids[target] if target is not None else None})
    for i, image in enumerate(images):
        for j, cls in enumerate(image.target_classes):
            if j in matched[i]:
                continue
            confusion[int(cls), 3] += 1
            if cls == 2:
                sob_errors.append({'kind': 'omission', 'id': image.image_id, 'group_id': image.group_id,
                                   'actual': 'Sobremadura', 'predicted': None, 'target_id': image.target_ids[j]})
    classes = {}
    for label, name in enumerate(CLASS_NAMES):
        correct = int(confusion[label, label])
        support = int(confusion[label].sum())
        predicted = int(confusion[:, label].sum())
        classes[name] = {
            'correct': correct, 'support': support, 'predicted': predicted,
            'precision': correct / predicted if predicted else None,
            'recall': correct / support if support else None,
            'f1': 2 * correct / (support + predicted) if support else None,
        }
    return {'actual_rows': [*CLASS_NAMES, 'Background'], 'predicted_columns': [*CLASS_NAMES, 'Omitted'],
            'matrix': confusion.tolist(), 'by_class': classes, 'sobremadura': sob_errors,
            'sobremadura_counts': dict(Counter(event['kind'] for event in sob_errors))}


def evaluate_images(images, threshold=None):
    events = list(operating_events(images))
    if threshold is None:
        threshold = choose_threshold(images, events)
    metrics = ap_summary(images)
    metrics['by_size'] = {band: dict(
        class_agnostic=average_precisions(images, band=band),
        sobremadura=average_precisions(images, 2, band),
    ) for band in AREA_BANDS}
    groups = {}
    for image in images:
        groups.setdefault(image.group_id, []).append(image)
    metrics['by_group'] = {key: ap_summary(rows) for key, rows in groups.items()}
    metrics['operating_point'] = operating_summary(images, events, threshold)
    return threshold, metrics
