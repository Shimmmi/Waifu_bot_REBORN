"""Track Telegram group/supergroup chats where the bot is a member."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError
from aiogram.types import Chat, ChatMemberUpdated
from sqlalchemy import func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    BotGroupChat,
    ChatAudioTrack,
    GDCycle,
    Guild,
    GuildRaid,
    PlayerChatFirstSeen,
)

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset(
    {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        "member",
        "administrator",
        "creator",
    }
)
LEFT_STATUSES = frozenset({ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, "left", "kicked"})


def _status_str(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def build_telegram_group_url(
    chat_id: int,
    *,
    username: str | None = None,
    invite_link: str | None = None,
) -> str | None:
    if invite_link:
        return invite_link.strip() or None
    if username:
        un = username.strip().lstrip("@")
        if un:
            return f"https://t.me/{un}"
    cid = int(chat_id)
    if cid < -10**12:
        internal = abs(cid) - 10**12
        return f"https://t.me/c/{internal}/1"
    return None


def _chat_meta_from_telegram_chat(chat: Chat) -> dict[str, Any]:
    return {
        "chat_type": str(chat.type.value) if hasattr(chat.type, "value") else str(chat.type),
        "title": chat.title,
        "username": chat.username,
        "invite_link": getattr(chat, "invite_link", None),
    }


async def apply_chat_metadata_from_api(
    session: AsyncSession,
    bot: Bot,
    chat_id: int,
) -> BotGroupChat | None:
    row = await session.get(BotGroupChat, int(chat_id))
    if not row:
        return None
    try:
        chat = await bot.get_chat(int(chat_id))
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.debug("get_chat failed chat_id=%s: %s", chat_id, e)
        return row
    meta = _chat_meta_from_telegram_chat(chat)
    row.chat_type = meta["chat_type"] or row.chat_type
    if meta["title"]:
        row.title = meta["title"]
    if meta["username"]:
        row.username = meta["username"]
    if meta["invite_link"]:
        row.invite_link = meta["invite_link"]
    try:
        me = await bot.me()
        member = await bot.get_chat_member(int(chat_id), me.id)
        row.status = _status_str(member.status)
        if row.status in LEFT_STATUSES:
            if row.left_at is None:
                row.left_at = datetime.now(tz=timezone.utc)
        else:
            row.left_at = None
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.debug("get_chat_member failed chat_id=%s: %s", chat_id, e)
    return row


async def record_bot_chat_member_update(
    session: AsyncSession,
    update: ChatMemberUpdated,
    bot: Bot,
) -> None:
    chat = update.chat
    if not chat or chat.type not in ("group", "supergroup"):
        return
    me = await bot.me()
    new_member = update.new_chat_member
    if not new_member or new_member.user.id != me.id:
        return

    chat_id = int(chat.id)
    status = _status_str(new_member.status)
    now = datetime.now(tz=timezone.utc)
    meta = _chat_meta_from_telegram_chat(chat)

    row = await session.get(BotGroupChat, chat_id)
    if row is None:
        row = BotGroupChat(
            chat_id=chat_id,
            chat_type=meta["chat_type"],
            title=meta["title"],
            username=meta["username"],
            invite_link=meta["invite_link"],
            status=status,
            joined_at=now,
            discovered_via="my_chat_member",
            last_activity_at=now,
        )
        session.add(row)
    else:
        row.chat_type = meta["chat_type"] or row.chat_type
        if meta["title"]:
            row.title = meta["title"]
        if meta["username"]:
            row.username = meta["username"]
        if meta["invite_link"]:
            row.invite_link = meta["invite_link"]
        row.status = status
        if status in LEFT_STATUSES:
            if row.left_at is None:
                row.left_at = now
        else:
            row.left_at = None
        if row.discovered_via == "backfill":
            row.discovered_via = "my_chat_member"

    await session.flush()
    await apply_chat_metadata_from_api(session, bot, chat_id)


async def touch_bot_group_chat_activity(session: AsyncSession, chat_id: int) -> None:
    if int(chat_id) >= 0:
        return
    now = datetime.now(tz=timezone.utc)
    row = await session.get(BotGroupChat, int(chat_id))
    if row is None:
        return
    row.last_activity_at = now


def _row_to_dict(row: BotGroupChat) -> dict[str, Any]:
    return {
        "chat_id": row.chat_id,
        "chat_type": row.chat_type,
        "title": row.title,
        "username": row.username,
        "status": row.status,
        "joined_at": row.joined_at.isoformat() if row.joined_at else None,
        "left_at": row.left_at.isoformat() if row.left_at else None,
        "last_activity_at": row.last_activity_at.isoformat() if row.last_activity_at else None,
        "discovered_via": row.discovered_via,
        "telegram_url": build_telegram_group_url(
            row.chat_id, username=row.username, invite_link=row.invite_link
        ),
    }


def _status_filter_clause(status_filter: str):
    sf = (status_filter or "all").strip().lower()
    if sf == "all":
        return None
    if sf == "active":
        return BotGroupChat.status.in_(("member", "administrator", "creator"))
    return BotGroupChat.status == sf


async def list_bot_group_chats(
    session: AsyncSession,
    *,
    status_filter: str = "all",
    q: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    base = select(BotGroupChat)
    clause = _status_filter_clause(status_filter)
    if clause is not None:
        base = base.where(clause)
    q_clean = q.strip()
    if q_clean:
        if q_clean.lstrip("-").isdigit():
            base = base.where(BotGroupChat.chat_id == int(q_clean))
        else:
            like = f"%{q_clean}%"
            base = base.where(
                or_(
                    BotGroupChat.title.ilike(like),
                    BotGroupChat.username.ilike(like),
                )
            )
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    offset = (page - 1) * page_size
    order = BotGroupChat.last_activity_at.desc().nullslast(), BotGroupChat.joined_at.desc()
    rows = (
        await session.execute(base.order_by(*order).offset(offset).limit(page_size))
    ).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_row_to_dict(r) for r in rows],
    }


async def refresh_bot_group_chats(
    session: AsyncSession,
    bot: Bot,
    chat_ids: list[int] | None = None,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    if chat_ids:
        ids = [int(x) for x in chat_ids[:limit]]
    else:
        rows = (
            await session.execute(
                select(BotGroupChat.chat_id).order_by(BotGroupChat.last_activity_at.desc().nullslast()).limit(limit)
            )
        ).all()
        ids = [int(r[0]) for r in rows]
    updated = 0
    for cid in ids:
        row = await apply_chat_metadata_from_api(session, bot, cid)
        if row:
            updated += 1
    await session.commit()
    return {"refreshed": updated, "chat_ids": ids}


async def collect_backfill_chat_ids(session: AsyncSession) -> list[int]:
    parts = [
        select(GDCycle.chat_id).where(GDCycle.chat_id < 0).distinct(),
        select(PlayerChatFirstSeen.chat_id).where(PlayerChatFirstSeen.chat_id < 0).distinct(),
        select(Guild.telegram_chat_id).where(Guild.telegram_chat_id.is_not(None)).distinct(),
        select(GuildRaid.chat_id).where(GuildRaid.chat_id < 0).distinct(),
        select(ChatAudioTrack.chat_id).where(ChatAudioTrack.chat_id < 0).distinct(),
    ]
    combined = union(*parts).subquery()
    rows = (await session.execute(select(combined.c.chat_id))).all()
    return sorted({int(r[0]) for r in rows if r[0] is not None and int(r[0]) < 0})


async def backfill_bot_group_chats(session: AsyncSession, bot: Bot) -> dict[str, Any]:
    chat_ids = await collect_backfill_chat_ids(session)
    now = datetime.now(tz=timezone.utc)
    inserted = 0
    updated = 0
    for chat_id in chat_ids:
        existing = await session.get(BotGroupChat, chat_id)
        if existing:
            await apply_chat_metadata_from_api(session, bot, chat_id)
            updated += 1
            continue
        chat_type = "supergroup" if chat_id < -10**12 else "group"
        status = "member"
        title = None
        username = None
        invite_link = None
        try:
            chat = await bot.get_chat(chat_id)
            meta = _chat_meta_from_telegram_chat(chat)
            chat_type = meta["chat_type"] or chat_type
            title = meta["title"]
            username = meta["username"]
            invite_link = meta["invite_link"]
            me = await bot.me()
            member = await bot.get_chat_member(chat_id, me.id)
            status = _status_str(member.status)
        except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TimeoutError) as e:
            logger.warning("backfill get_chat chat_id=%s: %s", chat_id, e)

        left_at = now if status in ("left", "kicked") else None
        session.add(
            BotGroupChat(
                chat_id=chat_id,
                chat_type=chat_type,
                title=title,
                username=username,
                invite_link=invite_link,
                status=status,
                joined_at=now,
                left_at=left_at,
                discovered_via="backfill",
                last_activity_at=now,
            )
        )
        inserted += 1
    await session.commit()
    return {"chat_ids_found": len(chat_ids), "inserted": inserted, "updated": updated}
