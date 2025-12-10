"""FastAPI dependencies."""
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core import redis as redis_core
from waifu_bot.core.config import settings
from waifu_bot.db.session import get_session
from waifu_bot.services.auth import validate_init_data


async def get_db() -> AsyncSession:
    """Provide DB session for request lifecycle."""
    async for session in get_session():
        yield session


def get_redis():
    """Provide Redis client (singleton)."""
    return redis_core.get_redis()


async def get_player_id(
    init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    x_player_id: int | None = Header(None, alias="X-Player-Id"),
) -> int:
    """
    Extract player id using Telegram WebApp initData.

    For dev convenience (environment=dev) can fallback to X-Player-Id.
    """
    if init_data:
        data = validate_init_data(init_data, settings.bot_token)
        user = data.get("user") or {}
        user_id = user.get("id")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user id missing in init data")
        return int(user_id)

    if settings.environment == "dev" and x_player_id:
        if x_player_id <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid player id")
        return x_player_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Telegram init data",
    )

