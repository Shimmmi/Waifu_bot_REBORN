"""Track group chats where a player was seen (for achievement broadcasts)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import BotGroupChat, GDCycle, GDRegistration, PlayerChatFirstSeen
from waifu_bot.services.bot_group_chats import ACTIVE_STATUSES, build_telegram_group_url


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


async def list_player_active_bot_group_chats(
    session: AsyncSession, player_id: int
) -> list[dict[str, Any]]:
    """Group chats where the player was seen AND the bot is still an active member.

    Used by GD WebApp chat picker (and mirrors tavern BGM / guild raid chat lists).
    """
    player_chats = await resolve_player_group_chats(session, player_id)
    if not player_chats:
        return []
    rows = (
        await session.execute(
            select(BotGroupChat).where(
                BotGroupChat.chat_id.in_(player_chats),
                BotGroupChat.status.in_(tuple(ACTIVE_STATUSES)),
            )
        )
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        cid = int(row.chat_id)
        title = (row.title or "").strip() or f"Чат {cid}"
        username = (row.username or "").strip() or None
        invite = (row.invite_link or "").strip() or None
        out.append(
            {
                "chat_id": cid,
                "title": title,
                "username": username,
                "invite_link": invite,
                "telegram_url": build_telegram_group_url(
                    cid, username=username, invite_link=invite
                ),
            }
        )
    out.sort(key=lambda x: (str(x.get("title") or "").lower(), int(x["chat_id"])))
    return out


async def player_has_active_bot_chat(
    session: AsyncSession, player_id: int, chat_id: int
) -> bool:
    """True if chat_id is in the player's player∩bot active group set."""
    cid = int(chat_id)
    chats = await list_player_active_bot_group_chats(session, player_id)
    return any(int(c["chat_id"]) == cid for c in chats)


async def players_seen_in_group_chat(session: AsyncSession, chat_id: int) -> list[int]:
    """Player IDs seen in a group chat (messages or GD registration)."""
    cid = int(chat_id)
    if cid >= 0:
        return []
    gd_q = (
        select(GDRegistration.user_id.label("player_id"))
        .join(GDCycle, GDRegistration.cycle_id == GDCycle.id)
        .where(GDCycle.chat_id == cid)
        .distinct()
    )
    seen_q = (
        select(PlayerChatFirstSeen.player_id.label("player_id"))
        .where(PlayerChatFirstSeen.chat_id == cid)
        .distinct()
    )
    combined = union(gd_q, seen_q).subquery()
    rows = (await session.execute(select(combined.c.player_id))).all()
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
