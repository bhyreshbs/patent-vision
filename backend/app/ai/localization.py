"""Product detection/localization from the foreground mask (controlled fallback to a YOLO-style box)."""
from dataclasses import dataclass

import numpy as np

from app.ai.errors import PipelineError
from app.ai.imaging import Box, mask_bbox, validate_box
from app.ai.masks import select_product_components


@dataclass
class Localization:
    box: Box  # padded product box, clipped to the image
    foreground: np.ndarray  # 0/255 mask of the complete product only (unrelated blobs removed)


def gap_for(shape: tuple[int, int]) -> int:
    return max(5, int(0.02 * max(shape)))


def localize_product(foreground: np.ndarray) -> Localization:
    h, w = foreground.shape
    product = select_product_components(foreground, gap_for((h, w)))
    bbox = mask_bbox(product)
    if bbox is None:
        raise PipelineError(
            "localization",
            "No product region could be located.",
            "Use a photo where the product contrasts with its background.",
        )
    pad = max(2, int(0.01 * max(h, w)))
    x0, y0, x1, y1 = bbox
    box = validate_box((x0 - pad, y0 - pad, x1 + pad, y1 + pad), w, h)
    return Localization(box=box, foreground=product)
