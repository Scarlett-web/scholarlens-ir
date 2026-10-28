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
import re
from io import BytesIO
from backend.db_migrations import backup_before_upgrade, VERSION

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
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


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(
        default=None, min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$"
    )
    display_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str = Field(min_length=10, max_length=128, repr=False)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)


class PasswordResetVerify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=12)
    new_password: str = Field(min_length=10, max_length=128, repr=False)


class PublicUser(BaseModel):
    id: int
    username: str
    role: str


class AdminUserSummary(PublicUser):
    display_name: str
    email: str | None
    disabled: bool
    created_at: str
    updated_at: str


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool | None = None
    role: str | None = Field(default=None, pattern="^(user|admin)$")


class ProfileResponse(PublicUser):
    display_name: str
    email: str | None
    avatar_available: bool
    created_at: str
    updated_at: str
    email_verified: bool = False


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


class Folder(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str
    paper_count: int = 0


class FolderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def clean_name(cls, v):
        if not v.strip():
            raise ValueError("folder name cannot be blank")
        return v.strip()


class FolderPaperInput(BaseModel):
    paper_id: str = Field(min_length=1, max_length=512)


class BrowsingRecord(BaseModel):
    id: int
    paper_id: str
    accessed_at: str
    title: str = ""


class Notification(BaseModel):
    id: int
    kind: str
    message: str
    read: bool
    created_at: str


class StatusResponse(BaseModel):
    status: str
    message: str


class Store:
    def __init__(self, runtime: str):
        self.root = Path(runtime)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "scholarlens.sqlite3"
        backup_before_upgrade(self.path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
                INSERT INTO schema_version(version) SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
                    failures INTEGER NOT NULL DEFAULT 0, locked_until REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '', email TEXT,
                    avatar_name TEXT, updated_at TEXT NOT NULL DEFAULT '');
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
                CREATE TABLE IF NOT EXISTS favorite_folders (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(user_id,name));
                CREATE TABLE IF NOT EXISTS favorite_folder_items (
                    folder_id INTEGER NOT NULL REFERENCES favorite_folders(id) ON DELETE CASCADE,
                    paper_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(folder_id,paper_id));
                CREATE TABLE IF NOT EXISTS browsing_history (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    paper_id TEXT NOT NULL, accessed_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS browsing_user_time ON browsing_history(user_id,accessed_at);
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, message TEXT NOT NULL, read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    code_hash TEXT NOT NULL, expires_at REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, citations_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS conversation_user_time ON conversations(user_id,updated_at);
            """)
            self._migrate(db)

    def _migrate(self, db):
        """Idempotent additive migrations; never remove user data or columns."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
        additions = {
            "display_name": "TEXT NOT NULL DEFAULT ''",
            "email": "TEXT",
            "avatar_name": "TEXT",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
            "disabled": "INTEGER NOT NULL DEFAULT 0",
            "email_verified": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        db.execute(
            "UPDATE users SET updated_at=created_at WHERE updated_at='' OR updated_at IS NULL"
        )
        reset_columns = {row[1] for row in db.execute("PRAGMA table_info(password_reset_tokens)")}
        if "attempts" not in reset_columns:
            db.execute(
                "ALTER TABLE password_reset_tokens ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "archived" not in {r[1] for r in db.execute("PRAGMA table_info(uploads)")}:
            db.execute("ALTER TABLE uploads ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE schema_version SET version=MAX(version,?)", (VERSION,))

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

    def profile(self, row):
        return {
            **self.public_user(row),
            "display_name": row["display_name"] or "",
            "email": row["email"],
            "avatar_available": bool(row["avatar_name"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "email_verified": bool(row["email_verified"]),
        }

    def authenticate(self, authorization: str | None):
        if not authorization or not authorization.startswith("Bearer "):
            raise problem(401, "unauthenticated", "请先登录")
        token = authorization[7:]
        if not 20 <= len(token) <= 128:
            raise problem(401, "unauthenticated", "登录状态无效")
        with self.connect() as db:
            row = db.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.disabled=0",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        if row is None:
            raise problem(401, "unauthenticated", "登录已过期或已退出")
        return self.public_user(row)

    def current(self, authorization: str | None = Header(default=None)):
        return self.authenticate(authorization)


def router(store: Store, read_paper):
    api = APIRouter(prefix="/api")

    def full_user(user):
        with store.connect() as db:
            row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        if row is None:
            raise problem(401, "unauthenticated", "用户不存在")
        return row

    def add_notification(user_id: int, kind: str, message: str):
        with store.connect() as db:
            db.execute(
                "INSERT INTO notifications(user_id,kind,message,created_at) VALUES(?,?,?,?)",
                (user_id, kind, message, now()),
            )

    def admin_user(user=Depends(store.current)):
        with store.connect() as db:
            row = db.execute("SELECT role,disabled FROM users WHERE id=?", (user["id"],)).fetchone()
        if row is None or row["role"] != "admin" or row["disabled"]:
            raise problem(403, "forbidden", "需要管理员权限")
        return user

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
            if row is None or not valid or row["disabled"]:
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

    @api.get("/me/profile", response_model=ProfileResponse)
    def profile(user=Depends(store.current)):
        return store.profile(full_user(user))

    @api.get("/admin/users", response_model=Page[AdminUserSummary])
    def admin_users(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(admin_user),
    ):
        with store.connect() as db:
            total = db.execute("SELECT count(*) FROM users").fetchone()[0]
            rows = db.execute(
                "SELECT id,username,role,display_name,email,disabled,created_at,updated_at FROM users ORDER BY id LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [{**dict(row), "disabled": bool(row["disabled"])} for row in rows],
        }

    @api.get("/admin/users/{user_id}", response_model=AdminUserSummary)
    def admin_user_detail(user_id: int, user=Depends(admin_user)):
        with store.connect() as db:
            row = db.execute(
                "SELECT id,username,role,display_name,email,disabled,created_at,updated_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        if row is None:
            raise problem(404, "not_found", "用户不存在")
        return {**dict(row), "disabled": bool(row["disabled"])}

    @api.patch("/admin/users/{user_id}", response_model=AdminUserSummary)
    def admin_user_update(user_id: int, body: AdminUserUpdate, user=Depends(admin_user)):
        values = body.model_dump(exclude_unset=True)
        if user_id == user["id"] and values.get("disabled") is True:
            raise problem(400, "invalid_parameter", "不能禁用当前管理员账号")
        if any(v is None for v in values.values()):
            raise problem(400, "invalid_parameter", "管理字段不接受null")
        if not values:
            return admin_user_detail(user_id, user)
        assignments = ",".join(f"{k}=?" for k in values)
        params = list(values.values()) + [now(), user_id]
        with store.connect() as db:
            # Serialize the invariant check with the write, including other admin removals.
            db.execute("BEGIN IMMEDIATE")
            actor = db.execute("SELECT role,disabled FROM users WHERE id=?", (user["id"],)).fetchone()
            if actor is None or actor["role"] != "admin" or actor["disabled"]:
                raise problem(403, "forbidden", "需要管理员权限")
            target = db.execute("SELECT role,disabled FROM users WHERE id=?", (user_id,)).fetchone()
            if (
                target
                and target["role"] == "admin"
                and not target["disabled"]
                and (values.get("role") == "user" or values.get("disabled"))
            ):
                admins = db.execute(
                    "SELECT count(*) FROM users WHERE role='admin' AND disabled=0"
                ).fetchone()[0]
                if admins <= 1:
                    raise problem(409, "invalid_state", "至少保留一名有效管理员")
            changed = db.execute(f"UPDATE users SET {assignments},updated_at=? WHERE id=?", params)
            if not changed.rowcount:
                raise problem(404, "not_found", "用户不存在")
            row = db.execute(
                "SELECT id,username,role,display_name,email,disabled,created_at,updated_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
        return {**dict(row), "disabled": bool(row["disabled"])}

    @api.patch("/me/profile", response_model=ProfileResponse)
    def update_profile(body: ProfileUpdate, user=Depends(store.current)):
        values = body.model_dump(exclude_unset=True)
        if any(k in values and values[k] is None for k in ("username", "display_name")):
            raise problem(400, "invalid_parameter", "用户名及显示名称不接受null")
        if "username" in values and values["username"] is not None:
            values["username"] = values["username"].strip()
            if not values["username"]:
                raise problem(400, "invalid_parameter", "用户名不能为空")
        if "email" in values and values["email"]:
            values["email"] = values["email"].strip().lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", values["email"]):
                raise problem(400, "invalid_parameter", "邮箱格式无效")
        if not values:
            return store.profile(full_user(user))
        if "email" in values:
            values["email_verified"] = 0
        assignments = ",".join(f"{key}=?" for key in values)
        params = list(values.values()) + [now(), user["id"]]
        try:
            with store.connect() as db:
                db.execute(f"UPDATE users SET {assignments},updated_at=? WHERE id=?", params)
                row = db.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise problem(409, "duplicate_record", "用户名已存在") from exc
        return store.profile(row)

    @api.post("/me/avatar", response_model=ProfileResponse)
    def avatar(file: UploadFile = File(...), user=Depends(store.current)):
        name = Path(file.filename or "avatar").name
        if len(name) > 120 or any(ord(c) < 32 for c in name):
            raise problem(400, "invalid_file", "头像文件名无效")
        data = file.file.read(2 * 1024 * 1024 + 1)
        signatures = (
            (".png", b"\x89PNG\r\n\x1a\n"),
            (".jpg", b"\xff\xd8\xff"),
            (".jpeg", b"\xff\xd8\xff"),
        )
        if len(data) > 2 * 1024 * 1024 or not any(
            name.lower().endswith(ext) and data.startswith(sig) for ext, sig in signatures
        ):
            raise problem(400, "invalid_file", "只接收不超过2MiB的PNG或JPEG头像")
        avatar_dir = store.root / "avatars"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        stored = f"{user['id']}-{secrets.token_hex(12)}.png"
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG") or image.width * image.height > 4_000_000:
                    raise ValueError("image limits")
                image.load()
                # Re-encode pixels only: discard scripts, comments, EXIF and appended payloads.
                image.convert("RGB").save(avatar_dir / stored, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise problem(400, "invalid_file", "头像不是有效PNG/JPEG或像素超限") from exc
        with store.connect() as db:
            old = db.execute("SELECT avatar_name FROM users WHERE id=?", (user["id"],)).fetchone()[
                0
            ]
            db.execute(
                "UPDATE users SET avatar_name=?,updated_at=? WHERE id=?",
                (stored, now(), user["id"]),
            )
        if old:
            (avatar_dir / old).unlink(missing_ok=True)
        return store.profile(full_user(user))

    @api.get("/me/avatar")
    def get_avatar(user=Depends(store.current)):
        name = full_user(user)["avatar_name"]
        path = store.root / "avatars" / (name or "missing")
        if (
            not name
            or not path.is_file()
            or path.parent.resolve() != (store.root / "avatars").resolve()
        ):
            raise problem(404, "not_found", "头像不存在")
        return FileResponse(
            path,
            media_type="image/png",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    @api.post("/auth/password", response_model=StatusResponse)
    def change_password(body: PasswordChange, user=Depends(store.current)):
        row = full_user(user)
        if not hmac.compare_digest(
            password_hash(body.current_password, row["salt"]), row["password_hash"]
        ):
            raise problem(401, "invalid_credentials", "当前密码错误")
        if body.current_password == body.new_password:
            raise problem(400, "invalid_parameter", "新密码必须不同")
        salt = secrets.token_hex(16)
        with store.connect() as db:
            db.execute(
                "UPDATE users SET salt=?,password_hash=?,updated_at=? WHERE id=?",
                (salt, password_hash(body.new_password, salt), now(), user["id"]),
            )
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        return {"status": "password_changed", "message": "密码已修改，请重新登录"}

    @api.post("/auth/deactivate", response_model=StatusResponse)
    def deactivate(body: Credentials, user=Depends(store.current)):
        row = full_user(user)
        if body.username.casefold() != row["username"].casefold() or not hmac.compare_digest(
            password_hash(body.password, row["salt"]), row["password_hash"]
        ):
            raise problem(401, "invalid_credentials", "请确认当前用户名和密码")
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT role,disabled FROM users WHERE id=?", (user["id"],)).fetchone()
            if current is None or current["disabled"]:
                raise problem(401, "unauthenticated", "登录已过期或已退出")
            if (
                current["role"] == "admin"
                and db.execute(
                    "SELECT count(*) FROM users WHERE role='admin' AND disabled=0"
                ).fetchone()[0]
                <= 1
            ):
                raise problem(409, "invalid_state", "最后一名管理员不能停用自己的账号")
            db.execute("UPDATE users SET disabled=1,updated_at=? WHERE id=?", (now(), user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        return {"status": "deactivated", "message": "账号已停用，原数据保留；需要恢复时联系管理员"}

    @api.get("/me/notifications", response_model=Page[Notification])
    def notifications(
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM notifications WHERE user_id=?", (user["id"],)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT id,kind,message,read,created_at FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                (user["id"], page_size, (page - 1) * page_size),
            ).fetchall()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": [{**dict(r), "read": bool(r["read"])} for r in rows],
        }

    @api.post("/me/notifications/{notification_id}/read", response_model=StatusResponse)
    def mark_notification(notification_id: int, user=Depends(store.current)):
        with store.connect() as db:
            changed = db.execute(
                "UPDATE notifications SET read=1 WHERE id=? AND user_id=?",
                (notification_id, user["id"]),
            )
        if not changed.rowcount:
            raise problem(404, "not_found", "通知不存在")
        return {"status": "read", "message": "通知已读"}

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
            db.execute(
                "DELETE FROM favorite_folder_items WHERE paper_id=? AND folder_id IN (SELECT id FROM favorite_folders WHERE user_id=?)",
                (paper_id, user["id"]),
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

    @api.post("/me/favorite-folders", response_model=Folder, status_code=201)
    def create_folder(body: FolderInput, user=Depends(store.current)):
        stamp = now()
        try:
            with store.connect() as db:
                result = db.execute(
                    "INSERT INTO favorite_folders(user_id,name,created_at,updated_at) VALUES(?,?,?,?)",
                    (user["id"], body.name.strip(), stamp, stamp),
                )
                return {
                    "id": result.lastrowid,
                    "name": body.name.strip(),
                    "created_at": stamp,
                    "updated_at": stamp,
                    "paper_count": 0,
                }
        except sqlite3.IntegrityError as exc:
            raise problem(409, "duplicate_record", "收藏夹名称已存在") from exc

    @api.get("/me/favorite-folders", response_model=list[Folder])
    def list_folders(user=Depends(store.current)):
        with store.connect() as db:
            rows = db.execute(
                "SELECT f.*,count(i.paper_id) AS paper_count FROM favorite_folders f LEFT JOIN favorite_folder_items i ON i.folder_id=f.id WHERE f.user_id=? GROUP BY f.id ORDER BY f.id",
                (user["id"],),
            ).fetchall()
        return [dict(row) for row in rows]

    def own_folder(folder_id: int, user):
        with store.connect() as db:
            row = db.execute(
                "SELECT * FROM favorite_folders WHERE id=? AND user_id=?", (folder_id, user["id"])
            ).fetchone()
        if row is None:
            raise problem(404, "not_found", "收藏夹不存在")
        return row

    @api.patch("/me/favorite-folders/{folder_id}", response_model=Folder)
    def rename_folder(folder_id: int, body: FolderInput, user=Depends(store.current)):
        own_folder(folder_id, user)
        try:
            with store.connect() as db:
                db.execute(
                    "UPDATE favorite_folders SET name=?,updated_at=? WHERE id=? AND user_id=?",
                    (body.name.strip(), now(), folder_id, user["id"]),
                )
                row = db.execute(
                    "SELECT f.*,count(i.paper_id) AS paper_count FROM favorite_folders f LEFT JOIN favorite_folder_items i ON i.folder_id=f.id WHERE f.id=? GROUP BY f.id",
                    (folder_id,),
                ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise problem(409, "duplicate_record", "收藏夹名称已存在") from exc
        return dict(row)

    @api.delete("/me/favorite-folders/{folder_id}", response_model=DeleteResponse)
    def delete_folder(folder_id: int, user=Depends(store.current)):
        own_folder(folder_id, user)
        with store.connect() as db:
            db.execute(
                "DELETE FROM favorite_folders WHERE id=? AND user_id=?", (folder_id, user["id"])
            )
        return {"deleted": True}

    @api.get("/me/favorite-folders/{folder_id}/papers", response_model=Page[FavoriteItem])
    def folder_papers(
        folder_id: int,
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        own_folder(folder_id, user)
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM favorite_folder_items WHERE folder_id=?", (folder_id,)
            ).fetchone()[0]
            rows = db.execute(
                "SELECT paper_id,created_at FROM favorite_folder_items WHERE folder_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (folder_id, page_size, (page - 1) * page_size),
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
            except HTTPException:
                results.append(
                    {**dict(row), "title": "", "authors": [], "year": None, "available": False}
                )
        return {"total": total, "page": page, "page_size": page_size, "results": results}

    @api.put("/me/favorite-folders/{folder_id}/papers", response_model=StatusResponse)
    def add_folder_paper(folder_id: int, body: FolderPaperInput, user=Depends(store.current)):
        own_folder(folder_id, user)
        read_paper(body.paper_id)
        with store.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO favorite_folder_items(folder_id,paper_id,created_at) VALUES(?,?,?)",
                (folder_id, body.paper_id, now()),
            )
            db.execute(
                "INSERT OR IGNORE INTO favorites(user_id,paper_id,created_at) VALUES(?,?,?)",
                (user["id"], body.paper_id, now()),
            )
        return {"status": "added", "message": "论文已加入收藏夹"}

    @api.delete(
        "/me/favorite-folders/{folder_id}/papers/{paper_id:path}", response_model=DeleteResponse
    )
    def remove_folder_paper(folder_id: int, paper_id: str, user=Depends(store.current)):
        own_folder(folder_id, user)
        with store.connect() as db:
            db.execute(
                "DELETE FROM favorite_folder_items WHERE folder_id=? AND paper_id=?",
                (folder_id, paper_id),
            )
        return {"deleted": True}

    @api.post("/me/browsing-history", response_model=StatusResponse, status_code=201)
    def add_browsing_history(body: FolderPaperInput, user=Depends(store.current)):
        read_paper(body.paper_id)
        with store.connect() as db:
            db.execute(
                "INSERT INTO browsing_history(user_id,paper_id,accessed_at) VALUES(?,?,?)",
                (user["id"], body.paper_id, now()),
            )
            db.execute(
                "DELETE FROM browsing_history WHERE user_id=? AND id NOT IN (SELECT id FROM browsing_history WHERE user_id=? ORDER BY id DESC LIMIT 500)",
                (user["id"], user["id"]),
            )
        return {"status": "recorded", "message": "浏览记录已保存"}

    @api.get("/me/browsing-history", response_model=Page[BrowsingRecord])
    def browsing_history(
        days: int = Query(default=7, ge=1, le=30),
        page: int = Query(default=1, ge=1, le=10000),
        page_size: int = Query(default=20, ge=1, le=100),
        user=Depends(store.current),
    ):
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        # ISO timestamps compare lexicographically, so use a generated ISO cutoff.
        cutoff_text = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
        with store.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM browsing_history WHERE user_id=? AND accessed_at>=?",
                (user["id"], cutoff_text),
            ).fetchone()[0]
            rows = db.execute(
                "SELECT id,paper_id,accessed_at FROM browsing_history WHERE user_id=? AND accessed_at>=? ORDER BY accessed_at DESC LIMIT ? OFFSET ?",
                (user["id"], cutoff_text, page_size, (page - 1) * page_size),
            ).fetchall()
        results = []
        for row in rows:
            try:
                title = read_paper(row["paper_id"])[0].get("title", "")
            except HTTPException:
                title = ""
            results.append({**dict(row), "title": title})
        return {"total": total, "page": page, "page_size": page_size, "results": results}

    @api.delete("/me/browsing-history/{history_id}", response_model=DeleteResponse)
    def delete_browsing_history(history_id: int, user=Depends(store.current)):
        with store.connect() as db:
            changed = db.execute(
                "DELETE FROM browsing_history WHERE id=? AND user_id=?", (history_id, user["id"])
            )
        if not changed.rowcount:
            raise problem(404, "not_found", "浏览记录不存在")
        return {"deleted": True}

    @api.delete("/me/browsing-history", response_model=ClearResponse)
    def clear_browsing_history(user=Depends(store.current)):
        with store.connect() as db:
            db.execute("DELETE FROM browsing_history WHERE user_id=?", (user["id"],))
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
