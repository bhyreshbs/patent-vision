import cv2
import numpy as np
import pytest

from app.ai.errors import PipelineError
from app.ai.localization import gap_for, localize_product
from app.ai.mask_validation import choose_mask, clean_mask, evaluate_mask
from app.ai.masks import border_contact_fraction, fill_small_holes, iou, select_product_components
from app.ai.segmentation import Candidate, SamSegmenter, get_segmenter


def blank(h=400, w=600):
    return np.zeros((h, w), np.uint8)


def two_boxes():
    m = blank()
    cv2.rectangle(m, (50, 150), (250, 300), 255, -1)
    cv2.rectangle(m, (350, 150), (550, 300), 255, -1)
    cv2.rectangle(m, (250, 200), (350, 240), 255, -1)  # connector
    return m


def test_fill_small_holes_keeps_large_openings():
    m = blank()
    cv2.rectangle(m, (50, 50), (350, 350), 255, -1)
    cv2.rectangle(m, (100, 100), (110, 110), 0, -1)  # logo-sized pocket
    cv2.rectangle(m, (200, 100), (300, 250), 0, -1)  # real opening
    out = fill_small_holes(m, max_hole_area=500)
    assert out[105, 105] == 255
    assert out[150, 250] == 0


def test_select_product_components_drops_far_noise_keeps_nearby_parts():
    m = blank()
    cv2.rectangle(m, (100, 100), (300, 300), 255, -1)
    cv2.rectangle(m, (310, 150), (340, 250), 255, -1)  # part separated by a 10px gap
    cv2.circle(m, (560, 40), 8, 255, -1)  # unrelated speck far away
    out = select_product_components(m, gap_px=20)
    assert out[200, 320] == 255
    assert out[40, 560] == 0


def test_border_contact_and_iou():
    m = blank(100, 100)
    m[:, :] = 255
    assert border_contact_fraction(m) == 1.0
    assert border_contact_fraction(blank()) == 0.0
    a, b = blank(), blank()
    a[:100, :100] = 255
    b[:100, :50] = 255
    assert iou(a, b) == pytest.approx(0.5)


def test_localize_product_unions_all_parts_and_clips_box():
    loc = localize_product(two_boxes())
    x0, y0, x1, y1 = loc.box
    assert x0 <= 50 and x1 >= 550 and y0 <= 150 and y1 >= 300
    assert x0 >= 0 and y1 <= 400


def test_localize_empty_foreground_fails_clearly():
    with pytest.raises(PipelineError) as e:
        localize_product(blank())
    assert e.value.stage == "localization"


def test_valid_mask_is_accepted():
    ref = two_boxes()
    cand = [Candidate("full", ref.copy())]
    mask, name, reports = choose_mask(cand, ref, gap_for(ref.shape))
    assert name == "full" and reports[0].accepted
    assert iou(mask, ref) > 0.99


def test_empty_mask_rejected():
    ref = two_boxes()
    with pytest.raises(PipelineError) as e:
        choose_mask([Candidate("empty", blank())], ref, gap_for(ref.shape))
    assert e.value.stage == "mask_validation" and "empty" in e.value.message


def test_single_compartment_is_rejected_not_polished():
    """PRD §7: segmenting one compartment of a multi-compartment organizer must be rejected."""
    ref = two_boxes()
    one = blank()
    cv2.rectangle(one, (50, 150), (250, 300), 255, -1)
    with pytest.raises(PipelineError) as e:
        choose_mask([Candidate("one-compartment", one)], ref, gap_for(ref.shape))
    assert "incomplete" in e.value.message


def test_whole_image_mask_rejected_as_background():
    ref = two_boxes()
    full = np.full_like(ref, 255)
    rep = evaluate_mask("full", clean_mask(full, 10), ref)
    assert not rep.accepted and "background" in rep.reason


def test_contaminated_mask_rejected():
    ref = two_boxes()
    wide = ref.copy()
    cv2.rectangle(wide, (0, 0), (300, 120), 255, -1)  # drags in unrelated area
    rep = evaluate_mask("wide", clean_mask(wide, 10), ref)
    assert not rep.accepted


def test_choose_mask_falls_back_to_next_valid_candidate_and_reports_all():
    ref = two_boxes()
    bad = blank()
    cv2.rectangle(bad, (50, 150), (250, 300), 255, -1)
    mask, name, reports = choose_mask(
        [Candidate("bad", bad), Candidate("foreground-mask", ref)], ref, gap_for(ref.shape)
    )
    assert name == "foreground-mask"
    assert [r.accepted for r in reports] == [False, True]


def test_sam_without_checkpoint_fails_with_clear_error():
    seg = SamSegmenter(checkpoint=None)
    with pytest.raises(PipelineError) as e:
        seg.segment(np.zeros((50, 50, 3), np.uint8), (0, 0, 50, 50), blank(50, 50))
    assert e.value.stage == "segmentation" and "checkpoint" in e.value.message


def test_get_segmenter_selection():
    assert get_segmenter("classical").__class__.__name__ == "ClassicalSegmenter"
    assert get_segmenter("sam", "/nope.pth").__class__.__name__ == "SamSegmenter"
    with pytest.raises(ValueError):
        get_segmenter("bogus")
