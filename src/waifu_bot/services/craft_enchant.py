"""Craft-enchant: add / reroll / upgrade fraction secondaries for dust."""

from __future__ import annotations

import math
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.enchanting import recalculate_enchant_steps, roll_awakened_fraction
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map

CraftOperation = Literal["add", "reroll", "upgrade"]


def _item_tier(inv: m.InventoryItem) -> int:
    try:
        t = int(inv.tier or (inv.item.tier if inv.item else 1) or 1)
        return max(1, min(10, t))
    except (TypeError, ValueError):
        return 1


def fraction_cap_for_tier(tier: int, cfg: dict[str, str]) -> float:
    t = max(1, min(10, int(tier)))
    for probe in (t, 5, 10):
        key = f"craft.sec_value_cap_by_tier.{probe}"
        cap = cfg_float(cfg, key, 0.0)
        if cap > 0:
            if probe >= t:
                return cap
    return cfg_float(cfg, "craft.sec_value_cap_by_tier.10", 0.035)


def craft_operation_cost_dust(operation: CraftOperation, tier: int, cfg: dict[str, str]) -> int:
    t = max(1, min(10, int(tier)))
    if operation == "add":
        return max(1, int(cfg_float(cfg, "craft.add_dust_base", 40)))
    mult = cfg_float(
        cfg,
        "craft.reroll_dust_mult" if operation == "reroll" else "craft.upgrade_dust_mult",
        18.0 if operation == "reroll" else 12.0,
    )
    base = cfg_float(cfg, "craft.add_dust_base", 40)
    return max(1, int(round(base * t * mult / 10.0)))


async def build_craft_enchant_preview(
    session: AsyncSession,
    inv: m.InventoryItem,
) -> dict[str, Any]:
    cfg = await get_game_config_map(session)
    tier = _item_tier(inv)
    has_fraction = bool(inv.secondary_fraction_type) and float(inv.secondary_fraction_value or 0) > 0
    cap = fraction_cap_for_tier(tier, cfg)
    return {
        "has_fraction": has_fraction,
        "secondary_fraction_type": inv.secondary_fraction_type,
        "secondary_fraction_value": float(inv.secondary_fraction_value or 0),
        "fraction_cap": cap,
        "costs": {
            "add": craft_operation_cost_dust("add", tier, cfg) if not has_fraction else None,
            "reroll": craft_operation_cost_dust("reroll", tier, cfg) if has_fraction else None,
            "upgrade": craft_operation_cost_dust("upgrade", tier, cfg) if has_fraction else None,
        },
        "enchant_sec_step": float(inv.enchant_sec_step or 0.0),
    }


async def craft_enchant_inventory_item(
    session: AsyncSession,
    inventory_item_id: int,
    player_id: int,
    operation: CraftOperation,
    *,
    target: str = "fraction",
) -> dict[str, Any]:
    if target != "fraction":
        return {"error": "invalid_target"}

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

    player = await session.get(m.Player, int(player_id))
    if not player:
        return {"error": "not_found"}

    cfg = await get_game_config_map(session)
    tier = _item_tier(inv)
    has_fraction = bool(inv.secondary_fraction_type) and float(inv.secondary_fraction_value or 0) > 0

    if operation == "add":
        if has_fraction:
            return {"error": "fraction_already_exists"}
    elif operation in ("reroll", "upgrade"):
        if not has_fraction:
            return {"error": "no_fraction_to_modify"}
    else:
        return {"error": "invalid_operation"}

    dust_cost = craft_operation_cost_dust(operation, tier, cfg)
    have = int(getattr(player, "enchant_dust", 0) or 0)
    if have < dust_cost:
        return {"error": "insufficient_dust", "required": dust_cost, "have": have}

    if operation == "add":
        typ, val = roll_awakened_fraction(inv, cfg)
        inv.secondary_fraction_type = typ
        inv.secondary_fraction_value = val
    elif operation == "reroll":
        typ, val = roll_awakened_fraction(inv, cfg)
        inv.secondary_fraction_type = typ
        inv.secondary_fraction_value = val
    else:
        step = cfg_float(cfg, "craft.sec_upgrade_step", 0.002)
        cap = fraction_cap_for_tier(tier, cfg)
        new_val = min(cap, float(inv.secondary_fraction_value or 0) + step)
        inv.secondary_fraction_value = round(new_val, 4)

    player.enchant_dust = have - dust_cost
    await recalculate_enchant_steps(session, inv)
    await session.commit()

    return {
        "success": True,
        "operation": operation,
        "secondary_fraction_type": inv.secondary_fraction_type,
        "secondary_fraction_value": float(inv.secondary_fraction_value or 0),
        "dust_spent": dust_cost,
        "enchant_dust": int(player.enchant_dust or 0),
        "enchant_sec_step": float(inv.enchant_sec_step or 0.0),
    }
