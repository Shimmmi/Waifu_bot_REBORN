"""Build and cache compact JSON snapshots for client hubs."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api.main_waifu_media import (
    main_waifu_profile_paperdoll_url,
    main_waifu_profile_portrait_url,
)
from waifu_bot.db import models as m
from waifu_bot.game.economy import ECONOMY_TELEGRAM, normalize_economy

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _source_revision(session: AsyncSession, player_id: int) -> int:
    """Cheap invalidation token from mutable row counts / levels."""
    mw = await session.scalar(
        select(m.MainWaifu.level).where(m.MainWaifu.player_id == player_id)
    )
    inv_n = await session.scalar(
        select(func.count())
        .select_from(m.InventoryItem)
        .where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.economy == ECONOMY_TELEGRAM,
        )
    )
    merc_n = await session.scalar(
        select(func.count()).select_from(m.HiredWaifu).where(m.HiredWaifu.player_id == player_id)
    )
    gold = await session.scalar(select(m.Player.gold).where(m.Player.id == player_id))
    return int(mw or 0) * 1_000_003 + int(inv_n or 0) * 97 + int(merc_n or 0) * 13 + int(gold or 0)


async def rebuild_client_snapshot(session: AsyncSession, player_id: int) -> m.PlayerClientSnapshot:
    player = (
        await session.execute(
            select(m.Player)
            .options(selectinload(m.Player.main_waifu))
            .where(m.Player.id == player_id)
        )
    ).scalar_one_or_none()
    if not player:
        raise ValueError("player_not_found")

    mw = player.main_waifu
    hub = {
        "player_id": player.id,
        "username": player.username,
        "act": int(player.current_act or 1),
        "max_act": int(player.max_act or 1),
        "gold": int(player.gold or 0),
        "has_main_waifu": mw is not None,
        "waifu": None,
    }
    if mw is not None:
        hub["waifu"] = {
            "id": mw.id,
            "name": mw.name,
            "level": int(mw.level or 1),
            "current_hp": int(mw.current_hp or 0),
            "max_hp": int(mw.max_hp or 0),
            "race": mw.race,
            "class": mw.class_,
            "portrait_url": main_waifu_profile_portrait_url(mw, player_id),
            "paperdoll_url": main_waifu_profile_paperdoll_url(mw, player_id),
        }

    inv_rows = (
        await session.execute(
            select(m.InventoryItem).where(
                m.InventoryItem.player_id == player_id,
                m.InventoryItem.economy == ECONOMY_TELEGRAM,
            )
        )
    ).scalars().all()

    loadout = []
    bag_summary = []
    for it in inv_rows:
        card = {
            "id": it.id,
            "name": getattr(it, "name", None) or f"item#{it.id}",
            "slot_type": it.slot_type,
            "equipment_slot": it.equipment_slot,
            "level": int(it.level or 1),
            "rarity": int(it.rarity or 1),
            "is_legendary": bool(it.is_legendary),
        }
        if it.equipment_slot:
            loadout.append(card)
        else:
            bag_summary.append(card)

    chronicle_lite = {}
    try:
        from waifu_bot.services.delve import lite_showcase, list_companions, companion_out

        chronicle_lite = await lite_showcase(session, player_id)
        companions = [companion_out(c) for c in await list_companions(session, player_id)]
        chronicle_lite["companions"] = companions
    except Exception:
        logger.debug("delve lite snapshot failed", exc_info=True)
        companions = []

    rev = await _source_revision(session, player_id)
    snap = await session.get(m.PlayerClientSnapshot, player_id)
    if not snap:
        snap = m.PlayerClientSnapshot(player_id=player_id)
        session.add(snap)

    snap.hub_json = hub
    snap.loadout_json = {"economy": ECONOMY_TELEGRAM, "items": loadout}
    snap.inventory_summary_json = {
        "economy": ECONOMY_TELEGRAM,
        "equipped_count": len(loadout),
        "bag_count": len(bag_summary),
        "bag_preview": bag_summary[:40],
    }
    snap.mercenaries_summary_json = {
        "count": len(chronicle_lite.get("companions") or []),
        "chronicle": chronicle_lite,
        "delve": chronicle_lite,
        "items": chronicle_lite.get("companions") or [],
    }
    snap.source_revision = rev
    snap.revision = int(snap.revision or 0) + 1
    snap.updated_at = _utc_now()
    await session.flush()
    return snap


async def get_or_build_client_snapshot(
    session: AsyncSession,
    player_id: int,
    *,
    force: bool = False,
) -> dict:
    snap = await session.get(m.PlayerClientSnapshot, player_id)
    current_rev = await _source_revision(session, player_id)
    stale = (
        snap is None
        or force
        or snap.source_revision is None
        or int(snap.source_revision) != current_rev
    )
    if stale:
        try:
            snap = await rebuild_client_snapshot(session, player_id)
            await session.commit()
        except Exception:
            logger.exception("rebuild_client_snapshot failed player_id=%s", player_id)
            await session.rollback()
            if snap is None:
                raise

    return {
        "player_id": player_id,
        "revision": int(snap.revision or 0),
        "source_revision": int(snap.source_revision or 0) if snap.source_revision is not None else None,
        "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
        "economy": normalize_economy(ECONOMY_TELEGRAM),
        "hub": snap.hub_json or {},
        "loadout": snap.loadout_json or {},
        "inventory_summary": snap.inventory_summary_json or {},
        "mercenaries_summary": snap.mercenaries_summary_json or {},
    }
