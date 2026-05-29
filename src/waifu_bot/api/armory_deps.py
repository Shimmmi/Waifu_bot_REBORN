"""FastAPI dependencies for Armory browser portal."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_redis
from waifu_bot.core.config import settings
from waifu_bot.services.armory_session import CSRF_COOKIE, SESSION_COOKIE, decode_session_token, is_session_jti_valid
from waifu_bot.services.player_ban import is_player_banned


async def _session_payload(
    armory_session: str | None = Cookie(None, alias=SESSION_COOKIE),
    redis=Depends(get_redis),
) -> dict | None:
    if not armory_session:
        return None
    payload = decode_session_token(armory_session)
    tg_id = int(payload.get("tg_id") or payload.get("sub") or 0)
    jti = payload.get("jti")
    if not tg_id or not jti:
        return None
    if not await is_session_jti_valid(redis, tg_id, jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session revoked")
    return payload


async def get_armory_user(
    payload: dict | None = Depends(_session_payload),
) -> int | None:
    if not payload:
        return None
    return int(payload["tg_id"])


async def require_armory_user(
    tg_id: int | None = Depends(get_armory_user),
    session: AsyncSession = Depends(get_db),
) -> int:
    if tg_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    if await is_player_banned(session, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")
    return tg_id


async def require_armory_admin(
    tg_id: int = Depends(require_armory_user),
) -> int:
    if not settings.is_admin(tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    return tg_id


def verify_csrf(
    request: Request,
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    armory_csrf: str | None = Cookie(None, alias=CSRF_COOKIE),
) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    if not x_csrf_token or not armory_csrf or x_csrf_token != armory_csrf:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf validation failed")


ArmoryUserOptional = Annotated[int | None, Depends(get_armory_user)]
ArmoryUser = Annotated[int, Depends(require_armory_user)]
ArmoryAdmin = Annotated[int, Depends(require_armory_admin)]
