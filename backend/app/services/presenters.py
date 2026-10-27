"""Map ORM rows to API schemas. Only public URLs are exposed, never storage keys or local paths."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AIResult, Image, Project
from app.schemas import ImageOut, JobOut, ProjectOut, ResultOut

DOWNLOAD_KINDS = {
    "drawing": "patent_drawing_path",
    "background_removed": "background_removed_path",
    "mask": "mask_path",
    "outline": "outline_path",
}


def result_out(result: AIResult) -> ResultOut:
    urls: dict[str, str | None] = {
        kind: (f"/ai/results/{result.id}/download?kind={kind}" if getattr(result, attr) else None)
        for kind, attr in DOWNLOAD_KINDS.items()
    }
    urls["original"] = f"/ai/results/{result.id}/download?kind=original"
    return ResultOut(
        id=result.id,
        image_id=result.image_id,
        status=result.status,
        error_message=result.error_message,
        failed_stage=result.failed_stage,
        metrics=result.metrics,
        created_at=result.created_at,
        updated_at=result.updated_at,
        urls=urls,
    )


def image_out(image: Image) -> ImageOut:
    return ImageOut(
        id=image.id,
        project_id=image.project_id,
        original_filename=image.original_filename,
        mime_type=image.mime_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        view_type=image.view_type,
        processing_status=image.processing_status,
        created_at=image.created_at,
        original_url=f"/images/{image.id}/original",
        result=result_out(image.result) if image.result else None,
        job=JobOut.model_validate(image.job) if image.job else None,
    )


def project_out(db: Session, project: Project) -> ProjectOut:
    rows = db.execute(
        select(Image.processing_status, func.count())
        .where(Image.project_id == project.id)
        .group_by(Image.processing_status)
    ).all()
    counts = {status: n for status, n in rows}
    out = ProjectOut.model_validate(project)
    out.image_count = sum(counts.values())
    out.status_counts = counts
    return out
