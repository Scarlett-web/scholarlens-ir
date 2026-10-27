"""Purpose-bound, expiring, attempt-limited codes sent through an operator-configured mail API."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.accounts import password_hash, now, problem


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def valid(cls, v):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("invalid email")
        return v.strip().lower()


class CodeInput(EmailRequest):
    code: str = Field(pattern=r"^\d{8}$", repr=False)


class ResetInput(CodeInput):
    new_password: str = Field(min_length=10, max_length=128, repr=False)


def setup(db):
    db.execute("""CREATE TABLE IF NOT EXISTS email_codes(
        id INTEGER PRIMARY KEY, email TEXT NOT NULL,purpose TEXT NOT NULL,user_id INTEGER,
        salt TEXT NOT NULL, code_hash TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        used INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)""")
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS verified_email_unique ON users(lower(email)) WHERE email_verified=1 AND email IS NOT NULL"
    )


def code_hash(code, salt):
    return hashlib.sha256((salt + "\0" + code).encode()).hexdigest()


def router(store):
    api = APIRouter(prefix="/api")
    with store.connect() as db:
        setup(db)

    def issue(email, purpose, user_id):
        endpoint = os.getenv("EMAIL_BASE_URL", "")
        if not endpoint:
            raise problem(503, "email_not_configured", "邮件服务尚未配置")
        parsed = urlparse(endpoint)
        if (
            parsed.scheme not in ("https", "http")
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise problem(503, "email_not_configured", "邮件地址配置无效")
        code = f"{secrets.randbelow(10**8):08d}"
        salt = secrets.token_hex(16)
        with store.connect() as db:
            recent = db.execute(
                "SELECT created FROM email_codes WHERE email=? AND purpose=? ORDER BY id DESC LIMIT 1",
                (email, purpose),
            ).fetchone()
            if recent and time.time() - recent["created"] < 60:
                raise problem(429, "rate_limited", "请等待60秒后重试")
            db.execute(
                "UPDATE email_codes SET used=1 WHERE email=? AND purpose=?", (email, purpose)
            )
            result = db.execute(
                "INSERT INTO email_codes(email,purpose,user_id,salt,code_hash,expires,created) VALUES(?,?,?,?,?,?,?)",
                (
                    email,
                    purpose,
                    user_id,
                    salt,
                    code_hash(code, salt),
                    time.time() + 600,
                    time.time(),
                ),
            )
            row_id = result.lastrowid
        # Unknown reset accounts receive the same response but no actual message or usable code.
        if user_id is not None:
            try:
                response = httpx.post(
                    endpoint,
                    json={
                        "to": email,
                        "subject": "ScholarLens verification",
                        "purpose": purpose,
                        "code": code,
                    },
                    headers={"Authorization": "Bearer " + os.environ["EMAIL_API_KEY"]}
                    if os.getenv("EMAIL_API_KEY")
                    else {},
                    timeout=10,
                    trust_env=False,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                with store.connect() as db:
                    db.execute("UPDATE email_codes SET used=1 WHERE id=?", (row_id,))
                raise problem(503, "email_service_unavailable", "邮件服务未确认接收请求") from exc
        return {
            "status": "accepted",
            "message": "若账号符合条件，邮件服务将发送验证码；有效期10分钟",
        }

    def consume(db, email, purpose, code, user_id=None):
        row = db.execute(
            "SELECT * FROM email_codes WHERE email=? AND purpose=? ORDER BY id DESC LIMIT 1",
            (email, purpose),
        ).fetchone()
        valid = (
            row
            and not row["used"]
            and row["expires"] > time.time()
            and row["attempts"] < 5
            and row["user_id"] is not None
        )
        if user_id is not None:
            valid = valid and row["user_id"] == user_id
        if row:
            db.execute("UPDATE email_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        if not valid or not hmac.compare_digest(row["code_hash"], code_hash(code, row["salt"])):
            db.commit()  # Do not roll back failed-attempt limits with the HTTP exception.
            raise problem(400, "invalid_code", "验证码无效、过期或尝试次数过多")
        db.execute("UPDATE email_codes SET used=1 WHERE id=?", (row["id"],))
        return row["user_id"]

    @api.post("/me/email/request")
    def request_email(body: EmailRequest, user=Depends(store.current)):
        with store.connect() as db:
            current = db.execute("SELECT email FROM users WHERE id=?", (user["id"],)).fetchone()
        if not current or current["email"] != body.email:
            raise problem(400, "invalid_parameter", "请先在个人资料中设置该邮箱")
        return issue(body.email, "verify_email", user["id"])

    @api.post("/me/email/verify")
    def verify_email(body: CodeInput, user=Depends(store.current)):
        try:
            with store.connect() as db:
                consume(db, body.email, "verify_email", body.code, user["id"])
                current = db.execute("SELECT email FROM users WHERE id=?", (user["id"],)).fetchone()
                if current["email"] != body.email:
                    raise problem(400, "invalid_code", "邮箱已更改，请重新验证")
                db.execute(
                    "UPDATE users SET email_verified=1,updated_at=? WHERE id=?", (now(), user["id"])
                )
        except sqlite3.IntegrityError as exc:
            raise problem(409, "duplicate_record", "该邮箱已由其他账号验证") from exc
        return {"status": "email_verified"}

    @api.post("/auth/password-reset/request")
    def request_reset(body: EmailRequest):
        with store.connect() as db:
            row = db.execute(
                "SELECT id FROM users WHERE lower(email)=? AND email_verified=1 AND disabled=0",
                (body.email,),
            ).fetchone()
        return issue(body.email, "reset_password", row["id"] if row else None)

    @api.post("/auth/password-reset/verify")
    def reset(body: ResetInput):
        with store.connect() as db:
            user_id = consume(db, body.email, "reset_password", body.code)
            row = db.execute(
                "SELECT email,email_verified,disabled FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if (
                not row
                or row["email"] != body.email
                or not row["email_verified"]
                or row["disabled"]
            ):
                raise problem(400, "invalid_code", "账号状态或邮箱已改变")
            salt = secrets.token_hex(16)
            db.execute(
                "UPDATE users SET salt=?,password_hash=?,updated_at=? WHERE id=?",
                (salt, password_hash(body.new_password, salt), now(), user_id),
            )
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("UPDATE email_codes SET used=1 WHERE user_id=?", (user_id,))
        return {"status": "password_reset", "message": "密码已重置，请重新登录"}

    return api
