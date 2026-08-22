"""Item bonus scale for Dungeon+ ilvl above the campaign T10/A10 anchor."""
from __future__ import annotations

import math
from typing import Any, Literal

from waifu_bot.game.dungeon_plus_scaling import dungeon_plus_drop_power_rank

ScaleClass = Literal["flat", "pct", "none"]

ILVL_SCALE_ANCHOR = 60
CURRENT_SCALE_VER = 1
PCT_LN_COEFF = 0.40
TEMPLATE_FRACTION_LN_COEFF = 0.12

PRIMARY_STATS: frozenset[str] = frozenset(
    {
        "strength",
        "agility",
        "intelligence",
        "endurance",
        "charm",
        "luck",
    }
)

PRIMARY_A1_BAND = (1, 2)
PRIMARY_A2_BAND = (2, 3)
PRIMARY_A10_BAND = (12, 20)

PRIMARY_FAMILY_IDS: tuple[str, ...] = (
    "p_primary_strength",
    "p_primary_agility",
    "p_primary_intelligence",
    "p_primary_endurance",
    "p_primary_charm",
    "p_primary_luck",
)

# A3–A10: same ilvl windows as other Diablo families.
_PRIMARY_TIER_BANDS: tuple[tuple[int, int, int, int, int, int, int], ...] = (
    (3, 11, 15, 3, 5, 2, 3),
    (4, 16, 20, 4, 6, 3, 4),
    (5, 21, 25, 5, 8, 3, 4),
    (6, 26, 30, 6, 10, 3, 5),
    (7, 31, 35, 7, 11, 3, 5),
    (8, 36, 40, 8, 13, 4, 6),
    (9, 41, 45, 10, 16, 4, 6),
    (10, 46, 60, 12, 20, 4, 6),
)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default)


def _row_get(obj: Any, key: str, default: Any = 0) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    mapping = getattr(obj, "_mapping", None)
    if mapping is not None:
        if key in mapping:
            return mapping[key]
        return default
    return getattr(obj, key, default)


def item_scale_ilvl(obj: Any) -> int:
    """Budget ilvl for scale. Never use display total_level (affix level_delta inflates it)."""
    power_rank = _as_int(_row_get(obj, "power_rank", 0), 0)
    if power_rank > 0:
        return power_rank
    plus = _as_int(_row_get(obj, "plus_level_source", 0), 0)
    if plus > 0:
        return dungeon_plus_drop_power_rank(plus)
    return 0


def flat_scale(ilvl: int) -> float:
    lvl = max(0, int(ilvl or 0))
    if lvl <= ILVL_SCALE_ANCHOR:
        return 1.0
    return float(lvl) / float(ILVL_SCALE_ANCHOR)


def pct_affix_scale(ilvl: int) -> float:
    lvl = max(int(ILVL_SCALE_ANCHOR), int(ilvl or 0))
    if lvl <= ILVL_SCALE_ANCHOR:
        return 1.0
    return 1.0 + float(PCT_LN_COEFF) * math.log(float(lvl) / float(ILVL_SCALE_ANCHOR))


def template_fraction_scale(ilvl: int) -> float:
    lvl = max(int(ILVL_SCALE_ANCHOR), int(ilvl or 0))
    if lvl <= ILVL_SCALE_ANCHOR:
        return 1.0
    return 1.0 + float(TEMPLATE_FRACTION_LN_COEFF) * math.log(
        float(lvl) / float(ILVL_SCALE_ANCHOR)
    )


def scale_class(effect_key: str | None) -> ScaleClass:
    key = str(effect_key or "").strip().lower()
    if not key:
        return "none"
    if (
        key.startswith("passive_node_level_add:")
        or key.startswith("passive_branch_level_add:")
        or key == "passive_all_nodes_level_add"
    ):
        return "none"
    if key in PRIMARY_STATS:
        return "flat"
    if (
        key.endswith("_pct")
        or key.endswith("_percent")
        or key.startswith("media_damage_")
        or ":percent" in key
    ):
        return "pct"
    if key.endswith("_flat") or ":flat" in key or key in {"damage_flat"}:
        return "flat"
    return "flat"


def scale_int(value: int, scale: float) -> int:
    raw = int(value or 0)
    if raw == 0:
        return 0
    factor = float(scale)
    if factor <= 1.0:
        return raw
    out = int(round(raw * factor))
    if raw > 0:
        return max(raw, out)
    return min(raw, out)


def apply_flat_to_int(value: int | None, ilvl: int) -> int | None:
    if value is None:
        return None
    return scale_int(int(value), flat_scale(ilvl))


def apply_template_fraction(value: float, ilvl: int) -> float:
    raw = float(value or 0.0)
    if raw <= 0:
        return raw
    return raw * template_fraction_scale(ilvl)


def scale_affix_raw(effect_key: str | None, raw: int, ilvl: int) -> int:
    kind = scale_class(effect_key)
    if kind == "none":
        return int(raw)
    if kind == "pct":
        return scale_int(int(raw), pct_affix_scale(ilvl))
    return scale_int(int(raw), flat_scale(ilvl))


def remap_legacy_primary_to_a10(raw: int, affix_tier: int | None) -> int:
    """Map A1/A2 primary rolls onto the A10 band by percentile."""
    value = int(raw or 0)
    tier = int(affix_tier or 1)
    if tier >= 10:
        return value
    if tier <= 1:
        vmin, vmax = PRIMARY_A1_BAND
    elif tier <= 2:
        vmin, vmax = PRIMARY_A2_BAND
    else:
        return value
    span = max(1, int(vmax) - int(vmin))
    pct = max(0.0, min(1.0, (value - int(vmin)) / float(span)))
    a10_lo, a10_hi = PRIMARY_A10_BAND
    return int(round(int(a10_lo) + pct * (int(a10_hi) - int(a10_lo))))


def primary_catchup_scaled(raw: int, affix_tier: int | None, ilvl: int) -> int:
    mapped = remap_legacy_primary_to_a10(raw, affix_tier)
    return scale_int(mapped, flat_scale(ilvl))


def scaled_template_armor(armor_base: int | float, obj: Any) -> int:
    raw = int(armor_base or 0)
    if raw <= 0:
        return 0
    return scale_int(raw, flat_scale(item_scale_ilvl(obj)))


def scaled_template_fraction(value: float, obj: Any) -> float:
    return apply_template_fraction(float(value or 0.0), item_scale_ilvl(obj))


def should_rescale_inventory(obj: Any) -> bool:
    ver = _as_int(_row_get(obj, "ilvl_stat_scale_ver", 0), 0)
    if ver >= CURRENT_SCALE_VER:
        return False
    plus = _as_int(_row_get(obj, "plus_level_source", 0), 0)
    rank = _as_int(_row_get(obj, "power_rank", 0), 0)
    return plus > 0 or rank > 0


def apply_ilvl_scale_to_fresh_item(
    inv: Any,
    item: Any | None = None,
    *,
    scale_ilvl: int | None = None,
) -> None:
    """Multiply stored T10-band numbers once after generation rolls."""
    ver = _as_int(getattr(inv, "ilvl_stat_scale_ver", 0), 0)
    if ver >= CURRENT_SCALE_VER:
        return
    silvl = int(scale_ilvl) if scale_ilvl is not None else item_scale_ilvl(inv)
    if silvl <= 0:
        inv.ilvl_stat_scale_ver = CURRENT_SCALE_VER
        return

    if getattr(inv, "base_stat_value", None) is not None:
        inv.base_stat_value = apply_flat_to_int(int(inv.base_stat_value), silvl)
    if getattr(inv, "damage_min", None) is not None:
        inv.damage_min = apply_flat_to_int(int(inv.damage_min), silvl)
    if getattr(inv, "damage_max", None) is not None:
        inv.damage_max = apply_flat_to_int(int(inv.damage_max), silvl)
    if item is not None and getattr(item, "damage", None) is not None:
        item.damage = inv.damage_max if getattr(inv, "damage_max", None) is not None else inv.damage_min

    for aff in getattr(inv, "affixes", None) or []:
        stat = str(getattr(aff, "stat", "") or "")
        try:
            raw = int(float(getattr(aff, "value", 0) or 0))
        except (TypeError, ValueError):
            continue
        aff.value = str(scale_affix_raw(stat, raw, silvl))

    inv.ilvl_stat_scale_ver = CURRENT_SCALE_VER


def stamp_ilvl_scale_meta(
    inv: Any,
    *,
    plus_level: int = 0,
    scale_ilvl: int = 0,
) -> None:
    """Set power_rank / plus source so later reads use the drop budget, not display ilvl."""
    pl = max(0, int(plus_level or 0))
    silvl = max(0, int(scale_ilvl or 0))
    if pl > 0:
        inv.plus_level_source = pl
    if _as_int(getattr(inv, "power_rank", 0), 0) <= 0:
        if silvl > 0:
            inv.power_rank = silvl
        elif pl > 0:
            inv.power_rank = dungeon_plus_drop_power_rank(pl)


def primary_affix_tier_seed_rows() -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for family_id in PRIMARY_FAMILY_IDS:
        for tier, min_lvl, max_lvl, vmin, vmax, dmin, dmax in _PRIMARY_TIER_BANDS:
            rows.append(
                {
                    "family_id": family_id,
                    "affix_tier": tier,
                    "min_total_level": min_lvl,
                    "max_total_level": max_lvl,
                    "value_min": vmin,
                    "value_max": vmax,
                    "level_delta_min": dmin,
                    "level_delta_max": dmax,
                    "weight_mult": 100,
                }
            )
    return rows
