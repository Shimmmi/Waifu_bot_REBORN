"""Armory browser session management (JWT + Redis jti)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Response, status

from waifu_bot.core.config import settings

SESSION_COOKIE = "armory_session"
CSRF_COOKIE = "armory_csrf"
SESSION_TTL_DAYS = 7
SESSION_PATH = "/"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_session_token(tg_id: int, *, is_admin: bool) -> tuple[str, str]:
    """Return (jwt_token, jti)."""
    jti = uuid.uuid4().hex
    now = _now_utc()
    payload = {
        "sub": str(tg_id),
        "tg_id": tg_id,
        "is_admin": is_admin,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=SESSION_TTL_DAYS)).timestamp()),
    }
    token = jwt.encode(payload, settings.armory_session_key, algorithm="HS256")
    return token, jti


def decode_session_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.armory_session_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session") from e


async def store_session_jti(redis: Any, tg_id: int, jti: str) -> None:
    if not redis:
        return
    key = f"armory:session:{tg_id}:{jti}"
    ttl = SESSION_TTL_DAYS * 86400
    await redis.setex(key, ttl, "1")


async def revoke_session_jti(redis: Any, tg_id: int, jti: str) -> None:
    if not redis:
        return
    await redis.delete(f"armory:session:{tg_id}:{jti}")


async def is_session_jti_valid(redis: Any, tg_id: int, jti: str) -> bool:
    if not redis:
        return True
    return bool(await redis.exists(f"armory:session:{tg_id}:{jti}"))


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(response: Response, jwt_token: str, csrf_token: str) -> None:
    secure = settings.environment not in ("dev", "testing")
    cookie_kwargs: dict[str, Any] = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": SESSION_PATH,
        "max_age": SESSION_TTL_DAYS * 86400,
    }
    if settings.armory_cookie_domain:
        cookie_kwargs["domain"] = settings.armory_cookie_domain

    response.set_cookie(SESSION_COOKIE, jwt_token, **cookie_kwargs)
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path=SESSION_PATH,
        max_age=SESSION_TTL_DAYS * 86400,
        domain=settings.armory_cookie_domain,
    )


def clear_session_cookies(response: Response) -> None:
    delete_kwargs: dict[str, Any] = {"path": SESSION_PATH}
    if settings.armory_cookie_domain:
        delete_kwargs["domain"] = settings.armory_cookie_domain
    response.delete_cookie(SESSION_COOKIE, **delete_kwargs)
    response.delete_cookie(CSRF_COOKIE, **delete_kwargs)


async def mark_telegram_login_hash_used(redis: Any, login_hash: str) -> bool:
    """Return True if hash was already used (replay)."""
    if not redis:
        return False
    key = f"armory:tg_login_hash:{login_hash}"
    inserted = await redis.set(key, "1", ex=3600, nx=True)
    return not inserted
