"""Player ban checks."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.armory import PlayerBan


async def is_player_banned(session: AsyncSession, player_id: int) -> bool:
    ban = await session.get(PlayerBan, player_id)
    if not ban:
        return False
    if ban.expires_at is not None:
        now = datetime.now(timezone.utc)
        exp = ban.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            return False
    return True
