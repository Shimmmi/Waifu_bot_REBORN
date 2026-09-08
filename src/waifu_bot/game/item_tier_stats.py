"""Scale identity base stats from native template tier to drop tier 1–10."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

# Fallback if catalog SQL / baked curves are unavailable.
_DEFAULT_CURVE: dict[str, list[float]] = {
    "dmg_min": [4, 6, 8, 11, 14, 18, 22, 28, 35, 44],
    "dmg_max": [7, 11, 15, 20, 26, 33, 41, 51, 64, 80],
    "armor_base": [4, 8, 14, 22, 32, 44, 58, 74, 94, 118],
    "stat1_value": [1, 1, 2, 2, 2, 3, 3, 4, 4, 5],
    "stat2_value": [0, 0, 1, 1, 2, 2, 3, 3, 4, 5],
    "base_price": [10, 22, 40, 65, 100, 150, 210, 290, 380, 500],
}

STAT_KEYS = ("dmg_min", "dmg_max", "armor_base", "stat1_value", "stat2_value", "base_price")

_WEAPON_RE = re.compile(
    r"\('([^']*(?:''[^']*)*)','([^']+)','([^']*)',(?:NULL|'([^']*)'),"
    r"(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(?:NULL|'([^']*)'),(\d+),(\d+)"
)
_ARMOR_RE = re.compile(
    r"\('([^']*(?:''[^']*)*)','(armor)','([^']*)',(?:NULL|'([^']*)')?,"
    r"(\d+),(\d+),(\d+),(\d+),(?:NULL|'([^']*)'),(\d+),(\d+)"
)


def _repo_root() -> Path:
    from waifu_bot.paths import repository_root

    return repository_root()


def _parse_catalog_stat_rows() -> list[dict[str, Any]]:
    path = _repo_root() / "info" / "item_base_templates_import.sql"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for m in _WEAPON_RE.finditer(text):
        rows.append(
            {
                "item_type": m.group(2),
                "subtype": m.group(3),
                "tier": int(m.group(5)),
                "dmg_min": int(m.group(8)),
                "dmg_max": int(m.group(9)),
                "armor_base": int(m.group(11)),
                "stat1_value": int(m.group(13)),
                "stat2_value": 0,
                "base_price": int(m.group(14)),
            }
        )
    for m in _ARMOR_RE.finditer(text):
        rows.append(
            {
                "item_type": "armor",
                "subtype": m.group(3),
                "tier": int(m.group(5)),
                "dmg_min": 0,
                "dmg_max": 0,
                "armor_base": int(m.group(8)),
                "stat1_value": int(m.group(10)),
                "stat2_value": 0,
                "base_price": int(m.group(11)),
            }
        )
    return rows


def _median_or_zero(vals: list[float]) -> float:
    nums = [float(v) for v in vals if v is not None]
    if not nums:
        return 0.0
    return float(median(nums))


@lru_cache(maxsize=1)
def stat_curves() -> dict[tuple[str, str], dict[str, list[float]]]:
    """(item_type, subtype) → per-stat list index 0 = tier 1."""
    baked = _repo_root() / "scripts" / "data" / "item_tier_stat_curves.json"
    if baked.is_file():
        try:
            raw = json.loads(baked.read_text(encoding="utf-8"))
            out: dict[tuple[str, str], dict[str, list[float]]] = {}
            for key, stats in (raw.get("curves") or {}).items():
                if "|" not in str(key):
                    continue
                it, st = str(key).split("|", 1)
                out[(it, st)] = {k: [float(x) for x in v] for k, v in stats.items()}
            if out:
                return out
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    rows = _parse_catalog_stat_rows()
    grouped: dict[tuple[str, str], dict[int, list[dict[str, Any]]]] = {}
    for r in rows:
        key = (str(r.get("item_type") or ""), str(r.get("subtype") or ""))
        t = max(1, min(10, int(r.get("tier") or 1)))
        grouped.setdefault(key, {}).setdefault(t, []).append(r)

    curves: dict[tuple[str, str], dict[str, list[float]]] = {}
    for key, by_tier in grouped.items():
        curve: dict[str, list[float]] = {sk: [] for sk in STAT_KEYS}
        for t in range(1, 11):
            bucket = by_tier.get(t) or []
            for sk in STAT_KEYS:
                if bucket:
                    curve[sk].append(_median_or_zero([float(x.get(sk) or 0) for x in bucket]))
                else:
                    curve[sk].append(float(_DEFAULT_CURVE[sk][t - 1]))
        curves[key] = curve
    return curves


def _curve_for(item_type: str, subtype: str) -> dict[str, list[float]]:
    curves = stat_curves()
    key = (str(item_type or ""), str(subtype or ""))
    if key in curves:
        return curves[key]
    for (it, _st), c in curves.items():
        if it == key[0]:
            return c
    return {sk: list(vals) for sk, vals in _DEFAULT_CURVE.items()}


def _factor(native_tier: int, drop_tier: int, series: list[float]) -> float:
    n = max(1, min(10, int(native_tier)))
    d = max(1, min(10, int(drop_tier)))
    src = float(series[n - 1]) if n - 1 < len(series) else 1.0
    dst = float(series[d - 1]) if d - 1 < len(series) else src
    if src <= 0:
        fallback = float(_DEFAULT_CURVE["dmg_min"][n - 1] or 1)
        return dst / max(1.0, fallback)
    return dst / src


def level_band_for_tier(tier: int) -> tuple[int, int]:
    t = max(1, min(10, int(tier)))
    lo = (t - 1) * 5 + 1
    return lo, lo + 4


def apply_drop_tier_to_base(base: dict[str, Any], drop_tier: int) -> dict[str, Any]:
    """Return a copy of the identity row with stats/levels for ``drop_tier``."""
    out = dict(base)
    native = max(1, min(10, int(base.get("tier") or 1)))
    dest = max(1, min(10, int(drop_tier)))
    lo, hi = level_band_for_tier(dest)
    out["_native_tier"] = native
    if native == dest:
        out["tier"] = dest
        out["level_min"] = lo
        out["level_max"] = hi
        return out

    curve = _curve_for(str(base.get("item_type") or ""), str(base.get("subtype") or ""))
    for sk in STAT_KEYS:
        raw = out.get(sk)
        try:
            val = int(raw or 0)
        except (TypeError, ValueError):
            val = 0
        if val <= 0:
            continue
        fac = _factor(native, dest, curve.get(sk) or _DEFAULT_CURVE.get(sk) or [1.0] * 10)
        scaled = int(round(val * fac))
        if sk in {"dmg_min", "dmg_max", "stat1_value", "stat2_value", "base_price"}:
            scaled = max(1, scaled)
        else:
            scaled = max(0, scaled)
        out[sk] = scaled
    if int(out.get("dmg_min") or 0) > int(out.get("dmg_max") or 0) > 0:
        out["dmg_max"] = out["dmg_min"]
    out["tier"] = dest
    out["level_min"] = lo
    out["level_max"] = hi
    return out


def median_anchor_stats(item_type: str, subtype: str, *, tier: int = 5) -> dict[str, int]:
    """Typical stats for a new extra identity at the given native tier."""
    t = max(1, min(10, int(tier)))
    curve = _curve_for(item_type, subtype)
    out: dict[str, int] = {}
    for sk in STAT_KEYS:
        series = curve.get(sk) or _DEFAULT_CURVE[sk]
        out[sk] = max(0, int(round(float(series[t - 1]))))
    it = str(item_type or "")
    st = str(subtype or "")
    if it in {"ring", "amulet"}:
        out["dmg_min"] = 0
        out["dmg_max"] = 0
        out["armor_base"] = 0
    elif it == "armor" or st == "offhand":
        out["dmg_min"] = 0
        out["dmg_max"] = 0
    elif st != "offhand":
        out["armor_base"] = 0
    return out
