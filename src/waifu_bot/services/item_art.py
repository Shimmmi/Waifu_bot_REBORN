"""Tiered item art (webp) helpers.

The WebApp serves assets from /webapp/assets via FastAPI StaticFiles mount.
We keep a DB registry to map (art_key, tier) -> relative_path so the asset
layout can change without code changes.
"""

from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m


def normalize_tier(tier: Any) -> int:
    try:
        t = int(tier)
    except Exception:
        t = 1
    if t < 1:
        return 1
    if t > 10:
        return 10
    return t


def derive_image_key(slot_type: str | None, weapon_type: str | None) -> str:
    """Legacy base image key (svg placeholders)."""
    st = (slot_type or "").lower()
    wt = (weapon_type or "").lower()
    if "ring" in st:
        return "ring"
    if "amulet" in st:
        return "amulet"
    if "costume" in st or "armor" in st:
        return "armor"
    if "offhand" in st:
        return "shield"
    if "weapon" in st:
        if "axe" in wt:
            return "weapon_axe"
        if "sword" in wt:
            return "weapon_sword"
        if "bow" in wt:
            return "weapon_bow"
        if "staff" in wt or "wand" in wt:
            return "weapon_staff"
        if "dagger" in wt:
            return "generic"
        return "generic"
    return "generic"


def derive_art_key(slot_type: str | None, weapon_type: str | None) -> str:
    """Tiered art key (webp): includes handedness where it matters."""
    st = (slot_type or "").lower()
    base = derive_image_key(slot_type, weapon_type)

    # Distinguish 1h/2h for swords/axes (as per planned art packs).
    if base in ("weapon_sword", "weapon_axe"):
        if "2h" in st:
            return f"{base}_2h"
        if "1h" in st:
            return f"{base}_1h"
        # If slot_type isn't specific, keep base.
        return base

    return base


def default_relative_path(art_key: str, tier: int) -> str:
    return f"items_webp/{art_key}/t{tier}.webp"


def _get_field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _set_field(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        try:
            setattr(obj, key, value)
        except Exception:
            # Pydantic models may be frozen depending on config; ignore silently.
            pass


async def enrich_items_with_image_urls(session: AsyncSession, items: list[Any]) -> list[Any]:
    """Attach image_url to payload items (dict or Pydantic models).

    Expects each item to have:
    - art_key (preferred) or image_key
    - tier
    """
    pairs: set[tuple[str, int]] = set()
    for it in items:
        k = str(_get_field(it, "art_key") or _get_field(it, "image_key") or "").strip()
        if not k:
            continue
        t = normalize_tier(_get_field(it, "tier"))
        pairs.add((k, t))

    art_map: dict[tuple[str, int], str] = {}
    if pairs:
        res = await session.execute(
            select(m.ItemArt).where(
                tuple_(m.ItemArt.art_key, m.ItemArt.tier).in_(pairs),
                m.ItemArt.enabled.is_(True),
            )
        )
        for row in res.scalars().all():
            art_map[(row.art_key, int(row.tier))] = row.relative_path

    for it in items:
        k = str(_get_field(it, "art_key") or _get_field(it, "image_key") or "").strip()
        if not k:
            continue
        t = normalize_tier(_get_field(it, "tier"))
        rel = art_map.get((k, t)) or default_relative_path(k, t)
        _set_field(it, "image_url", f"/webapp/assets/{rel.lstrip('/')}")

    return items

