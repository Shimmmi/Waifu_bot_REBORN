"""Compute equip requirements for generated inventory items."""

from __future__ import annotations

import math
from typing import Any

from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.game.item_ilvl_scaling import item_scale_ilvl

_STAT_KEYS = frozenset(
    {"strength", "agility", "intelligence", "endurance", "charm", "luck"}
)

_MIN_STAT_REQ = 8
REQ_ILVL_ANCHOR = 60


def round_half_up(value: float) -> int:
    return int(math.floor(float(value) + 0.5))


def requirement_scale(req_ilvl: int) -> float:
    """Campaign (req_ilvl <= 0) stays 1.0. Plus uses budget ilvl / 60."""
    n = int(req_ilvl or 0)
    if n <= 0:
        return 1.0
    return max(1.0, float(n) / float(REQ_ILVL_ANCHOR))


def is_plus_item(inv: Any) -> bool:
    return int(item_scale_ilvl(inv) or 0) > 0


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


def _normalize_primary(primary_stat: str | None, slot_type: str) -> str | None:
    stat_key = str(primary_stat or "").lower()
    if stat_key in _STAT_KEYS:
        return stat_key
    st = str(slot_type or "").lower()
    if st == "costume":
        return "endurance"
    if st == "ring":
        return "luck"
    if st == "amulet":
        return "intelligence"
    return None


def _cap_level_min(level_min: int) -> int:
    return min(int(MAX_LEVEL), max(1, int(level_min)))


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
    req_ilvl: int = 0,
) -> dict:
    """Build requirements JSON for an inventory item instance."""
    req: dict = {"level": _cap_level_min(level_min)}

    stat_key = _normalize_primary(primary_stat, slot_type)
    if stat_key in _STAT_KEYS:
        raw = _base_stat_requirement(tier, slot_type)
        raw -= _lock_discount(has_race_lock=has_race_lock, has_class_lock=has_class_lock)
        scale = requirement_scale(int(req_ilvl or 0))
        req[stat_key] = max(_MIN_STAT_REQ, round_half_up(raw * scale))

    if required_race is not None:
        req["waifu_race"] = int(required_race)
    if required_class is not None:
        req["waifu_class"] = int(required_class)

    return req


def _stored_requirements(inv: Any) -> dict:
    raw = getattr(inv, "requirements", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _locks_from_stored(stored: dict) -> tuple[int | None, int | None]:
    race = stored.get("waifu_race")
    klass = stored.get("waifu_class")
    required_race: int | None = None
    required_class: int | None = None
    if race is not None and str(race).strip() != "":
        try:
            required_race = int(race)
        except (TypeError, ValueError):
            required_race = None
    if klass is not None and str(klass).strip() != "":
        try:
            required_class = int(klass)
        except (TypeError, ValueError):
            required_class = None
    return required_race, required_class


def _primary_from_inv(inv: Any, stored: dict, slot_type: str) -> str | None:
    primary = _normalize_primary(getattr(inv, "base_stat", None), slot_type)
    if primary:
        return primary
    for key in _STAT_KEYS:
        try:
            if int(stored.get(key) or 0) > 0:
                return key
        except (TypeError, ValueError):
            continue
    return _normalize_primary(None, slot_type)


def _level_min_from_inv(inv: Any, stored: dict, tier: int) -> int:
    try:
        stored_level = int(stored.get("level") or 0)
    except (TypeError, ValueError):
        stored_level = 0
    if stored_level > 0:
        return stored_level
    return (max(1, min(10, int(tier))) - 1) * 5 + 1


def resolve_runtime_requirements(inv: Any) -> dict:
    """Canonical requirements for checks and UI. Plus items ignore sticky stat JSON."""
    stored = _stored_requirements(inv)
    req_ilvl = int(item_scale_ilvl(inv) or 0)
    slot_type = str(getattr(inv, "slot_type", None) or "other")
    try:
        tier = max(1, min(10, int(getattr(inv, "tier", None) or 1)))
    except (TypeError, ValueError):
        tier = 1
    required_race, required_class = _locks_from_stored(stored)
    level_min = _level_min_from_inv(inv, stored, tier)
    primary = _primary_from_inv(inv, stored, slot_type)

    if req_ilvl <= 0 and stored:
        out = dict(stored)
        if "level" in out:
            try:
                out["level"] = _cap_level_min(int(out.get("level") or 1))
            except (TypeError, ValueError):
                out["level"] = _cap_level_min(level_min)
        return out

    return compute_item_requirements(
        tier=tier,
        slot_type=slot_type,
        level_min=level_min,
        primary_stat=primary,
        has_race_lock=required_race is not None,
        has_class_lock=required_class is not None,
        required_race=required_race,
        required_class=required_class,
        req_ilvl=req_ilvl,
    )


def requirements_export(inv: Any) -> tuple[dict, int, bool]:
    """Resolved reqs plus client plus-signal (budget ilvl, never display level)."""
    req = resolve_runtime_requirements(inv)
    rank = int(item_scale_ilvl(inv) or 0)
    return req, rank, rank > 0
