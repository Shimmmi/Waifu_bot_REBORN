"""Canonical vs legendary display names for item_base_templates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from waifu_bot.db import models as m


def template_item_name(base: dict[str, Any] | Any, *, legendary: bool) -> str:
    """Spawn-time items.name: legendary display name or canonical base name."""
    if isinstance(base, dict):
        if legendary:
            leg = str(base.get("legendary_name_ru") or "").strip()
            if leg:
                return leg
        return str(base.get("name") or "Предмет")
    if legendary:
        leg = str(getattr(base, "legendary_name_ru", None) or "").strip()
        if leg:
            return leg
    return str(getattr(base, "name", None) or "Предмет")


def resolve_art_base_name_ru(inv: "m.InventoryItem", display_base_name: str) -> str:
    """Slug source for webp art: canonical template name when known."""
    canon = getattr(inv, "_canonical_base_name", None)
    if canon is not None:
        canon_s = str(canon).strip()
        if canon_s:
            return canon_s
    return str(display_base_name or "").strip() or "Предмет"
