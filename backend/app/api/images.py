import uuid

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_image, get_owned_project
from app.api.files import file_response
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.ratelimit import rate_limit
from app.core.storage import storage
from app.models import VIEW_TYPES, Image, User, utcnow
from app.schemas import ImageOut, ImageUpdate
from app.services.presenters import image_out
from app.services.processing import expire_stale
from app.services.uploads import validate_upload

router = APIRouter(tags=["images"])

_CHUNK = 1024 * 1024


def _read_limited(file: UploadFile, limit: int) -> bytes:
    buf = bytearray()
    while chunk := file.file.read(_CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            raise ApiError(
                413,
                "file_too_large",
                f"The file exceeds the {limit / (1024 * 1024):.0f} MB upload limit.",
                "Upload a smaller image.",
            )
    return bytes(buf)


@router.post(
    "/projects/{project_id}/images",
    response_model=ImageOut,
    status_code=201,
    dependencies=[Depends(rate_limit("upload"))],
)
def upload_image(
    project_id: int,
    file: UploadFile = File(...),
    view_type: str = Form("Other"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = get_owned_project(db, user, project_id)
    if view_type not in VIEW_TYPES:
        raise ApiError(422, "invalid_view", f"view_type must be one of {', '.join(VIEW_TYPES)}.")

    settings = get_settings()
    data = _read_limited(file, settings.max_upload_bytes)
    info = validate_upload(data, file.filename, settings.max_image_pixels)

    key = f"uploads/{project.id}/{uuid.uuid4().hex}.{info.ext}"
    storage.save_bytes(key, data, info.mime_type)  # original bytes are preserved untouched
    try:
        image = Image(
            project_id=project.id,
            original_filename=info.safe_name,
            storage_key=key,
            mime_type=info.mime_type,
            size_bytes=len(data),
            width=info.width,
            height=info.height,
            view_type=view_type,
            processing_status="Uploaded",
        )
        db.add(image)
        project.updated_at = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return image_out(image)


@router.get("/projects/{project_id}/images", response_model=list[ImageOut])
def list_images(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = get_owned_project(db, user, project_id)
    expire_stale(db, project.images)
    return [image_out(i) for i in project.images]


@router.get("/images/{image_id}", response_model=ImageOut)
def get_image(image_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    image = get_owned_image(db, user, image_id)
    expire_stale(db, [image])
    return image_out(image)


@router.patch("/images/{image_id}", response_model=ImageOut)
def update_image(
    image_id: int, body: ImageUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    image = get_owned_image(db, user, image_id)
    image.view_type = body.view_type
    db.commit()
    return image_out(image)


@router.get("/images/{image_id}/original")
def download_original(
    image_id: int, download: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    image = get_owned_image(db, user, image_id)
    return file_response(
        image.storage_key,
        image.mime_type,
        image.original_filename if download else None,
        "Re-upload the image.",
    )


@router.delete("/images/{image_id}", status_code=204)
def delete_image(image_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    image = get_owned_image(db, user, image_id)
    if image.processing_status in ("Queued", "Processing"):
        raise ApiError(409, "already_processing", "This image is being processed.", "Wait for the job to finish.")
    key, pid, iid = image.storage_key, image.project_id, image.id
    db.delete(image)
    db.commit()
    storage.delete(key)
    storage.delete_tree(f"generated/{pid}/{iid}")
    return Response(status_code=204)
