"""Bestiary (pokedex) discovery tiers and per-monster combat bonuses.

Discovery tier is derived from the number of kills a player has logged against a
specific monster template. Each tier unlocks more information about the monster
(name -> hp -> type -> ...) and grants a small *per-monster* combat bonus that
only applies when fighting that monster (Monster Hunter style).

All thresholds and bonus values live here so balance can be tuned in one place.
The tier is never persisted; it is computed from ``kills`` on read.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BestiaryTier:
    """A single discovery tier definition."""

    tier: int
    kills_required: int
    name: str  # RU label shown in the UI
    # What information about the monster becomes visible at this tier.
    reveals_name: bool = False
    reveals_hp: bool = False
    reveals_type: bool = False
    reveals_damage: bool = False
    reveals_rewards: bool = False
    reveals_abilities: bool = False
    reveals_lore: bool = False
    # Per-monster combat bonuses (cumulative across reached tiers).
    dmg_pct: float = 0.0  # extra outgoing damage vs this monster
    dmg_taken_pct: float = 0.0  # change to incoming damage from this monster (negative = less)
    exp_pct: float = 0.0  # extra experience from this monster
    gold_pct: float = 0.0  # extra gold from this monster
    # Optional title/achievement unlocked at this tier.
    title: str | None = None


# Ordered ascending by kills_required. Tier 0 is the "encountered" baseline.
BESTIARY_TIERS: tuple[BestiaryTier, ...] = (
    BestiaryTier(
        tier=0,
        kills_required=0,
        name="Не изучен",
    ),
    BestiaryTier(
        tier=1,
        kills_required=1,
        name="Замечен",
        reveals_name=True,
        exp_pct=0.03,
    ),
    BestiaryTier(
        tier=2,
        kills_required=5,
        name="Изучается",
        reveals_name=True,
        reveals_hp=True,
        gold_pct=0.03,
    ),
    BestiaryTier(
        tier=3,
        kills_required=10,
        name="Известен",
        reveals_name=True,
        reveals_hp=True,
        reveals_type=True,
        dmg_pct=0.03,
    ),
    BestiaryTier(
        tier=4,
        kills_required=25,
        name="Изучен",
        reveals_name=True,
        reveals_hp=True,
        reveals_type=True,
        reveals_damage=True,
        reveals_rewards=True,
        dmg_pct=0.05,
    ),
    BestiaryTier(
        tier=5,
        kills_required=50,
        name="Эксперт",
        reveals_name=True,
        reveals_hp=True,
        reveals_type=True,
        reveals_damage=True,
        reveals_rewards=True,
        reveals_abilities=True,
        reveals_lore=True,
        dmg_taken_pct=-0.05,
    ),
    BestiaryTier(
        tier=6,
        kills_required=100,
        name="Покоритель",
        reveals_name=True,
        reveals_hp=True,
        reveals_type=True,
        reveals_damage=True,
        reveals_rewards=True,
        reveals_abilities=True,
        reveals_lore=True,
        exp_pct=0.05,
        gold_pct=0.05,
        title="Покоритель вида",
    ),
)

MAX_TIER: int = BESTIARY_TIERS[-1].tier


@dataclass(frozen=True)
class BestiaryBonuses:
    """Resolved cumulative combat bonuses for a given tier."""

    dmg_pct: float = 0.0
    dmg_taken_pct: float = 0.0
    exp_pct: float = 0.0
    gold_pct: float = 0.0


def tier_for_kills(kills: int) -> int:
    """Return the discovery tier index for the given kill count."""
    k = max(0, int(kills or 0))
    result = 0
    for t in BESTIARY_TIERS:
        if k >= t.kills_required:
            result = t.tier
        else:
            break
    return result


def get_tier_def(tier: int) -> BestiaryTier:
    """Return the tier definition by tier index (clamped to valid range)."""
    idx = max(0, min(int(tier or 0), len(BESTIARY_TIERS) - 1))
    return BESTIARY_TIERS[idx]


def reveal_flags_for_tier(tier: int) -> dict[str, bool]:
    """Return a flat dict of what is revealed at (and below) the given tier."""
    t = get_tier_def(tier)
    return {
        "name": t.reveals_name,
        "hp": t.reveals_hp,
        "type": t.reveals_type,
        "damage": t.reveals_damage,
        "rewards": t.reveals_rewards,
        "abilities": t.reveals_abilities,
        "lore": t.reveals_lore,
    }


def cumulative_bonuses_for_tier(tier: int) -> BestiaryBonuses:
    """Sum the per-monster bonuses from every tier up to and including ``tier``."""
    dmg = dmg_taken = exp = gold = 0.0
    target = max(0, min(int(tier or 0), MAX_TIER))
    for t in BESTIARY_TIERS:
        if t.tier <= target:
            dmg += t.dmg_pct
            dmg_taken += t.dmg_taken_pct
            exp += t.exp_pct
            gold += t.gold_pct
    return BestiaryBonuses(
        dmg_pct=round(dmg, 4),
        dmg_taken_pct=round(dmg_taken, 4),
        exp_pct=round(exp, 4),
        gold_pct=round(gold, 4),
    )


def next_tier_threshold(kills: int) -> int | None:
    """Kills required to reach the next tier, or None if already at max."""
    cur = tier_for_kills(kills)
    for t in BESTIARY_TIERS:
        if t.tier == cur + 1:
            return t.kills_required
    return None
