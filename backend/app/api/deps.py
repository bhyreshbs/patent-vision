from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.models import Image, Project, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None:
        raise ApiError(401, "unauthorized", "Authentication required.", "Log in and try again.")
    user_id = decode_access_token(creds.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise ApiError(401, "unauthorized", "Invalid or expired session.", "Log in again.")
    return user


def get_owned_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        # Same response for "missing" and "not yours": do not reveal other users' resources.
        raise ApiError(404, "project_not_found", "Project not found.")
    return project


def get_owned_image(db: Session, user: User, image_id: int) -> Image:
    image = db.get(Image, image_id)
    if image is None or image.project.user_id != user.id:
        raise ApiError(404, "image_not_found", "Image not found.")
    return image
