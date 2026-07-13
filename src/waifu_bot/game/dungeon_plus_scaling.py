"""Dungeon+ combat/reward scaling — TTK-anchored HP, decoupled monster damage."""

from __future__ import annotations

import math

# Typical endgame message damage used to size monster HP (balance anchor).
REF_MSG_DAMAGE = 5000

# ttk_normal(N) = TTK_BASE + TTK_PER_PLUS * N  → +1≈3.4 … +30≈15 messages @ REF
TTK_BASE = 3.0
TTK_PER_PLUS = 0.4

# Monster outgoing damage grows slower than HP.
DMG_MULT_PER_PLUS = 0.08

# Extra monsters in the run: +1 every EXTRA_MOBS_EVERY plus levels.
EXTRA_MOBS_EVERY = 4

# Reward curve (applied after character % sum on kills).
REWARD_LINEAR_PER_PLUS = 0.22
REWARD_LOG_COEFF = 0.15

RARITY_TIERS = ("common", "uncommon", "rare", "epic", "legendary")


def dungeon_plus_ttk_normal(plus_level: int) -> float:
    """Target messages-to-kill for a normal (non-boss) mob at plus_level."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    return float(TTK_BASE) + float(TTK_PER_PLUS) * float(n)


def dungeon_plus_hp_target(plus_level: int) -> float:
    """Absolute HP target for a normal mob before boss/elite multipliers."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 0.0
    return float(REF_MSG_DAMAGE) * dungeon_plus_ttk_normal(n)


def dungeon_plus_hp_mult_for_rolled(plus_level: int, rolled_hp: int) -> float:
    """Scale factor so rolled HP lands near the TTK anchor target."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    target = dungeon_plus_hp_target(n)
    base = max(1, int(rolled_hp or 0))
    return max(1.0, float(target) / float(base))


def dungeon_plus_dmg_mult(plus_level: int) -> float:
    """Monster damage multiplier for Dungeon+ (decoupled from HP)."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    return 1.0 + float(DMG_MULT_PER_PLUS) * float(n)


def dungeon_plus_reward_mult(plus_level: int) -> float:
    """Dungeon+ difficulty reward multiplier (applied after character % sum)."""
    n = max(0, int(plus_level or 0))
    return 1.0 + n * float(REWARD_LINEAR_PER_PLUS) + math.log1p(n) * float(REWARD_LOG_COEFF)


def dungeon_plus_extra_monsters(plus_level: int) -> int:
    """Extra monsters added to obstacle_min/max for Dungeon+."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 0
    return int(n) // int(EXTRA_MOBS_EVERY)


def dungeon_plus_budget_mult(plus_level: int) -> float:
    """Difficulty budget scale for template picking / run.difficulty_rating."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    return max(1.0, dungeon_plus_ttk_normal(n))


def dungeon_plus_difficulty_params(plus_level: int) -> dict:
    """Full Dungeon+ difficulty params used at run start."""
    n = max(0, int(plus_level or 0))
    rarity = RARITY_TIERS[min(n // 2, 4)] if n > 0 else RARITY_TIERS[0]
    return {
        "hp_target": dungeon_plus_hp_target(n),
        "dmg_mult": dungeon_plus_dmg_mult(n),
        "budget_mult": dungeon_plus_budget_mult(n),
        "reward_mult": dungeon_plus_reward_mult(n),
        "item_level_bonus": n,
        "rarity_floor": rarity,
        "elite_chance_bonus": min(0.40, n * 0.02),
        "extra_monsters": dungeon_plus_extra_monsters(n),
    }
