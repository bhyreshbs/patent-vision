from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_image, get_owned_project
from app.api.files import file_response
from app.core.database import get_db
from app.core.errors import ApiError
from app.core.ratelimit import rate_limit
from app.models import ACTIVE_STATUSES, AIResult, Image, Project, User
from app.schemas import JobOut, ProcessAccepted, ProjectProcessAccepted, ResultOut
from app.services.presenters import DOWNLOAD_KINDS, result_out
from app.services.processing import expire_stale, queue_image, run_job

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/process/project/{project_id}",
    response_model=ProjectProcessAccepted,
    dependencies=[Depends(rate_limit("process"))],
)
def process_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Process every image that is not already in flight (so failed views can be re-run)."""
    project = get_owned_project(db, user, project_id)
    expire_stale(db, project.images)
    queued, skipped = [], []
    for image in list(project.images):
        if image.processing_status in ACTIVE_STATUSES:
            skipped.append(image.id)
            continue
        try:
            queue_image(db, image)
        except ApiError:
            skipped.append(image.id)
            continue
        queued.append(image.id)
        run_job(image.id)
    return ProjectProcessAccepted(project_id=project.id, queued=queued, skipped=skipped)


@router.post(
    "/process/{image_id}",
    response_model=ProcessAccepted,
    dependencies=[Depends(rate_limit("process"))],
)
def process_image(image_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Run the pipeline for one image and return its final status (Completed or Failed)."""
    image = get_owned_image(db, user, image_id)
    queue_image(db, image)
    run_job(image.id)
    db.expire_all()
    image = db.get(Image, image_id)
    return ProcessAccepted(image_id=image.id, status=image.processing_status, job=JobOut.model_validate(image.job))


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
    kind: Literal["drawing", "svg", "background_removed", "mask", "outline", "original"] = "drawing",
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
        key = getattr(result, DOWNLOAD_KINDS[kind])
        mime, ext = ("image/svg+xml", "svg") if kind == "svg" else ("image/png", "png")

    stem = image.original_filename.rsplit(".", 1)[0] or "image"
    return file_response(key, mime, f"{stem}_{kind}.{ext}" if download else None, "Retry processing.")
