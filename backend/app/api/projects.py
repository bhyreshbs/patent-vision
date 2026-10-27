from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_project
from app.core.database import get_db
from app.core.storage import storage
from app.models import Project, User
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from app.services.presenters import project_out

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    project = Project(name=body.name, description=body.description, user_id=user.id)
    db.add(project)
    db.commit()
    return project_out(db, project)


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc(), Project.id.desc())
    ).all()
    return [project_out(db, p) for p in rows]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return project_out(db, get_owned_project(db, user, project_id))


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, body: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    project = get_owned_project(db, user, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(project, field, value)
    db.commit()
    return project_out(db, project)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Deletes the project, its images, results and jobs (DB cascade) and all stored files."""
    project = get_owned_project(db, user, project_id)
    pid = project.id
    db.delete(project)
    db.commit()
    storage.delete_tree(f"uploads/{pid}")
    storage.delete_tree(f"generated/{pid}")
    return Response(status_code=204)
