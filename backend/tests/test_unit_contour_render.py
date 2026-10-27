import cv2
import numpy as np
import pytest

from app.ai.contour import ContourSet, extract_contours, smooth_contour
from app.ai.errors import PipelineError
from app.ai.rendering import Drawing, overlay_outline, render_drawing, validate_drawing


def rect_mask(h=300, w=400):
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (60, 80), (340, 220), 255, -1)
    return m


def roughness(pts: np.ndarray) -> float:
    """Mean absolute second difference: high for staircase/jagged lines."""
    d2 = np.roll(pts, -1, axis=0) - 2 * pts + np.roll(pts, 1, axis=0)
    return float(np.linalg.norm(d2, axis=1).mean())


def test_extract_contours_removes_small_noise():
    m = rect_mask()
    cv2.circle(m, (30, 30), 3, 255, -1)  # isolated speck
    cs = extract_contours(m)
    assert len(cs.outer) == 1 and not cs.holes
    xs, ys = cs.outer[0][:, 0], cs.outer[0][:, 1]
    assert xs.min() >= 59 and xs.max() <= 341 and ys.min() >= 79


def test_extract_contours_empty_mask_raises():
    with pytest.raises(PipelineError) as e:
        extract_contours(np.zeros((50, 50), np.uint8))
    assert e.value.stage == "contour_extraction"


def test_large_openings_kept_small_ones_dropped_and_toggle():
    m = rect_mask()
    cv2.rectangle(m, (120, 110), (200, 190), 0, -1)  # big opening
    cv2.rectangle(m, (260, 120), (266, 126), 0, -1)  # tiny pocket
    assert len(extract_contours(m, keep_openings=True).holes) == 1
    assert len(extract_contours(m).holes) == 0  # default: strict outer outline


def test_smoothing_reduces_jaggedness_but_keeps_shape():
    m = np.zeros((300, 300), np.uint8)
    cv2.circle(m, (150, 150), 100, 255, -1)
    rng = np.random.default_rng(0)
    for _ in range(300):  # carve 1px noise into the edge
        a = rng.uniform(0, 2 * np.pi)
        r = 100 + rng.integers(-2, 3)
        m[int(150 + r * np.sin(a)), int(150 + r * np.cos(a))] = rng.choice([0, 255])
    raw = extract_contours(m, smooth=False).outer[0]
    smooth = extract_contours(m, smooth=True).outer[0]
    assert roughness(smooth) < 0.5 * roughness(raw)
    radius = np.linalg.norm(smooth - np.array([150, 150]), axis=1)
    assert abs(radius.mean() - 100) < 2.5


def test_smoothing_preserves_corners():
    pts = extract_contours(rect_mask(), smooth=False).outer[0]
    sm = smooth_contour(pts)
    for corner in [(60, 80), (339, 80), (60, 219), (339, 219)]:
        assert np.linalg.norm(sm - np.array(corner), axis=1).min() < 2.0


def test_concave_region_is_preserved():
    m = np.zeros((300, 300), np.uint8)
    cv2.rectangle(m, (50, 50), (250, 250), 255, -1)
    cv2.rectangle(m, (120, 50), (180, 150), 0, -1)  # notch cut from the top
    cs = extract_contours(m)
    notch = cv2.pointPolygonTest(cs.outer[0].reshape(-1, 1, 2), (150.0, 90.0), False)
    assert notch < 0  # the notch interior is outside the outline


def test_render_dimensions_white_background_and_margins():
    cs = extract_contours(rect_mask())
    d = render_drawing(cs, long_side=800, line_width=4)
    h, w = d.image.shape
    assert max(h, w) == pytest.approx(800, abs=2)
    assert w > h  # aspect ratio preserved (280x140 box)
    assert d.image[:5, :5].min() == 255 and d.image[-5:, -5:].min() == 255
    ys, xs = np.nonzero(d.image < 128)
    assert xs.min() > 0.05 * w and ys.min() > 0.05 * h
    assert xs.max() < 0.95 * w and ys.max() < 0.95 * h
    assert set(np.unique(d.image)) != {0, 255}  # anti-aliased, not 1-bit
    assert validate_drawing(d)["line_width_ratio"] == pytest.approx(1.0, abs=0.25)


def test_render_line_thickness_is_uniform_on_curves_and_straights():
    m = np.zeros((400, 600), np.uint8)
    cv2.ellipse(m, (200, 200), (120, 90), 0, 0, 360, 255, -1)
    cv2.rectangle(m, (330, 110), (560, 290), 255, -1)
    d = render_drawing(extract_contours(m), long_side=1200, line_width=5)
    dist = cv2.distanceTransform((d.image < 128).astype(np.uint8), cv2.DIST_L2, 5)
    ridge = dist[(dist == cv2.dilate(dist, np.ones((3, 3), np.uint8))) & (dist > 0)]  # stroke centre line
    widths = ridge * 2
    assert np.median(widths) == pytest.approx(5, abs=1.0)
    assert np.percentile(widths, 10) > 3.5 and np.percentile(widths, 90) < 6.5  # uniform, no thin/fat spots


def test_validate_drawing_rejects_bad_outputs():
    blank = Drawing(np.full((200, 200), 255, np.uint8), 100.0, 4.0)
    with pytest.raises(PipelineError) as e:
        validate_drawing(blank)
    assert e.value.stage == "output_validation"

    dark_bg = Drawing(np.zeros((200, 200), np.uint8), 100.0, 4.0)
    with pytest.raises(PipelineError):
        validate_drawing(dark_bg)

    img = np.full((200, 200), 255, np.uint8)
    cv2.rectangle(img, (0, 0), (199, 199), 0, 4)  # touches the edges: no margin
    with pytest.raises(PipelineError):
        validate_drawing(Drawing(img, 800.0, 4.0))


def test_overlay_outline_matches_source_dimensions():
    src = np.full((300, 400, 3), 200, np.uint8)
    out = overlay_outline(src, extract_contours(rect_mask()))
    assert out.shape == src.shape
    assert (out != src).any()
