"""Post-inference evidence overlays; never imported by the RGB detector."""
from __future__ import annotations


def aligned_overlay(image_bgr, frame, *, prediction=None, visibility=None, gate=None):
    """Return an annotated copy of the exact RGB frame, refusing stale evidence.

    The caller verifies file SHA before decoding; this function checks every
    evidence row against its frame id, native timestamp and image digest.
    Native truth boxes and learned RGB boxes have distinct colors and legends.
    """
    import cv2
    for source in (prediction, visibility):
        if source is not None and any(source[k] != frame[k] for k in ('frame_id', 'stamp_ns', 'image_sha256')):
            raise ValueError('Overlay evidence does not match the exact RGB frame')
    if gate is not None and gate['stamp_ns'] != frame['stamp_ns']:
        raise ValueError('Overlay gate has a different timestamp')
    if (image_bgr.shape[1], image_bgr.shape[0]) != (frame['width'], frame['height']):
        raise ValueError('Overlay RGB dimensions differ from the frame contract')
    result = image_bgr.copy()
    for detection in (() if prediction is None else prediction['detections']):
        x0, y0, x1, y1 = map(round, detection['box_xyxy_px'])
        cv2.rectangle(result, (x0, y0), (x1, y1), (55, 220, 70), 1)
    if visibility is not None:
        admitted = set() if gate is None else {r['id'] for r in gate['targets'] if r['eligible']}
        for target in visibility['targets']:
            if not target['visible_pixels']:
                continue
            x0, y0, x1, y1 = map(round, target['box_xyxy_px'])
            color = (255, 180, 0) if target['id'] in admitted else (230, 120, 40)
            cv2.rectangle(result, (x0, y0), (x1, y1), color, 2)
            text = target['id'].split(':')[0] + f" native {target['visible_pixels']}px"
            cv2.putText(result, text, (x0, max(40, y0-4)), cv2.FONT_HERSHEY_SIMPLEX, .4, color, 1)
    mode = 'RGB only' if visibility is None else ('native visibility / privileged simulation' if prediction is None else 'RGB + simulator identity association')
    cv2.rectangle(result, (0, 0), (result.shape[1], 29), (20, 20, 20), -1)
    cv2.putText(result, f'{mode} | t={frame["stamp_ns"]/1e9:.3f}s | RGB green / native blue',
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, .45, (245, 245, 245), 1)
    return result
