"""Job lifecycle: queue -> process -> persist, with failures always recorded and visible."""
import logging
import threading
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import PipelineError
from app.ai.pipeline import run_pipeline
from app.ai.segmentation import Segmenter, get_segmenter
from app.core import database
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.storage import storage
from app.models import ACTIVE_STATUSES, AIResult, Image, ProcessingJob, utcnow

log = logging.getLogger("patentvision.processing")

_OUTPUTS = (
    ("background_removed", "background_removed_path"),
    ("mask", "mask_path"),
    ("outline", "outline_path"),
    ("drawing", "patent_drawing_path"),
)
_slot_lock = threading.Lock()
_slots: threading.BoundedSemaphore | None = None


def _job_slots() -> threading.BoundedSemaphore:
    global _slots
    with _slot_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(max(1, get_settings().max_concurrent_jobs))
        return _slots


@lru_cache
def _segmenter(kind: str, checkpoint: str | None, model_type: str) -> Segmenter:
    """One segmenter per config so heavyweight models load once and are reused."""
    return get_segmenter(kind, checkpoint, model_type)


def generated_prefix(image: Image) -> str:
    return f"generated/{image.project_id}/{image.id}"


def _clear_outputs(result: AIResult, image: Image) -> None:
    storage.delete_tree(generated_prefix(image))
    for _, attr in _OUTPUTS:
        setattr(result, attr, None)
    result.metrics = None


def queue_image(db: Session, image: Image) -> ProcessingJob:
    """Mark an image Queued. Safe to call repeatedly: an in-flight job is never duplicated."""
    if image.processing_status in ACTIVE_STATUSES:
        raise ApiError(
            409,
            "already_processing",
            "This image is already queued or being processed.",
            "Wait for the current job to finish.",
        )
    job = image.job
    if job is None:
        job = ProcessingJob(image_id=image.id, retry_count=0)
        db.add(job)
    elif job.job_status in ("Failed", "Completed"):
        job.retry_count += 1
    job.job_status = "Queued"
    job.started_at = job.completed_at = None
    job.error_message = job.failed_stage = None

    result = image.result
    if result is None:
        result = AIResult(image_id=image.id)
        db.add(result)
    result.status = "Queued"
    result.error_message = result.failed_stage = None

    image.processing_status = "Queued"
    db.commit()
    db.refresh(job)
    return job


def run_job(image_id: int) -> None:
    """Background entry point; owns its own DB session."""
    with _job_slots():
        db = database.SessionLocal()
        try:
            _execute(db, image_id)
        except Exception:  # last-resort guard: never leave a job stuck in Processing
            log.exception("job for image %s crashed outside the pipeline", image_id)
            db.rollback()
            _mark_failed(db, image_id, "persistence", "Saving the result failed. Retry processing.")
        finally:
            db.close()


def _execute(db: Session, image_id: int) -> None:
    image = db.get(Image, image_id)
    if image is None or image.processing_status != "Queued":
        return
    job, result = image.job, image.result
    image.processing_status = job.job_status = result.status = "Processing"
    job.started_at = utcnow()
    db.commit()

    current = {"stage": "load"}
    try:
        if not storage.exists(image.storage_key):
            raise PipelineError(
                "load", "The original image file is missing from storage.", "Re-upload the image."
            )
        settings = get_settings()
        out = run_pipeline(
            storage.read_bytes(image.storage_key),
            settings,
            on_stage=lambda s: current.update(stage=s),
            segmenter=_segmenter(settings.segmenter, settings.sam_checkpoint, settings.sam_model_type),
        )
        current["stage"] = "save"
        prefix = generated_prefix(image)
        files = {
            "background_removed_path": storage.save_bytes(f"{prefix}/background_removed.png", out.background_removed),
            "mask_path": storage.save_bytes(f"{prefix}/mask.png", out.mask),
            "outline_path": storage.save_bytes(f"{prefix}/outline.png", out.outline),
            "patent_drawing_path": storage.save_bytes(f"{prefix}/drawing.png", out.drawing),
        }
        missing = [k for k, v in files.items() if not storage.exists(v)]
        if missing:
            raise PipelineError("save", "Generated files could not be saved.", "Retry processing.")

        current["stage"] = "persistence"
        for attr, key in files.items():
            setattr(result, attr, key)
        result.metrics = out.metrics
        result.error_message = result.failed_stage = None
        job.error_message = job.failed_stage = None
        image.processing_status = job.job_status = result.status = "Completed"
        job.completed_at = utcnow()
        db.commit()
    except PipelineError as exc:
        db.rollback()
        _mark_failed(db, image_id, exc.stage, exc.user_message())
    except Exception:
        log.exception("unexpected error in stage %s for image %s", current["stage"], image_id)
        db.rollback()
        _mark_failed(
            db,
            image_id,
            current["stage"],
            f"An unexpected error occurred during {current['stage'].replace('_', ' ')}. Retry processing.",
        )


def _mark_failed(db: Session, image_id: int, stage: str, message: str) -> None:
    image = db.get(Image, image_id)
    if image is None:
        return
    job, result = image.job, image.result
    image.processing_status = "Failed"
    if job:
        job.job_status, job.error_message, job.failed_stage, job.completed_at = "Failed", message, stage, utcnow()
    if result:
        _clear_outputs(result, image)
        result.status, result.error_message, result.failed_stage = "Failed", message, stage
    db.commit()
    log.warning("image %s failed at %s: %s", image_id, stage, message)


def recover_interrupted() -> int:
    """After a restart no worker owns Queued/Processing jobs: surface them as Failed so they can be retried."""
    db = database.SessionLocal()
    try:
        ids = db.scalars(select(Image.id).where(Image.processing_status.in_(ACTIVE_STATUSES))).all()
        for image_id in ids:
            _mark_failed(db, image_id, "interrupted", "Processing was interrupted by a server restart. Retry processing.")
        return len(ids)
    finally:
        db.close()
