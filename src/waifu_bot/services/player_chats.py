"""Track group chats where a player was seen (for achievement broadcasts)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GDCycle, GDRegistration, PlayerChatFirstSeen


async def touch_player_chat_seen(session: AsyncSession, player_id: int, chat_id: int) -> None:
    """Record that the player sent a message in a group chat (chat_id < 0)."""
    if int(chat_id) >= 0:
        return
    stmt = (
        pg_insert(PlayerChatFirstSeen.__table__)
        .values(
            player_id=int(player_id),
            chat_id=int(chat_id),
            first_seen_at=datetime.now(tz=timezone.utc),
        )
        .on_conflict_do_nothing(index_elements=["player_id", "chat_id"])
    )
    await session.execute(stmt)


async def resolve_player_group_chats(session: AsyncSession, player_id: int) -> list[int]:
    """All group chats to notify: GD registration history + chats where player was seen."""
    pid = int(player_id)
    gd_q = (
        select(GDCycle.chat_id)
        .join(GDRegistration, GDRegistration.cycle_id == GDCycle.id)
        .where(GDRegistration.user_id == pid, GDCycle.chat_id < 0)
        .distinct()
    )
    seen_q = (
        select(PlayerChatFirstSeen.chat_id)
        .where(PlayerChatFirstSeen.player_id == pid, PlayerChatFirstSeen.chat_id < 0)
        .distinct()
    )
    combined = union(gd_q, seen_q).subquery()
    rows = (await session.execute(select(combined.c.chat_id))).all()
    return sorted({int(r[0]) for r in rows})


async def forget_player_chat_seen(
    session: AsyncSession, player_id: int, chat_id: int
) -> None:
    """Remove stale chat record (e.g. bot was kicked)."""
    await session.execute(
        delete(PlayerChatFirstSeen).where(
            PlayerChatFirstSeen.player_id == int(player_id),
            PlayerChatFirstSeen.chat_id == int(chat_id),
        )
    )
