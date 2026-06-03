"""Compose Russian display names for inventory items (multi-prefix / multi-suffix)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waifu_bot.db import models as m


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
    if low.endswith("ый") or low.endswith("ой"):
        stem = a[:-2]
        return stem + ("ая" if gender == "f" else "ое")
    if low.endswith(("кий", "гий", "хий")):
        stem = a[:-2]
        return stem + ("ая" if gender == "f" else "ое")
    if low.endswith("ий"):
        stem = a[:-2]
        return stem + ("яя" if gender == "f" else "ее")
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
        name = str(getattr(a, "name", "") or "").strip()
        if not name:
            continue
        if kind == "affix":
            prefixes.append(name)
        elif kind == "suffix":
            suffixes.append(name)

    base_name = resolve_base_name_ru(inv)
    if inflect_prefixes and prefixes:
        gender = guess_gender_ru(base_name)
        prefixes = [inflect_adj_ru(p, gender) for p in prefixes]

    display_name = " ".join(prefixes + [base_name] + suffixes).strip()
    return base_name, display_name or base_name
