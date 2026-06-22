"""Compose Russian display names for inventory items (multi-prefix / multi-suffix)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waifu_bot.db import models as m


from waifu_bot.game.affix_display_names import (
    _is_raw_affix_name,
    resolve_prefix_name_ru,
    resolve_suffix_name_ru,
)


def _affix_family_string_id(affix: "m.InventoryAffix") -> str | None:
    fam = getattr(affix, "family", None)
    if fam is not None:
        fid = getattr(fam, "family_id", None)
        if fid:
            return str(fid)
    stored = str(getattr(affix, "name", "") or "").strip()
    if stored.startswith(("s_", "p_")) and _is_raw_affix_name(stored, family_id=stored):
        return stored
    return None


def resolve_stored_affix_name_ru(affix: "m.InventoryAffix") -> str:
    """Re-resolve affix display name when DB holds a raw effect_key / family_id placeholder."""
    stored = str(getattr(affix, "name", "") or "").strip()
    kind = getattr(affix, "kind", None)
    tier = int(getattr(affix, "affix_tier", None) or getattr(affix, "tier", None) or 1)
    stat = str(getattr(affix, "stat", "") or "")
    if stored and not _is_raw_affix_name(stored, effect_key=stat):
        return stored
    fam_key = _affix_family_string_id(affix)
    if kind == "suffix":
        if fam_key:
            return resolve_suffix_name_ru(fam_key, tier)
        return stored
    return resolve_prefix_name_ru(stat, tier, family_id=fam_key)


def fallback_base_name_ru(inv: "m.InventoryItem") -> str:
    st = (inv.slot_type or "").lower()
    wt = (inv.weapon_type or "").lower()
    if "ring" in st:
        return "Кольцо"
    if "amulet" in st:
        return "Амулет"
    if "costume" in st or "armor" in st:
        return "Доспех"
    if "offhand" in st:
        item_name = (inv.item.name if inv.item else "") or ""
        if wt == "orb" or "сфера" in item_name.lower():
            return "Сфера"
        return "Щит"
    if "weapon" in st:
        if "axe" in wt:
            return "Топор"
        if "sword" in wt:
            return "Меч"
        if "bow" in wt:
            return "Лук"
        if "staff" in wt or "wand" in wt:
            return "Посох"
        if "dagger" in wt:
            return "Кинжал"
        return "Оружие"
    return "Предмет"


def resolve_base_name_ru(inv: "m.InventoryItem") -> str:
    base_name = inv.item.name if inv.item else fallback_base_name_ru(inv)
    if str(base_name or "").strip().lower() in ("предмет", "item"):
        return fallback_base_name_ru(inv)
    return str(base_name or "").strip() or fallback_base_name_ru(inv)


def guess_gender_ru(noun: str) -> str:
    """Rough grammatical gender for RU nouns: n, f, or m (default)."""
    w_full = (noun or "").strip().lower()
    head = w_full.split()[0] if w_full else ""
    w = head.strip("()[]{}.,!?:;\"'") if head else w_full.strip("()[]{}.,!?:;\"'")
    if not w:
        return "m"
    if w.endswith(("о", "е", "ё", "ие", "мя")):
        return "n"
    if w.endswith(("а", "я")):
        return "f"
    return "m"


def inflect_adj_ru(adj: str, gender: str) -> str:
    """Minimal adjective agreement for common masculine nominative forms."""
    a = (adj or "").strip()
    if not a or gender == "m":
        return a
    low = a.lower()

    def _cap(stem: str, ending: str) -> str:
        if not stem:
            return ending
        if stem[0].isupper():
            return stem[0] + stem[1:] + ending
        return stem + ending

    if low.endswith("ский") or low.endswith("ческий"):
        stem = a[:-2]
        return _cap(stem, "ая" if gender == "f" else "ое")
    if low.endswith("ённый") or low.endswith("енный"):
        stem = a[:-2]
        return _cap(stem, "ая" if gender == "f" else "ое")
    if low.endswith("ый") or low.endswith("ой"):
        stem = a[:-2]
        return _cap(stem, "ая" if gender == "f" else "ое")
    if low.endswith(("кий", "гий", "хий")):
        stem = a[:-2]
        return _cap(stem, "ая" if gender == "f" else "ое")
    if low.endswith("ий"):
        stem = a[:-2]
        return _cap(stem, "яя" if gender == "f" else "ее")
    return a


def compose_item_display_name_ru(
    inv: "m.InventoryItem",
    *,
    inflect_prefixes: bool = True,
) -> tuple[str, str]:
    """Return (base_name, display_name) with all prefixes before base and suffixes after."""
    prefixes: list[str] = []
    suffixes: list[str] = []
    for a in inv.affixes or []:
        kind = getattr(a, "kind", None)
        name = resolve_stored_affix_name_ru(a)
        if not name:
            continue
        if kind == "affix":
            prefixes.append(name)
        elif kind == "suffix":
            suffixes.append(name)

    base_name = resolve_base_name_ru(inv)
    if getattr(inv, "is_legendary", False) is True or int(getattr(inv, "rarity", 0) or 0) >= 5:
        return base_name, base_name
    if inflect_prefixes and prefixes:
        gender = guess_gender_ru(base_name)
        prefixes = [inflect_adj_ru(p, gender) for p in prefixes]

    display_name = " ".join(prefixes + [base_name] + suffixes).strip()
    return base_name, display_name or base_name
