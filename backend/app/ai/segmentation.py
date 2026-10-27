"""Segmentation backends. Each returns candidate masks in preference order; validation picks one."""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from app.ai.errors import PipelineError
from app.ai.imaging import Box
from app.ai.masks import ellipse, to_binary

GRABCUT_MAX_SIDE = 640


@dataclass
class Candidate:
    name: str
    mask: np.ndarray  # 0/255, same size as the image


class Segmenter(Protocol):
    def segment(self, bgr: np.ndarray, box: Box, foreground: np.ndarray) -> list[Candidate]: ...


def _grabcut(bgr: np.ndarray, box: Box, foreground: np.ndarray) -> np.ndarray | None:
    h, w = foreground.shape
    s = min(1.0, GRABCUT_MAX_SIDE / max(h, w))
    sw, sh = max(1, round(w * s)), max(1, round(h * s))
    img = cv2.resize(bgr, (sw, sh), interpolation=cv2.INTER_AREA) if s < 1 else bgr.copy()
    fg = cv2.resize(foreground, (sw, sh), interpolation=cv2.INTER_NEAREST) if s < 1 else foreground

    k = max(3, sw // 80)
    sure_fg = cv2.erode(fg, ellipse(k))
    maybe_bg = cv2.dilate(fg, ellipse(2 * k))
    gc = np.full((sh, sw), cv2.GC_BGD, np.uint8)
    gc[maybe_bg > 0] = cv2.GC_PR_BGD
    gc[fg > 0] = cv2.GC_PR_FGD
    gc[sure_fg > 0] = cv2.GC_FGD
    if not (gc == cv2.GC_FGD).any() or not (gc == cv2.GC_BGD).any():
        return None

    try:
        bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        cv2.grabCut(img, gc, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None

    out = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    if s < 1:
        out = to_binary(cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR))
    x0, y0, x1, y1 = box
    clipped = np.zeros_like(out)
    clipped[y0:y1, x0:x1] = out[y0:y1, x0:x1]
    return clipped


class ClassicalSegmenter:
    """GrabCut refinement of the foreground mask, with the foreground mask itself as the fallback."""

    def segment(self, bgr: np.ndarray, box: Box, foreground: np.ndarray) -> list[Candidate]:
        candidates: list[Candidate] = []
        refined = _grabcut(bgr, box, foreground)
        if refined is not None:
            candidates.append(Candidate("grabcut", refined))
        candidates.append(Candidate("foreground-mask", foreground))
        return candidates


class SamSegmenter:
    """Segment Anything, prompted with the localized product box. Needs torch + a checkpoint."""

    def __init__(self, checkpoint: str | None, model_type: str = "vit_b") -> None:
        self.checkpoint = checkpoint
        self.model_type = model_type
        self._predictor = None

    def _load(self):
        if self._predictor is not None:
            return self._predictor
        if not self.checkpoint or not Path(self.checkpoint).is_file():
            raise PipelineError(
                "segmentation",
                "The SAM model checkpoint is missing.",
                "Set PV_SAM_CHECKPOINT to a valid checkpoint file or use PV_SEGMENTER=classical.",
            )
        try:
            from segment_anything import SamPredictor, sam_model_registry
        except ImportError as exc:
            raise PipelineError(
                "segmentation",
                "The segment-anything package is not installed.",
                "Install torch and segment-anything or use PV_SEGMENTER=classical.",
            ) from exc
        sam = sam_model_registry[self.model_type](checkpoint=self.checkpoint)
        self._predictor = SamPredictor(sam)
        return self._predictor

    def segment(self, bgr: np.ndarray, box: Box, foreground: np.ndarray) -> list[Candidate]:
        predictor = self._load()
        predictor.set_image(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        masks, scores, _ = predictor.predict(box=np.array(box), multimask_output=True)
        order = np.argsort(-scores)
        return [
            Candidate(f"sam-{i}", np.where(masks[i], 255, 0).astype(np.uint8)) for i in order
        ] + [Candidate("foreground-mask", foreground)]


def get_segmenter(kind: str, sam_checkpoint: str | None = None, sam_model_type: str = "vit_b") -> Segmenter:
    if kind == "classical":
        return ClassicalSegmenter()
    if kind == "sam":
        return SamSegmenter(sam_checkpoint, sam_model_type)
    raise ValueError(f"Unknown segmenter '{kind}'. Use 'classical' or 'sam'.")
