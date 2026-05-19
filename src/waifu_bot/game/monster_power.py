"""Vary monster HP vs damage while keeping a weighted power budget (solo dungeons)."""
from __future__ import annotations

import random
from typing import Literal

from waifu_bot.game.constants import (
    MONSTER_POWER_HP_MULT_MAX,
    MONSTER_POWER_HP_MULT_MIN,
    MONSTER_POWER_W_DMG,
    MONSTER_POWER_W_HP,
)

StatProfile = Literal["tank", "balanced", "glass"]


def compute_stat_profile(hp_mult: float) -> StatProfile:
    if hp_mult > 1.05:
        return "tank"
    if hp_mult < 0.95:
        return "glass"
    return "balanced"


def vary_hp_dmg_for_power_budget(
    hp0: int,
    dmg0: int,
    rng: random.Random,
    *,
    w_hp: float = MONSTER_POWER_W_HP,
    w_dmg: float = MONSTER_POWER_W_DMG,
    hp_mult_min: float = MONSTER_POWER_HP_MULT_MIN,
    hp_mult_max: float = MONSTER_POWER_HP_MULT_MAX,
) -> tuple[int, int, StatProfile]:
    """Return (hp, dmg, profile) with same linear power P = w_hp*hp0 + w_dmg*dmg0 as baseline."""
    hp0 = max(1, int(hp0))
    dmg0 = max(1, int(dmg0))
    w_hp = float(w_hp)
    w_dmg = float(w_dmg)
    p = w_hp * hp0 + w_dmg * dmg0
    if p <= 0:
        return hp0, dmg0, "balanced"

    # hp = hp0*x, dmg = dmg0*y, P = w_hp*hp0*x + w_dmg*dmg0*y => y = (P - w_hp*hp0*x)/(w_dmg*dmg0)
    lo, hi = 0.75, 1.25
    denom_x = max(w_hp * hp0, 1e-9)
    x_floor = (p - hi * w_dmg * dmg0) / denom_x
    x_ceil = (p - lo * w_dmg * dmg0) / denom_x
    x_min = max(hp_mult_min, x_floor)
    x_max = min(hp_mult_max, x_ceil)
    if x_min > x_max:
        return hp0, dmg0, "balanced"

    x_mult = rng.uniform(x_min, x_max)
    hp = max(1, int(round(hp0 * x_mult)))
    dmg = max(1, int(round((p - w_hp * hp) / max(w_dmg, 1e-9))))

    profile = compute_stat_profile(hp / max(1.0, float(hp0)))
    return hp, dmg, profile

