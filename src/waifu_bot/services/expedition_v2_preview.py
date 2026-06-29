"""Превью экспедиции v2 без ежедневного слота."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import HiredWaifu
from waifu_bot.game.expedition_difficulty_tags import (
    calc_tag_effectiveness_mult,
    squad_covered_tags,
    sorted_tag_list,
)
from waifu_bot.game.expedition_overhaul import (
    depth_tier_by_id,
    squad_power_total,
    validate_reward_type,
)
from waifu_bot.game.expedition_redesign import AFFIX_LEVEL_BASE_HP_PCT, CHALLENGE_CATEGORIES


async def preview_expedition_v2(
    session,
    player_id: int,
    squad_waifu_ids: list[int],
    reward_type: str,
    depth_tier: int,
) -> dict:
    rt = validate_reward_type(reward_type)
    if not rt:
        return {"error": "invalid_reward_type"}
    depth = depth_tier_by_id(int(depth_tier))
    if depth is None:
        return {"error": "invalid_depth_tier"}

    squad: list[HiredWaifu] = []
    for wid in squad_waifu_ids or []:
        w = await session.get(HiredWaifu, wid)
        if w and w.player_id == player_id:
            squad.append(w)

    sq_power = squad_power_total(squad)
    power_ok = sq_power >= depth.min_squad_power
    active_tags = frozenset(CHALLENGE_CATEGORIES[: min(3, depth.tier + 1)])
    covered = squad_covered_tags(squad) if squad else frozenset()
    tag_mult = calc_tag_effectiveness_mult(active_tags, covered & active_tags, squad=squad, affix_level=depth.difficulty_level)
    eff_pct = max(0.0, min(100.0, (1.0 - tag_mult) * 100.0 + 50.0))

    # HP-прогноз по базовому урону тира (без variance 0.85–1.15 и твистов).
    # Теги/аффиксы случайно генерируются на старте — здесь не учитываются.
    base_dmg_pct = float(AFFIX_LEVEL_BASE_HP_PCT.get(depth.difficulty_level, 0.15))
    events_count = depth.events_count
    total_loss_pct = base_dmg_pct * events_count * 100.0
    hp_forecast_pct = max(0.0, 100.0 - total_loss_pct)

    return {
        "reward_type": rt,
        "depth_tier": depth.tier,
        "depth_name": depth.name_ru,
        "squad_power": sq_power,
        "min_squad_power": depth.min_squad_power,
        "power_ok": power_ok,
        "events_count": events_count,
        "duration_minutes": depth.duration_minutes,
        "squad_size": len(squad),
        "active_tags": sorted_tag_list(active_tags),
        "covered_tags": sorted_tag_list(covered & active_tags),
        "tag_effectiveness_pct": round(eff_pct, 1),
        "tag_effectiveness_mult": round(tag_mult, 3),
        "damage_per_event_pct": round(base_dmg_pct * 100.0, 1),
        "hp_forecast_pct": round(hp_forecast_pct, 1),
    }
