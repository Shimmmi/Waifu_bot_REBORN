"""One-time account link codes (Telegram → Steam/Mobile)."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, status

LINK_CODE_TTL_SEC = 600  # 10 minutes
LINK_CODE_PREFIX = "auth:link_code:"


async def issue_link_code(redis: Any, player_id: int) -> str:
    if not redis:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="redis_unavailable"
        )
    code = secrets.token_hex(4).upper()  # 8 hex chars
    await redis.setex(f"{LINK_CODE_PREFIX}{code}", LINK_CODE_TTL_SEC, str(int(player_id)))
    return code


async def consume_link_code(redis: Any, code: str) -> int:
    if not redis:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="redis_unavailable"
        )
    key = f"{LINK_CODE_PREFIX}{(code or '').strip().upper()}"
    raw = await redis.get(key)
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_or_expired_link_code")
    await redis.delete(key)
    try:
        return int(raw if isinstance(raw, str) else raw.decode())
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_link_code") from e
