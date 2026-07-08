"""Compute equip requirements for generated inventory items."""

from __future__ import annotations

_STAT_KEYS = frozenset(
    {"strength", "agility", "intelligence", "endurance", "charm", "luck"}
)

_MIN_STAT_REQ = 8


def _base_stat_requirement(tier: int, slot_type: str) -> int:
    t = max(1, min(10, int(tier)))
    st = str(slot_type or "").lower()
    if st in {"weapon_1h", "weapon_2h"}:
        return 8 + t * 3
    if st == "offhand":
        return 6 + t * 2
    if st == "costume":
        return 6 + t * 3
    if st in {"ring", "amulet"}:
        return 5 + t * 2
    return 6 + t * 2


def _lock_discount(*, has_race_lock: bool, has_class_lock: bool) -> int:
    if has_race_lock and has_class_lock:
        return 5
    if has_race_lock or has_class_lock:
        return 3
    return 0


def compute_item_requirements(
    *,
    tier: int,
    slot_type: str,
    level_min: int,
    primary_stat: str | None,
    has_race_lock: bool = False,
    has_class_lock: bool = False,
    required_race: int | None = None,
    required_class: int | None = None,
) -> dict:
    """Build requirements JSON for an inventory item instance."""
    req: dict = {"level": max(1, int(level_min))}

    stat_key = str(primary_stat or "").lower()
    if stat_key not in _STAT_KEYS:
        if str(slot_type or "").lower() == "costume":
            stat_key = "endurance"
        elif str(slot_type or "").lower() == "ring":
            stat_key = "luck"
        elif str(slot_type or "").lower() == "amulet":
            stat_key = "intelligence"

    if stat_key in _STAT_KEYS:
        raw = _base_stat_requirement(tier, slot_type)
        raw -= _lock_discount(has_race_lock=has_race_lock, has_class_lock=has_class_lock)
        req[stat_key] = max(_MIN_STAT_REQ, int(raw))

    if required_race is not None:
        req["waifu_race"] = int(required_race)
    if required_class is not None:
        req["waifu_class"] = int(required_class)

    return req
