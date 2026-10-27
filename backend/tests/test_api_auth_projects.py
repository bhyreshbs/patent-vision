from app.core.ratelimit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from tests.conftest import register


def test_password_hashing_is_salted_and_verifiable():
    a, b = hash_password("hunter2hunter2"), hash_password("hunter2hunter2")
    assert a != b and "hunter2" not in a
    assert verify_password("hunter2hunter2", a)
    assert not verify_password("wrong-password", a)
    assert not verify_password("x", "garbage")


def test_register_login_me_flow(client):
    r = client.post("/auth/register", json={"name": "Ada", "email": "Ada@Example.com", "password": "longenough1"})
    assert r.status_code == 201
    assert r.json()["user"]["email"] == "ada@example.com"
    assert "password" not in r.text

    r = client.post("/auth/login", json={"email": "ada@example.com", "password": "longenough1"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["name"] == "Ada"


def test_register_validation_and_duplicates(client):
    assert client.post("/auth/register", json={"name": "A", "email": "nope", "password": "longenough1"}).status_code == 422
    assert client.post("/auth/register", json={"name": "A", "email": "a@b.co", "password": "short"}).status_code == 422
    register(client, "dup@example.com")
    r = client.post("/auth/register", json={"name": "B", "email": "dup@example.com", "password": "longenough1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_invalid_credentials_rejected(client, auth):
    r = client.post("/auth/login", json={"email": "ada@example.com", "password": "wrong-password"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert r.status_code == 401


def test_unauthenticated_and_bad_tokens_rejected(client):
    for method, url in [("get", "/projects"), ("get", "/dashboard"), ("post", "/ai/process/1"), ("get", "/images/1")]:
        r = getattr(client, method)(url)
        assert r.status_code == 401, url
        assert r.json()["error"]["code"] == "unauthorized"
    r = client.get("/projects", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401
    ghost = create_access_token(9999)  # valid signature, nonexistent user
    assert client.get("/projects", headers={"Authorization": f"Bearer {ghost}"}).status_code == 401


def test_project_crud(client, auth):
    r = client.post("/projects", json={"name": "  Desk set ", "description": "d"}, headers=auth)
    assert r.status_code == 201
    p = r.json()
    assert p["name"] == "Desk set" and p["status"] == "active" and p["image_count"] == 0

    assert [x["id"] for x in client.get("/projects", headers=auth).json()] == [p["id"]]
    assert client.get(f"/projects/{p['id']}", headers=auth).json()["description"] == "d"

    r = client.put(f"/projects/{p['id']}", json={"name": "Renamed", "status": "archived"}, headers=auth)
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["status"] == "archived"
    assert r.json()["description"] == "d"  # untouched fields persist
    assert client.get(f"/projects/{p['id']}", headers=auth).json()["name"] == "Renamed"

    assert client.delete(f"/projects/{p['id']}", headers=auth).status_code == 204
    assert client.get(f"/projects/{p['id']}", headers=auth).status_code == 404
    assert client.get("/projects", headers=auth).json() == []


def test_project_validation(client, auth):
    assert client.post("/projects", json={"name": "   "}, headers=auth).status_code == 422
    assert client.post("/projects", json={}, headers=auth).status_code == 422
    r = client.post("/projects", json={"name": "x" * 500}, headers=auth)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert client.put("/projects/999", json={"name": "x"}, headers=auth).status_code == 404


def test_projects_are_private_to_their_owner(client, auth, other_auth, project):
    pid = project["id"]
    assert client.get("/projects", headers=other_auth).json() == []
    assert client.get(f"/projects/{pid}", headers=other_auth).status_code == 404
    assert client.put(f"/projects/{pid}", json={"name": "hax"}, headers=other_auth).status_code == 404
    assert client.delete(f"/projects/{pid}", headers=other_auth).status_code == 404
    assert client.get(f"/projects/{pid}/images", headers=other_auth).status_code == 404
    assert client.get(f"/projects/{pid}", headers=auth).json()["name"] == "Organizer"


def test_rate_limiting_returns_429(client, auth, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 2)
    limiter.reset()
    from tests.conftest import upload

    pid = client.post("/projects", json={"name": "p"}, headers=auth).json()["id"]
    codes = [upload(client, auth, pid, b"junk").status_code for _ in range(3)]
    assert codes[:2] == [422, 422] and codes[2] == 429


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
