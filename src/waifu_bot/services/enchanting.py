"""Enchanting (+1..+10): flat steps, risk after safe_max, protection stone."""
from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.hidden_skills import increment_skill_counter


def secondary_bonus_value_for_enchant_step(
    secondary_bonus_type: str | None, secondary_bonus_value: float
) -> float:
    """Целочисленные бонусы к пассивам не должны давать шаг зачарки как у долей crit/exp."""
    t = str(secondary_bonus_type or "").strip().lower()
    if t.startswith("passive_node_level_add:") or t.startswith("passive_branch_level_add:"):
        return 0.0
    if t == "passive_all_nodes_level_add":
        return 0.0
    return float(secondary_bonus_value or 0.0)


def calculate_enchant_steps(
    dmg_min: int | None,
    dmg_max: int | None,
    armor_base: int,
    secondary_bonus_value: float,
    cfg: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compute fixed enchant steps from base stats (call once when item is created)."""
    c = cfg or {}
    dmg_ratio = cfg_float(c, "enchant.dmg_ratio", 0.15)
    arm_ratio = cfg_float(c, "enchant.arm_ratio", 0.12)
    sec_ratio = cfg_float(c, "enchant.sec_ratio", 0.20)

    lo = int(dmg_min or 0)
    hi = int(dmg_max or 0)
    if hi < lo:
        lo, hi = hi, lo
    avg_dmg = (lo + hi) / 2.0 if (lo > 0 or hi > 0) else 0.0
    enchant_dmg_step = max(1, round(avg_dmg * dmg_ratio)) if avg_dmg > 0 else 0

    ab = max(0, int(armor_base))
    enchant_arm_step = max(1, round(ab * arm_ratio)) if ab > 0 else 0

    sec = float(secondary_bonus_value or 0.0)
    enchant_sec_step = round(sec * sec_ratio, 4) if sec else 0.0

    return {
        "enchant_dmg_step": int(enchant_dmg_step),
        "enchant_arm_step": int(enchant_arm_step),
        "enchant_sec_step": float(enchant_sec_step),
    }


def get_effective_params(
    inv: Any,
    armor_base: int = 0,
    secondary_bonus_value: float = 0.0,
) -> dict[str, Any]:
    """Effective combat/display stats including enchant (broken items use 0)."""
    e = int(inv.enchant_level or 0) if not bool(inv.is_broken) else 0
    dm = inv.damage_min
    dx = inv.damage_max
    lo = int(dm) if dm is not None else None
    hi = int(dx) if dx is not None else None
    ds = int(inv.enchant_dmg_step or 0)
    if lo is not None:
        lo = lo + ds * e
    if hi is not None:
        hi = hi + ds * e
    arm = max(0, int(armor_base)) + int(inv.enchant_arm_step or 0) * e
    sec = float(secondary_bonus_value or 0.0) + float(inv.enchant_sec_step or 0.0) * e
    return {
        "damage_min": lo,
        "damage_max": hi,
        "armor": int(arm),
        "secondary": float(sec),
        "enchant_level": e,
    }


async def _fetch_template_stats(session: AsyncSession, inv: m.InventoryItem) -> tuple[int, float, str | None]:
    item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
    tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
    if not item_name or tier <= 0:
        return 0, 0.0, None
    row = (
        await session.execute(
            text(
                """
                SELECT armor_base,
                       COALESCE(secondary_bonus_value, 0.0) AS secondary_bonus_value,
                       secondary_bonus_type
                FROM item_base_templates
                WHERE name = :name AND tier = :tier
                LIMIT 1
                """
            ),
            {"name": item_name, "tier": tier},
        )
    ).mappings().first()
    if not row:
        return 0, 0.0, None
    return (
        int(getattr(row, "armor_base", 0) or 0),
        float(getattr(row, "secondary_bonus_value", 0.0) or 0.0),
        getattr(row, "secondary_bonus_type", None),
    )


async def apply_enchant_steps_to_inventory_item(session: AsyncSession, inv: m.InventoryItem) -> None:
    """Fill enchant_*_step fields on a freshly created inventory row."""
    cfg = await get_game_config_map(session)
    armor_base, sec_val, sec_type = await _fetch_template_stats(session, inv)
    sec_for_step = secondary_bonus_value_for_enchant_step(sec_type, sec_val)
    steps = calculate_enchant_steps(
        inv.damage_min,
        inv.damage_max,
        armor_base,
        sec_for_step,
        cfg=cfg,
    )
    inv.enchant_dmg_step = int(steps["enchant_dmg_step"])
    inv.enchant_arm_step = int(steps["enchant_arm_step"])
    inv.enchant_sec_step = float(steps["enchant_sec_step"])
    inv.enchant_level = int(getattr(inv, "enchant_level", 0) or 0)
    inv.is_broken = bool(getattr(inv, "is_broken", False))


def _inventory_rarity(inv: m.InventoryItem) -> int:
    try:
        if inv.rarity is not None:
            return max(1, min(5, int(inv.rarity)))
    except (TypeError, ValueError):
        pass
    try:
        if inv.item and inv.item.rarity is not None:
            return max(1, min(5, int(inv.item.rarity)))
    except (TypeError, ValueError):
        pass
    return 1


def _inventory_item_level(inv: m.InventoryItem) -> int:
    try:
        tl = int(getattr(inv, "total_level", 0) or 0)
        if tl > 0:
            return max(1, tl)
    except (TypeError, ValueError):
        pass
    try:
        if inv.level is not None:
            return max(1, int(inv.level))
    except (TypeError, ValueError):
        pass
    try:
        if inv.item and inv.item.level is not None:
            return max(1, int(inv.item.level))
    except (TypeError, ValueError):
        pass
    return 1


def enchant_cost_gold(
    base_value: int,
    current_enchant_level: int,
    cfg: dict[str, str],
    *,
    item_rarity: int | None = None,
    item_level: int | None = None,
) -> int:
    """Gold cost for next attempt: base × (current+1) × ratio × rarity × item level (min 1)."""
    ratio = cfg_float(cfg, "enchant.cost_ratio", 0.1)
    nxt = max(1, int(current_enchant_level) + 1)
    base = max(1, int(base_value))
    r = max(1, min(5, int(item_rarity or 1)))
    rarity_defaults = {1: 1.0, 2: 1.12, 3: 1.28, 4: 1.48, 5: 1.72}
    rarity_mult = cfg_float(cfg, f"enchant.rarity_cost_mult_{r}", rarity_defaults.get(r, 1.0))
    lv = max(1, int(item_level or 1))
    level_base = cfg_float(cfg, "enchant.item_level_cost_base", 1.0)
    level_per = cfg_float(cfg, "enchant.item_level_cost_per", 0.02)
    level_mult = max(0.25, level_base + (lv - 1) * level_per)
    return max(1, int(round(base * nxt * ratio * rarity_mult * level_mult)))


async def enchant_inventory_item(
    session: AsyncSession,
    inventory_item_id: int,
    player_id: int,
    use_protection_stone: bool,
) -> dict[str, Any]:
    """Attempt +1 enchant. Deducts gold; optionally consumes protection stone on risky failure."""
    cfg = await get_game_config_map(session)
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(inventory_item_id), m.InventoryItem.player_id == int(player_id))
    )
    if not inv or not inv.item:
        return {"error": "not_found"}
    if bool(inv.is_broken):
        return {"error": "item_is_broken"}
    cur = int(inv.enchant_level or 0)
    if cur >= 10:
        return {"error": "enchant_max_reached"}

    player = await session.get(m.Player, int(player_id))
    if not player:
        return {"error": "not_found"}

    cost = enchant_cost_gold(
        int(inv.item.base_value or 0),
        cur,
        cfg,
        item_rarity=_inventory_rarity(inv),
        item_level=_inventory_item_level(inv),
    )
    if int(player.gold or 0) < cost:
        return {"error": "insufficient_gold", "required": cost, "have": int(player.gold or 0)}

    target = cur + 1
    safe_max = cfg_int(cfg, "enchant.safe_max", 7)

    if use_protection_stone:
        if int(getattr(player, "protection_stones", 0) or 0) < 1:
            return {"error": "no_protection_stone"}
        if target < 8:
            return {"error": "stone_not_needed"}

    # Pay gold
    player.gold = int(player.gold or 0) - cost

    if cur < safe_max:
        inv.enchant_level = target
        if target == 5:
            await increment_skill_counter(session, player_id, "enchant_5plus", 1)
        await session.commit()
        return {
            "success": True,
            "new_level": target,
            "broken": False,
            "stone_used": False,
            "gold_paid": cost,
            "gold_remaining": int(player.gold or 0),
        }

    chances = {
        8: cfg_float(cfg, "enchant.chance_8", 0.70),
        9: cfg_float(cfg, "enchant.chance_9", 0.50),
        10: cfg_float(cfg, "enchant.chance_10", 0.30),
    }
    chance = float(chances.get(target, 0.30))
    roll = random.random()

    if roll < chance:
        inv.enchant_level = target
        if target == 5:
            await increment_skill_counter(session, player_id, "enchant_5plus", 1)
        await session.commit()
        return {
            "success": True,
            "new_level": target,
            "broken": False,
            "stone_used": False,
            "gold_paid": cost,
            "gold_remaining": int(player.gold or 0),
        }

    # Failure
    if use_protection_stone:
        player.protection_stones = max(0, int(player.protection_stones or 0) - 1)
        inv.enchant_level = 6
        await session.commit()
        return {
            "success": False,
            "new_level": 6,
            "broken": False,
            "stone_used": True,
            "gold_paid": cost,
            "gold_remaining": int(player.gold or 0),
        }

    if target == 10:
        # Нет починки: при поломке предмет полностью удаляется из инвентаря (в т.ч. с экипа).
        await session.delete(inv)
        await session.commit()
        return {
            "success": False,
            "new_level": 0,
            "broken": True,
            "removed": True,
            "stone_used": False,
            "gold_paid": cost,
            "gold_remaining": int(player.gold or 0),
        }

    rollback = 7 if target == 8 else 6
    inv.enchant_level = rollback
    await session.commit()
    return {
        "success": False,
        "new_level": rollback,
        "broken": False,
        "stone_used": False,
        "gold_paid": cost,
        "gold_remaining": int(player.gold or 0),
    }


async def build_enchant_preview(session: AsyncSession, inventory_item_id: int, player_id: int) -> dict[str, Any]:
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(inventory_item_id), m.InventoryItem.player_id == int(player_id))
    )
    if not inv or not inv.item:
        return {"error": "not_found"}

    cfg = await get_game_config_map(session)
    armor_base, sec_val, _sec_type = await _fetch_template_stats(session, inv)
    cur = int(inv.enchant_level or 0)
    if bool(inv.is_broken):
        cur = 0
    if int(inv.enchant_level or 0) >= 10 and not bool(inv.is_broken):
        return {"error": "enchant_max_reached"}
    target = cur + 1
    safe_max = cfg_int(cfg, "enchant.safe_max", 7)

    eff_cur = get_effective_params(inv, armor_base=armor_base, secondary_bonus_value=sec_val)
    inv_next = SimpleNamespace(
        enchant_level=target,
        is_broken=False,
        damage_min=inv.damage_min,
        damage_max=inv.damage_max,
        enchant_dmg_step=inv.enchant_dmg_step,
        enchant_arm_step=inv.enchant_arm_step,
        enchant_sec_step=inv.enchant_sec_step,
    )
    eff_tgt = get_effective_params(inv_next, armor_base=armor_base, secondary_bonus_value=sec_val)

    is_risky = cur >= safe_max
    chance: float | None = None
    if is_risky and target >= 8:
        chances = {
            8: cfg_float(cfg, "enchant.chance_8", 0.70),
            9: cfg_float(cfg, "enchant.chance_9", 0.50),
            10: cfg_float(cfg, "enchant.chance_10", 0.30),
        }
        chance = float(chances.get(target, 0.30))

    cost = enchant_cost_gold(
        int(inv.item.base_value or 0),
        cur,
        cfg,
        item_rarity=_inventory_rarity(inv),
        item_level=_inventory_item_level(inv),
    )
    on_fail = "—"
    if is_risky:
        if target == 10:
            on_fail = "поломка (без камня) или откат до +6 (с камнем)"
        elif target == 8:
            on_fail = "откат до +7"
        else:
            on_fail = "откат до +6"

    return {
        "current_level": cur,
        "target_level": target,
        "chance": chance,
        "is_risky": is_risky,
        "is_broken": bool(inv.is_broken),
        "enchant_cost_gold": cost,
        "on_fail_hint": on_fail,
        "current_params": {
            "damage_min": eff_cur["damage_min"],
            "damage_max": eff_cur["damage_max"],
            "armor": eff_cur["armor"],
            "secondary": eff_cur["secondary"],
        },
        "target_params": {
            "damage_min": eff_tgt["damage_min"],
            "damage_max": eff_tgt["damage_max"],
            "armor": eff_tgt["armor"],
            "secondary": eff_tgt["secondary"],
        },
    }
