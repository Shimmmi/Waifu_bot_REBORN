"""Dismantle inventory items into enchant dust."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map

BULK_MAX_RARITY = 5
RAID_RARITY_MIN = 6
BulkAction = Literal["sell", "dismantle"]


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
    inv_id = int(inv.id)
    await session.delete(inv)
    from waifu_bot.services import wallet as wallet_svc

    await wallet_svc.add(
        session,
        int(player_id),
        "enchant_dust",
        dust,
        source="dismantle",
        ref_type="inventory_item",
        ref_id=inv_id,
    )
    await session.commit()
    return {
        "success": True,
        "dust_received": dust,
        "enchant_dust": await wallet_svc.get_amount(session, int(player_id), "enchant_dust"),
    }


def bulk_item_rarity(inv: Any) -> int:
    """Instance rarity, then catalog ``item.rarity``, then common."""
    raw = getattr(inv, "rarity", None)
    if raw is None:
        item = getattr(inv, "item", None)
        raw = getattr(item, "rarity", None) if item is not None else None
    try:
        return int(raw or 1)
    except (TypeError, ValueError):
        return 1


def bulk_item_tier(inv: Any) -> int:
    raw = getattr(inv, "tier", None)
    if raw is None:
        item = getattr(inv, "item", None)
        raw = getattr(item, "tier", None) if item is not None else None
    try:
        return max(1, int(raw or 1))
    except (TypeError, ValueError):
        return 1


def is_raid_rarity(rarity: int) -> bool:
    return int(rarity) >= RAID_RARITY_MIN


def item_is_locked(inv: Any) -> bool:
    return bool(getattr(inv, "is_locked", False))


def is_bulk_candidate(inv: Any, max_rarity: int) -> bool:
    """Unequipped, unlocked, not raid, rarity within the threshold."""
    if getattr(inv, "equipment_slot", None) is not None:
        return False
    if item_is_locked(inv):
        return False
    r = bulk_item_rarity(inv)
    if is_raid_rarity(r):
        return False
    return r <= max(1, min(BULK_MAX_RARITY, int(max_rarity)))


def select_bulk_items(
    items: list[Any],
    max_rarity: int,
    *,
    shop_ids: set[int] | None = None,
    skip_shop: bool = False,
) -> list[Any]:
    shop = shop_ids or set()
    out: list[Any] = []
    for inv in items:
        if not is_bulk_candidate(inv, max_rarity):
            continue
        if skip_shop and int(getattr(inv, "id", 0) or 0) in shop:
            continue
        out.append(inv)
    return out


def _empty_bulk_cell() -> dict[str, int]:
    return {
        "count": 0,
        "gold_total": 0,
        "dismantle_count": 0,
        "dust_total": 0,
        "legendary_count": 0,
        "dismantle_legendary_count": 0,
    }


def summarize_bulk_cells(
    items: list[Any],
    *,
    shop_ids: set[int] | None = None,
    price_fn: Callable[[Any], int],
    cfg: dict[str, str],
) -> dict[str, dict[str, int]]:
    """Build threshold 1..5 cells from an already-loaded bag (no I/O)."""
    shop = {int(x) for x in (shop_ids or set())}
    cells: dict[str, dict[str, int]] = {str(r): _empty_bulk_cell() for r in range(1, BULK_MAX_RARITY + 1)}
    for max_r in range(1, BULK_MAX_RARITY + 1):
        sell_items = select_bulk_items(items, max_r)
        dust_items = select_bulk_items(items, max_r, shop_ids=shop, skip_shop=True)
        gold = 0
        for inv in sell_items:
            gold += max(1, int(price_fn(inv) or 0))
        dust = 0
        for inv in dust_items:
            dust += calculate_dismantle_dust(
                rarity=bulk_item_rarity(inv),
                tier=bulk_item_tier(inv),
                cfg=cfg,
            )
        cell = cells[str(max_r)]
        cell["count"] = len(sell_items)
        cell["gold_total"] = gold
        cell["dismantle_count"] = len(dust_items)
        cell["dust_total"] = dust
        if max_r >= 5:
            cell["legendary_count"] = sum(1 for inv in sell_items if bulk_item_rarity(inv) == 5)
            cell["dismantle_legendary_count"] = sum(
                1 for inv in dust_items if bulk_item_rarity(inv) == 5
            )
    return cells


def inventory_item_base_value(inv: Any) -> int:
    item = getattr(inv, "item", None)
    if item is not None and getattr(item, "base_value", None) is not None:
        return max(1, int(item.base_value))
    return max(1, 100 * bulk_item_tier(inv) * bulk_item_rarity(inv))


async def _load_unequipped_bag(session: AsyncSession, player_id: int) -> list[m.InventoryItem]:
    rows = (
        await session.execute(
            select(m.InventoryItem)
            .options(selectinload(m.InventoryItem.item))
            .where(
                m.InventoryItem.player_id == int(player_id),
                m.InventoryItem.equipment_slot.is_(None),
            )
        )
    ).scalars().all()
    return list(rows or [])


async def active_shop_inventory_ids(session: AsyncSession, item_ids: list[int]) -> set[int]:
    ids = [int(x) for x in item_ids if x]
    if not ids:
        return set()
    rows = (
        await session.execute(
            select(m.ShopOffer.inventory_item_id).where(
                m.ShopOffer.inventory_item_id.in_(ids),
                m.ShopOffer.purchased.is_(False),
            )
        )
    ).scalars().all()
    return {int(x) for x in rows if x is not None}


async def bulk_sell_price_fn(session: AsyncSession, player_id: int) -> Callable[[Any], int]:
    """Same gold as single sell, with charm/passives loaded once."""
    from waifu_bot.game.formulas import SHOP_SELL_VS_BUY_RATIO, shop_buy_price_from_merchant_discount
    from waifu_bot.services.passive_skills import (
        compute_passive_buy_price_from_bonuses,
        get_passive_skill_bonuses,
        merchant_discount_pct_for_player,
    )

    disc = await merchant_discount_pct_for_player(session, int(player_id))
    try:
        ps = await get_passive_skill_bonuses(session, int(player_id))
    except Exception:
        ps = {}
    hs: dict[str, float] | None = None
    try:
        from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses

        hs = await get_hidden_skill_bonuses(session, int(player_id))
    except Exception:
        hs = None

    def price_for(inv: Any) -> int:
        raw_buy = shop_buy_price_from_merchant_discount(inventory_item_base_value(inv), disc)
        anchor = compute_passive_buy_price_from_bonuses(raw_buy, ps, hs)
        return max(1, int(anchor * SHOP_SELL_VS_BUY_RATIO))

    return price_for


async def build_bulk_matrix(session: AsyncSession, player_id: int) -> dict[str, Any]:
    items = await _load_unequipped_bag(session, int(player_id))
    shop_ids = await active_shop_inventory_ids(session, [int(i.id) for i in items])
    cfg = await get_game_config_map(session)
    price_fn = await bulk_sell_price_fn(session, int(player_id))
    return {"cells": summarize_bulk_cells(items, shop_ids=shop_ids, price_fn=price_fn, cfg=cfg)}


async def bulk_dispose(
    session: AsyncSession,
    player_id: int,
    *,
    action: str,
    max_rarity: int,
) -> dict[str, Any]:
    act = str(action or "").strip().lower()
    if act not in ("sell", "dismantle"):
        return {"error": "invalid_action"}
    try:
        cap = int(max_rarity)
    except (TypeError, ValueError):
        return {"error": "invalid_rarity"}
    if cap < 1 or cap > BULK_MAX_RARITY:
        return {"error": "invalid_rarity"}

    player = await session.get(m.Player, int(player_id))
    if not player:
        return {"error": "not_found"}

    items = await _load_unequipped_bag(session, int(player_id))
    shop_ids = await active_shop_inventory_ids(session, [int(i.id) for i in items])
    skip_shop = act == "dismantle"
    selected = select_bulk_items(items, cap, shop_ids=shop_ids, skip_shop=skip_shop)

    skipped = {
        "raid": sum(1 for inv in items if is_raid_rarity(bulk_item_rarity(inv))),
        "shop": (
            sum(1 for inv in items if int(inv.id) in shop_ids and is_bulk_candidate(inv, cap))
            if skip_shop
            else 0
        ),
        "equipped": 0,
        "locked": sum(
            1
            for inv in items
            if item_is_locked(inv)
            and getattr(inv, "equipment_slot", None) is None
            and not is_raid_rarity(bulk_item_rarity(inv))
            and bulk_item_rarity(inv) <= cap
        ),
    }

    legendary_count = sum(1 for inv in selected if bulk_item_rarity(inv) == 5)

    from waifu_bot.services import wallet as wallet_svc

    if act == "sell":
        price_fn = await bulk_sell_price_fn(session, int(player_id))
        total_gold = 0
        for inv in selected:
            total_gold += max(1, int(price_fn(inv) or 0))
            await session.delete(inv)
        if total_gold > 0:
            await wallet_svc.add_gold(
                session,
                player,
                int(total_gold),
                source="shop_sell",
                ref_type="bulk_sell",
                ref_id=int(player_id),
            )
        await session.commit()
        return {
            "success": True,
            "action": "sell",
            "count": len(selected),
            "gold_received": int(total_gold),
            "gold_remaining": int(getattr(player, "gold", 0) or 0),
            "legendary_count": legendary_count,
            "skipped": skipped,
        }

    cfg = await get_game_config_map(session)
    total_dust = 0
    for inv in selected:
        total_dust += calculate_dismantle_dust(
            rarity=bulk_item_rarity(inv),
            tier=bulk_item_tier(inv),
            cfg=cfg,
        )
        await session.delete(inv)
    if total_dust > 0:
        await wallet_svc.add(
            session,
            int(player_id),
            "enchant_dust",
            int(total_dust),
            source="dismantle",
            ref_type="bulk_dismantle",
            ref_id=int(player_id),
        )
    await session.commit()
    return {
        "success": True,
        "action": "dismantle",
        "count": len(selected),
        "dust_received": int(total_dust),
        "enchant_dust": await wallet_svc.get_amount(session, int(player_id), "enchant_dust"),
        "legendary_count": legendary_count,
        "skipped": skipped,
    }
