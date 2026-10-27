import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, auth, dashboard, images, projects
from app.core import database
from app.core.config import get_settings
from app.core.errors import install_error_handlers

log = logging.getLogger("patentvision")


class PlatformMiddleware:
    """Pure ASGI middleware for serverless hosting.

    - Requests arriving as /api/... (Vercel routes that prefix to this service) get root_path=/api, so the
      same routes answer at /projects locally and at /api/projects in production.
    - The Vercel request headers (including the short-lived OIDC token used for Blob credentials) are
      exposed to the Vercel SDK for the duration of the request.
    """

    def __init__(self, app, prefix: str) -> None:
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope.get("path", "")
            if self.prefix and (path == self.prefix or path.startswith(self.prefix + "/")):
                scope = {**scope, "root_path": self.prefix}
            if scope["type"] == "http":
                from vercel.headers import headers_from_asgi_scope, set_headers

                set_headers(headers_from_asgi_scope(scope))
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if not settings.use_blob and not settings.on_vercel:
        settings.storage_root.mkdir(parents=True, exist_ok=True)
    try:
        database.init_db()
    except Exception:  # surfaced per request instead (e.g. database_not_configured)
        log.exception("database initialisation failed at startup")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PatentVision AI",
        version="1.1.0",
        description="Turns product photographs into clean black-and-white patent-style outline drawings.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    app.add_middleware(PlatformMiddleware, prefix=settings.api_prefix)
    install_error_handlers(app)
    for router in (auth.router, projects.router, images.router, ai.router, dashboard.router):
        app.include_router(router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
