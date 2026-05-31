"""Resolve instance vs template secondaries on inventory items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FRACTION_SECONDARIES: frozenset[str] = frozenset(
    {
        "crit_chance_pct",
        "evade_pct",
        "dmg_reduce_pct",
        "hp_max_pct",
        "exp_bonus_pct",
        "gold_bonus_pct",
        "magic_find_pct",
    }
)


@dataclass(frozen=True)
class TemplateSecondaryRow:
    armor_base: int = 0
    secondary_bonus_type: str | None = None
    secondary_bonus_value: float = 0.0


@dataclass(frozen=True)
class ResolvedSecondaries:
    armor_base: int
    bonus_type: str | None
    bonus_value: float
    fraction_type: str | None
    fraction_value: float
    fraction_awakened: bool


def is_fraction_secondary_type(secondary_type: str | None) -> bool:
    return str(secondary_type or "").strip().lower() in FRACTION_SECONDARIES


def is_passive_secondary_type(secondary_type: str | None) -> bool:
    t = str(secondary_type or "").strip().lower()
    return (
        t.startswith("passive_node_level_add:")
        or t.startswith("passive_branch_level_add:")
        or t == "passive_all_nodes_level_add"
    )


def is_accessory_slot(inv: Any) -> bool:
    st = str(getattr(inv, "slot_type", "") or "").lower()
    return "ring" in st or "amulet" in st


def template_row_from_mapping(row: Any) -> TemplateSecondaryRow:
    if isinstance(row, dict):
        return TemplateSecondaryRow(
            armor_base=int(row.get("armor_base", 0) or 0),
            secondary_bonus_type=row.get("secondary_bonus_type"),
            secondary_bonus_value=float(row.get("secondary_bonus_value", 0.0) or 0.0),
        )
    return TemplateSecondaryRow(
        armor_base=int(getattr(row, "armor_base", 0) or 0),
        secondary_bonus_type=getattr(row, "secondary_bonus_type", None),
        secondary_bonus_value=float(getattr(row, "secondary_bonus_value", 0.0) or 0.0),
    )


def resolve_item_secondaries(
    inv: Any,
    template: TemplateSecondaryRow | None = None,
) -> ResolvedSecondaries:
    """Instance columns take precedence; template fills gaps."""
    tpl = template or TemplateSecondaryRow()
    armor = int(getattr(inv, "_armor_base", None) or tpl.armor_base or 0)

    inst_bonus_type = getattr(inv, "secondary_bonus_type", None)
    inst_frac_type = getattr(inv, "secondary_fraction_type", None)
    awakened = bool(getattr(inv, "secondary_awakened", False))

    bonus_type: str | None = inst_bonus_type
    bonus_value = float(getattr(inv, "secondary_bonus_value", 0) or 0)
    fraction_type: str | None = inst_frac_type
    fraction_value = float(getattr(inv, "secondary_fraction_value", 0) or 0)

    tpl_type = str(tpl.secondary_bonus_type or "").strip() or None
    tpl_val = float(tpl.secondary_bonus_value or 0.0)

    if bonus_type is None and tpl_type:
        if is_passive_secondary_type(tpl_type):
            bonus_type = tpl_type
            bonus_value = tpl_val
        elif not is_fraction_secondary_type(tpl_type):
            bonus_type = tpl_type
            bonus_value = tpl_val

    if fraction_type is None and tpl_type and is_fraction_secondary_type(tpl_type):
        fraction_type = tpl_type
        fraction_value = tpl_val

    if bonus_type is not None and is_fraction_secondary_type(bonus_type):
        if fraction_type is None:
            fraction_type = bonus_type
            fraction_value = bonus_value
        bonus_type = None
        bonus_value = 0.0

    return ResolvedSecondaries(
        armor_base=armor,
        bonus_type=bonus_type,
        bonus_value=bonus_value,
        fraction_type=fraction_type,
        fraction_value=fraction_value,
        fraction_awakened=awakened,
    )


def attach_resolved_attrs(inv: Any, resolved: ResolvedSecondaries) -> None:
    setattr(inv, "_armor_base", resolved.armor_base)
    setattr(inv, "_secondary_bonus_type", resolved.bonus_type)
    setattr(inv, "_secondary_bonus_value", resolved.bonus_value if resolved.bonus_type else 0.0)
    setattr(inv, "_secondary_fraction_type", resolved.fraction_type)
    setattr(inv, "_secondary_fraction_value", resolved.fraction_value)
    setattr(inv, "_secondary_awakened", resolved.fraction_awakened)
    setattr(inv, "_resolved_secondaries", resolved)


def effective_fraction_for_enchant(
    _inv: Any,
    resolved: ResolvedSecondaries,
) -> tuple[str | None, float]:
    """Value used to compute enchant_sec_step (fraction channel only)."""
    return resolved.fraction_type, resolved.fraction_value


def effective_fraction_combat(
    inv: Any,
    resolved: ResolvedSecondaries,
) -> tuple[str | None, float]:
    """Fraction value including sharpen bonus."""
    e = 0 if bool(getattr(inv, "is_broken", False)) else int(getattr(inv, "enchant_level", 0) or 0)
    sec_step = float(getattr(inv, "enchant_sec_step", 0.0) or 0.0)
    val = float(resolved.fraction_value) + sec_step * e
    return resolved.fraction_type, val


def snapshot_secondaries_from_template(inv: Any, template: TemplateSecondaryRow) -> None:
    """Copy template secondary into instance columns at item creation."""
    t = str(template.secondary_bonus_type or "").strip() or None
    v = float(template.secondary_bonus_value or 0.0)
    if not t or v <= 0:
        return
    if is_passive_secondary_type(t):
        inv.secondary_bonus_type = t
        inv.secondary_bonus_value = v
    elif is_fraction_secondary_type(t):
        inv.secondary_fraction_type = t
        inv.secondary_fraction_value = v


def should_awaken_fraction_on_plus_one(inv: Any, resolved: ResolvedSecondaries) -> bool:
    if resolved.fraction_awakened or resolved.fraction_value > 0:
        return False
    if is_accessory_slot(inv):
        return True
    return is_passive_secondary_type(resolved.bonus_type)
