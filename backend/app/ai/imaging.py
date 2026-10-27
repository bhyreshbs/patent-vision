"""Image loading, encoding and coordinate helpers shared by the pipeline stages."""
import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.ai.errors import PipelineError

Box = tuple[int, int, int, int]  # x0, y0, x1, y1 (x1/y1 exclusive), pixel coordinates


@dataclass
class LoadedImage:
    bgr: np.ndarray  # H x W x 3 uint8, alpha flattened onto white
    prior_mask: np.ndarray | None  # H x W uint8 0/255 when the source had real transparency
    original_size: tuple[int, int]  # (width, height) after EXIF orientation
    scale: float  # processed / original

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.bgr.shape[:2]
        return w, h


def load_image(data: bytes, max_side: int) -> LoadedImage:
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.load()
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            rgba = im.convert("RGBA")
    except Exception as exc:
        raise PipelineError(
            "load", "The stored image could not be decoded.", "Re-upload the original image."
        ) from exc

    arr = np.asarray(rgba)
    alpha = arr[:, :, 3]
    prior = None
    if has_alpha and (alpha < 250).mean() > 0.01 and (alpha > 128).any():
        prior = np.where(alpha > 128, 255, 0).astype(np.uint8)

    rgb = arr[:, :, :3].astype(np.float32)
    a = (alpha.astype(np.float32) / 255.0)[:, :, None]
    flat = (rgb * a + 255.0 * (1.0 - a)).astype(np.uint8)
    bgr = cv2.cvtColor(flat, cv2.COLOR_RGB2BGR)

    h, w = bgr.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        bgr = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        if prior is not None:
            prior = cv2.resize(prior, (nw, nh), interpolation=cv2.INTER_NEAREST)
    return LoadedImage(bgr=bgr, prior_mask=prior, original_size=(w, h), scale=scale)


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise PipelineError("save", "Failed to encode an output image.")
    return buf.tobytes()


def decode_gray(data: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
    if arr is None:
        raise PipelineError("save", "A stored output image could not be decoded.")
    return arr


def clip_box(box: Box, width: int, height: int) -> Box:
    x0, y0, x1, y1 = box
    return (max(0, x0), max(0, y0), min(width, x1), min(height, y1))


def validate_box(box: Box, width: int, height: int, min_side: int = 8) -> Box:
    """Clip a detector box to the image and reject degenerate ones."""
    x0, y0, x1, y1 = clip_box(box, width, height)
    if x1 - x0 < min_side or y1 - y0 < min_side:
        raise PipelineError(
            "localization",
            "The detected product region is empty or too small.",
            "Use a photo where the product fills more of the frame.",
        )
    return (x0, y0, x1, y1)


def scale_box(box: Box, factor: float) -> Box:
    """Transform a box between coordinate spaces (e.g. processed -> original resolution)."""
    x0, y0, x1, y1 = box
    return (round(x0 * factor), round(y0 * factor), round(x1 * factor), round(y1 * factor))


def mask_bbox(mask: np.ndarray) -> Box | None:
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
