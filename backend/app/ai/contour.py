"""Outer-contour extraction and corner-preserving smoothing."""
from dataclasses import dataclass, field

import cv2
import numpy as np

from app.ai.errors import PipelineError

CORNER_ANGLE_DEG = 50.0
MIN_COMPONENT_RATIO = 0.01
MIN_HOLE_RATIO = 0.01


@dataclass
class ContourSet:
    outer: list[np.ndarray] = field(default_factory=list)  # each (N, 2) float32, x/y pixels
    holes: list[np.ndarray] = field(default_factory=list)  # genuine see-through openings

    @property
    def all(self) -> list[np.ndarray]:
        return self.outer + self.holes

    @property
    def point_count(self) -> int:
        return sum(len(c) for c in self.all)


def _circular_gaussian(values: np.ndarray, sigma: float) -> np.ndarray:
    radius = max(1, int(3 * sigma))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    n = len(values)
    if n <= 2 * radius:
        radius = max(1, (n - 1) // 2)
        x = np.arange(-radius, radius + 1)
        kernel = np.exp(-0.5 * (x / sigma) ** 2)
        kernel /= kernel.sum()
    pad = len(kernel) // 2
    if values.ndim == 1:
        padded = np.concatenate([values[-pad:], values, values[:pad]])
        return np.convolve(padded, kernel, mode="valid")
    return np.stack([_circular_gaussian(values[:, i], sigma) for i in range(values.shape[1])], axis=1)


def smooth_contour(points: np.ndarray, sigma: float | None = None) -> np.ndarray:
    """Remove pixel staircase noise while keeping real corners sharp."""
    pts = points.astype(np.float64)
    n = len(pts)
    if n < 12:
        return pts.astype(np.float32)
    sigma = sigma if sigma is not None else float(np.clip(n / 300.0, 1.5, 5.0))

    k = max(2, int(round(sigma * 1.5)))
    v1 = pts - np.roll(pts, k, axis=0)
    v2 = np.roll(pts, -k, axis=0) - pts
    denom = np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1)
    cos = np.where(denom > 0, (v1 * v2).sum(axis=1) / np.maximum(denom, 1e-9), 1.0)
    turning = np.degrees(np.arccos(np.clip(cos, -1, 1)))

    corner = (turning > CORNER_ANGLE_DEG).astype(np.float64)
    # Blend back to the original points around corners so they are not rounded off.
    spread = _circular_gaussian(corner, max(1.0, sigma))
    keep_original = np.clip(spread * 4.0, 0.0, 1.0)

    smooth = _circular_gaussian(pts, sigma)
    out = (1.0 - keep_original)[:, None] * smooth + keep_original[:, None] * pts
    return out.astype(np.float32)


def extract_contours(mask: np.ndarray, smooth: bool = True, keep_openings: bool = False) -> ContourSet:
    """External contour(s) of the product, plus large enclosed openings (handles) as holes."""
    found, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not found or hierarchy is None:
        raise PipelineError(
            "contour_extraction",
            "No contour could be extracted from the mask.",
            "Retry processing, or use a clearer photo.",
        )
    hier = hierarchy[0]
    areas = [cv2.contourArea(c) for c in found]
    outer_idx = [i for i in range(len(found)) if hier[i][3] == -1]
    if not outer_idx:
        raise PipelineError("contour_extraction", "The mask has no external contour.")
    largest = max(areas[i] for i in outer_idx)
    outer_idx = [i for i in outer_idx if areas[i] >= MIN_COMPONENT_RATIO * largest and len(found[i]) >= 8]
    total_outer = sum(areas[i] for i in outer_idx)
    hole_idx = [
        i
        for i in range(len(found))
        if keep_openings
        and hier[i][3] != -1
        and hier[i][3] in outer_idx
        and areas[i] >= MIN_HOLE_RATIO * total_outer
        and len(found[i]) >= 8
    ]

    def prep(i: int) -> np.ndarray:
        pts = found[i].reshape(-1, 2).astype(np.float32)
        return smooth_contour(pts) if smooth else pts

    if not outer_idx:
        raise PipelineError("contour_extraction", "All contours were rejected as noise.")
    return ContourSet(outer=[prep(i) for i in outer_idx], holes=[prep(i) for i in hole_idx])
