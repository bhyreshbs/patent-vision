"""Background removal. Replaceable behind the BackgroundRemover interface."""
from typing import Protocol

import cv2
import numpy as np

from app.ai.errors import PipelineError
from app.ai.masks import ellipse, to_binary

L_WEIGHT = 0.6  # de-emphasise lightness so soft shadows are not treated as product
MIN_THRESHOLD, MAX_THRESHOLD = 14.0, 70.0


class BackgroundRemover(Protocol):
    def remove(self, bgr: np.ndarray, prior_mask: np.ndarray | None = None) -> np.ndarray:
        """Return a 0/255 foreground mask the size of `bgr`."""


def background_distance(bgr: np.ndarray) -> np.ndarray:
    """Per-pixel colour distance (Lab) from the dominant colours sampled around the image border."""
    h, w = bgr.shape[:2]
    blurred = cv2.GaussianBlur(bgr, (5, 5), 0)
    lab = cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)

    ring = max(4, int(0.03 * min(h, w)))
    ring_mask = np.ones((h, w), dtype=bool)
    ring_mask[ring : h - ring, ring : w - ring] = False
    samples = lab[ring_mask]
    if len(samples) > 20000:
        samples = samples[np.random.default_rng(0).choice(len(samples), 20000, replace=False)]

    k = 3
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(
        samples, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.ravel(), minlength=k)
    centers = centers[counts >= 0.08 * counts.sum()]
    if len(centers) == 0:
        centers = np.median(samples, axis=0, keepdims=True)

    weights = np.array([L_WEIGHT, 1.0, 1.0], dtype=np.float32)
    best = None
    for c in centers:
        d = np.sqrt((((lab - c) * weights) ** 2).sum(axis=2))
        best = d if best is None else np.minimum(best, d)
    return best


def otsu_threshold(dist: np.ndarray) -> float:
    d8 = np.clip(dist, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return float(np.clip(t, MIN_THRESHOLD, MAX_THRESHOLD))


class ClassicalBackgroundRemover:
    """Border-colour model + Otsu threshold. No model files required."""

    def remove(self, bgr: np.ndarray, prior_mask: np.ndarray | None = None) -> np.ndarray:
        if prior_mask is not None:
            mask = to_binary(prior_mask)
        else:
            dist = background_distance(bgr)
            mask = np.where(dist > otsu_threshold(dist), 255, 0).astype(np.uint8)
            side = min(mask.shape)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, ellipse(3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ellipse(max(3, side // 150)))
        if not mask.any():
            raise PipelineError(
                "background_removal",
                "No foreground could be separated from the background.",
                "Use a photo where the product contrasts with its background.",
            )
        return mask


def cutout_rgba(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Background-removed image: product pixels with the mask as alpha (transparent background)."""
    b, g, r = cv2.split(bgr)
    return cv2.merge([b, g, r, mask])
