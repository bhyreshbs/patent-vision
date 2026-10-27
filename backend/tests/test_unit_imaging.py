import io

import numpy as np
import pytest
from PIL import Image as PILImage

from app.ai.errors import PipelineError
from app.ai.imaging import clip_box, load_image, scale_box, validate_box
from app.core.errors import ApiError
from app.services.uploads import sanitize_filename, validate_upload
from tests import synthetic

MAX_PIXELS = 40_000_000


def _png(w=120, h=80, mode="RGB", fmt="PNG", **kw) -> bytes:
    buf = io.BytesIO()
    PILImage.new(mode, (w, h), (200, 30, 30) if mode == "RGB" else (200, 30, 30, 255)).save(buf, fmt, **kw)
    return buf.getvalue()


# ---- image validation ----
@pytest.mark.parametrize("fmt,mime", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")])
def test_validate_upload_accepts_supported_formats(fmt, mime):
    info = validate_upload(_png(fmt=fmt), "my photo.png", MAX_PIXELS)
    assert info.mime_type == mime
    assert (info.width, info.height) == (120, 80)


def test_validate_upload_rejects_empty_and_corrupt():
    with pytest.raises(ApiError) as e:
        validate_upload(b"", "x.png", MAX_PIXELS)
    assert e.value.code == "empty_file"

    with pytest.raises(ApiError) as e:
        validate_upload(b"definitely not an image", "x.png", MAX_PIXELS)
    assert e.value.code == "corrupt_image" and e.value.status_code == 422

    truncated = _png(400, 400)[:-300]
    with pytest.raises(ApiError) as e:
        validate_upload(truncated, "x.png", MAX_PIXELS)
    assert e.value.code == "corrupt_image"


def test_validate_upload_rejects_unsupported_types():
    with pytest.raises(ApiError) as e:
        validate_upload(_png(fmt="GIF"), "x.gif", MAX_PIXELS)
    assert e.value.code == "unsupported_image_type" and e.value.status_code == 415

    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
    with pytest.raises(ApiError) as e:
        validate_upload(heic, "x.heic", MAX_PIXELS)
    assert e.value.code == "unsupported_image_type" and "HEIC" in e.value.message


def test_validate_upload_enforces_pixel_and_min_size_limits():
    with pytest.raises(ApiError) as e:
        validate_upload(_png(200, 200), "x.png", max_pixels=1000)
    assert e.value.code == "image_too_large"
    with pytest.raises(ApiError) as e:
        validate_upload(_png(10, 10), "x.png", MAX_PIXELS)
    assert e.value.code == "image_too_small"


def test_validate_upload_trusts_content_not_extension():
    info = validate_upload(_png(fmt="JPEG"), "photo.png", MAX_PIXELS)
    assert info.mime_type == "image/jpeg" and info.ext == "jpg"


def test_exif_orientation_is_applied_to_dimensions():
    im = PILImage.new("RGB", (120, 80), (10, 200, 10))
    exif = im.getexif()
    exif[0x0112] = 6  # rotate 90 deg
    buf = io.BytesIO()
    im.save(buf, "JPEG", exif=exif)
    info = validate_upload(buf.getvalue(), "r.jpg", MAX_PIXELS)
    assert (info.width, info.height) == (80, 120)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\my photo (1).JPG", "my_photo_1_.JPG"),
        ("", "image"),
        (None, "image"),
        ("a" * 300 + ".png", "a" * 100),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


# ---- box clipping / coordinates / dimensions ----
def test_clip_and_validate_box():
    assert clip_box((-10, -5, 500, 400), 200, 100) == (0, 0, 200, 100)
    assert validate_box((-10, 5, 150, 90), 200, 100) == (0, 5, 150, 90)
    with pytest.raises(PipelineError) as e:
        validate_box((50, 50, 52, 52), 200, 100)
    assert e.value.stage == "localization"
    with pytest.raises(PipelineError):
        validate_box((300, 300, 400, 400), 200, 100)  # entirely outside


def test_scale_box_round_trip():
    assert scale_box((10, 20, 110, 220), 2.0) == (20, 40, 220, 440)
    assert scale_box(scale_box((10, 20, 110, 220), 0.5), 2.0) == (10, 20, 110, 220)


def test_load_image_downscales_and_reports_scale():
    img, _ = synthetic.organizer(w=1000, h=650)
    loaded = load_image(synthetic.encode(img), max_side=500)
    assert loaded.original_size == (1000, 650)
    assert loaded.size == (500, 325)
    assert loaded.scale == pytest.approx(0.5)


def test_load_image_keeps_small_images_and_flattens_alpha():
    rgba = PILImage.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(30, 70):
        for y in range(30, 70):
            rgba.putpixel((x, y), (255, 0, 0, 255))
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    loaded = load_image(buf.getvalue(), max_side=500)
    assert loaded.scale == 1.0 and loaded.size == (100, 100)
    assert loaded.prior_mask is not None and loaded.prior_mask[50, 50] == 255 and loaded.prior_mask[5, 5] == 0
    assert tuple(loaded.bgr[5, 5]) == (255, 255, 255)  # transparent -> white


def test_load_image_undecodable_raises_pipeline_error():
    with pytest.raises(PipelineError) as e:
        load_image(b"garbage", 500)
    assert e.value.stage == "load"
