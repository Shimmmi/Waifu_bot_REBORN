"""Tiered item art (webp) helpers.

Assets live under repo `static/game/` and are served at `/static/game/...`.
We keep a DB registry to map (art_key, tier) -> relative_path so the asset
layout can change without code changes. Legacy DB paths may use `items_webp/...`.

`art_key` is usually ``category/name_slug`` (one slash): filesystem path under
``items/webp/``; slug comes from the item template base name (no affixes).
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.paths import static_game_directory

logger = logging.getLogger(__name__)


class ItemArtPersistError(Exception):
    """Raised when generated item art cannot be written or registered."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

GAME_STATIC_PREFIX = "/static/game"


def normalize_game_relative_path(relative_path: str) -> str:
    """Normalize DB/default relative_path to filesystem path under static/game/."""
    rel = (relative_path or "").strip().lstrip("/")
    if rel.startswith("items_webp/"):
        rel = "items/webp/" + rel[len("items_webp/") :]
    return rel


def game_asset_public_url(relative_path: str) -> str:
    """Map stored relative_path (DB or default) to public URL under /static/game/."""
    return f"{GAME_STATIC_PREFIX}/{normalize_game_relative_path(relative_path)}"


def relative_path_to_game_file(relative_path: str) -> Path:
    """Resolve relative_path to an absolute file under static/game/."""
    rel = normalize_game_relative_path(relative_path)
    return static_game_directory() / rel


def read_game_asset_data_url(relative_path: str) -> str | None:
    """Read a static/game asset as data URL for multimodal AI; None if missing."""
    path = relative_path_to_game_file(relative_path)
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    mime = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


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


def _display_name_implies_staff_wand(display_name: str | None) -> bool:
    """RU/EN hints when weapon_type in DB is missing or wrong (e.g. жезл → generic art)."""
    if not display_name:
        return False
    n = display_name.casefold()
    needles = (
        "жезл",
        "посох",
        "скипетр",
        "staff",
        "wand",
        "rod",
        "scepter",
        "sceptre",
        "crystal rod",
    )
    return any(x in n for x in needles)


def _weapon_category_from_display_name(display_name: str | None) -> str | None:
    """When ``weapon_type`` is only ``two_hand`` / ``one_hand`` etc., infer art category from name."""
    if not display_name:
        return None
    n = display_name.casefold()
    if _display_name_implies_staff_wand(display_name) and "bow" not in n and "axe" not in n:
        return "weapon_staff"
    if any(x in n for x in ("арбалет", "crossbow")):
        return "weapon_bow"
    if "лук" in n or " bow" in n or n.startswith("bow"):
        return "weapon_bow"
    if any(
        x in n
        for x in (
            "пика",
            "копь",
            "spear",
            "pike",
            "lance",
            "глеф",
            "алебард",
            "halberd",
            "trident",
            "трезуб",
        )
    ):
        return "weapon_sword"
    if any(x in n for x in ("топор", "axe", "секир")):
        return "weapon_axe"
    if any(x in n for x in ("меч", "sword", "сабл", "клинок", "ятаган", "скимитар", "rapier", "катана")):
        return "weapon_sword"
    if any(x in n for x in ("кинжал", "dagger", "knife", "кортик")):
        return "generic"
    return None


def derive_image_key(
    slot_type: str | None,
    weapon_type: str | None,
    display_name: str | None = None,
) -> str:
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
        if wt == "orb":
            return "orb"
        return "shield"
    if "weapon" in st:
        inferred = _weapon_category_from_display_name(display_name)
        if inferred:
            return inferred
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


def derive_art_key(
    slot_type: str | None,
    weapon_type: str | None,
    display_name: str | None = None,
) -> str:
    """Tiered art key (webp): includes handedness where it matters."""
    st = (slot_type or "").lower()
    base = derive_image_key(slot_type, weapon_type, display_name)

    # Distinguish 1h/2h for swords/axes (as per planned art packs).
    if base in ("weapon_sword", "weapon_axe"):
        if "2h" in st:
            return f"{base}_2h"
        if "1h" in st:
            return f"{base}_1h"
        # If slot_type isn't specific, keep base.
        return base

    return base


# Russian (and common Cyrillic letters) → latin, for stable directory slugs.
_CYR_TO_LATIN: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "і": "i",
    "ї": "yi",
    "є": "ye",
    "ґ": "g",
}


def slugify_item_base_name(name: str | None, *, max_len: int = 48) -> str:
    """ASCII slug from template base name (affix-free). Empty → ``base``."""
    raw = (name or "").strip().lower()
    if not raw:
        return "base"
    parts: list[str] = []
    for ch in raw:
        if ch.isascii() and ch.isalnum():
            parts.append(ch)
        elif ch in _CYR_TO_LATIN:
            parts.append(_CYR_TO_LATIN[ch])
        else:
            parts.append("_")
    merged = "".join(parts)
    merged = re.sub(r"[^a-z0-9]+", "_", merged)
    merged = re.sub(r"_+", "_", merged).strip("_")
    if not merged:
        return "base"
    if len(merged) > max_len:
        merged = merged[:max_len].rstrip("_")
    return merged or "base"


def derive_item_art_key(
    slot_type: str | None,
    weapon_type: str | None,
    base_name: str | None,
    *,
    display_name: str | None = None,
) -> str:
    """Full tiered art key: ``derive_art_key(...) / slugify(base_name)``."""
    label = display_name or base_name
    cat = derive_art_key(slot_type, weapon_type, label)
    slug = slugify_item_base_name(base_name)
    return f"{cat}/{slug}"


LEGENDARY_ART_PREFIX = "legendary"


def with_legendary_art_prefix(art_key: str) -> str:
    """Prefix base art_key for legendary-tier icons: ``legendary/cat/slug``."""
    k = str(art_key or "").strip().strip("/")
    if not k or k.startswith(f"{LEGENDARY_ART_PREFIX}/"):
        return k
    return f"{LEGENDARY_ART_PREFIX}/{k}"


def is_legendary_art_key(art_key: str) -> bool:
    return str(art_key or "").strip().startswith(f"{LEGENDARY_ART_PREFIX}/")


def resolve_inventory_item_art_key(
    inv: Any,
    *,
    display_base_name: str,
) -> str:
    """Art key for an inventory item; legendaries use ``legendary/`` prefix."""
    from waifu_bot.game.item_template_names import resolve_art_base_name_ru

    art_base = resolve_art_base_name_ru(inv, display_base_name)
    base_key = derive_item_art_key(
        getattr(inv, "slot_type", None),
        getattr(inv, "weapon_type", None),
        art_base,
        display_name=art_base,
    )
    if getattr(inv, "is_legendary", False) or int(getattr(inv, "rarity", 0) or 0) >= 5:
        return with_legendary_art_prefix(base_key)
    return base_key


def _slug_from_art_key(art_key: str) -> str | None:
    k = str(art_key or "").strip()
    if "/" not in k:
        return None
    slug = k.rsplit("/", 1)[-1].strip()
    return slug or None


async def _lookup_item_art_row(
    session: AsyncSession,
    art_key: str,
    tier: int,
) -> m.ItemArt | None:
    """Exact (art_key, tier) match, then slug+tier fallback for legacy admin paths."""
    k = str(art_key or "").strip()
    t = normalize_tier(tier)
    if not k:
        return None
    row = (
        await session.execute(
            select(m.ItemArt).where(
                m.ItemArt.art_key == k,
                m.ItemArt.tier == t,
                m.ItemArt.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    slug = _slug_from_art_key(k)
    if not slug:
        return None
    if is_legendary_art_key(k):
        leg_rows = (
            (
                await session.execute(
                    select(m.ItemArt).where(
                        m.ItemArt.art_key.like(f"{LEGENDARY_ART_PREFIX}/%/{slug}"),
                        m.ItemArt.tier == t,
                        m.ItemArt.enabled.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(leg_rows) == 1:
            return leg_rows[0]
        if len(leg_rows) > 1:
            for row in leg_rows:
                if row.art_key == k:
                    return row
        return None
    alt_rows = (
        (
            await session.execute(
                select(m.ItemArt).where(
                    m.ItemArt.art_key.like(f"%/{slug}"),
                    m.ItemArt.art_key.not_like(f"{LEGENDARY_ART_PREFIX}/%"),
                    m.ItemArt.tier == t,
                    m.ItemArt.enabled.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(alt_rows) == 1:
        return alt_rows[0]
    return None


def default_relative_path(art_key: str, tier: int) -> str:
    return f"items_webp/{art_key}/t{tier}.webp"


async def persist_item_art_webp(
    session: AsyncSession,
    art_key: str,
    tier: int,
    webp: bytes,
) -> str:
    """Write WebP bytes to static/game and upsert ``item_art`` row; return public URL."""
    from waifu_bot.services.item_art_generation import normalize_art_key

    ak = normalize_art_key(art_key)
    if not ak:
        raise ItemArtPersistError("invalid_art_key")

    t = normalize_tier(tier)
    out_dir = static_game_directory() / "items" / "webp" / ak
    out_file = out_dir / f"t{t}.webp"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(webp)
    except OSError:
        logger.exception(
            "persist_item_art_webp write failed path=%s (check REPO_ROOT / filesystem permissions)",
            out_file,
        )
        raise ItemArtPersistError("item_art_write_failed") from None

    db_rel = default_relative_path(ak, t)
    row = (
        await session.execute(
            select(m.ItemArt).where(m.ItemArt.art_key == ak, m.ItemArt.tier == t)
        )
    ).scalar_one_or_none()
    if row:
        row.relative_path = db_rel
        row.mime = "image/webp"
        row.enabled = True
    else:
        session.add(
            m.ItemArt(
                art_key=ak,
                tier=t,
                relative_path=db_rel,
                mime="image/webp",
                enabled=True,
            )
        )
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("persist_item_art_webp DB commit failed art_key=%s tier=%s", ak, t)
        try:
            out_file.unlink(missing_ok=True)
        except OSError:
            logger.exception("persist_item_art_webp unlink after DB fail path=%s", out_file)
        raise ItemArtPersistError("item_art_db_failed") from None

    return game_asset_public_url(db_rel)


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


async def resolve_item_art_relative_path(
    session: AsyncSession,
    art_key: str,
    tier: Any,
) -> str:
    """DB relative_path for (art_key, tier) or default items_webp/... path."""
    k = str(art_key or "").strip()
    t = normalize_tier(tier)
    if not k:
        return default_relative_path("misc/base", t)
    row = await _lookup_item_art_row(session, k, t)
    if row and (row.relative_path or "").strip():
        return str(row.relative_path).strip()
    return default_relative_path(k, t)


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
        rel = art_map.get((k, t))
        if not rel:
            row = await _lookup_item_art_row(session, k, t)
            if row and (row.relative_path or "").strip():
                rel = str(row.relative_path).strip()
        if not rel:
            rel = default_relative_path(k, t)
        _set_field(it, "image_url", game_asset_public_url(rel))

    return items

