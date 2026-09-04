"""Scale legendary bonus magnitudes by item tier (catalog value = T10 max)."""

from __future__ import annotations

import copy
import random
from typing import Any

TIER_MIN_SCALE = 0.33
TIER_MAX_SCALE = 1.0

# Additive / percent-of-base magnitudes (0.60 → 60%).
FRACTION_KEYS = frozenset(
    {
        "damage_bonus",
        "drop_bonus",
        "gold_bonus",
        "extra_hit_pct",
        "phantom_pct",
        "hit_pct",
        "heal_pct",
        "heal_pct_of_damage",
        "heal_pct_max_hp",
        "max_bonus",
        "bonus_per_affix",
        "bonus_per_10pct",
        "bonus_per_block",
        "bonus_per_charge",
        "bonus_per_sale",
        "bonus_pct",
        "echo_pct",
        "aoe_multiplier",
        "remaining_monsters_damage_multiplier",
        "monster_self_damage_pct_base",
        "damage_flat_pct_base",
        "drop_bonus_per_stack",
        "damage_per_minute",
    }
)

# Multipliers stored as 2.0 = ×2. Scale the excess over 1. Values < 1 are left as-is.
RATIO_KEYS = frozenset(
    {
        "damage_multiplier",
        "crit_damage_multiplier",
        "cap_multiplier",
        "max_damage_multiplier",
        "drop_multiplier",
        "gold_multiplier",
        "drop_chance_multiplier",
        "discharge_multiplier",
        "return_multiplier",
    }
)

FLAT_KEYS = frozenset(
    {
        "damage_flat",
        "heal_flat",
        "monster_self_damage",
    }
)

LIST_FRACTION_KEYS = frozenset(
    {
        "extra_hits",
        "replace_with_hits",
    }
)


def clamp_tier(tier: int) -> int:
    return max(1, min(10, int(tier or 1)))


def scale_lo(tier: int) -> float:
    t = clamp_tier(tier)
    return TIER_MIN_SCALE + (TIER_MAX_SCALE - TIER_MIN_SCALE) * (t - 1) / 9.0


def scale_hi(tier: int) -> float:
    t = clamp_tier(tier)
    if t >= 10:
        return TIER_MAX_SCALE
    return TIER_MIN_SCALE + (TIER_MAX_SCALE - TIER_MIN_SCALE) * t / 9.0


def scale_mid(tier: int) -> float:
    return (scale_lo(tier) + scale_hi(tier)) / 2.0


def roll_scale_k(tier: int, *, rng: random.Random | None = None) -> float:
    lo, hi = scale_lo(tier), scale_hi(tier)
    if hi < lo:
        lo, hi = hi, lo
    roller = rng.uniform if rng is not None else random.uniform
    return float(roller(lo, hi))


def transform_numeric(key: str, value: Any, k: float) -> Any:
    name = str(key or "")
    if name in RATIO_KEYS:
        fv = float(value)
        if fv > 1.0:
            return 1.0 + (fv - 1.0) * float(k)
        return fv
    if name in FRACTION_KEYS:
        return float(value) * float(k)
    if name in FLAT_KEYS:
        return int(round(float(value) * float(k)))
    return value


def _walk(obj: Any, k: float) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, val in obj.items():
            if key in LIST_FRACTION_KEYS and isinstance(val, list):
                out[key] = [float(x) * float(k) for x in val]
            elif key in FRACTION_KEYS or key in RATIO_KEYS or key in FLAT_KEYS:
                try:
                    out[key] = transform_numeric(str(key), val, k)
                except (TypeError, ValueError):
                    out[key] = _walk(val, k)
            else:
                out[key] = _walk(val, k)
        return out
    if isinstance(obj, list):
        return [_walk(x, k) for x in obj]
    return obj


def scale_params(params: dict[str, Any] | None, k: float) -> dict[str, Any]:
    """Return a deep copy of params with magnitude keys scaled by ``k``."""
    src = copy.deepcopy(params or {})
    if not isinstance(src, dict):
        return {}
    return _walk(src, float(k))


def magnitude_overlay(catalog: dict[str, Any] | None, scaled: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only scaled magnitude keys (for JSONB snapshot)."""
    cat = catalog or {}
    sc = scaled or {}

    def _pick(src: Any, scaled_node: Any) -> Any:
        if isinstance(src, dict) and isinstance(scaled_node, dict):
            out: dict[str, Any] = {}
            for key, val in src.items():
                if key in LIST_FRACTION_KEYS and key in scaled_node:
                    out[key] = scaled_node[key]
                elif key in FRACTION_KEYS or key in RATIO_KEYS or key in FLAT_KEYS:
                    if key in scaled_node:
                        out[key] = scaled_node[key]
                elif isinstance(val, dict):
                    nested = _pick(val, scaled_node.get(key))
                    if nested:
                        out[key] = nested
                elif isinstance(val, list) and val and isinstance(val[0], dict):
                    items = []
                    sc_list = scaled_node.get(key) if isinstance(scaled_node.get(key), list) else []
                    for i, item in enumerate(val):
                        sc_item = sc_list[i] if i < len(sc_list) else {}
                        nested = _pick(item, sc_item)
                        items.append(nested if nested else item)
                    if items:
                        out[key] = items
            return out
        return {}

    overlay = _pick(cat, sc)
    return overlay if isinstance(overlay, dict) else {}


def roll_bonus_magnitudes(
    params: dict[str, Any] | None,
    tier: int,
    *,
    midpoint: bool = False,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    k = scale_mid(tier) if midpoint else roll_scale_k(tier, rng=rng)
    scaled = scale_params(params, k)
    return magnitude_overlay(params, scaled)


def deep_merge(base: dict[str, Any] | None, overlay: dict[str, Any] | None) -> dict[str, Any]:
    """Recursive dict merge; overlay wins on leaves."""
    if not isinstance(base, dict):
        return copy.deepcopy(overlay) if isinstance(overlay, dict) else {}
    out = copy.deepcopy(base)
    if not isinstance(overlay, dict):
        return out
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out
