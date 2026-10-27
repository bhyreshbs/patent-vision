import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PV_ENV_FILE="" disables .env loading (tests must not pick up a developer's local settings).
    model_config = SettingsConfigDict(
        env_prefix="PV_", env_file=os.environ.get("PV_ENV_FILE", ".env") or None, extra="ignore"
    )

    # PV_DATABASE_URL wins; otherwise the DATABASE_URL / POSTGRES_URL injected by the Neon integration.
    database_url: str = Field(
        default="sqlite:///./patentvision.db",
        validation_alias=AliasChoices("PV_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL"),
    )
    auto_create_tables: bool = True

    # local: files under storage_root. blob: Vercel Blob (private store). auto: blob when Blob credentials exist.
    storage_backend: str = "auto"
    storage_root: Path = Path("./storage")

    # Public URL prefix the API is mounted under (Vercel routes /api/* to this service). Stripped if present.
    api_prefix: str = "/api"

    secret_key: str = "dev-insecure-secret-change-me"
    access_token_minutes: int = 60 * 24

    # Vercel Functions accept request bodies up to 4.5 MB; the web app shrinks larger photos before upload.
    max_upload_bytes: int = 4 * 1024 * 1024
    max_image_pixels: int = 40_000_000
    processing_max_side: int = 1600

    segmenter: str = "classical"  # classical | sam
    sam_checkpoint: str | None = None
    sam_model_type: str = "vit_b"

    # False (default, per PRD FR-09) = strict outer outline. True keeps large enclosed openings (e.g. a mug
    # handle) as inner contours; a light label on a light background can then be mistaken for an opening.
    keep_openings: bool = False
    drawing_long_side: int = 1400
    drawing_line_width: float = 4.0

    rate_limit_per_minute: int = 60
    max_concurrent_jobs: int = 2
    # A job still Queued/Processing after this long lost its worker (crash, timeout) and is shown as Failed.
    stale_job_minutes: int = 10

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @property
    def on_vercel(self) -> bool:
        return bool(os.environ.get("VERCEL"))

    @property
    def use_blob(self) -> bool:
        if self.storage_backend == "blob":
            return True
        if self.storage_backend == "local":
            return False
        return bool(
            os.environ.get("BLOB_READ_WRITE_TOKEN")
            or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN")
            or os.environ.get("BLOB_STORE_ID")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
