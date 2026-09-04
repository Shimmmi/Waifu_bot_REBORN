"""Format legendary bonus description_tpl with rolled/catalog params."""

from __future__ import annotations

import re
from typing import Any


def _pct(value: Any) -> str:
    try:
        return str(int(round(float(value) * 100)))
    except (TypeError, ValueError):
        return "0"


def _num(value: Any, *, digits: int = 2) -> str:
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(fv - round(fv)) < 1e-9:
        return str(int(round(fv)))
    text = f"{fv:.{digits}f}".rstrip("0").rstrip(".")
    return text


def build_format_mapping(params: dict[str, Any] | None) -> dict[str, Any]:
    """Expand params with ``*_pct`` / display aliases used in description_tpl."""
    src = dict(params or {})
    out: dict[str, Any] = dict(src)
    effects = src.get("effects") if isinstance(src.get("effects"), dict) else {}

    def _put(key: str, value: Any) -> None:
        out[key] = value
        if isinstance(value, (int, float)) and not str(key).endswith("_pct"):
            if 0 < float(value) <= 1.5 and key not in {
                "damage_multiplier",
                "crit_damage_multiplier",
                "cap_multiplier",
                "max_damage_multiplier",
                "drop_multiplier",
                "gold_multiplier",
                "drop_chance_multiplier",
                "discharge_multiplier",
            }:
                out[f"{key}_pct"] = int(round(float(value) * 100))
            out[f"{key}_display"] = _num(value)

    for key, val in list(src.items()):
        if key == "effects":
            continue
        _put(str(key), val)
    for key, val in effects.items():
        _put(str(key), val)

    # Common aliases from migration 0091 templates.
    if "damage_bonus" in out and "damage_bonus_pct" not in out:
        out["damage_bonus_pct"] = int(round(float(out["damage_bonus"]) * 100))
    if "drop_bonus" in out and "drop_bonus_pct" not in out:
        out["drop_bonus_pct"] = int(round(float(out["drop_bonus"]) * 100))
    if "bonus_per_affix" in out:
        out["bonus_per_affix_pct"] = int(round(float(out["bonus_per_affix"]) * 100))
    if "hp_threshold_pct" in out:
        out["hp_threshold_pct_display"] = int(round(float(out["hp_threshold_pct"]) * 100))
    if "bonus_per_10pct" in out:
        out["bonus_per_10pct_pct"] = int(round(float(out["bonus_per_10pct"]) * 100))
    if "max_bonus" in out:
        out["max_bonus_pct"] = int(round(float(out["max_bonus"]) * 100))
    if "proc_chance" in out:
        out["proc_chance_pct"] = int(round(float(out["proc_chance"]) * 100))
    if "heal_pct" in out:
        out["heal_pct"] = out.get("heal_pct")
        out["heal_pct_pct"] = int(round(float(out["heal_pct"]) * 100)) if float(out.get("heal_pct") or 0) <= 1.5 else out["heal_pct"]
    if "heal_pct_of_damage" in out:
        out["heal_pct_of_damage_pct"] = int(round(float(out["heal_pct_of_damage"]) * 100))
    if "phantom_pct" in out:
        out["phantom_pct_pct"] = int(round(float(out["phantom_pct"]) * 100))
    if "hit_pct" in out:
        out["hit_pct_pct"] = int(round(float(out["hit_pct"]) * 100))
    if "echo_pct" in out:
        out["echo_pct_pct"] = int(round(float(out["echo_pct"]) * 100))
    if "return_multiplier" in out:
        out["return_multiplier_pct"] = int(round(float(out["return_multiplier"]) * 100))
    if "bonus_per_sale" in out:
        out["bonus_per_sale_pct"] = int(round(float(out["bonus_per_sale"]) * 100))
    if "drop_bonus_per_stack" in out:
        out["drop_bonus_per_stack_pct"] = int(round(float(out["drop_bonus_per_stack"]) * 100))
    if "bonus_pct" in out and "bonus_pct_pct" not in out:
        try:
            bp = float(out["bonus_pct"])
            if bp <= 1.5:
                out["bonus_pct"] = int(round(bp * 100)) if "{bonus_pct}" in "" else out["bonus_pct"]
                out["bonus_pct_pct"] = int(round(bp * 100))
        except (TypeError, ValueError):
            pass
    return out


class _SafeMap(dict):
    def __missing__(self, key: str) -> str:
        return "{" + str(key) + "}"


def _rewrite_generic(tpl: str, params: dict[str, Any]) -> str:
    effects = params.get("effects") if isinstance(params.get("effects"), dict) else {}
    text = tpl
    mult = effects.get("damage_multiplier")
    if mult is None:
        mult = params.get("damage_multiplier")
    if mult is not None:
        text = re.sub(r"[×xX](\d+(?:[.,]\d+)?)", f"×{_num(mult)}", text, count=1)
    bonus = effects.get("damage_bonus")
    if bonus is None:
        bonus = params.get("damage_bonus")
    if bonus is not None:
        text = re.sub(
            r"\+(\d+(?:[.,]\d+)?)%",
            f"+{_pct(bonus)}%",
            text,
            count=1,
        )
    extra = effects.get("extra_hit_pct")
    if extra is None and isinstance(effects.get("extra_hits"), list) and effects["extra_hits"]:
        extra = effects["extra_hits"][0]
    if extra is not None:
        text = re.sub(
            r"(\d+)\s*%\s*(урона|удара)",
            lambda m: f"{_pct(extra)}% {m.group(2)}",
            text,
            count=1,
        )
    return text


def format_legendary_description(tpl: str, params: dict[str, Any] | None) -> str:
    raw = str(tpl or "").strip()
    if not raw:
        return ""
    mapping = build_format_mapping(params)
    if "{" in raw:
        try:
            return raw.format_map(_SafeMap(mapping))
        except (ValueError, IndexError):
            pass
    return _rewrite_generic(raw, mapping)
