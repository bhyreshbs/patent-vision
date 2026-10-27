from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Image, Project, User
from app.schemas import DashboardOut
from app.core.config import get_settings
from app.services.presenters import image_out, project_out

router = APIRouter(tags=["dashboard"])


@router.get("/meta", tags=["meta"])
def meta():
    """Public limits the web app needs before uploading (e.g. to shrink large photos client-side)."""
    s = get_settings()
    return {
        "max_upload_bytes": s.max_upload_bytes,
        "accepted_types": ["image/jpeg", "image/png", "image/webp"],
        "storage": "blob" if s.use_blob else "local",
    }


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    owned = select(Project.id).where(Project.user_id == user.id)
    rows = db.execute(
        select(Image.processing_status, func.count())
        .where(Image.project_id.in_(owned))
        .group_by(Image.processing_status)
    ).all()
    counts = {status: n for status, n in rows}

    recent_projects = db.scalars(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(6)
    ).all()
    recent_results = db.scalars(
        select(Image)
        .where(Image.project_id.in_(owned), Image.processing_status == "Completed")
        .order_by(Image.id.desc())
        .limit(6)
    ).all()
    return DashboardOut(
        project_count=db.scalar(select(func.count()).select_from(Project).where(Project.user_id == user.id)) or 0,
        image_count=sum(counts.values()),
        status_counts=counts,
        recent_projects=[project_out(db, p) for p in recent_projects],
        recent_results=[image_out(i) for i in recent_results],
    )
