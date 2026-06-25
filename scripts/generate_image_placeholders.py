#!/usr/bin/env python3
"""Generate WebP placeholder files for items (tiered), monsters (from SQL seed), expedition biomes, nav icons.

Uses existing tiered orb webp as source (same pattern as manual orb stubs).

Per-template item dirs (``category/name_slug/t1..t10.webp``) require DATABASE_URL or
POSTGRES_DSN (async ``postgresql+asyncpg://`` or sync ``postgresql://``).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ITEM_WEBP = ROOT / "static/game/items/webp"
ORB = ITEM_WEBP / "orb"
MONSTERS = ROOT / "static/game/monsters"
EXPEDITION_BIOMES = ROOT / "static/game/expeditions/biomes"
NAV_ICONS_DIR = ROOT / "static/game/ui/nav"
SQL_FILE = ROOT / "info/monster_templates_import.sql"

NAV_ICON_SPECS: dict[str, str] = {
    "profile": "👤",
    "dungeons": "🏰",
    "shop": "🏪",
    "tavern": "🍻",
    "caravan": "🐫",
    "guild": "🏛️",
    "training": "💪",
    "menu": "🏠",
}

_NAV_PLACEHOLDER_SIZE = 64
_NAV_PLACEHOLDER_RGB = (26, 20, 16)  # #1a1410 — nav.basement palette
_NAV_PLACEHOLDER_MAX_BYTES = 4096

# biomeBg keys in app.js + BIOME_EMOJI extras (expedition_redesign.py)
EXPEDITION_BIOME_TAGS = [
    "cave",
    "forest",
    "ruins",
    "swamp",
    "temple",
    "dark_temple",
    "fortress",
    "crypt",
    "desert",
    "volcano",
    "abyss",
    "sky",
    "sea_depth",
    "tundra",
    "mountain",
    "dungeon",
    "coast",
]

# static/game/items/webp/README.md art_key list (orb filled separately / refreshed here)
ITEM_ART_KEYS = [
    "weapon_sword_1h",
    "weapon_sword_2h",
    "weapon_axe_1h",
    "weapon_axe_2h",
    "weapon_bow",
    "weapon_staff",
    "armor",
    "shield",
    "orb",
    "ring",
    "amulet",
    "generic",
]


def _ensure_orb_tiers() -> None:
    if not ORB.is_dir():
        print(f"Missing {ORB}", file=sys.stderr)
        sys.exit(1)
    for t in range(1, 11):
        p = ORB / f"t{t}.webp"
        if not p.is_file():
            print(f"Missing {p}", file=sys.stderr)
            sys.exit(1)


def _slot_type_for_item_row(item_type: int, weapon_type: str) -> str:
    """Match guild bank / inventory slot naming for ``items`` table rows."""
    it = int(item_type)
    wt = (weapon_type or "").lower()
    if it == 1:
        return "weapon_1h"
    if it == 2:
        if "orb" in wt:
            return "offhand"
        return "weapon_2h"
    if it == 3:
        return "costume"
    if it in (4, 5):
        return "ring"
    if it == 6:
        return "amulet"
    return "other"


def _async_database_url() -> str | None:
    dsn = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_DSN")
    if not dsn:
        return None
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+asyncpg://", 1)
    return None


def fill_item_webp_legacy() -> None:
    """Flat ``items/webp/<art_key>/t*.webp`` (legacy coarse keys)."""
    _ensure_orb_tiers()
    for key in ITEM_ART_KEYS:
        dest_dir = ITEM_WEBP / key
        dest_dir.mkdir(parents=True, exist_ok=True)
        for t in range(1, 11):
            src = ORB / f"t{t}.webp"
            dst = dest_dir / f"t{t}.webp"
            if src.resolve() == dst.resolve():
                continue
            shutil.copy2(src, dst)
    print(f"items/webp (legacy flat): {len(ITEM_ART_KEYS)} types x 10 tiers -> {ITEM_WEBP}")


_ITEM_PLACEHOLDER_MAX_BYTES = 1024


async def fill_item_webp_from_db(*, force: bool = False) -> int:
    """``items/webp/<category>/<name_slug>/t*.webp`` from item_templates + items."""
    src = ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from waifu_bot.services.item_art import derive_item_art_key, with_legendary_art_prefix

    dsn = _async_database_url()
    if not dsn:
        print(
            "items/webp (per base name): skip — set DATABASE_URL or POSTGRES_DSN",
            file=sys.stderr,
        )
        return 0

    _ensure_orb_tiers()
    engine = create_async_engine(dsn, pool_pre_ping=True)
    keys: set[str] = set()
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT DISTINCT name, slot_type, COALESCE(weapon_type, '') AS wt "
                    "FROM item_templates WHERE name IS NOT NULL AND trim(name) <> ''"
                )
            )
            for name, slot_type, wt in res:
                wt = (wt or "").strip() or None
                keys.add(
                    derive_item_art_key(slot_type, wt, str(name).strip(), display_name=str(name).strip())
                )

            res2 = await conn.execute(
                text(
                    "SELECT DISTINCT name, item_type, COALESCE(weapon_type, '') AS wt "
                    "FROM items WHERE name IS NOT NULL AND trim(name) <> ''"
                )
            )
            for name, item_type, wt in res2:
                wt = (wt or "").strip() or None
                st = _slot_type_for_item_row(int(item_type or 0), wt or "")
                nm = str(name).strip()
                keys.add(derive_item_art_key(st, wt, nm, display_name=nm))
    finally:
        await engine.dispose()

    all_keys = set(keys)
    for key in keys:
        all_keys.add(with_legendary_art_prefix(key))

    counters = {"created": 0, "skipped": 0, "overwritten": 0}
    for key in sorted(all_keys):
        is_legendary = key.startswith("legendary/")
        dest = ITEM_WEBP
        for part in key.split("/"):
            dest = dest / part
        dest.mkdir(parents=True, exist_ok=True)
        for t in range(1, 11):
            src_f = ORB / f"t{t}.webp"
            dst_f = dest / f"t{t}.webp"
            if src_f.resolve() == dst_f.resolve():
                continue
            if (
                not force
                and not is_legendary
                and dst_f.is_file()
                and dst_f.stat().st_size > _ITEM_PLACEHOLDER_MAX_BYTES
            ):
                counters["skipped"] += 1
                continue
            existed = dst_f.is_file()
            shutil.copy2(src_f, dst_f)
            counters["overwritten" if existed else "created"] += 1
    print(
        f"items/webp (per base name): {len(keys)} base + {len(all_keys) - len(keys)} legendary keys "
        f"-> {ITEM_WEBP}; created={counters['created']}, skipped={counters['skipped']}, "
        f"overwritten={counters['overwritten']}"
    )
    return len(all_keys)


# 3:2 placeholders (match solo battle frame)
_MONSTER_PLACEHOLDER_W = 900
_MONSTER_PLACEHOLDER_H = 600
# Generated slug placeholders are ~2.3 KB; custom art is typically much larger.
_MONSTER_PLACEHOLDER_MAX_BYTES = 4096

# Base RGB tints by family (subtle; full art replaces these)
_FAMILY_PLACEHOLDER_RGB: dict[str, tuple[int, int, int]] = {
    "undead": (26, 16, 46),
    "beast": (22, 42, 24),
    "humanoid": (46, 28, 18),
    "demon": (46, 18, 18),
    "elemental": (16, 36, 52),
    "construct": (34, 34, 38),
    "slime": (18, 46, 32),
    "dragon": (52, 36, 12),
    "fae": (38, 20, 46),
}


def _monster_base_rgb(family: str) -> tuple[int, int, int]:
    f = (family or "").strip().lower()
    return _FAMILY_PLACEHOLDER_RGB.get(f, (22, 28, 42))


def _monster_rgb_with_tier(base: tuple[int, int, int], tier: int) -> tuple[int, int, int]:
    t = max(1, min(5, int(tier)))
    f = 0.78 + 0.055 * t
    return tuple(min(255, int(c * f)) for c in base)


def _write_monster_placeholder_webp(
    out_path: Path,
    *,
    family: str,
    tier: int | None,
    skip_existing_art: bool = False,
) -> str:
    """Solid-family-tint 3:2 WebP with a small centered orb marker.

    Returns ``created``, ``skipped``, or ``overwritten``.
    """
    if (
        skip_existing_art
        and out_path.is_file()
        and out_path.stat().st_size > _MONSTER_PLACEHOLDER_MAX_BYTES
    ):
        return "skipped"
    existed = out_path.is_file()
    w, h = _MONSTER_PLACEHOLDER_W, _MONSTER_PLACEHOLDER_H
    base = _monster_base_rgb(family)
    rgb = _monster_rgb_with_tier(base, tier) if tier is not None else base
    img = Image.new("RGB", (w, h), rgb)
    try:
        orb_path = ORB / "t1.webp"
        if orb_path.is_file():
            orb = Image.open(orb_path).convert("RGBA")
            ow, oh = orb.size
            target = min(w, h) // 5
            scale = target / max(ow, oh)
            nw = max(40, int(ow * scale))
            nh = max(40, int(oh * scale))
            orb_s = orb.resize((nw, nh), Image.Resampling.LANCZOS)
            px = (w - nw) // 2
            py = (h - nh) // 2
            img.paste(orb_s, (px, py), orb_s)
    except OSError:
        pass
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=82, method=4)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf.getvalue())
    return "overwritten" if existed else "created"


def parse_monster_rows(sql_text: str) -> list[tuple[str, str]]:
    """Return (family, slug) from INSERT lines."""
    rows: list[tuple[str, str]] = []
    for line in sql_text.splitlines():
        line = line.strip()
        if not line.startswith("('"):
            continue
        # family: third single-quoted field (name, emoji, family)
        m_family = re.match(
            r"\('(?:[^']|\\')*',\s*'(?:[^']|\\')*',\s*'([a-z]+)'\s*,",
            line,
        )
        m_slug = re.search(r",\s*'([a-z0-9_]+)'\s*,\s*FALSE\)\s*[;,]?\s*$", line)
        if m_family and m_slug:
            rows.append((m_family.group(1), m_slug.group(1)))
    return rows


def fill_monsters(*, force: bool = False) -> None:
    if not SQL_FILE.is_file():
        print(f"Missing {SQL_FILE}", file=sys.stderr)
        sys.exit(1)
    _ensure_orb_tiers()
    sql = SQL_FILE.read_text(encoding="utf-8")
    rows = parse_monster_rows(sql)
    if len(rows) < 200:
        print(f"Warning: expected ~285 rows, got {len(rows)}", file=sys.stderr)

    skip_slug_art = not force
    counters = {"created": 0, "skipped": 0, "overwritten": 0}

    def _bump(status: str) -> None:
        counters[status] = counters.get(status, 0) + 1

    MONSTERS.mkdir(parents=True, exist_ok=True)
    _bump(_write_monster_placeholder_webp(MONSTERS / "_unknown.webp", family="unknown", tier=None))

    families: set[str] = set()
    for family, slug in rows:
        families.add(family)
        _bump(
            _write_monster_placeholder_webp(
                MONSTERS / family / f"{slug}.webp",
                family=family,
                tier=None,
                skip_existing_art=skip_slug_art,
            )
        )

    for family in sorted(families):
        _bump(
            _write_monster_placeholder_webp(
                MONSTERS / family / "_family.webp",
                family=family,
                tier=None,
            )
        )
        for t in range(1, 6):
            _bump(
                _write_monster_placeholder_webp(
                    MONSTERS / family / f"_family_t{t}.webp",
                    family=family,
                    tier=t,
                )
            )

    print(
        f"monsters: {len(rows)} slug webp (3:2), {len(families)} families "
        f"(+ _family + _family_t1..5), _unknown -> {MONSTERS}; "
        f"created={counters['created']}, skipped={counters['skipped']}, "
        f"overwritten={counters['overwritten']}"
    )


def fill_expedition_biomes() -> None:
    """One webp per biome tag + default (see static/game/expeditions/biomes/README.md)."""
    _ensure_orb_tiers()
    template = ORB / "t1.webp"
    EXPEDITION_BIOMES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, EXPEDITION_BIOMES / "default.webp")
    for tag in EXPEDITION_BIOME_TAGS:
        shutil.copy2(template, EXPEDITION_BIOMES / f"{tag}.webp")
    print(f"expeditions/biomes: default + {len(EXPEDITION_BIOME_TAGS)} tags -> {EXPEDITION_BIOMES}")


def _nav_color_emoji_font(size: int) -> ImageFont.FreeTypeFont | None:
    candidates = [
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path("/usr/share/fonts/google-noto-emoji/NotoColorEmoji.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return None


def _nav_text_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_nav_marker(draw: ImageDraw.ImageDraw, emoji: str, stem: str, size: int) -> None:
    font_size = max(18, size // 3)
    emoji_font = _nav_color_emoji_font(font_size)
    if emoji_font is not None:
        marker = emoji
        font = emoji_font
        fill = None
    else:
        marker = stem[:2].upper()
        font = _nav_text_font(font_size)
        fill = (232, 184, 75)
    bbox = draw.textbbox((0, 0), marker, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2 - bbox[0]
    y = (size - th) // 2 - bbox[1]
    if fill is None:
        try:
            draw.text((x, y), marker, font=font, embedded_color=True)
            return
        except TypeError:
            fill = (232, 184, 75)
    draw.text((x, y), marker, fill=fill, font=font)


def _write_nav_placeholder_webp(
    out_path: Path,
    *,
    stem: str,
    emoji: str,
    skip_existing_art: bool = True,
) -> str:
    if (
        skip_existing_art
        and out_path.is_file()
        and out_path.stat().st_size > _NAV_PLACEHOLDER_MAX_BYTES
    ):
        return "skipped"
    existed = out_path.is_file()
    size = _NAV_PLACEHOLDER_SIZE
    img = Image.new("RGB", (size, size), _NAV_PLACEHOLDER_RGB)
    draw = ImageDraw.Draw(img)
    _draw_nav_marker(draw, emoji, stem, size)
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=82, method=4)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buf.getvalue())
    return "overwritten" if existed else "created"


def fill_nav_icons(*, force: bool = False) -> None:
    """64×64 WebP stubs for bottom navigation (see static/game/ui/nav/README.md)."""
    skip_existing_art = not force
    counters = {"created": 0, "skipped": 0, "overwritten": 0}
    for stem, emoji in NAV_ICON_SPECS.items():
        status = _write_nav_placeholder_webp(
            NAV_ICONS_DIR / f"{stem}.webp",
            stem=stem,
            emoji=emoji,
            skip_existing_art=skip_existing_art,
        )
        counters[status] += 1
    print(
        f"ui/nav: {len(NAV_ICON_SPECS)} icons -> {NAV_ICONS_DIR}; "
        f"created={counters['created']}, skipped={counters['skipped']}, "
        f"overwritten={counters['overwritten']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate WebP placeholders for items, monsters, expedition biomes, and nav icons.",
    )
    parser.add_argument(
        "--skip-monsters",
        action="store_true",
        help="Do not generate or update monster webp placeholders.",
    )
    parser.add_argument(
        "--force-monsters",
        action="store_true",
        help="Overwrite all monster webp, including custom slug art.",
    )
    parser.add_argument(
        "--force-items",
        action="store_true",
        help="Overwrite all per-name item webp, including custom base art.",
    )
    parser.add_argument(
        "--skip-nav",
        action="store_true",
        help="Do not generate or update nav icon webp placeholders.",
    )
    parser.add_argument(
        "--force-nav",
        action="store_true",
        help="Overwrite all nav icon webp, including custom art.",
    )
    args = parser.parse_args()

    fill_item_webp_legacy()
    asyncio.run(fill_item_webp_from_db(force=args.force_items))
    if not args.skip_monsters:
        fill_monsters(force=args.force_monsters)
    fill_expedition_biomes()
    if not args.skip_nav:
        fill_nav_icons(force=args.force_nav)


if __name__ == "__main__":
    main()
