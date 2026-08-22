"""Dungeon+ combat/reward scaling — nonlinear HP curve, decoupled monster damage."""

from __future__ import annotations

import math
import random

# Soft early (+1 ≈ 2.4k HP for campaign graduates ~1k text dmg), steep late (+30 ≈ 152k).
# hp_target(N) = HP_FLAT + HP_SCALE * N ** HP_EXP
HP_FLAT = 2300.0
HP_SCALE = 100.0
HP_EXP = 2.15

# Orientative TTK helper: messages at ~1k text damage (campaign graduate).
ENTRY_REF_MSG_DAMAGE = 1000

# Monster outgoing damage grows slower than HP.
DMG_MULT_PER_PLUS = 0.08

# Extra monsters: none before +8; then +1 every 4 plus levels past +4.
EXTRA_MOBS_OFFSET = 4
EXTRA_MOBS_EVERY = 4

# Reward curve (applied after character % sum on kills).
REWARD_LINEAR_PER_PLUS = 0.22
REWARD_LOG_COEFF = 0.15

RARITY_TIERS = ("common", "uncommon", "rare", "epic", "legendary")
RARITY_TIER_INDEX = {
    "common": 1,
    "uncommon": 2,
    "rare": 3,
    "epic": 4,
    "legendary": 5,
}

# Extra completion-chest items cap (1 guaranteed + up to this many).
COMPLETION_EXTRA_ITEM_ROLLS_CAP = 4


def dungeon_plus_hp_target(plus_level: int) -> float:
    """Absolute HP target for a normal mob before boss/elite multipliers."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 0.0
    return float(HP_FLAT) + float(HP_SCALE) * (float(n) ** float(HP_EXP))


def dungeon_plus_ttk_normal(plus_level: int) -> float:
    """Derived TTK (messages) at ENTRY_REF_MSG_DAMAGE ≈ 1k for docs/UI."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    return float(dungeon_plus_hp_target(n)) / float(ENTRY_REF_MSG_DAMAGE)


def dungeon_plus_hp_mult_for_rolled(plus_level: int, rolled_hp: int) -> float:
    """Scale factor so rolled HP lands near the nonlinear HP target."""
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
    """Extra monsters added to obstacle_min/max for Dungeon+.

    +1..+7 → 0; +8..+11 → 1; …; +30 → 6.
    """
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 0
    return max(0, (int(n) - int(EXTRA_MOBS_OFFSET)) // int(EXTRA_MOBS_EVERY))


def dungeon_plus_budget_mult(plus_level: int) -> float:
    """Difficulty budget scale for template picking / run.difficulty_rating."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 1.0
    base = dungeon_plus_hp_target(1)
    if base <= 0:
        return 1.0
    return max(1.0, (dungeon_plus_hp_target(n) / base) ** 0.5)


def dungeon_plus_rarity_floor_index(plus_level: int) -> int:
    """Minimum item rarity 1–5 for the main completion chest. 1 when plus is 0."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return int(RARITY_TIER_INDEX[RARITY_TIERS[0]])
    name = RARITY_TIERS[min(n // 2, 4)]
    return int(RARITY_TIER_INDEX[name])


def dungeon_plus_drop_effective_act(dungeon_act: int, plus_level: int) -> int:
    """DropRule act for plus runs so early-act dungeons are not stuck on 0% legendary."""
    act = max(1, min(5, int(dungeon_act or 1)))
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return act
    return min(5, max(act, 1 + n // 6))


def dungeon_plus_completion_item_rolls(plus_level: int) -> int:
    """Completion chest rolls: 1 + extra_monsters, capped at 5."""
    extra = dungeon_plus_extra_monsters(plus_level)
    return 1 + min(int(COMPLETION_EXTRA_ITEM_ROLLS_CAP), int(extra))


def dungeon_plus_drop_power_rank(plus_level: int) -> int:
    """Snapshot power used as Dungeon+ item level / affix budget."""
    n = max(0, int(plus_level or 0))
    if n <= 0:
        return 0
    return int(50 + n * 10)


def dungeon_plus_completion_item_level(
    plus_level: int,
    dungeon_level: int,
    *,
    drop_power_rank: int = 0,
    jitter: int | None = None,
) -> int:
    """Item level for a completion drop. Base dungeons stay capped at 60; plus does not."""
    n = max(0, int(plus_level or 0))
    extra = random.randint(0, 4) if jitter is None else max(0, int(jitter))
    if n <= 0:
        return max(1, min(int(dungeon_level or 1) + extra, 60))
    rank = int(drop_power_rank or 0)
    base = rank if rank > 0 else dungeon_plus_drop_power_rank(n)
    return max(1, int(base) + extra)


def apply_completion_rarity_floor(rolled: int, plus_level: int, *, is_main: bool) -> int:
    """Raise the main chest rarity to the plus floor; extra rolls keep the raw roll."""
    rarity = max(1, min(5, int(rolled or 1)))
    if not is_main or int(plus_level or 0) <= 0:
        return rarity
    return max(rarity, dungeon_plus_rarity_floor_index(plus_level))


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
        "drop_power_rank": dungeon_plus_drop_power_rank(n),
        "completion_item_rolls": dungeon_plus_completion_item_rolls(n),
    }
