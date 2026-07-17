"""Grant activity-economy starter gear (shared Steam / Mobile catalog)."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.economy import ECONOMY_ACTIVITY

logger = logging.getLogger(__name__)

STARTER_SLUG = "activity_starter_dagger"


async def ensure_activity_starter_gear(session: AsyncSession, player_id: int) -> m.InventoryItem | None:
    """
    Ensure the player has the activity starter dagger equipped in slot 1.
    Idempotent: if any activity weapon already exists, do nothing.
    """
    existing = await session.execute(
        select(m.InventoryItem).where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.economy == ECONOMY_ACTIVITY,
            m.InventoryItem.slot_type.in_(("weapon_1h", "weapon_2h")),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        return None

    tmpl = (
        await session.execute(
            select(m.ActivityItemTemplate).where(m.ActivityItemTemplate.slug == STARTER_SLUG)
        )
    ).scalar_one_or_none()
    if not tmpl:
        logger.warning("activity starter template %s missing — run migrations", STARTER_SLUG)
        return None

    # Need a placeholder Item row for FK; reuse/create a catalog stub.
    item_row = (
        await session.execute(select(m.Item).where(m.Item.name == tmpl.name).limit(1))
    ).scalar_one_or_none()
    if not item_row:
        item_row = m.Item(
            name=tmpl.name,
            description="Стартовое оружие режима Activity (шаги / клики).",
            rarity=1,
            tier=1,
            level=1,
            item_type=1,
            damage=int(tmpl.damage_max),
            attack_speed=int(tmpl.attack_speed),
            weapon_type=tmpl.weapon_type,
            attack_type=tmpl.attack_type,
            required_level=int(tmpl.required_level),
            base_value=1,
            is_legendary=False,
        )
        session.add(item_row)
        await session.flush()

    # Unequip any activity item already in slot 1 (should be none for new players).
    slot1 = await session.execute(
        select(m.InventoryItem).where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.economy == ECONOMY_ACTIVITY,
            m.InventoryItem.equipment_slot == 1,
        )
    )
    for it in slot1.scalars().all():
        it.equipment_slot = None

    inv = m.InventoryItem(
        player_id=player_id,
        item_id=item_row.id,
        rarity=1,
        tier=1,
        level=1,
        power_rank=0,
        base_level=1,
        total_level=1,
        plus_level_source=0,
        is_legendary=False,
        damage_min=int(tmpl.damage_min),
        damage_max=int(tmpl.damage_max),
        attack_speed=int(tmpl.attack_speed),
        attack_type=tmpl.attack_type,
        weapon_type=tmpl.weapon_type,
        base_stat=tmpl.base_stat,
        base_stat_value=tmpl.base_stat_value,
        slot_type=tmpl.slot_type,
        equipment_slot=1,
        economy=ECONOMY_ACTIVITY,
        requirements={"level": int(tmpl.required_level)},
    )
    session.add(inv)
    await session.flush()
    logger.info("Granted activity starter gear to player %s (inv=%s)", player_id, inv.id)
    return inv
