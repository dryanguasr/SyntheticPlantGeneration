"""Moderate photometric phenomena accepted against the real train profile."""

from __future__ import annotations

import random
from typing import Any

from .profiles import image_photometry, photometry_within_train_support


def augment_photometric(image, rng: random.Random, profile: dict[str, Any]):
    """Return an accepted image, sequence and parameters or ``None``.

    Candidate magnitudes are engineering heuristics. Acceptance is empirical:
    output luminance, saturation and local contrast must remain inside the
    train p01-p99 support measured by :mod:`profiles`.
    """
    phenomena = ("exposure", "exposure_shadow", "white_balance", "local_contrast")
    for _ in range(16):
        phenomenon = rng.choice(phenomena)
        if phenomenon == "exposure":
            factor = rng.uniform(0.86, 1.14)
            output = _exposure(image, factor)
            sequence = ("exposure",)
            parameters = ({"factor": factor, "status": "engineering_heuristic"},)
        elif phenomenon == "exposure_shadow":
            factor = rng.uniform(0.92, 1.08)
            shadow_strength = rng.uniform(0.10, 0.24)
            angle = rng.uniform(0.0, 360.0)
            output = _soft_directional_shadow(_exposure(image, factor), shadow_strength, angle, rng)
            sequence = ("exposure", "soft_directional_shadow")
            parameters = (
                {"factor": factor, "status": "engineering_heuristic"},
                {"strength": shadow_strength, "angle_degrees": angle, "status": "engineering_heuristic"},
            )
        elif phenomenon == "white_balance":
            gains = tuple(rng.uniform(0.94, 1.06) for _ in range(3))
            output = _white_balance(image, gains)
            sequence = ("white_balance",)
            parameters = ({"bgr_gains": gains, "status": "engineering_heuristic"},)
        else:
            clip_limit = rng.uniform(1.15, 1.55)
            blend = rng.uniform(0.18, 0.38)
            output = _local_contrast(image, clip_limit, blend)
            sequence = ("local_contrast",)
            parameters = ({"clahe_clip_limit": clip_limit, "blend": blend, "status": "engineering_heuristic"},)
        metrics = image_photometry(output)
        if photometry_within_train_support(metrics, profile):
            return output, sequence, parameters, metrics
    return None


def _exposure(image, factor: float):
    import numpy as np

    return np.clip(image.astype("float32") * factor, 0, 255).astype("uint8")


def _white_balance(image, gains: tuple[float, float, float]):
    import numpy as np

    gain_array = np.asarray(gains, dtype="float32").reshape(1, 1, 3)
    return np.clip(image.astype("float32") * gain_array, 0, 255).astype("uint8")


def _soft_directional_shadow(image, strength: float, angle_degrees: float, rng: random.Random):
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width].astype("float32")
    radians = np.deg2rad(angle_degrees)
    projection = xx * np.cos(radians) + yy * np.sin(radians)
    threshold = rng.uniform(float(projection.min()), float(projection.max()))
    softness = max(height, width) * rng.uniform(0.08, 0.18)
    shadow = 1.0 / (1.0 + np.exp(-(projection - threshold) / max(softness, 1.0)))
    shadow = cv2.GaussianBlur(shadow, (0, 0), max(height, width) * 0.015)
    multiplier = 1.0 - strength * shadow[:, :, None]
    return np.clip(image.astype("float32") * multiplier, 0, 255).astype("uint8")


def _local_contrast(image, clip_limit: float, blend: float):
    import cv2

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    luminance, a, b = cv2.split(lab)
    adjusted = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(luminance)
    luminance = cv2.addWeighted(luminance, 1.0 - blend, adjusted, blend, 0.0)
    return cv2.cvtColor(cv2.merge((luminance, a, b)), cv2.COLOR_LAB2BGR)
