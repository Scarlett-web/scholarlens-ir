"""Real SQLite/router acceptance for secondary credentials; no production or ES clients."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from backend.tests.account_fixture import PAPER, create_fixture_app


@pytest.fixture
def fixture(tmp_path):
    app, store = create_fixture_app(tmp_path)
    with TestClient(app) as api:
        yield api, store


def register(api, username="fixture_reader"):
    credentials = {"username": username, "password": "fixture-account-password"}
    assert api.post("/api/auth/register", json=credentials).status_code == 201
    return credentials


def login(api, credentials):
    response = api.post("/api/auth/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def save_note(api, headers):
    state = api.get("/api/me/workspace", headers=headers).json()
    payload = {"version": state["version"], "collections": ["全部收藏", "待读"],
               "favorites": [{"paper_id": PAPER["paper_id"], "collection": "待读", "note": "Private fixture note"}],
               "history": []}
    assert api.put("/api/me/workspace", json=payload, headers=headers).status_code == 200


@pytest.mark.parametrize("endpoint,payload", [
    ("password", {"current_password": "wrong-current-password", "new_password": "fixture-new-password"}),
    ("deactivate", {"username": "fixture_reader", "password": "wrong-current-password"}),
    ("deactivate", {"username": "different_reader", "password": "fixture-account-password"}),
])
def test_failed_secondary_credentials_preserve_all_sessions_and_workspace(fixture, endpoint, payload):
    api, store = fixture
    credentials = register(api)
    first, second = login(api, credentials), login(api, credentials)
    save_note(api, first)
    before = api.get("/api/me/workspace", headers=first).json()
    with store.connect() as db:
        stored_before = tuple(db.execute("SELECT password_hash,salt,disabled FROM users").fetchone())
    response = api.post("/api/auth/" + endpoint, json=payload, headers=first)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    for headers in (first, second):
        assert api.get("/api/auth/me", headers=headers).status_code == 200
        assert api.get("/api/me/workspace", headers=headers).json() == before
    with store.connect() as db:
        assert tuple(db.execute("SELECT password_hash,salt,disabled FROM users").fetchone()) == stored_before
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 2


@pytest.mark.parametrize("state", ["missing", "unknown", "expired", "revoked", "disabled"])
@pytest.mark.parametrize("endpoint", ["password", "deactivate"])
def test_real_authentication_failures_still_return_unauthenticated(fixture, state, endpoint):
    api, store = fixture
    credentials = register(api)
    headers = login(api, credentials)
    token_hash = hashlib.sha256(headers["Authorization"][7:].encode()).hexdigest()
    with store.connect() as db:
        if state == "expired":
            db.execute("UPDATE sessions SET expires_at=1 WHERE token_hash=?", (token_hash,))
        elif state == "revoked":
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        elif state == "disabled":
            db.execute("UPDATE users SET disabled=1")
    if state == "missing":
        headers = {}
    elif state == "unknown":
        headers = {"Authorization": "Bearer fixture-unknown-session"}
    payload = credentials if endpoint == "deactivate" else {
        "current_password": credentials["password"], "new_password": "fixture-new-password",
    }
    response = api.post("/api/auth/" + endpoint, json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_successful_password_change_revokes_all_sessions_and_preserves_private_data(fixture):
    api, _ = fixture
    credentials = register(api)
    first, second = login(api, credentials), login(api, credentials)
    other = login(api, register(api, "fixture_other"))
    save_note(api, first)
    before = api.get("/api/me/workspace", headers=first).json()
    response = api.post("/api/auth/password", headers=first, json={
        "current_password": credentials["password"], "new_password": "fixture-new-password",
    })
    assert response.status_code == 200
    for headers in (first, second):
        assert api.get("/api/me/workspace", headers=headers).status_code == 401
    assert api.post("/api/auth/login", json=credentials).status_code == 401
    new = login(api, {**credentials, "password": "fixture-new-password"})
    assert api.get("/api/me/workspace", headers=new).json() == before
    assert api.get("/api/me/workspace", headers=other).json()["favorites"] == []


def test_successful_deactivate_revokes_sessions_preserves_records_and_last_admin(fixture):
    api, store = fixture
    credentials = register(api)
    first, second = login(api, credentials), login(api, credentials)
    admin_credentials = register(api, "fixture_admin")
    admin = login(api, admin_credentials)
    save_note(api, first)
    with store.connect() as db:
        db.execute("UPDATE users SET role='admin' WHERE username=?", (admin_credentials["username"],))
    assert api.post("/api/auth/deactivate", headers=admin, json=admin_credentials).status_code == 409
    assert api.get("/api/auth/me", headers=admin).status_code == 200
    assert api.post("/api/auth/deactivate", headers=first, json=credentials).status_code == 200
    for headers in (first, second):
        assert api.get("/api/auth/me", headers=headers).status_code == 401
    assert api.post("/api/auth/login", json=credentials).status_code == 401
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM favorites").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1
    assert api.get("/api/me/workspace", headers=admin).json()["favorites"] == []
