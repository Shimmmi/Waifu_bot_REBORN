"""Drop eligibility rules for legendary bonuses (tier band, slot, waifu-level gates)."""

from __future__ import annotations

from typing import Any

from waifu_bot.game.legendary_bonuses.compat import slot_allowed

ALL_SLOT_TYPES: tuple[str, ...] = (
    "weapon_1h",
    "weapon_2h",
    "offhand",
    "costume",
    "ring",
    "amulet",
)

WEAPON_ARMOR_SLOTS: frozenset[str] = frozenset({"weapon_1h", "weapon_2h", "offhand", "costume"})
RING_AMULET_SLOTS: frozenset[str] = frozenset({"ring", "amulet"})

# Splash / boss-only bonuses fit weapons & armor better than jewelry.
WEAPON_ARMOR_PREFERRED: frozenset[str] = frozenset(
    {
        "TYPE_HUNTER",
        "PRISM",
        "BOSS_SLAYER",
        "AFFIX_MASTERY",
        "IMMUNITY_BREAKER",
        "DETONATOR",
        "MEDIA_TRIO",
        "CHARGED_DISCHARGE",
    }
)

RING_AMULET_PREFERRED: frozenset[str] = frozenset(
    {
        "GOLD_PULSE",
        "HUNTER_EXPERIENCE",
        "FIRST_DAILY_DUNGEON",
        "MORNING_RITUAL",
        "MIDNIGHT_STRIKE",
        "RARITY_SYNERGY",
        "SURVIVOR_SPIRIT",
        "PAIN_COLLECTOR",
        "LIVING_ARTIFACT",
    }
)

# Manual overrides when params alone are insufficient.
MANUAL_OVERRIDES: dict[str, dict[str, Any]] = {
    "APPRENTICE_SURGE": {"max_item_tier": 3},
    "ROOKIE_NERVE": {"max_item_tier": 2},
    "VETERAN_EDGE": {"min_item_tier": 8},
    "LEVEL_RESONANCE": {"min_item_tier": 6},
    "MUSCLE_MEMORY": {"min_item_tier": 8},
    "ACROBAT": {"min_item_tier": 8},
    "SCHOLAR": {"min_item_tier": 8},
    "FORTUNE_FAVORED": {"min_item_tier": 8},
    "JACKPOT_SENSE": {"min_item_tier": 10},
    "LAST_BREATH": {"allowed_slot_types": ["ring"]},
    "BOSS_SLAYER": {
        "allowed_slot_types": ["weapon_1h", "weapon_2h", "offhand", "costume"],
    },
}


def tier_from_level(level: int) -> int:
    return max(1, min(10, (int(level) - 1) // 5 + 1))


def _has_splash_effect(bonus: dict[str, Any]) -> bool:
    params = bonus.get("params") or {}
    effects = params.get("effects") or {}
    if effects.get("remaining_monsters_damage_multiplier"):
        return True
    return str(bonus.get("bonus_key") or "") in WEAPON_ARMOR_PREFERRED


def allowed_slots_for_bonus(bonus: dict[str, Any]) -> list[str]:
    """Hard slot filter for a bonus (empty list = none)."""
    key = str(bonus.get("bonus_key") or "")
    override = MANUAL_OVERRIDES.get(key, {})
    if "allowed_slot_types" in override:
        return list(override["allowed_slot_types"])

    allowed: list[str] = []
    for slot in ALL_SLOT_TYPES:
        if not slot_allowed(key, slot):
            continue
        if _has_splash_effect(bonus) and slot in RING_AMULET_SLOTS:
            continue
        if key in RING_AMULET_PREFERRED and slot in WEAPON_ARMOR_SLOTS:
            continue
        allowed.append(slot)
    return allowed


def _tier_bounds_from_params(params: dict[str, Any]) -> tuple[int, int]:
    min_tier = 1
    max_tier = 10
    handler = str(params.get("handler") or "")
    if handler != "meta_scale":
        return min_tier, max_tier

    source = str(params.get("source") or "")
    mode = str(params.get("mode") or "")

    if source == "waifu_level":
        try:
            val = int(params.get("value") or 0)
        except (TypeError, ValueError):
            val = 0
        if mode == "below" and val > 0:
            max_tier = min(max_tier, tier_from_level(val))
        elif mode == "above" and val > 0:
            min_tier = max(min_tier, tier_from_level(val))

    if source == "stat":
        try:
            val = int(params.get("value") or 0)
        except (TypeError, ValueError):
            val = 0
        if mode == "above" and val >= 40:
            min_tier = max(min_tier, 8)
        elif mode == "above" and val >= 60:
            min_tier = max(min_tier, 10)

    return min_tier, max_tier


def derive_drop_eligibility(bonus: dict[str, Any]) -> dict[str, Any]:
    """Compute drop_eligibility fields for a legendary_bonuses row."""
    key = str(bonus.get("bonus_key") or "")
    params = bonus.get("params") or {}
    min_tier, max_tier = _tier_bounds_from_params(params)

    override = MANUAL_OVERRIDES.get(key, {})
    if "min_item_tier" in override:
        min_tier = max(min_tier, int(override["min_item_tier"]))
    if "max_item_tier" in override:
        max_tier = min(max_tier, int(override["max_item_tier"]))

    if min_tier > max_tier:
        min_tier, max_tier = max_tier, min_tier

    slots = allowed_slots_for_bonus(bonus)
    is_drop_enabled = bool(bonus.get("is_active", True)) and len(slots) > 0

    return {
        "min_item_tier": int(min_tier),
        "max_item_tier": int(max_tier),
        "allowed_slot_types": slots,
        "is_drop_enabled": is_drop_enabled,
    }


def bonus_fits_drop(
    bonus: dict[str, Any],
    *,
    tier: int,
    slot_type: str,
) -> bool:
    """Runtime filter: can this bonus roll on an item of given tier/slot?"""
    if not bonus.get("is_active", True):
        return False
    if not bonus.get("is_drop_enabled", True):
        return False

    t = max(1, min(10, int(tier)))
    min_t = int(bonus.get("min_item_tier") or 1)
    max_t = int(bonus.get("max_item_tier") or 10)
    if t < min_t or t > max_t:
        return False

    allowed = bonus.get("allowed_slot_types") or []
    st = str(slot_type or "").lower()
    if allowed and st not in {str(s).lower() for s in allowed}:
        return False
    return True


def drop_weight_for_bonus(bonus: dict[str, Any], *, tier: int, slot_type: str) -> int:
    """Soft weight: preferred families/slots get higher weight."""
    key = str(bonus.get("bonus_key") or "")
    st = str(slot_type or "").lower()
    weight = 10

    if key in WEAPON_ARMOR_PREFERRED and st in WEAPON_ARMOR_SLOTS:
        weight += 5
    if key in RING_AMULET_PREFERRED and st in RING_AMULET_SLOTS:
        weight += 5

    # Slight preference for trigger families that match high tiers (meta/economy on T9+).
    tg = str(bonus.get("trigger_group") or "")
    t = max(1, min(10, int(tier)))
    if t >= 9 and tg in {"meta_inventory", "economy", "exotic"}:
        weight += 2
    if t <= 3 and tg in {"media_type", "text_content", "time_calendar"}:
        weight += 2

    return max(1, weight)
