"""Combat Rating (CR) for hired waifus — replaces opaque «мощь» UX."""
from __future__ import annotations

from typing import Any

from waifu_bot.db.models.waifu import WaifuRarity

POWER_RARITY_BASE: dict[int, int] = {
    int(WaifuRarity.COMMON): 40,
    int(WaifuRarity.UNCOMMON): 55,
    int(WaifuRarity.RARE): 75,
    int(WaifuRarity.EPIC): 95,
    int(WaifuRarity.LEGENDARY): 120,
}
POWER_PER_LEVEL = 3
POWER_PER_STAR = 8
POWER_PER_PERK_LEVEL = 2
POWER_PER_GEAR_SCORE = 1


def compute_hired_cr(
    level: int,
    rarity: int,
    *,
    potential_stars: int = 0,
    perk_level_sum: int = 0,
    gear_score: int = 0,
) -> int:
    lv = max(1, int(level or 1))
    r = int(rarity or int(WaifuRarity.COMMON))
    base = POWER_RARITY_BASE.get(r, 40)
    stars = max(0, min(5, int(potential_stars or 0)))
    perk_sum = max(0, int(perk_level_sum or 0))
    gear = max(0, int(gear_score or 0))
    return (
        base
        + (lv - 1) * POWER_PER_LEVEL
        + stars * POWER_PER_STAR
        + perk_sum * POWER_PER_PERK_LEVEL
        + gear * POWER_PER_GEAR_SCORE
    )


def compute_hired_power(level: int, rarity: int) -> int:
    """Backward-compatible alias (level+rarity only)."""
    return compute_hired_cr(level, rarity)


def cr_breakdown_for_unit(unit: Any) -> dict[str, int]:
    level = int(getattr(unit, "level", 1) or 1)
    rarity = int(getattr(unit, "rarity", 1) or 1)
    stars = int(getattr(unit, "potential_stars", 0) or 0)
    perk_levels = getattr(unit, "perk_levels", None) or {}
    perk_sum = 0
    if isinstance(perk_levels, dict):
        perk_sum = sum(max(0, int(v or 0)) for v in perk_levels.values())
    gear_score = int(getattr(unit, "gear_score_cache", 0) or 0)
    total = compute_hired_cr(
        level, rarity, potential_stars=stars, perk_level_sum=perk_sum, gear_score=gear_score
    )
    base_only = compute_hired_cr(level, rarity)
    return {
        "base": base_only,
        "stars": stars * POWER_PER_STAR,
        "perks": perk_sum * POWER_PER_PERK_LEVEL,
        "gear": gear_score * POWER_PER_GEAR_SCORE,
        "total": total,
    }


def refresh_unit_power(unit: Any) -> int:
    """Set unit.power from full CR and return it."""
    bd = cr_breakdown_for_unit(unit)
    total = int(bd["total"])
    try:
        unit.power = total
    except Exception:
        pass
    return total
