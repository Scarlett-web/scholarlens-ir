"""Real SQLite/account routes: authorization and last-admin concurrency, no external services."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

from fastapi.testclient import TestClient
import pytest

from backend.tests.account_fixture import create_fixture_app


@pytest.fixture
def accounts(tmp_path):
    app, store = create_fixture_app(tmp_path)
    with TestClient(app) as api:
        users = []
        for name in ("fixture_admin_a", "fixture_admin_b", "fixture_regular"):
            credentials = {"username": name, "password": "isolated-admin-password"}
            response = api.post("/api/auth/register", json=credentials)
            assert response.status_code == 201
            logged_in = api.post("/api/auth/login", json=credentials)
            assert logged_in.status_code == 200
            users.append({"id": response.json()["id"], "credentials": credentials,
                          "headers": {"Authorization": "Bearer " + logged_in.json()["access_token"]}})
        with store.connect() as db:
            db.execute("UPDATE users SET role='admin' WHERE id IN (?,?)", (users[0]["id"], users[1]["id"]))
        yield api, store, users


@pytest.mark.parametrize("operation", ["list", "detail", "update"])
@pytest.mark.parametrize("actor,status", [(None, 401), (2, 403), (0, 200)])
def test_admin_user_routes_require_real_role(accounts, operation, actor, status):
    api, _, users = accounts
    headers = {} if actor is None else users[actor]["headers"]
    path = "/api/admin/users" + ("" if operation == "list" else "/" + str(users[2]["id"]))
    response = api.patch(path, headers=headers, json={"role": "user"}) if operation == "update" else api.get(path, headers=headers)
    assert response.status_code == status, response.text
    if status == 200:
        assert "password_hash" not in response.text and "salt" not in response.text


def test_sequential_admin_protection_and_live_role_recheck(accounts):
    api, store, users = accounts
    first, second, regular = users
    assert api.patch(f'/api/admin/users/{first["id"]}', headers=first["headers"], json={"disabled": True}).status_code == 400
    assert api.patch(f'/api/admin/users/{second["id"]}', headers=first["headers"], json={"role": "user"}).status_code == 200
    assert api.get("/api/admin/users", headers=second["headers"]).status_code == 403
    assert api.patch(f'/api/admin/users/{first["id"]}', headers=first["headers"], json={"role": "user"}).status_code == 409
    assert api.post("/api/auth/deactivate", headers=first["headers"], json=first["credentials"]).status_code == 409
    assert api.patch("/api/admin/users/99999", headers=first["headers"], json={"role": "user"}).status_code == 404
    assert api.patch(f'/api/admin/users/{regular["id"]}', headers=first["headers"], json={"role": None}).status_code == 400
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0] == 1
    assert api.get("/api/auth/me", headers=first["headers"]).status_code == 200


def test_disabled_admin_demotion_does_not_reduce_active_admin_count(accounts):
    api, store, users = accounts
    first, second, _ = users
    with store.connect() as db:
        db.execute("UPDATE users SET disabled=1 WHERE id=?", (second["id"],))
    response = api.patch(f'/api/admin/users/{second["id"]}', headers=first["headers"], json={"role": "user"})
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "user" and response.json()["disabled"] is True
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0] == 1


def behind_writer(monkeypatch, store, request, mutate):
    """Let authentication finish, then change roles before the real write lock is granted."""
    original = store.connect
    waiting = threading.Event()

    class Connection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            if sql == "BEGIN IMMEDIATE":
                waiting.set()
            return self.db.execute(sql, *args)

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def connected():
        with original() as db:
            yield Connection(db)

    monkeypatch.setattr(store, "connect", connected)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original() as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            future = pool.submit(request)
            try:
                assert waiting.wait(5), "Request did not reach its write transaction"
                mutate(blocker)
            finally:
                blocker.commit()
        return future.result(timeout=5)


def test_admin_losing_role_while_waiting_cannot_change_another_user(accounts, monkeypatch):
    api, store, users = accounts
    first, _, regular = users
    response = behind_writer(monkeypatch, store,
        lambda: api.patch(f'/api/admin/users/{regular["id"]}', headers=first["headers"], json={"role": "admin"}),
        lambda db: db.execute("UPDATE users SET role='user' WHERE id=?", (first["id"],)))
    assert response.status_code == 403
    with store.connect() as db:
        assert db.execute("SELECT role FROM users WHERE id=?", (regular["id"],)).fetchone()[0] == "user"


def test_deactivate_checks_latest_role_after_waiting_for_writer(accounts, monkeypatch):
    api, store, users = accounts
    regular = users[2]

    def promote_only_admin(db):
        db.execute("UPDATE users SET role='user'")
        db.execute("UPDATE users SET role='admin' WHERE id=?", (regular["id"],))

    response = behind_writer(monkeypatch, store,
        lambda: api.post("/api/auth/deactivate", headers=regular["headers"], json=regular["credentials"]),
        promote_only_admin)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"
    assert api.get("/api/auth/me", headers=regular["headers"]).status_code == 200
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0] == 1


def coordinate_admin_counts(monkeypatch, store):
    """Expose the old check/write race; a writer transaction makes the reads serialize.

    Only pause AFTER the actual SQLite count is read. On a serialized implementation
    the first reader times out its bounded scheduling gate; the second then reads
    the committed count. No authorization/query/write result is fabricated.
    """
    original = store.connect
    gate = threading.Barrier(2, timeout=0.75)

    class CountCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            row = self.cursor.fetchone()
            try:
                gate.wait()
            except threading.BrokenBarrierError:
                pass
            return row

    class Connection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            cursor = self.db.execute(sql, *args)
            if sql == "SELECT count(*) FROM users WHERE role='admin' AND disabled=0":
                return CountCursor(cursor)
            return cursor

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def connected():
        with original() as db:
            yield Connection(db)

    monkeypatch.setattr(store, "connect", connected)


@pytest.mark.parametrize("operations", [("demote", "demote"), ("deactivate", "deactivate"), ("demote", "deactivate")])
def test_concurrent_requests_cannot_remove_all_active_admins(accounts, monkeypatch, operations):
    api, store, users = accounts
    coordinate_admin_counts(monkeypatch, store)
    start = threading.Barrier(2, timeout=5)

    def change(index):
        user = users[index]
        start.wait()
        if operations[index] == "deactivate":
            return api.post("/api/auth/deactivate", headers=user["headers"], json=user["credentials"])
        return api.patch(f'/api/admin/users/{user["id"]}', headers=user["headers"], json={"role": "user"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(change, range(2)))
    statuses = [response.status_code for response in responses]
    with store.connect() as db:
        remaining = db.execute("SELECT count(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
    assert remaining == 1, {"statuses": statuses, "remaining_admins": remaining}
    assert sorted(statuses) == [200, 409]
    for i, response in enumerate(responses):
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "invalid_state"
        expected = 401 if response.status_code == 200 and operations[i] == "deactivate" else 200
        assert api.get("/api/auth/me", headers=users[i]["headers"]).status_code == expected
