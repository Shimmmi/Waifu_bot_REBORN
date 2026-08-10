"""Daily GD personal rewards: waifu level + chat activity (1..500 msgs) → exp/gold/items."""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map

logger = logging.getLogger(__name__)

# Defaults (also seeded / overridable via game_config)
DEFAULTS = {
    "gd_daily_reward_msg_min": 1,
    "gd_daily_reward_msg_cap": 500,
    "gd_daily_reward_exp_at_l1": 80,
    "gd_daily_reward_gold_at_l1": 120,
    "gd_daily_reward_exp_at_cap_l1": 4000,
    "gd_daily_reward_gold_at_cap_l1": 6000,
    "gd_daily_reward_level_scale": 0.035,
    "gd_daily_reward_perfection_bonus_cap": 0.15,
    "gd_daily_reward_perfection_per_level": 0.005,
    "gd_daily_item_chance_at_min": 0.05,
    "gd_daily_item_chance_at_cap": 0.85,
    "gd_daily_item_max_count": 2,
    "gd_daily_item_ilvl_offset": 0,
}


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return t * t * (3.0 - 2.0 * t)


def activity_t(msg_total: int, *, msg_min: int = 1, msg_cap: int = 500) -> float | None:
    """Return activity factor in [0,1], or None if below min (no reward)."""
    m = max(0, int(msg_total))
    lo = max(1, int(msg_min))
    hi = max(lo, int(msg_cap))
    if m < lo:
        return None
    m = min(m, hi)
    if hi == lo:
        return 1.0
    return smoothstep((m - lo) / float(hi - lo))


def level_scale_mult(
    level: int,
    *,
    level_scale: float = 0.035,
    perfection_level: int = 0,
    perfection_per_level: float = 0.005,
    perfection_bonus_cap: float = 0.15,
) -> float:
    lv = max(1, min(int(MAX_LEVEL), int(level or 1)))
    base = 1.0 + float(lv - 1) * float(level_scale)
    if lv >= int(MAX_LEVEL) and int(perfection_level or 0) > 0:
        bonus = min(
            float(perfection_bonus_cap),
            float(perfection_level) * float(perfection_per_level),
        )
        base *= 1.0 + bonus
    return base


def lerp(a: float, b: float, t: float) -> float:
    return float(a) + (float(b) - float(a)) * max(0.0, min(1.0, float(t)))


def compute_daily_payout(
    *,
    msg_total: int,
    waifu_level: int,
    perfection_level: int = 0,
    cfg: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Pure payout calc (no DB). Returns exp/gold/item_chance/counted_msgs."""
    cfg = cfg or {}
    msg_min = cfg_int(cfg, "gd_daily_reward_msg_min", DEFAULTS["gd_daily_reward_msg_min"])
    msg_cap = cfg_int(cfg, "gd_daily_reward_msg_cap", DEFAULTS["gd_daily_reward_msg_cap"])
    exp_lo = cfg_float(cfg, "gd_daily_reward_exp_at_l1", DEFAULTS["gd_daily_reward_exp_at_l1"])
    gold_lo = cfg_float(cfg, "gd_daily_reward_gold_at_l1", DEFAULTS["gd_daily_reward_gold_at_l1"])
    exp_hi = cfg_float(cfg, "gd_daily_reward_exp_at_cap_l1", DEFAULTS["gd_daily_reward_exp_at_cap_l1"])
    gold_hi = cfg_float(cfg, "gd_daily_reward_gold_at_cap_l1", DEFAULTS["gd_daily_reward_gold_at_cap_l1"])
    level_scale = cfg_float(cfg, "gd_daily_reward_level_scale", DEFAULTS["gd_daily_reward_level_scale"])
    perf_per = cfg_float(
        cfg, "gd_daily_reward_perfection_per_level", DEFAULTS["gd_daily_reward_perfection_per_level"]
    )
    perf_cap = cfg_float(
        cfg, "gd_daily_reward_perfection_bonus_cap", DEFAULTS["gd_daily_reward_perfection_bonus_cap"]
    )
    chance_lo = cfg_float(cfg, "gd_daily_item_chance_at_min", DEFAULTS["gd_daily_item_chance_at_min"])
    chance_hi = cfg_float(cfg, "gd_daily_item_chance_at_cap", DEFAULTS["gd_daily_item_chance_at_cap"])
    item_max = cfg_int(cfg, "gd_daily_item_max_count", DEFAULTS["gd_daily_item_max_count"])

    t = activity_t(msg_total, msg_min=msg_min, msg_cap=msg_cap)
    counted = 0 if t is None else min(max(0, int(msg_total)), msg_cap)
    if t is None:
        return {
            "exp": 0,
            "gold": 0,
            "item_chance": 0.0,
            "item_rolls": 0,
            "counted_msgs": 0,
            "activity_t": None,
            "eligible": False,
        }

    lm = level_scale_mult(
        waifu_level,
        level_scale=level_scale,
        perfection_level=perfection_level,
        perfection_per_level=perf_per,
        perfection_bonus_cap=perf_cap,
    )
    exp = int(round(lerp(exp_lo, exp_hi, t) * lm))
    gold = int(round(lerp(gold_lo, gold_hi, t) * lm))
    item_chance = lerp(chance_lo, chance_hi, t)
    # Second roll only at high activity (t >= 0.6), still capped by item_max
    rolls = 1
    if item_max >= 2 and t >= 0.6:
        rolls = 2
    rolls = min(max(0, item_max), rolls)

    return {
        "exp": max(0, exp),
        "gold": max(0, gold),
        "item_chance": max(0.0, min(1.0, item_chance)),
        "item_rolls": rolls,
        "counted_msgs": counted,
        "activity_t": t,
        "eligible": True,
        "level_mult": lm,
    }


async def roll_daily_reward_items(
    session: AsyncSession,
    *,
    player_id: int,
    waifu_level: int,
    item_chance: float,
    item_rolls: int,
    cfg: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Roll 0..N items into inventory; returns summary dicts for GDRewardRow.items_json."""
    from waifu_bot.db.models import Player
    from waifu_bot.services.item_service import ItemService
    from waifu_bot.services.gd_loot import _act_from_avg_level, _roll_rarity_from_drop_rule

    cfg = cfg or await get_game_config_map(session)
    out: list[dict[str, Any]] = []
    if item_rolls <= 0 or item_chance <= 0:
        return out
    ilvl_off = cfg_int(cfg, "gd_daily_item_ilvl_offset", DEFAULTS["gd_daily_item_ilvl_offset"])
    base_lv = max(1, min(int(MAX_LEVEL), int(waifu_level or 1) + ilvl_off))
    act = _act_from_avg_level(base_lv)
    player = await session.get(Player, int(player_id))
    if player and getattr(player, "current_act", None):
        act = max(1, int(player.current_act or act))
    svc = ItemService()
    for _ in range(max(0, int(item_rolls))):
        if random.random() > float(item_chance):
            continue
        rarity = await _roll_rarity_from_drop_rule(session, act, boss=False)
        item_level = max(1, min(base_lv + random.randint(0, 3), int(MAX_LEVEL)))
        try:
            inv = await svc.generate_inventory_item(
                session=session,
                player_id=int(player_id),
                act=act,
                rarity=rarity,
                level=item_level,
                is_shop=False,
                plus_level=0,
            )
            await session.flush()
            name = (
                getattr(inv, "_display_name", None)
                or (inv.item.name if getattr(inv, "item", None) else None)
                or "Предмет"
            )
            out.append(
                {
                    "inventory_item_id": int(inv.id),
                    "name": str(name),
                    "rarity": int(inv.rarity or rarity),
                    "level": int(inv.level or item_level),
                }
            )
        except Exception:
            logger.exception("GD daily item roll failed player_id=%s", player_id)
    return out


def contribution_display_pct(msg_total: int, sum_msgs: int) -> float:
    if sum_msgs <= 0:
        return 0.0
    return round(100.0 * max(0, int(msg_total)) / float(sum_msgs), 2)
