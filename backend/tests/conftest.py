import os
import shutil
import tempfile
from pathlib import Path

# Configure the app BEFORE importing it: tests use a throw-away database and storage root.
_TMP = Path(tempfile.mkdtemp(prefix="pv-tests-"))
os.environ["PV_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["PV_STORAGE_ROOT"] = str(_TMP / "storage")
os.environ["PV_SECRET_KEY"] = "test-secret-key"
os.environ["PV_RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["PV_AUTO_CREATE_TABLES"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import database  # noqa: E402
from app.core.ratelimit import limiter  # noqa: E402
from app.core.storage import storage  # noqa: E402
from app.main import app  # noqa: E402
from tests import synthetic  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_state():
    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    shutil.rmtree(storage.root, ignore_errors=True)
    storage.root.mkdir(parents=True, exist_ok=True)
    limiter.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def register(client: TestClient, email: str = "ada@example.com", password: str = "s3cret-pass") -> dict:
    r = client.post("/auth/register", json={"name": "Ada", "email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


@pytest.fixture
def other_auth(client):
    return register(client, "grace@example.com")


@pytest.fixture
def project(client, auth):
    r = client.post("/projects", json={"name": "Organizer", "description": "desk"}, headers=auth)
    assert r.status_code == 201
    return r.json()


@pytest.fixture(scope="session")
def organizer_photo():
    img, truth = synthetic.organizer()
    return img, truth, synthetic.encode(img, ".png")


def upload(client, auth, project_id, data: bytes, name="photo.png", mime="image/png", view="Front"):
    return client.post(
        f"/projects/{project_id}/images",
        files={"file": (name, data, mime)},
        data={"view_type": view},
        headers=auth,
    )
