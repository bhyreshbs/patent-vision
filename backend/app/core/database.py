import threading
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import ApiError


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    """Neon/Heroku style postgres:// URLs -> SQLAlchemy + psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _make_engine() -> Engine:
    url = normalize_url(get_settings().database_url)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    # Serverless-friendly pool: few connections, verified before use, recycled before Neon idles them out.
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3, pool_recycle=240)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

_init_lock = threading.Lock()
_initialized = False


def init_db() -> None:
    """Create tables once per process (idempotent). Serverless instances may skip ASGI lifespan."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        if get_settings().auto_create_tables:
            from app import models  # noqa: F401  (registers tables)

            Base.metadata.create_all(engine)
        _initialized = True


def _check_configured() -> None:
    settings = get_settings()
    if settings.on_vercel and normalize_url(settings.database_url).startswith("sqlite"):
        raise ApiError(
            503,
            "database_not_configured",
            "The database is not configured for this deployment.",
            "Connect a Postgres database (e.g. Neon) to the Vercel project so DATABASE_URL is set.",
        )


def get_db() -> Iterator[Session]:
    _check_configured()
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
