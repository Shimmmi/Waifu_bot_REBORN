"""Guild hall stats and activity feed."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.db.models.guild_extended import GuildActivityLog


def _member_power(w: m.MainWaifu | None) -> int:
    if w is None:
        return 0
    return (
        int(w.strength or 0)
        + int(w.agility or 0)
        + int(w.intelligence or 0)
        + int(w.endurance or 0)
        + int(w.charm or 0)
        + int(w.luck or 0)
        + int(w.level or 1) * 10
    )


async def compute_guild_power(session: AsyncSession, guild_id: int) -> int:
    stmt = (
        select(m.MainWaifu)
        .join(m.GuildMember, m.GuildMember.player_id == m.MainWaifu.player_id)
        .where(m.GuildMember.guild_id == guild_id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return sum(_member_power(w) for w in rows)


async def compute_guild_rating(session: AsyncSession, guild_id: int) -> int | None:
    stmt = select(m.Guild.id, m.Guild.experience).order_by(
        m.Guild.experience.desc(), m.Guild.id.asc()
    )
    rows = (await session.execute(stmt)).all()
    for rank, (gid, _) in enumerate(rows, start=1):
        if int(gid) == int(guild_id):
            return rank
    return None


def _activity_row_to_dict(row: GuildActivityLog) -> dict:
    created = row.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": int(row.id),
        "type": row.event_type,
        "actor_name": None,
        "actor_avatar": row.actor_avatar or "📋",
        "text": row.text,
        "created_at": created.isoformat() if created else None,
    }


async def fetch_guild_activity_feed(
    session: AsyncSession, guild_id: int, *, limit: int = 20
) -> list[dict]:
    stmt = (
        select(GuildActivityLog)
        .where(GuildActivityLog.guild_id == guild_id)
        .order_by(GuildActivityLog.created_at.desc(), GuildActivityLog.id.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_activity_row_to_dict(r) for r in rows]


async def fetch_guild_history(
    session: AsyncSession, guild_id: int, *, limit: int = 50
) -> list[dict]:
    return await fetch_guild_activity_feed(session, guild_id, limit=limit)


async def _player_display(session: AsyncSession, player_id: int) -> str:
    pl = await session.get(m.Player, player_id)
    if pl is None:
        return f"Игрок {player_id}"
    fn = (pl.first_name or "").strip()
    un = (pl.username or "").strip()
    return fn or (f"@{un}" if un else str(pl.id))


async def log_guild_activity(
    session: AsyncSession,
    guild_id: int,
    event_type: str,
    text: str,
    *,
    actor_player_id: int | None = None,
    actor_avatar: str | None = None,
) -> None:
    row = GuildActivityLog(
        guild_id=int(guild_id),
        event_type=str(event_type)[:32],
        actor_player_id=actor_player_id,
        text=str(text)[:512],
        actor_avatar=(actor_avatar or "📋")[:16],
        created_at=datetime.now(timezone.utc),
    )
    session.add(row)


async def log_member_join(
    session: AsyncSession, guild_id: int, player_id: int
) -> None:
    name = await _player_display(session, player_id)
    await log_guild_activity(
        session,
        guild_id,
        "member_join",
        f"{name} вступил в гильдию",
        actor_player_id=player_id,
        actor_avatar="🧜",
    )


async def log_bank_deposit(
    session: AsyncSession, guild_id: int, player_id: int, amount: int
) -> None:
    await log_guild_activity(
        session,
        guild_id,
        "bank_deposit",
        f"В казну добавлено +{int(amount)} золота",
        actor_player_id=player_id,
        actor_avatar="🧙",
    )


async def log_skill_upgrade(
    session: AsyncSession, guild_id: int, player_id: int, skill_name: str
) -> None:
    name = await _player_display(session, player_id)
    await log_guild_activity(
        session,
        guild_id,
        "skill_upgrade",
        f"{name} улучшил навык «{skill_name}»",
        actor_player_id=player_id,
        actor_avatar="🧝",
    )
