from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PV_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./patentvision.db"
    storage_root: Path = Path("./storage")
    auto_create_tables: bool = True

    secret_key: str = "dev-insecure-secret-change-me"
    access_token_minutes: int = 60 * 24

    max_upload_bytes: int = 15 * 1024 * 1024
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

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
