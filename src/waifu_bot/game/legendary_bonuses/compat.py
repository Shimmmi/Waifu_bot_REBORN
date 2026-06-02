"""Equip-time compatibility rules for legendary bonuses."""

from __future__ import annotations

SLOT_RESTRICTED: dict[str, frozenset[str]] = {
    "LAST_BREATH": frozenset({"ring"}),
    "BOSS_SLAYER": frozenset({"ring", "amulet"}),
}

INCOMPATIBLE_PAIRS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset({"AGONY", "LAST_BREATH"}),
        frozenset({"DAMAGE_MIRROR", "DETONATOR"}),
        frozenset({"MORNING_RITUAL", "SILENCE_BURST"}),
        frozenset({"MONOLOGUE", "VERBOSITY"}),
        frozenset({"SILENCE_BURST", "AMBUSH_SILENCE"}),
        frozenset({"HUNT_FRENZY", "SNIPER_SHOT"}),
        frozenset({"PHOENIX_RAGE", "LAST_BREATH"}),
    }
)

# Conflicts with passive / hidden skills — cap or replace at equip/build time (§8.1).
PASSIVE_HIDDEN_CONFLICTS: dict[str, str] = {
    "LAST_BREATH": "passive survive_chance — one proc per fight; lower survive_chance cap when equipped",
    "AGONY": "hidden nth_hit_crit — only one forced-crit source applies per hit",
    "PHOENIX_RAGE": "passive revive — phoenix window takes priority over generic revive",
    "SNIPER_SHOT": "hidden first_hit_crit — first hit uses SNIPER_SHOT if both active",
    "RARITY_SYNERGY": "requires second equipped legendary (any slot); bonus once per pair",
}

RARITY_SYNERGY_MIN_LEGENDARIES = 2


def slot_allowed(bonus_key: str, slot_type: str | None) -> bool:
    blocked = SLOT_RESTRICTED.get(bonus_key)
    if not blocked:
        return True
    st = str(slot_type or "").lower()
    for b in blocked:
        if b in st:
            return False
    return True


def bonuses_compatible(existing_keys: set[str], new_key: str) -> bool:
    for pair in INCOMPATIBLE_PAIRS:
        if new_key in pair and any(k in pair for k in existing_keys if k != new_key):
            return False
    return True


def passive_hidden_conflict_note(bonus_key: str) -> str | None:
    return PASSIVE_HIDDEN_CONFLICTS.get(bonus_key)
