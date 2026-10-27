"""Patent-style drawing rendering and output validation."""
from dataclasses import dataclass

import cv2
import numpy as np

from app.ai.contour import ContourSet
from app.ai.errors import PipelineError

SUPERSAMPLE = 4
SUBPIXEL_SHIFT = 4  # cv2 fixed-point bits for sub-pixel polyline coordinates
MARGIN_RATIO = 0.08


@dataclass
class Drawing:
    image: np.ndarray  # H x W uint8, white background, black line
    line_length_px: float
    line_width: float


def _contour_length(pts: np.ndarray) -> float:
    return float(np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1).sum())


def render_drawing(contours: ContourSet, long_side: int = 1400, line_width: float = 4.0) -> Drawing:
    """White canvas, uniform black anti-aliased outline, whole object visible with margins."""
    allpts = np.concatenate(contours.outer)
    mn, mx = allpts.min(axis=0), allpts.max(axis=0)
    bw, bh = float(mx[0] - mn[0]), float(mx[1] - mn[1])
    if bw < 2 or bh < 2:
        raise PipelineError("rendering", "The extracted contour is degenerate.")

    margin = MARGIN_RATIO * long_side
    scale = (long_side - 2 * margin) / max(bw, bh)
    width, height = round(bw * scale + 2 * margin), round(bh * scale + 2 * margin)

    big = np.full((height * SUPERSAMPLE, width * SUPERSAMPLE), 255, np.uint8)
    thickness = max(1, round(line_width * SUPERSAMPLE))
    factor = SUPERSAMPLE * (1 << SUBPIXEL_SHIFT)
    length = 0.0
    polys = []
    for pts in contours.all:
        mapped = (pts - mn) * scale + margin
        length += _contour_length(mapped)
        polys.append(np.round(mapped * factor).astype(np.int32).reshape(-1, 1, 2))
    cv2.polylines(
        big, polys, isClosed=True, color=0, thickness=thickness, lineType=cv2.LINE_AA, shift=SUBPIXEL_SHIFT
    )
    img = cv2.resize(big, (width, height), interpolation=cv2.INTER_AREA)
    return Drawing(image=img, line_length_px=length, line_width=line_width)


def validate_drawing(drawing: Drawing) -> dict:
    """Output validation: white background, visible ink, margins and uniform stroke width."""
    img = drawing.image
    h, w = img.shape
    fail = lambda msg: PipelineError(  # noqa: E731
        "output_validation", f"The generated drawing failed validation: {msg}.", "Retry processing."
    )
    if img.ndim != 2 or h < 50 or w < 50:
        raise fail("unexpected dimensions")
    c = 10
    corners = [img[:c, :c], img[:c, -c:], img[-c:, :c], img[-c:, -c:]]
    if min(float(p.mean()) for p in corners) < 250:
        raise fail("background is not white")

    ink = (255.0 - img.astype(np.float32)) / 255.0
    dark = img < 128
    if not dark.any():
        raise fail("no outline was drawn")
    ys, xs = np.nonzero(dark)
    margin = 0.03 * max(h, w)
    if xs.min() < margin or ys.min() < margin or xs.max() > w - margin or ys.max() > h - margin:
        raise fail("the outline is too close to the edge")

    ink_fraction = float(ink.sum() / (h * w))
    if not 0.0003 <= ink_fraction <= 0.25:
        raise fail("ink coverage is implausible")

    est_width = float(ink.sum() / max(drawing.line_length_px, 1.0))
    ratio = est_width / drawing.line_width
    if not 0.6 <= ratio <= 1.4:
        raise fail("line thickness is not uniform")
    return {"width": w, "height": h, "ink_fraction": round(ink_fraction, 5), "line_width_ratio": round(ratio, 3)}


def render_svg(contours: ContourSet, long_side: int = 1400, line_width: float = 4.0) -> str:
    """Vector version of the drawing: same framing and stroke as render_drawing, as SVG paths."""
    allpts = np.concatenate(contours.outer)
    mn, mx = allpts.min(axis=0), allpts.max(axis=0)
    bw, bh = float(mx[0] - mn[0]), float(mx[1] - mn[1])
    margin = MARGIN_RATIO * long_side
    scale = (long_side - 2 * margin) / max(bw, bh)
    width, height = round(bw * scale + 2 * margin), round(bh * scale + 2 * margin)

    paths = []
    for pts in contours.all:
        mapped = (pts - mn) * scale + margin
        coords = " L".join(f"{x:.2f},{y:.2f}" for x, y in mapped)
        paths.append(f'<path d="M{coords} Z"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'<g fill="none" stroke="#000" stroke-width="{line_width:g}" stroke-linejoin="round" '
        f'stroke-linecap="round">{"".join(paths)}</g></svg>'
    )


def overlay_outline(bgr: np.ndarray, contours: ContourSet) -> np.ndarray:
    """Review image: the extracted outline drawn on the source photo (same size as the mask)."""
    out = bgr.copy()
    thickness = max(2, round(max(out.shape[:2]) / 400))
    polys = [np.round(p).astype(np.int32).reshape(-1, 1, 2) for p in contours.all]
    cv2.polylines(out, polys, isClosed=True, color=(0, 0, 255), thickness=thickness, lineType=cv2.LINE_AA)
    return out
