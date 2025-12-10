"""FastAPI dependencies."""
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.session import get_session


async def get_db() -> AsyncSession:
    """Provide DB session for request lifecycle."""
    async for session in get_session():
        yield session


async def get_player_id(x_player_id: int = Header(..., alias="X-Player-Id")) -> int:
    """Extract player id from header (placeholder auth)."""
    if x_player_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid player id")
    return x_player_id

