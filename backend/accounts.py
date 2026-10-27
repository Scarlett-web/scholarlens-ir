"""SQLite users, revocable hashed sessions and user-isolated personal records."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from backend.api_models import Page


def problem(status: int, code: str, message: str):
    return HTTPException(status, detail={"code": code, "message": message, "details": {}})


def now():
    return datetime.now(timezone.utc).isoformat()


def password_hash(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=128, repr=False)


class PublicUser(BaseModel):
    id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    user: PublicUser
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class HistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(min_length=1, max_length=500)
    field: str = Field(
        default="all", pattern="^(all|title|authors|date|affiliation|address|fulltext)$"
    )
    mode: str = Field(default="keyword", pattern="^(keyword|semantic|hybrid)$")


class FavoriteState(BaseModel):
    paper_id: str
    is_favorite: bool


class FavoriteItem(BaseModel):
    paper_id: str
    created_at: str
    title: str
    authors: list[str]
    year: int | None
    available: bool


class HistoryRecord(HistoryInput):
    id: int
    created_at: str


class LogoutResponse(BaseModel):
    logged_out: bool


class DeleteResponse(BaseModel):
    deleted: bool


class ClearResponse(BaseModel):
    cleared: bool


class Store:
    def __init__(self, runtime: str):
        self.root = Path(runtime)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "scholarlens.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
                    failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL REFERENCES users(id), paper_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id,paper_id));
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    q TEXT NOT NULL, field TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS history_user ON history(user_id,id);
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    original_name TEXT NOT NULL, stored_name TEXT NOT NULL, sha256 TEXT NOT NULL,
                    size INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    paper_id TEXT, attempts INTEGER NOT NULL DEFAULT 0, generation TEXT,
                    UNIQUE(user_id,sha256));
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY, upload_id TEXT NOT NULL REFERENCES uploads(id),
                    admin_id INTEGER NOT NULL REFERENCES users(id), decision TEXT NOT NULL,
                    reason TEXT NOT NULL, created_at TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def public_user(self, row):
        return {key: row[key] for key in ("id", "username", "role")}

    def authenticate(self, authorization: str | None):
        if not authorization or not authorization.startswith("Bearer "):
            raise problem(401, "unauthenticated", "请先登录")
        token = authorization[7:]
        if not 20 <= len(token) <= 128:
            raise problem(401, "unauthenticated", "登录状态无效")
        with self.connect() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        if row is None:
            raise problem(401, "unauthenticated", "登录已过期或已退出")
        return self.public_user(row)

    def current(self, authorization: str | None = Header(default=None)):
        return self.authenticate(authorization)


def router(store: Store, read_paper):
    api = APIRouter(prefix="/api")

    @api.post("/auth/register", response_model=PublicUser, status_code=201)
    def register(body: Credentials):
        salt = secrets.token_hex(16)
        hashed = password_hash(body.password, salt)
        try:
            with store.connect() as db:
                result = db.execute(
                    "INSERT INTO users(username,salt,password_hash,created_at) VALUES(?,?,?,?)",
                    (body.username, salt, hashed, now()),
                )
                return {"id": result.lastrowid, "username": body.username, "role": "user"}
        except sqlite3.IntegrityError:
            raise problem(409, "duplicate_record", "账号已存在")

    @api.post("/auth/login", response_model=LoginResponse)
    def login(body: Credentials):
        with store.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
            if row is not None and row["locked_until"] > time.time():
                raise problem(429, "rate_limited", "登录尝试过多，请稍后重试")
            valid = hmac.compare_digest(
                password_hash(body.password, row["salt"] if row else "00" * 16),
                row["password_hash"] if row else "00" * 64,
            )
            if row is None or not valid:
                if row:
                    failures = row["failures"] + 1
                    db.execute(
                        "UPDATE users SET failures=?, locked_until=? WHERE id=?",
                        (failures, time.time() + 300 if failures >= 5 else 0, row["id"]),
                    )
                # Commit failed-attempt counters before raising the HTTP error.
                db.commit()
                raise problem(401, "unauthenticated", "账号或密码错误")
            db.execute("UPDATE users SET failures=0,locked_until=0 WHERE id=?", (row["id"],))
            token = secrets.token_urlsafe(32)
            expiry = 7 * 24 * 3600
            db.execute("DELETE FROM sessions WHERE expires_at<?", (time.time(),))
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), row["id"], time.time() + expiry),
            )
            return {"user": store.public_user(row), "access_token": token, "expires_in": expiry}

    @api.post("/auth/logout", response_model=LogoutResponse)
    def logout(user=Depends(store.current), authorization: str = Header()):
        with store.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE token_hash=? AND user_id=?",
                (hashlib.sha256(authorization[7:].encode()).hexdigest(), user["id"]),
            )
        return {"logged_out": True}

    @api.get("/auth/me", response_model=PublicUser)
    def me(user=Depends(store.current)):
        return user

    @api.get("/me/favorites", response_model=Page[FavoriteItem])
    def favorites(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM favorites WHERE user_id=?", (user["id"],)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT paper_id,created_at FROM favorites WHERE user_id=? ORDER BY created_at DESC,paper_id LIMIT ? OFFSET ?",
                (user["id"], page_size, (page - 1) * page_size),
            ).fetchall()
        results = []
        for row in rows:
            try:
                doc, _ = read_paper(row["paper_id"])
                results.append(
                    {
                        **dict(row),
                        "title": doc.get("title", ""),
                        "authors": doc.get("authors", []),
                        "year": doc.get("year"),
                        "available": True,
                    }
                )
            except HTTPException as e:
                if e.status_code != 404:
                    raise
                results.append(
                    {**dict(row), "title": "", "authors": [], "year": None, "available": False}
                )
        return {"total": total, "page": page, "page_size": page_size, "results": results}

    @api.get("/me/favorites/{paper_id}", response_model=FavoriteState)
    def is_favorite(paper_id: str, user=Depends(store.current)):
        with store.connect() as db:
            exists = db.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND paper_id=?", (user["id"], paper_id)
            ).fetchone()
        return {"paper_id": paper_id, "is_favorite": bool(exists)}

    @api.put("/me/favorites/{paper_id}", response_model=FavoriteState)
    def favorite(paper_id: str, user=Depends(store.current)):
        read_paper(paper_id)
        with store.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO favorites VALUES(?,?,?)", (user["id"], paper_id, now())
            )
        return {"paper_id": paper_id, "is_favorite": True}

    @api.delete("/me/favorites/{paper_id}", response_model=FavoriteState)
    def unfavorite(paper_id: str, user=Depends(store.current)):
        with store.connect() as db:
            db.execute(
                "DELETE FROM favorites WHERE user_id=? AND paper_id=?", (user["id"], paper_id)
            )
        return {"paper_id": paper_id, "is_favorite": False}

    @api.post("/me/history", status_code=201, response_model=HistoryRecord)
    def add_history(body: HistoryInput, user=Depends(store.current)):
        if not body.q.strip():
            raise problem(400, "invalid_parameter", "查询不能为空")
        stamp = now()
        with store.connect() as db:
            result = db.execute(
                "INSERT INTO history(user_id,q,field,mode,created_at) VALUES(?,?,?,?,?)",
                (user["id"], body.q.strip(), body.field, body.mode, stamp),
            )
            db.execute(
                "DELETE FROM history WHERE user_id=? AND id NOT IN (SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT 200)",
                (user["id"], user["id"]),
            )
            return {"id": result.lastrowid, **body.model_dump(), "created_at": stamp}

    @api.get("/me/history", response_model=Page[HistoryRecord])
    def history(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM history WHERE user_id=?", (user["id"],)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT id,q,field,mode,created_at FROM history WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (user["id"], page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [dict(row) for row in rows],
        }

    @api.delete("/me/history/{history_id}", response_model=DeleteResponse)
    def delete_history(history_id: int, user=Depends(store.current)):
        with store.connect() as db:
            result = db.execute(
                "DELETE FROM history WHERE user_id=? AND id=?", (user["id"], history_id)
            )
        if not result.rowcount:
            raise problem(404, "not_found", "记录不存在")
        return {"deleted": True}

    @api.delete("/me/history", response_model=ClearResponse)
    def clear_history(user=Depends(store.current)):
        with store.connect() as db:
            db.execute("DELETE FROM history WHERE user_id=?", (user["id"],))
        return {"cleared": True}

    return api


if __name__ == "__main__":
    from backend.config import Settings

    parser = argparse.ArgumentParser(
        description="Local operator only: grant administrator role to an existing user"
    )
    parser.add_argument("--promote", required=True)
    args = parser.parse_args()
    store = Store(Settings.from_env().runtime_dir)
    with store.connect() as db:
        result = db.execute("UPDATE users SET role='admin' WHERE username=?", (args.promote,))
        if result.rowcount != 1:
            raise SystemExit("existing account required")
    print(json.dumps({"promoted": args.promote}))
