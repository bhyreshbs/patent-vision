from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_image, get_owned_project
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.ratelimit import rate_limit
from app.core.storage import storage
from app.models import ACTIVE_STATUSES, AIResult, Image, Project, User
from app.schemas import JobOut, ProcessAccepted, ProjectProcessAccepted, ResultOut
from app.services.presenters import DOWNLOAD_KINDS, result_out
from app.services.processing import queue_image, run_job

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/process/project/{project_id}",
    response_model=ProjectProcessAccepted,
    status_code=202,
    dependencies=[Depends(rate_limit("process"))],
)
def process_project(
    project_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue every image that is not already queued/processing (so failed views can be re-run)."""
    project = get_owned_project(db, user, project_id)
    queued, skipped = [], []
    for image in project.images:
        if image.processing_status in ACTIVE_STATUSES:
            skipped.append(image.id)
            continue
        queue_image(db, image)
        queued.append(image.id)
        background.add_task(run_job, image.id)
    return ProjectProcessAccepted(project_id=project.id, queued=queued, skipped=skipped)


@router.post(
    "/process/{image_id}",
    response_model=ProcessAccepted,
    status_code=202,
    dependencies=[Depends(rate_limit("process"))],
)
def process_image(
    image_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    image = get_owned_image(db, user, image_id)
    job = queue_image(db, image)
    background.add_task(run_job, image.id)
    return ProcessAccepted(image_id=image.id, status=image.processing_status, job=JobOut.model_validate(job))


def _owned_result(db: Session, user: User, result_id: int) -> AIResult:
    result = db.scalar(
        select(AIResult)
        .join(Image, AIResult.image_id == Image.id)
        .join(Project, Image.project_id == Project.id)
        .where(AIResult.id == result_id, Project.user_id == user.id)
    )
    if result is None:
        raise ApiError(404, "result_not_found", "Result not found.")
    return result


@router.get("/results/{result_id}", response_model=ResultOut)
def get_result(result_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return result_out(_owned_result(db, user, result_id))


@router.get("/results/{result_id}/download")
def download_result(
    result_id: int,
    kind: Literal["drawing", "background_removed", "mask", "outline", "original"] = "drawing",
    download: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = _owned_result(db, user, result_id)
    image = result.image
    if kind == "original":
        key, mime, ext = image.storage_key, image.mime_type, image.storage_key.rsplit(".", 1)[-1]
    else:
        if result.status != "Completed":
            raise ApiError(
                409,
                "result_not_ready",
                "This result is not available because processing has not completed successfully.",
                "Process or retry the image first.",
            )
        key, mime, ext = getattr(result, DOWNLOAD_KINDS[kind]), "image/png", "png"
    if not key or not storage.exists(key):
        raise ApiError(404, "file_missing", "The requested file is missing from storage.", "Retry processing.")

    stem = image.original_filename.rsplit(".", 1)[0] or "image"
    return FileResponse(
        storage.path(key),
        media_type=mime,
        filename=f"{stem}_{kind}.{ext}" if download else None,
        headers={"Cache-Control": "private, no-store"},
    )
