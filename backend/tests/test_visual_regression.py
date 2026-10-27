"""Visual regression: pipeline output vs. the known-correct silhouettes of synthetic products.

Covers PRD §15.3/15.4: cups/containers, handles, multi-compartment organizers, connected protrusions,
dark backgrounds, logos/text and thin components.
"""
import cv2
import numpy as np
import pytest

from app.ai.imaging import decode_gray, mask_bbox
from app.ai.masks import iou
from app.ai.pipeline import run_pipeline
from app.core.config import Settings
from tests import synthetic

CASES = {  # name -> (generator, expected outer contours, expected inner openings in the default mode)
    "cup_with_handle": (synthetic.cup_with_handle, 1, 0),
    "organizer_dark_bg": (synthetic.organizer, 1, 0),
    "organizer_light_bg": (lambda: synthetic.organizer(bg=synthetic.LIGHT_BG, seed=7), 1, 0),
    "thin_spoon": (synthetic.thin_spoon, 1, 0),
    "logo_box": (synthetic.logo_box, 1, 0),
}


def outer_only(truth: np.ndarray) -> np.ndarray:
    """Reviewed reference for the default strict-outer-outline mode: enclosed openings filled."""
    pad = cv2.copyMakeBorder(truth, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    cv2.floodFill(pad, None, (0, 0), 128)
    return np.where(pad[1:-1, 1:-1] == 128, 0, 255).astype(np.uint8)


def silhouette_from_drawing(drawing: np.ndarray) -> np.ndarray:
    """Fill the drawn outline: everything not reachable from the border without crossing ink."""
    ink = (drawing < 128).astype(np.uint8)
    h, w = ink.shape
    flood = ink.copy() * 255
    pad = cv2.copyMakeBorder(flood, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    cv2.floodFill(pad, None, (0, 0), 128)
    outside = pad[1:-1, 1:-1] == 128
    return np.where(outside, 0, 255).astype(np.uint8)


def normalised_iou(a: np.ndarray, b: np.ndarray, size: int = 256) -> float:
    def crop(m):
        x0, y0, x1, y1 = mask_bbox(m)
        return cv2.resize(m[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_NEAREST)

    return iou(crop(a), crop(b))


@pytest.fixture(scope="module", params=list(CASES))
def case(request):
    gen, n_outer, n_open = CASES[request.param]
    img, truth = gen()
    out = run_pipeline(synthetic.encode(img))
    return request.param, img, outer_only(truth), out, n_outer, n_open


def test_mask_matches_reviewed_reference(case):
    name, img, truth, out, *_ = case
    mask = decode_gray(out.mask)
    assert mask.shape == truth.shape
    assert set(np.unique(mask)) <= {0, 255}
    assert iou(mask, truth) >= 0.95, name


def test_mask_has_no_background_or_shadow(case):
    name, img, truth, out, *_ = case
    mask = decode_gray(out.mask)
    assert not mask[:6, :6].any() and not mask[-6:, -6:].any()
    assert mask[truth == 0].mean() / 255 < 0.02, name  # almost nothing outside the true product


def test_drawing_is_faithful_to_reference_silhouette(case):
    name, img, truth, out, *_ = case
    drawing = decode_gray(out.drawing)
    assert normalised_iou(silhouette_from_drawing(drawing), truth) >= 0.93, name


def test_drawing_is_clean_outline_only(case):
    name, img, truth, out, n_outer, n_open = case
    drawing = decode_gray(out.drawing)
    assert drawing[:8, :8].min() == 255  # white background
    ink = (drawing < 128).astype(np.uint8)
    n_comp, *_ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    assert n_comp - 1 == n_outer + n_open, f"{name}: stray marks (logos/text/shadows) in drawing"
    assert out.metrics["contours"] == n_outer and out.metrics["openings"] == n_open
    assert out.metrics["fallback_used"] is False or out.metrics["mask_candidate"] == "foreground-mask"


def test_all_outputs_are_decodable_and_consistent(case):
    name, img, truth, out, *_ = case
    cut = cv2.imdecode(np.frombuffer(out.background_removed, np.uint8), cv2.IMREAD_UNCHANGED)
    assert cut.shape[:2] == img.shape[:2] and cut.shape[2] == 4
    assert cut[0, 0, 3] == 0  # transparent background
    outline = cv2.imdecode(np.frombuffer(out.outline, np.uint8), cv2.IMREAD_COLOR)
    assert outline.shape == img.shape
    m = out.metrics
    assert m["processed_size"] == [img.shape[1], img.shape[0]]
    x0, y0, x1, y1 = m["box"]
    assert 0 <= x0 < x1 <= img.shape[1] and 0 <= y0 < y1 <= img.shape[0]


def test_handle_opening_is_kept_only_when_opted_in():
    img, truth = synthetic.cup_with_handle()
    assert (truth == 0).sum() > (outer_only(truth) == 0).sum()  # the reference really has an opening

    strict = run_pipeline(synthetic.encode(img))
    assert strict.metrics["openings"] == 0

    out = run_pipeline(synthetic.encode(img), Settings(keep_openings=True))
    assert out.metrics["contours"] == 1 and out.metrics["openings"] == 1
    mask = decode_gray(out.mask)
    assert iou(mask, truth) >= 0.95  # mask now keeps the see-through handle opening
    ink = (decode_gray(out.drawing) < 128).astype(np.uint8)
    assert cv2.connectedComponents(ink, connectivity=8)[0] - 1 == 2  # outline + handle opening
    assert normalised_iou(silhouette_from_drawing(decode_gray(out.drawing)), outer_only(truth)) >= 0.93


def test_organizer_acceptance():
    """PRD §15.4: both compartments, middle connector, feet, holder; dark background excluded."""
    img, truth = synthetic.organizer()
    out = run_pipeline(synthetic.encode(img))
    mask = decode_gray(out.mask) > 0
    assert mask[340, 250], "left compartment missing"
    assert mask[340, 750], "right compartment missing"
    assert mask[335, 500], "middle connector missing"
    assert mask[200, 500], "cylindrical holder missing"
    for x in (150, 370, 630, 850):
        assert mask[470, x], f"foot at x={x} missing"
    assert not mask[40, 40] and not mask[600, 900], "dark background leaked into the mask"
    assert out.metrics["contours"] == 1, "expected one complete outer silhouette"
    x0, y0, x1, y1 = mask_bbox(mask.astype(np.uint8))
    assert x0 <= 112 and x1 >= 888 and y0 <= 108 and y1 >= 480  # full extent covered


def test_thin_handle_survives():
    img, truth = synthetic.thin_spoon()
    mask = decode_gray(run_pipeline(synthetic.encode(img)).mask) > 0
    assert mask[300, 600], "thin handle was lost"
    assert mask[300, 780], "handle end blob was lost"


def test_blank_photo_is_rejected_not_drawn():
    from app.ai.errors import PipelineError

    blank = np.full((400, 500, 3), 240, np.uint8)
    with pytest.raises(PipelineError) as e:
        run_pipeline(synthetic.encode(blank))
    assert e.value.stage in {"background_removal", "localization", "mask_validation"}


def test_large_photo_is_downscaled_and_boxes_map_back():
    img, truth = synthetic.organizer(w=2000, h=1300)
    big = cv2.resize(img, (2000, 1300))
    out = run_pipeline(synthetic.encode(big))
    m = out.metrics
    assert m["original_size"] == [2000, 1300]
    assert max(m["processed_size"]) == 1600
    ox0, oy0, ox1, oy1 = m["box_original"]
    assert 0 <= ox0 < ox1 <= 2000 and 0 <= oy0 < oy1 <= 1300
