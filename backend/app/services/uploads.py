"""Upload validation: type, size, integrity, dimensions and filename sanitising."""
import io
import os
import re
from dataclasses import dataclass

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from app.core.errors import ApiError

ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis")
MIN_SIDE = 32


@dataclass
class ValidatedUpload:
    mime_type: str
    ext: str
    width: int
    height: int
    safe_name: str


def sanitize_filename(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return (base or "image")[:100]


def _looks_like_heic(data: bytes) -> bool:
    return data[4:8] == b"ftyp" and data[8:12] in HEIC_BRANDS


def validate_upload(data: bytes, filename: str | None, max_pixels: int) -> ValidatedUpload:
    if not data:
        raise ApiError(422, "empty_file", "The uploaded file is empty.", "Choose a valid image file.")
    if _looks_like_heic(data):
        raise ApiError(
            415,
            "unsupported_image_type",
            "HEIC images are not supported yet.",
            "Convert the photo to JPG, PNG or WEBP and upload it again.",
        )
    try:
        with PILImage.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            if fmt not in ALLOWED:
                raise ApiError(
                    415,
                    "unsupported_image_type",
                    f"Unsupported image type{f' ({fmt})' if fmt else ''}.",
                    "Upload a JPG, PNG or WEBP image.",
                )
            if probe.width * probe.height > max_pixels:
                raise ApiError(
                    413,
                    "image_too_large",
                    "The image has too many pixels.",
                    "Downscale the image and upload it again.",
                )
        # Full decode catches truncated / corrupt files that open() alone accepts.
        with PILImage.open(io.BytesIO(data)) as im:
            im.load()
            oriented = ImageOps.exif_transpose(im)
            width, height = oriented.size
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, PILImage.DecompressionBombError) as exc:
        raise ApiError(
            422,
            "corrupt_image",
            "The file is not a readable image (it may be corrupt or truncated).",
            "Upload a valid JPG, PNG or WEBP image.",
        ) from exc

    if min(width, height) < MIN_SIDE:
        raise ApiError(
            422, "image_too_small", f"The image must be at least {MIN_SIDE}px on each side.", "Upload a larger photo."
        )
    mime, ext = ALLOWED[fmt]
    return ValidatedUpload(mime, ext, width, height, sanitize_filename(filename))
