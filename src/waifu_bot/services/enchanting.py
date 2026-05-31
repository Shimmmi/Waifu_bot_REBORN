"""Enchanting (+1..+10): flat steps, risk after safe_max, protection stone, fraction awaken."""
from __future__ import annotations

import random
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.item_secondary import (
    FRACTION_SECONDARIES,
    attach_resolved_attrs,
    effective_fraction_combat,
    effective_fraction_for_enchant,
    is_accessory_slot,
    is_passive_secondary_type,
    resolve_item_secondaries,
    should_awaken_fraction_on_plus_one,
    snapshot_secondaries_from_template,
    template_row_from_mapping,
)
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.hidden_skills import (
    get_hidden_skill_bonuses,
    increment_skill_counter,
    record_hidden_gold_spend,
)


def secondary_bonus_value_for_enchant_step(
    secondary_bonus_type: str | None, secondary_bonus_value: float
) -> float:
    """Passive secondaries must not contribute to enchant_sec_step."""
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


async def _fetch_template_stats(
    session: AsyncSession, inv: m.InventoryItem
) -> tuple[int, float, str | None, Any | None]:
    item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
    tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
    if not item_name or tier <= 0:
        return 0, 0.0, None, None
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
        return 0, 0.0, None, None
    return (
        int(getattr(row, "armor_base", 0) or row.get("armor_base", 0) or 0),
        float(getattr(row, "secondary_bonus_value", 0.0) or row.get("secondary_bonus_value", 0.0) or 0.0),
        getattr(row, "secondary_bonus_type", None) or row.get("secondary_bonus_type"),
        row,
    )


async def _resolve_for_inv(session: AsyncSession, inv: m.InventoryItem):
    armor_base, _, _, tpl_row = await _fetch_template_stats(session, inv)
    template = template_row_from_mapping(tpl_row) if tpl_row else None
    if template and armor_base:
        template = template_row_from_mapping(
            {
                "armor_base": armor_base,
                "secondary_bonus_type": template.secondary_bonus_type,
                "secondary_bonus_value": template.secondary_bonus_value,
            }
        )
    resolved = resolve_item_secondaries(inv, template)
    attach_resolved_attrs(inv, resolved)
    return resolved


async def recalculate_enchant_steps(session: AsyncSession, inv: m.InventoryItem) -> None:
    """Recompute enchant_sec_step after fraction change (awaken / craft)."""
    cfg = await get_game_config_map(session)
    resolved = await _resolve_for_inv(session, inv)
    _, frac_val = effective_fraction_for_enchant(inv, resolved)
    steps = calculate_enchant_steps(
        inv.damage_min,
        inv.damage_max,
        resolved.armor_base,
        frac_val,
        cfg=cfg,
    )
    inv.enchant_sec_step = float(steps["enchant_sec_step"])


async def apply_enchant_steps_to_inventory_item(session: AsyncSession, inv: m.InventoryItem) -> None:
    """Fill enchant_*_step fields on a freshly created inventory row."""
    cfg = await get_game_config_map(session)
    armor_base, _, _, tpl_row = await _fetch_template_stats(session, inv)
    template = template_row_from_mapping(tpl_row) if tpl_row else None
    if template:
        snapshot_secondaries_from_template(inv, template)
    resolved = resolve_item_secondaries(inv, template)
    _, frac_val = effective_fraction_for_enchant(inv, resolved)
    steps = calculate_enchant_steps(
        inv.damage_min,
        inv.damage_max,
        armor_base,
        frac_val,
        cfg=cfg,
    )
    inv.enchant_dmg_step = int(steps["enchant_dmg_step"])
    inv.enchant_arm_step = int(steps["enchant_arm_step"])
    inv.enchant_sec_step = float(steps["enchant_sec_step"])
    inv.enchant_level = int(getattr(inv, "enchant_level", 0) or 0)
    inv.is_broken = bool(getattr(inv, "is_broken", False))


def roll_awakened_fraction(inv: m.InventoryItem, cfg: dict[str, str]) -> tuple[str, float]:
    pool = list(FRACTION_SECONDARIES)
    typ = random.choice(pool)
    tier = max(1, min(10, int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 1)))
    base_min = cfg_float(cfg, "enchant.awaken.base_min", 0.003)
    base_per_tier = cfg_float(cfg, "enchant.awaken.base_per_tier", 0.002)
    val = round(base_min + tier * base_per_tier, 4)
    return typ, val


async def _maybe_awaken_fraction(
    session: AsyncSession,
    inv: m.InventoryItem,
    cfg: dict[str, str],
) -> dict[str, Any] | None:
    resolved = await _resolve_for_inv(session, inv)
    if not should_awaken_fraction_on_plus_one(inv, resolved):
        return None
    typ, val = roll_awakened_fraction(inv, cfg)
    inv.secondary_fraction_type = typ
    inv.secondary_fraction_value = val
    inv.secondary_awakened = True
    await recalculate_enchant_steps(session, inv)
    return {
        "secondary_fraction_type": typ,
        "secondary_fraction_value": val,
        "secondary_awakened": True,
    }


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


async def _commit_enchant_success(
    session: AsyncSession,
    inv: m.InventoryItem,
    player_id: int,
    target: int,
    cost: int,
    player: m.Player,
    cfg: dict[str, str],
    *,
    stone_used: bool = False,
) -> dict[str, Any]:
    inv.enchant_level = target
    awaken_payload: dict[str, Any] | None = None
    if target == 1:
        awaken_payload = await _maybe_awaken_fraction(session, inv, cfg)
    if target == 5:
        await increment_skill_counter(session, player_id, "enchant_5plus", 1)
    await session.commit()
    out: dict[str, Any] = {
        "success": True,
        "new_level": target,
        "broken": False,
        "stone_used": stone_used,
        "gold_paid": cost,
        "gold_remaining": int(player.gold or 0),
    }
    if awaken_payload:
        out["awaken"] = awaken_payload
        out["enchant_sec_step"] = float(inv.enchant_sec_step or 0.0)
    return out


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
    hs_enchant: dict[str, float] = {}
    try:
        hs_enchant = await get_hidden_skill_bonuses(session, int(player_id))
        ec = float(hs_enchant.get("enchant_cost_pct", 0) or 0)
        if ec:
            cost = max(1, int(round(cost * (1.0 + ec / 100.0))))
    except Exception:
        hs_enchant = {}
    if int(player.gold or 0) < cost:
        return {"error": "insufficient_gold", "required": cost, "have": int(player.gold or 0)}

    target = cur + 1
    safe_max = cfg_int(cfg, "enchant.safe_max", 7)

    if use_protection_stone:
        if int(getattr(player, "protection_stones", 0) or 0) < 1:
            return {"error": "no_protection_stone"}
        if target < 8:
            return {"error": "stone_not_needed"}

    player.gold = int(player.gold or 0) - cost
    await record_hidden_gold_spend(player_id)

    if cur < safe_max:
        return await _commit_enchant_success(
            session, inv, player_id, target, cost, player, cfg
        )

    chances = {
        8: cfg_float(cfg, "enchant.chance_8", 0.70),
        9: cfg_float(cfg, "enchant.chance_9", 0.50),
        10: cfg_float(cfg, "enchant.chance_10", 0.30),
    }
    chance = float(chances.get(target, 0.30))
    chb = float(hs_enchant.get("enchant_chance_pct", 0) or 0)
    if chb:
        chance = min(0.99, max(0.01, chance + chb / 100.0))
    roll = random.random()

    if roll < chance:
        return await _commit_enchant_success(
            session, inv, player_id, target, cost, player, cfg
        )

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
    resolved = await _resolve_for_inv(session, inv)
    _, frac_val = effective_fraction_combat(inv, resolved)
    cur = int(inv.enchant_level or 0)
    if bool(inv.is_broken):
        cur = 0
    if int(inv.enchant_level or 0) >= 10 and not bool(inv.is_broken):
        return {"error": "enchant_max_reached"}
    target = cur + 1
    safe_max = cfg_int(cfg, "enchant.safe_max", 7)

    eff_cur = get_effective_params(inv, armor_base=resolved.armor_base, secondary_bonus_value=frac_val)
    inv_next = SimpleNamespace(
        enchant_level=target,
        is_broken=False,
        damage_min=inv.damage_min,
        damage_max=inv.damage_max,
        enchant_dmg_step=inv.enchant_dmg_step,
        enchant_arm_step=inv.enchant_arm_step,
        enchant_sec_step=inv.enchant_sec_step,
    )
    _, frac_next_base = effective_fraction_for_enchant(inv, resolved)
    eff_tgt = get_effective_params(
        inv_next,
        armor_base=resolved.armor_base,
        secondary_bonus_value=frac_next_base,
    )

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

    awaken_hint = target == 1 and should_awaken_fraction_on_plus_one(inv, resolved)

    return {
        "current_level": cur,
        "target_level": target,
        "chance": chance,
        "is_risky": is_risky,
        "is_broken": bool(inv.is_broken),
        "enchant_cost_gold": cost,
        "on_fail_hint": on_fail,
        "awaken_on_success": awaken_hint,
        "passive_secondary_type": resolved.bonus_type if is_passive_secondary_type(resolved.bonus_type) else None,
        "passive_secondary_value": resolved.bonus_value if is_passive_secondary_type(resolved.bonus_type) else None,
        "fraction_secondary_type": resolved.fraction_type,
        "fraction_secondary_value": resolved.fraction_value,
        "fraction_secondary_effective": frac_val,
        "is_accessory": is_accessory_slot(inv),
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
