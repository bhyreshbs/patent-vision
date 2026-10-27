import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, auth, dashboard, images, projects
from app.core import database
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.models import Base
from app.services.processing import recover_interrupted

log = logging.getLogger("patentvision")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        Base.metadata.create_all(database.engine)
    interrupted = recover_interrupted()
    if interrupted:
        log.warning("marked %d interrupted job(s) as Failed", interrupted)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="PatentVision AI",
        version="1.0.0",
        description="Turns product photographs into clean black-and-white patent-style outline drawings.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    install_error_handlers(app)
    for router in (auth.router, projects.router, images.router, ai.router, dashboard.router):
        app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
