from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

ViewType = Literal["Front", "Rear", "Left", "Right", "Top", "Bottom", "Other"]
ImageStatus = Literal["Uploaded", "Queued", "Processing", "Completed", "Failed"]


def _as_utc(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth ----
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or " " in v:
            raise ValueError("must be a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: str
    created_at: UtcDatetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---- projects ----
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("must not be blank")
        return v


class ProjectOut(ORM):
    id: int
    name: str
    description: str
    status: str
    user_id: int
    created_at: UtcDatetime
    updated_at: UtcDatetime
    image_count: int = 0
    status_counts: dict[str, int] = {}


# ---- images / results ----
class ResultOut(BaseModel):
    id: int
    image_id: int
    status: ImageStatus
    error_message: str | None
    failed_stage: str | None
    metrics: dict | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    # Public API URLs (never filesystem paths). None until that asset exists.
    urls: dict[str, str | None]


class JobOut(ORM):
    id: int
    image_id: int
    job_status: ImageStatus
    started_at: UtcDatetime | None
    completed_at: UtcDatetime | None
    error_message: str | None
    failed_stage: str | None
    retry_count: int


class ImageOut(BaseModel):
    id: int
    project_id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    view_type: ViewType
    processing_status: ImageStatus
    created_at: UtcDatetime
    original_url: str
    result: ResultOut | None = None
    job: JobOut | None = None


class ImageUpdate(BaseModel):
    view_type: ViewType


class ProcessAccepted(BaseModel):
    image_id: int
    status: ImageStatus
    job: JobOut


class ProjectProcessAccepted(BaseModel):
    project_id: int
    queued: list[int]
    skipped: list[int]


class DashboardOut(BaseModel):
    project_count: int
    image_count: int
    status_counts: dict[str, int]
    recent_projects: list[ProjectOut]
    recent_results: list[ImageOut]
