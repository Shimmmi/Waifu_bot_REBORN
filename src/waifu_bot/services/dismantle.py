"""Dismantle inventory items into enchant dust."""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map


def calculate_dismantle_dust(
    *,
    rarity: int,
    tier: int,
    cfg: dict[str, str],
) -> int:
    """Dust from dismantle: base × rarity_mult × tier_mult^(tier-1). Enchant does not affect dust."""
    base = cfg_float(cfg, "dismantle.dust_base", 5.0)
    r = max(1, min(5, int(rarity or 1)))
    rarity_mult = cfg_float(cfg, f"dismantle.rarity_mult_{r}", 1.0)
    t = max(1, min(10, int(tier or 1)))
    tier_mult_base = cfg_float(cfg, "dismantle.tier_mult", 1.2)
    tier_mult = tier_mult_base ** (t - 1)
    dust = base * rarity_mult * tier_mult
    return max(1, int(math.floor(dust)))


async def _item_in_active_shop_offer(session: AsyncSession, inventory_item_id: int) -> bool:
    row = (
        await session.execute(
            select(m.ShopOffer.id).where(
                m.ShopOffer.inventory_item_id == int(inventory_item_id),
                m.ShopOffer.purchased.is_(False),
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def preview_dismantle_dust(session: AsyncSession, inv: m.InventoryItem) -> int:
    cfg = await get_game_config_map(session)
    rarity = int(inv.rarity or (inv.item.rarity if inv.item else 1) or 1)
    tier = int(inv.tier or (inv.item.tier if inv.item else 1) or 1)
    return calculate_dismantle_dust(
        rarity=rarity,
        tier=tier,
        cfg=cfg,
    )


async def dismantle_inventory_item(
    session: AsyncSession,
    inventory_item_id: int,
    player_id: int,
) -> dict[str, Any]:
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(
            m.InventoryItem.id == int(inventory_item_id),
            m.InventoryItem.player_id == int(player_id),
        )
    )
    if not inv:
        return {"error": "not_found"}
    if inv.equipment_slot is not None:
        return {"error": "item_equipped"}
    if inv.player_id is None:
        return {"error": "not_owned"}
    if await _item_in_active_shop_offer(session, inv.id):
        return {"error": "item_in_shop"}

    player = await session.get(m.Player, int(player_id))
    if not player:
        return {"error": "not_found"}

    dust = await preview_dismantle_dust(session, inv)
    await session.delete(inv)
    player.enchant_dust = int(getattr(player, "enchant_dust", 0) or 0) + dust
    await session.commit()
    return {
        "success": True,
        "dust_received": dust,
        "enchant_dust": int(player.enchant_dust or 0),
    }
