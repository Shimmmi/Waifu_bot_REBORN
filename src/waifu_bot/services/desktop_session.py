"""Desktop Electron session JWT (header X-Desktop-Session, not Armory cookies)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status

from waifu_bot.core.config import settings

SESSION_TTL_DAYS_DEFAULT = 30


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ttl_days() -> int:
    return int(getattr(settings, "desktop_session_ttl_days", None) or SESSION_TTL_DAYS_DEFAULT)


def create_desktop_session_token(player_id: int, *, auth_provider: str) -> tuple[str, str]:
    """Return (jwt_token, jti)."""
    jti = uuid.uuid4().hex
    now = _now_utc()
    ttl = _ttl_days()
    payload = {
        "sub": str(player_id),
        "player_id": player_id,
        "auth_provider": auth_provider,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=ttl)).timestamp()),
    }
    token = jwt.encode(payload, settings.desktop_session_key, algorithm="HS256")
    return token, jti


def decode_desktop_session_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.desktop_session_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="desktop_session_expired"
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="desktop_session_invalid"
        ) from e


async def store_desktop_session_jti(redis: Any, player_id: int, jti: str) -> None:
    if not redis:
        return
    key = f"desktop:session:{player_id}:{jti}"
    await redis.setex(key, _ttl_days() * 86400, "1")


async def revoke_desktop_session_jti(redis: Any, player_id: int, jti: str) -> None:
    if not redis:
        return
    await redis.delete(f"desktop:session:{player_id}:{jti}")


async def is_desktop_session_jti_valid(redis: Any, player_id: int, jti: str) -> bool:
    if not redis:
        return True
    return bool(await redis.exists(f"desktop:session:{player_id}:{jti}"))


async def resolve_player_id_from_desktop_session(
    redis: Any, token: str
) -> int:
    """Decode JWT, check Redis JTI, return player_id."""
    claims = decode_desktop_session_token(token)
    try:
        player_id = int(claims.get("player_id") or claims.get("sub"))
    except (TypeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="desktop_session_invalid"
        ) from e
    jti = str(claims.get("jti") or "")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="desktop_session_invalid"
        )
    if not await is_desktop_session_jti_valid(redis, player_id, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="desktop_session_revoked"
        )
    return player_id
