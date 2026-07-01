"""Solo dungeon kill reward percentages — additive stacking model."""

from __future__ import annotations

import math


def dungeon_plus_reward_mult(plus_level: int) -> float:
    """Dungeon+ difficulty reward multiplier (applied after character % sum)."""
    n = max(0, int(plus_level or 0))
    return 1.0 + n * 0.15 + math.log1p(n) * 0.10


def compute_solo_reward_fractions(
    *,
    gear_exp_frac: float = 0.0,
    gear_gold_frac: float = 0.0,
    intelligence_exp_frac: float = 0.0,
    luck_gold_frac: float = 0.0,
    guild_exp_frac: float = 0.0,
    guild_gold_frac: float = 0.0,
    bestiary_exp_frac: float = 0.0,
    bestiary_gold_frac: float = 0.0,
    boss_exp_frac: float = 0.0,
    boss_gold_frac: float = 0.0,
    elite_gold_frac: float = 0.0,
    quest_exp_frac: float = 0.0,
    first_clear_exp_frac: float = 0.0,
) -> tuple[float, float]:
    """Sum all character/monster-context % bonuses into single fractions (0.03 = +3%)."""
    exp_frac = (
        float(gear_exp_frac or 0.0)
        + float(intelligence_exp_frac or 0.0)
        + float(guild_exp_frac or 0.0)
        + float(bestiary_exp_frac or 0.0)
        + float(boss_exp_frac or 0.0)
        + float(quest_exp_frac or 0.0)
        + float(first_clear_exp_frac or 0.0)
    )
    gold_frac = (
        float(gear_gold_frac or 0.0)
        + float(luck_gold_frac or 0.0)
        + float(guild_gold_frac or 0.0)
        + float(bestiary_gold_frac or 0.0)
        + float(boss_gold_frac or 0.0)
        + float(elite_gold_frac or 0.0)
    )
    return exp_frac, gold_frac


def apply_solo_kill_reward_amounts(
    base_exp: int,
    base_gold: int,
    exp_frac: float,
    gold_frac: float,
    *,
    plus_reward_mult: float = 1.0,
    legendary_gold_mult: float = 1.0,
) -> tuple[int, int]:
    """Apply additive % totals, then Dungeon+ and legendary gold multipliers."""
    exp_gain = max(0, int(round(int(base_exp or 0) * (1.0 + float(exp_frac or 0.0)) * float(plus_reward_mult or 1.0))))
    gold_gain = max(
        0,
        int(
            round(
                int(base_gold or 0)
                * (1.0 + float(gold_frac or 0.0))
                * float(plus_reward_mult or 1.0)
                * float(legendary_gold_mult or 1.0)
            )
        ),
    )
    return exp_gain, gold_gain


def guild_reward_fractions(gfx: dict[str, float]) -> tuple[float, float]:
    """Extract additive guild fractions from effect_values map."""
    gold_frac = float(gfx.get("monster_gold_pct", 0) or 0) + float(gfx.get("global_reward_pct", 0) or 0)
    exp_frac = float(gfx.get("dungeon_exp_pct", 0) or 0) + float(gfx.get("global_reward_pct", 0) or 0)
    return exp_frac, gold_frac


def hidden_reward_fractions(hs: dict[str, float], *, night_moscow: bool = False) -> tuple[float, float]:
    """Hidden skill exp/gold fractions (DB values are percentage points)."""
    exp_frac = float(hs.get("exp_bonus_pct", 0) or 0) / 100.0
    gold_frac = float(hs.get("gold_drop_pct", 0) or 0) / 100.0
    if night_moscow:
        gold_frac += float(hs.get("gold_night_pct", 0) or 0) / 100.0
    return exp_frac, gold_frac


def enrich_profile_reward_bonus_pcts(
    details: dict,
    *,
    hs: dict | None = None,
    guild_exp_frac: float = 0.0,
    guild_gold_frac: float = 0.0,
    night_moscow: bool = False,
) -> dict:
    """Add hidden + guild dungeon reward % to profile details (display only)."""
    out = dict(details)
    h_exp, h_gold = hidden_reward_fractions(hs or {}, night_moscow=night_moscow)
    out["exp_bonus"] = round(float(out.get("exp_bonus", 0) or 0) + (h_exp + guild_exp_frac) * 100.0, 2)
    out["gold_bonus"] = round(float(out.get("gold_bonus", 0) or 0) + (h_gold + guild_gold_frac) * 100.0, 2)
    return out
