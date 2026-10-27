"""Serverless/Vercel behaviour: /api prefix, Blob storage backend, Postgres URLs, configuration errors."""
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import normalize_url
from app.main import create_app
from tests import synthetic
from tests.conftest import upload


def test_routes_answer_with_and_without_api_prefix(client, auth):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}
    pid = client.post("/api/projects", json={"name": "Prefixed"}, headers=auth).json()["id"]
    assert client.get(f"/projects/{pid}", headers=auth).json()["name"] == "Prefixed"
    assert client.get("/api/docs").status_code == 200
    assert client.get("/apiary").status_code == 404  # only a real /api segment is a prefix


def test_meta_exposes_upload_limits(client):
    meta = client.get("/api/meta").json()
    assert meta["max_upload_bytes"] == get_settings().max_upload_bytes <= 4.5 * 1024 * 1024
    assert "image/png" in meta["accepted_types"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("postgres://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("sqlite:///./x.db", "sqlite:///./x.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert normalize_url(raw) == expected


def test_database_url_falls_back_to_integration_variable(monkeypatch):
    from app.core.config import Settings

    monkeypatch.delenv("PV_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://neon/db")
    assert Settings().database_url == "postgres://neon/db"


def test_unconfigured_database_on_vercel_is_a_clear_503(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    r = client.post("/auth/login", json={"email": "a@b.co", "password": "whatever123"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_not_configured"


class FakeBlobStore:
    """In-memory stand-in for the vercel.blob.sync API (private store)."""

    def __init__(self):
        self.files: dict[str, tuple[bytes, str]] = {}

    def put_blob(self, pathname, body, *, access, content_type=None, allow_overwrite=False, **_):
        assert access == "private"
        assert allow_overwrite or pathname not in self.files
        self.files[pathname] = (bytes(body), content_type)

    def get_blob(self, pathname, *, access):
        from types import SimpleNamespace

        from vercel.blob import BlobNotFoundError

        assert access == "private"
        if pathname not in self.files:
            raise BlobNotFoundError()
        return SimpleNamespace(body=self.files[pathname][0])

    def head_blob(self, pathname):
        from vercel.blob import BlobNotFoundError

        if pathname not in self.files:
            raise BlobNotFoundError()
        return object()

    def delete_blob(self, names):
        for n in [names] if isinstance(names, str) else names:
            self.files.pop(n, None)

    def query_blobs(self, *, prefix=None, **_):
        from types import SimpleNamespace

        return [SimpleNamespace(pathname=p) for p in list(self.files) if p.startswith(prefix or "")]


@pytest.fixture
def blob(monkeypatch):
    import vercel.blob.sync as sync

    fake = FakeBlobStore()
    for name in ("put_blob", "get_blob", "head_blob", "delete_blob", "query_blobs"):
        monkeypatch.setattr(sync, name, getattr(fake, name))
    monkeypatch.setattr(get_settings(), "storage_backend", "blob")
    return fake


def test_full_flow_on_private_blob_storage(client, auth, project, organizer_photo, blob):
    assert client.get("/api/meta").json()["storage"] == "blob"
    iid = upload(client, auth, project["id"], organizer_photo[2]).json()["id"]
    uploads = [p for p in blob.files if p.startswith(f"uploads/{project['id']}/")]
    assert len(uploads) == 1 and blob.files[uploads[0]] == (organizer_photo[2], "image/png")

    r = client.post(f"/api/ai/process/{iid}", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "Completed"
    generated = sorted(p.rsplit("/", 1)[1] for p in blob.files if p.startswith(f"generated/{project['id']}/{iid}/"))
    assert generated == ["background_removed.png", "drawing.png", "drawing.svg", "mask.png", "outline.png"]
    assert blob.files[f"generated/{project['id']}/{iid}/drawing.svg"][1] == "image/svg+xml"

    res = client.get(f"/api/images/{iid}", headers=auth).json()["result"]
    d = client.get("/api" + res["urls"]["drawing"], headers=auth)
    assert d.status_code == 200 and d.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert d.headers["cache-control"] == "private, no-store"

    assert client.delete(f"/api/projects/{project['id']}", headers=auth).status_code == 204
    assert blob.files == {}  # uploads and generated outputs removed with the project


def test_missing_blob_is_reported_not_crashed(client, auth, project, organizer_photo, blob):
    image = upload(client, auth, project["id"], organizer_photo[2]).json()
    blob.files.clear()
    r = client.get(image["original_url"], headers=auth)
    assert r.status_code == 404 and r.json()["error"]["code"] == "file_missing"
    client.post(f"/ai/process/{image['id']}", headers=auth)
    res = client.get(f"/images/{image['id']}", headers=auth).json()["result"]
    assert res["status"] == "Failed" and res["failed_stage"] == "load"


def test_vercel_request_headers_reach_sync_routes():
    """Blob OIDC credentials are read from request headers inside threadpool-run sync handlers."""
    from vercel.headers import get_headers

    app = create_app()

    @app.get("/whoami")
    def whoami():
        return {"token": (get_headers() or {}).get("x-vercel-oidc-token")}

    c = TestClient(app)
    assert c.get("/api/whoami", headers={"x-vercel-oidc-token": "tok-123"}).json() == {"token": "tok-123"}
    assert c.get("/whoami").json() == {"token": None}
