"""Binary-mask helpers (white foreground = 255, black background = 0)."""
import cv2
import numpy as np


def odd(n: int) -> int:
    n = max(1, int(n))
    return n if n % 2 == 1 else n + 1


def ellipse(k: int) -> np.ndarray:
    k = odd(k)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def to_binary(mask: np.ndarray) -> np.ndarray:
    return np.where(mask > 127, 255, 0).astype(np.uint8)


def fill_small_holes(mask: np.ndarray, max_hole_area: float) -> np.ndarray:
    """Fill background pockets fully enclosed by foreground that are smaller than max_hole_area.

    Larger enclosed pockets (e.g. a mug handle opening) are real see-through regions and stay.
    """
    inv = cv2.bitwise_not(mask)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = mask.shape
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        touches_border = x == 0 or y == 0 or x + bw == w or y + bh == h
        if not touches_border and area <= max_hole_area:
            out[labels == i] = 255
    return out


def select_product_components(mask: np.ndarray, gap_px: int, min_group_ratio: float = 0.10) -> np.ndarray:
    """Keep the complete product: the dominant connected group plus nearby substantial groups.

    Pixels are grouped after a closing of `gap_px` so parts separated by thin gaps (feet, dividers,
    a holder next to the body) stay together; small far-away blobs are treated as noise.
    """
    if not mask.any():
        return mask
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ellipse(gap_px))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n <= 1:
        return mask
    areas = stats[1:, cv2.CC_STAT_AREA]
    main = 1 + int(np.argmax(areas))
    mx0, my0 = stats[main, cv2.CC_STAT_LEFT], stats[main, cv2.CC_STAT_TOP]
    mx1, my1 = mx0 + stats[main, cv2.CC_STAT_WIDTH], my0 + stats[main, cv2.CC_STAT_HEIGHT]
    diag = float(np.hypot(*mask.shape))
    max_dist = 0.10 * diag

    keep = np.zeros(n, dtype=bool)
    keep[main] = True
    for i in range(1, n):
        if i == main or stats[i, cv2.CC_STAT_AREA] < min_group_ratio * areas.max():
            continue
        x0, y0 = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        x1, y1 = x0 + stats[i, cv2.CC_STAT_WIDTH], y0 + stats[i, cv2.CC_STAT_HEIGHT]
        dx = max(mx0 - x1, x0 - mx1, 0)
        dy = max(my0 - y1, y0 - my1, 0)
        if np.hypot(dx, dy) <= max_dist:
            keep[i] = True
    return np.where(keep[labels] & (mask > 0), 255, 0).astype(np.uint8)


def border_contact_fraction(mask: np.ndarray) -> float:
    """Fraction of the image perimeter covered by foreground."""
    top, bottom = mask[0, :], mask[-1, :]
    left, right = mask[:, 0], mask[:, -1]
    total = top.size + bottom.size + left.size + right.size
    hit = int((top > 0).sum() + (bottom > 0).sum() + (left > 0).sum() + (right > 0).sum())
    return hit / total


def iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.count_nonzero((a > 0) & (b > 0))
    union = np.count_nonzero((a > 0) | (b > 0))
    return inter / union if union else 0.0
