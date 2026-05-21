"""In-game mail between guild members."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import GuildMember, InventoryItem, Item, Player, PlayerMail, PlayerMailStatus
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today_start_utc() -> datetime:
    now = _utcnow()
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _player_label(player: Player | None) -> str:
    if not player:
        return "Игрок"
    un = (player.username or "").strip()
    if un:
        return f"@{un}"
    return (player.first_name or "").strip() or f"Игрок {player.id}"


async def _assert_same_guild(session: AsyncSession, sender_id: int, recipient_id: int) -> tuple[int, int]:
    if sender_id == recipient_id:
        raise ValueError("cannot_mail_self")
    s_mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == sender_id))
    ).scalar_one_or_none()
    r_mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == recipient_id))
    ).scalar_one_or_none()
    if not s_mem or not r_mem or s_mem.guild_id != r_mem.guild_id:
        raise ValueError("not_same_guild")
    return int(s_mem.guild_id), int(r_mem.guild_id)


async def _inbox_count(session: AsyncSession, recipient_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PlayerMail)
            .where(
                PlayerMail.recipient_player_id == recipient_id,
                PlayerMail.recipient_deleted.is_(False),
            )
        )
        or 0
    )


async def _daily_send_count(session: AsyncSession, sender_id: int) -> int:
    day_start = _today_start_utc()
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PlayerMail)
            .where(
                PlayerMail.sender_player_id == sender_id,
                PlayerMail.created_at >= day_start,
            )
        )
        or 0
    )


def _mail_to_dict(mail: PlayerMail, *, sender: Player | None, item: InventoryItem | None) -> dict:
    item_name = None
    if item and item.item:
        item_name = item.item.name
    return {
        "id": int(mail.id),
        "sender_player_id": int(mail.sender_player_id),
        "recipient_player_id": int(mail.recipient_player_id),
        "sender_label": _player_label(sender),
        "body_text": mail.body_text,
        "gold_amount": int(mail.gold_amount or 0),
        "inventory_item_id": int(mail.inventory_item_id) if mail.inventory_item_id else None,
        "item_name": item_name,
        "status": str(mail.status),
        "created_at": mail.created_at.isoformat() if mail.created_at else None,
        "read_at": mail.read_at.isoformat() if mail.read_at else None,
        "claimed_at": mail.claimed_at.isoformat() if mail.claimed_at else None,
    }


async def send_mail(
    session: AsyncSession,
    sender_id: int,
    recipient_id: int,
    *,
    body_text: str | None,
    gold_amount: int = 0,
    inventory_item_id: int | None = None,
) -> dict:
    cfg = await get_game_config_map(session)
    max_body = cfg_int(cfg, "mail.max_body_length", 500)
    max_gold = cfg_int(cfg, "mail.max_gold_per_send", 100_000)
    max_inbox = cfg_int(cfg, "mail.max_inbox", 50)
    daily_limit = cfg_int(cfg, "mail.daily_send_limit", 20)

    await _assert_same_guild(session, sender_id, recipient_id)

    text = (body_text or "").strip()
    gold = max(0, int(gold_amount or 0))
    if len(text) > max_body:
        raise ValueError("body_too_long")
    if gold > max_gold:
        raise ValueError("gold_too_much")
    if not text and gold <= 0 and not inventory_item_id:
        raise ValueError("empty_mail")

    if await _inbox_count(session, recipient_id) >= max_inbox:
        raise ValueError("recipient_inbox_full")
    if await _daily_send_count(session, sender_id) >= daily_limit:
        raise ValueError("daily_send_limit")

    sender = await session.get(Player, sender_id)
    if not sender:
        raise ValueError("sender_not_found")
    recipient = await session.get(Player, recipient_id)
    if not recipient:
        raise ValueError("recipient_not_found")

    inv_item: InventoryItem | None = None
    if inventory_item_id:
        inv_item = (
            await session.execute(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item))
                .where(
                    InventoryItem.id == inventory_item_id,
                    InventoryItem.player_id == sender_id,
                )
            )
        ).scalar_one_or_none()
        if not inv_item:
            raise ValueError("item_not_found")
        if inv_item.equipment_slot is not None:
            raise ValueError("item_equipped")

    if gold > int(sender.gold or 0):
        raise ValueError("insufficient_gold")

    if gold > 0:
        sender.gold = int(sender.gold or 0) - gold
    if inv_item:
        inv_item.player_id = None

    mail = PlayerMail(
        sender_player_id=sender_id,
        recipient_player_id=recipient_id,
        body_text=text or None,
        gold_amount=gold,
        inventory_item_id=int(inv_item.id) if inv_item else None,
        status=PlayerMailStatus.UNREAD,
    )
    session.add(mail)
    await session.flush()
    await session.commit()
    await session.refresh(mail)

    sender_row = await session.get(Player, sender_id)
    return _mail_to_dict(mail, sender=sender_row, item=inv_item)


async def list_inbox(
    session: AsyncSession,
    player_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    rows = (
        await session.execute(
            select(PlayerMail, Player)
            .join(Player, Player.id == PlayerMail.sender_player_id)
            .where(
                PlayerMail.recipient_player_id == player_id,
                PlayerMail.recipient_deleted.is_(False),
            )
            .order_by(PlayerMail.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = [_mail_to_dict(m, sender=s, item=None) for m, s in rows]
    return {"items": items, "limit": limit, "offset": offset}


async def unread_count(session: AsyncSession, player_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(PlayerMail)
            .where(
                PlayerMail.recipient_player_id == player_id,
                PlayerMail.recipient_deleted.is_(False),
                PlayerMail.status == PlayerMailStatus.UNREAD,
            )
        )
        or 0
    )


async def get_mail(session: AsyncSession, player_id: int, mail_id: int) -> dict:
    row = (
        await session.execute(
            select(PlayerMail, Player)
            .join(Player, Player.id == PlayerMail.sender_player_id)
            .where(PlayerMail.id == mail_id)
        )
    ).first()
    if not row:
        raise ValueError("mail_not_found")
    mail, sender = row
    if mail.recipient_player_id != player_id or mail.recipient_deleted:
        raise ValueError("mail_not_found")

    inv_item = None
    if mail.inventory_item_id:
        inv_item = (
            await session.execute(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item))
                .where(InventoryItem.id == mail.inventory_item_id)
            )
        ).scalar_one_or_none()

    if mail.status == PlayerMailStatus.UNREAD:
        mail.status = PlayerMailStatus.READ
        mail.read_at = _utcnow()
        if not mail.gold_amount and not mail.inventory_item_id:
            mail.status = PlayerMailStatus.CLAIMED
            mail.claimed_at = mail.read_at
        await session.commit()
        await session.refresh(mail)

    return _mail_to_dict(mail, sender=sender, item=inv_item)


async def claim_mail(session: AsyncSession, player_id: int, mail_id: int) -> dict:
    mail = await session.get(PlayerMail, mail_id)
    if not mail or mail.recipient_player_id != player_id or mail.recipient_deleted:
        raise ValueError("mail_not_found")
    if mail.status == PlayerMailStatus.CLAIMED:
        sender = await session.get(Player, mail.sender_player_id)
        inv_item = None
        if mail.inventory_item_id:
            inv_item = (
                await session.execute(
                    select(InventoryItem)
                    .options(selectinload(InventoryItem.item))
                    .where(InventoryItem.id == mail.inventory_item_id)
                )
            ).scalar_one_or_none()
        return _mail_to_dict(mail, sender=sender, item=inv_item)

    recipient = await session.get(Player, player_id)
    if not recipient:
        raise ValueError("recipient_not_found")

    if mail.gold_amount > 0:
        recipient.gold = int(recipient.gold or 0) + int(mail.gold_amount)

    inv_item = None
    if mail.inventory_item_id:
        inv_item = (
            await session.execute(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item))
                .where(InventoryItem.id == mail.inventory_item_id)
            )
        ).scalar_one_or_none()
        if not inv_item:
            raise ValueError("item_missing")
        if inv_item.player_id is not None:
            raise ValueError("item_already_claimed")
        inv_item.player_id = player_id

    now = _utcnow()
    if mail.status == PlayerMailStatus.UNREAD:
        mail.read_at = now
    mail.status = PlayerMailStatus.CLAIMED
    mail.claimed_at = now
    await session.commit()
    await session.refresh(mail)

    sender = await session.get(Player, mail.sender_player_id)
    return _mail_to_dict(mail, sender=sender, item=inv_item)


async def delete_mail(session: AsyncSession, player_id: int, mail_id: int) -> None:
    mail = await session.get(PlayerMail, mail_id)
    if not mail or mail.recipient_player_id != player_id:
        raise ValueError("mail_not_found")
    mail.recipient_deleted = True
    await session.commit()
