"""Mask cleaning and validation: reject incomplete/contaminated masks instead of drawing them."""
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from app.ai.errors import PipelineError
from app.ai.imaging import mask_bbox
from app.ai.masks import (
    border_contact_fraction,
    ellipse,
    fill_small_holes,
    select_product_components,
    to_binary,
)

MIN_AREA_RATIO = 0.005
MAX_AREA_RATIO = 0.92
MIN_COVERAGE = 0.88
MAX_CONTAMINATION = 0.20
MIN_BOX_IOU = 0.97
MAX_BORDER_CONTACT = 0.50
HOLE_AREA_RATIO = 0.01  # enclosed pockets below this share of the product are noise (logos, text)


@dataclass
class MaskReport:
    name: str
    accepted: bool
    reason: str | None = None
    area_ratio: float = 0.0
    coverage: float = 0.0
    contamination: float = 0.0
    box_iou: float = 0.0
    border_contact: float = 0.0

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def hole_ratio(keep_openings: bool) -> float:
    """Share of the product below which an enclosed pocket is noise. 1.0+ fills every pocket."""
    return HOLE_AREA_RATIO if keep_openings else 1.0


def clean_mask(mask: np.ndarray, gap_px: int, keep_openings: bool = False) -> np.ndarray:
    """Binarise, drop specks, keep the complete product and fill logo/text-sized pockets."""
    m = to_binary(mask)
    if not m.any():
        return m
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, ellipse(3))
    m = select_product_components(m, gap_px)
    return fill_small_holes(m, hole_ratio(keep_openings) * np.count_nonzero(m))


def _box_iou(a: np.ndarray, b: np.ndarray) -> float:
    ba, bb = mask_bbox(a), mask_bbox(b)
    if ba is None or bb is None:
        return 0.0
    ix = max(0, min(ba[2], bb[2]) - max(ba[0], bb[0]))
    iy = max(0, min(ba[3], bb[3]) - max(ba[1], bb[1]))
    inter = ix * iy
    area = lambda b_: (b_[2] - b_[0]) * (b_[3] - b_[1])  # noqa: E731
    return inter / (area(ba) + area(bb) - inter)


def evaluate_mask(name: str, mask: np.ndarray, reference: np.ndarray) -> MaskReport:
    """Check a cleaned candidate against the localized foreground `reference`."""
    total = mask.size
    area = np.count_nonzero(mask)
    if area == 0:
        return MaskReport(name, False, "mask is empty")

    ref_area = max(1, np.count_nonzero(reference))
    inter = np.count_nonzero((mask > 0) & (reference > 0))
    rep = MaskReport(
        name,
        True,
        area_ratio=area / total,
        coverage=inter / ref_area,
        contamination=(area - inter) / area,
        box_iou=_box_iou(mask, reference),
        border_contact=border_contact_fraction(mask),
    )
    if rep.area_ratio < MIN_AREA_RATIO:
        rep.accepted, rep.reason = False, "mask is too small to be the product"
    elif rep.area_ratio > MAX_AREA_RATIO:
        rep.accepted, rep.reason = False, "mask covers almost the whole image (background included)"
    elif rep.border_contact > MAX_BORDER_CONTACT:
        rep.accepted, rep.reason = False, "mask runs along most of the image border (background included)"
    elif rep.coverage < MIN_COVERAGE or rep.box_iou < MIN_BOX_IOU:
        rep.accepted, rep.reason = False, "mask is incomplete: visible parts of the product are missing"
    elif rep.contamination > MAX_CONTAMINATION:
        rep.accepted, rep.reason = False, "mask includes regions outside the detected product"
    return rep


def choose_mask(
    candidates, reference: np.ndarray, gap_px: int, keep_openings: bool = False
) -> tuple[np.ndarray, str, list[MaskReport]]:
    """Return the first valid candidate (candidates are in preference order) or raise."""
    reference = fill_small_holes(
        reference, hole_ratio(keep_openings) * max(1, np.count_nonzero(reference))
    )
    reports: list[MaskReport] = []
    for cand in candidates:
        cleaned = clean_mask(cand.mask, gap_px, keep_openings)
        rep = evaluate_mask(cand.name, cleaned, reference)
        reports.append(rep)
        if rep.accepted:
            return cleaned, cand.name, reports
    reasons = "; ".join(f"{r.name}: {r.reason}" for r in reports)
    raise PipelineError(
        "mask_validation",
        f"No valid segmentation mask was produced ({reasons}).",
        "Retry with a clearer photo, or choose a different view/image.",
    )
