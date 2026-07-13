#!/usr/bin/env python3
"""Dump full image-generation prompts for expeditions, monsters, and items.

Writes text files under info/art_generation_prompts/ for manual generation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

OUT_DIR = ROOT / "info" / "art_generation_prompts"
SQL_FILE = ROOT / "info" / "monster_templates_import.sql"
ITEM_WEBP = ROOT / "static" / "game" / "items" / "webp"
CANONICAL_NAMES = ROOT / "scripts" / "data" / "item_base_template_canonical_names.json"

_MONSTER_LINE_RE = re.compile(
    r"\('([^']*)',\s*'[^']*',\s*'([a-z]+)',\s*'(\[[^\]]*\])'::jsonb,\s*"
    r"(\d+),\s*\d+,\s*\d+,\s*(\d+),\s*\d+,\s*\d+,\s*(\d+),\s*"
    r"(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*"
    r".*(TRUE|FALSE),\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*[\d.]+,\s*\d+,\s*"
    r"'([a-z0-9_]+)',\s*FALSE\)\s*[;,]?\s*$"
)


@dataclass(frozen=True)
class MonsterRow:
    template_id: int
    name: str
    family: str
    tags: list[str]
    tier: int
    level_min: int
    hp_base: int
    hp_per_level: int
    dmg_base: int
    dmg_per_level: int
    base_difficulty: int
    boss_allowed: bool
    slug: str


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


def parse_monster_rows(sql_text: str) -> list[MonsterRow]:
    rows: list[MonsterRow] = []
    tid = 0
    for line in sql_text.splitlines():
        line = line.strip()
        if not line.startswith("('"):
            continue
        m = _MONSTER_LINE_RE.match(line)
        if not m:
            continue
        tid += 1
        name, family, tags_raw, tier_s, level_min_s, bd_s, hp_b, hp_pl, dmg_b, dmg_pl, boss_s, slug = (
            m.groups()
        )
        try:
            tags = json.loads(tags_raw.replace("'", '"'))
        except json.JSONDecodeError:
            tags = []
        if not isinstance(tags, list):
            tags = []
        rows.append(
            MonsterRow(
                template_id=tid,
                name=name,
                family=family,
                tags=[str(t) for t in tags],
                tier=int(tier_s),
                level_min=int(level_min_s),
                hp_base=int(hp_b),
                hp_per_level=int(hp_pl),
                dmg_base=int(dmg_b),
                dmg_per_level=int(dmg_pl),
                base_difficulty=int(bd_s),
                boss_allowed=boss_s == "TRUE",
                slug=slug,
            )
        )
    return rows


def dominant_trait_ru(row: MonsterRow) -> str:
    dpl = float(row.dmg_per_level)
    hpl = float(row.hp_per_level)
    bd = float(row.base_difficulty)
    tr = float(row.tier)
    candidates: list[tuple[float, str]] = [
        (dpl / 2.5, "в бою особенно опасен быстрым ростом урона с уровнем"),
        (hpl / 12.0, "пугает плотностью — много здоровья на уровень"),
        (bd / 40.0, "отличается высокой базовой сложностью шаблона"),
        (tr / 4.0, "считается серьёзной угрозой по рангу"),
    ]
    score, label = max(candidates, key=lambda x: x[0])
    if score <= 0:
        return "на дороге встречается как обычная угроза акта"
    return label


def template_reference_stats(row: MonsterRow) -> tuple[int, int, int]:
    lv = max(1, row.level_min)
    hp = row.hp_base + row.hp_per_level * max(0, lv - 1)
    dmg = row.dmg_base + row.dmg_per_level * max(0, lv - 1)
    return lv, max(hp, 1), max(dmg, 1)


def dump_expeditions(out: Path) -> int:
    from waifu_bot.game.expedition_narrative_catalog import EXPEDITION_LOCATION_ARCHETYPES
    from waifu_bot.services.expedition_art_generation import build_expedition_watercolor_prompt

    lines: list[str] = [
        "# Expedition archetype image prompts (watercolor, 3:2)",
        f"# Total: {len(EXPEDITION_LOCATION_ARCHETYPES)}",
        "",
    ]
    for arch in EXPEDITION_LOCATION_ARCHETYPES:
        prompt = build_expedition_watercolor_prompt(
            archetype_id=arch.id,
            archetype_name=arch.name_ru,
            biome_tag=arch.biome_tag,
            narrative_hints=arch.narrative_hints,
        )
        lines.append(f"{'=' * 72}")
        lines.append(f"ID: {arch.id}")
        lines.append(f"Name: {arch.name_ru}")
        lines.append(f"Biome: {arch.biome_tag}")
        lines.append(f"Hints: {', '.join(arch.narrative_hints)}")
        lines.append(f"Output: static/game/expeditions/archetypes/{arch.id}.webp")
        lines.append("")
        lines.append(prompt)
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return len(EXPEDITION_LOCATION_ARCHETYPES)


def dump_monsters(out: Path) -> int:
    from waifu_bot.services.monster_art_generation import _family_gloss, build_monster_anime_prompt

    if not SQL_FILE.is_file():
        print(f"Missing {SQL_FILE}", file=sys.stderr)
        return 0
    rows = parse_monster_rows(SQL_FILE.read_text(encoding="utf-8"))
    lines: list[str] = [
        "# Monster image prompts (anime, 3:2)",
        f"# Source: {SQL_FILE.name}",
        f"# Total: {len(rows)}",
        "",
    ]
    for row in rows:
        level, max_hp, damage = template_reference_stats(row)
        family_en = _family_gloss(row.family)
        trait_ru = dominant_trait_ru(row)
        tags_hint = ", ".join(row.tags[:12]) if row.tags else None
        prompt = build_monster_anime_prompt(
            display_name=row.name,
            family_en=family_en,
            tier=row.tier,
            level=level,
            max_hp=max_hp,
            damage=damage,
            is_boss=row.boss_allowed,
            is_elite=False,
            affix_names=[],
            template_trait_ru=trait_ru,
            tags_hint=tags_hint,
        )
        lines.append(f"{'=' * 72}")
        lines.append(f"template_id: {row.template_id}")
        lines.append(f"Name: {row.name}")
        lines.append(f"Family: {row.family}")
        lines.append(f"Slug: {row.slug}")
        lines.append(f"Tier: {row.tier}/5")
        lines.append(f"Stats: level={level}, HP~{max_hp}, dmg~{damage}")
        lines.append(f"Output: static/game/monsters/{row.family}/{row.slug}.webp")
        lines.append("")
        lines.append(prompt)
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return len(rows)


def _build_slug_to_name_map() -> dict[str, str]:
    from waifu_bot.services.item_art import slugify_item_base_name

    slug_to_name: dict[str, str] = {}
    if CANONICAL_NAMES.is_file():
        data = json.loads(CANONICAL_NAMES.read_text(encoding="utf-8"))
        for name in (data.get("names") or {}).values():
            slug = slugify_item_base_name(str(name))
            slug_to_name.setdefault(slug, str(name))
    return slug_to_name


def _discover_art_keys_from_disk() -> list[tuple[str, str | None, str | None]]:
    """Return (art_key, display_label, weapon_type)."""
    from waifu_bot.services.item_art import derive_item_art_key, with_legendary_art_prefix

    slug_to_name = _build_slug_to_name_map()
    found: dict[str, tuple[str | None, str | None]] = {}

    def add_key(art_key: str, label: str | None, wt: str | None) -> None:
        if art_key not in found:
            found[art_key] = (label, wt)

    if ITEM_WEBP.is_dir():
        for path in ITEM_WEBP.rglob("t1.webp"):
            rel = path.relative_to(ITEM_WEBP)
            parts = rel.parts
            if len(parts) < 3:
                continue
            if parts[0] == "legendary" and len(parts) >= 4:
                art_key = "/".join(parts[:-1])
                slug = parts[-2]
            elif len(parts) == 3:
                art_key = f"{parts[0]}/{parts[1]}"
                slug = parts[1]
            else:
                continue
            label = slug_to_name.get(slug)
            add_key(art_key, label, None)
            leg = with_legendary_art_prefix(art_key)
            if leg != art_key:
                add_key(leg, label, None)

    seed = ROOT / "scripts" / "data" / "item_templates.json"
    if seed.is_file():
        for row in json.loads(seed.read_text(encoding="utf-8")):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            wt = (row.get("weapon_type") or "") or None
            ak = derive_item_art_key(
                row.get("slot_type"), wt, name, display_name=name
            )
            add_key(ak, name, wt)
            add_key(with_legendary_art_prefix(ak), name, wt)

    return sorted((k, v[0], v[1]) for k, v in found.items())


def _slot_type_for_item_row(item_type: int, weapon_type: str) -> str:
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


async def _fetch_art_keys_from_db() -> list[tuple[str, str | None, str | None]] | None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from waifu_bot.services.item_art import derive_item_art_key, with_legendary_art_prefix

    dsn = _async_database_url()
    if not dsn:
        return None

    found: dict[str, tuple[str | None, str | None]] = {}

    def add_key(art_key: str, label: str | None, wt: str | None) -> None:
        if art_key not in found or (label and not found[art_key][0]):
            found[art_key] = (label, wt)

    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT DISTINCT name, slot_type, COALESCE(weapon_type, '') AS wt "
                    "FROM item_templates WHERE name IS NOT NULL AND trim(name) <> ''"
                )
            )
            for name, slot_type, wt in res:
                nm = str(name).strip()
                w = (wt or "").strip() or None
                ak = derive_item_art_key(slot_type, w, nm, display_name=nm)
                add_key(ak, nm, w)
                add_key(with_legendary_art_prefix(ak), nm, w)

            res2 = await conn.execute(
                text(
                    "SELECT DISTINCT name, item_type, COALESCE(weapon_type, '') AS wt "
                    "FROM items WHERE name IS NOT NULL AND trim(name) <> ''"
                )
            )
            for name, item_type, wt in res2:
                nm = str(name).strip()
                w = (wt or "").strip() or None
                st = _slot_type_for_item_row(int(item_type or 0), w or "")
                ak = derive_item_art_key(st, w, nm, display_name=nm)
                add_key(ak, nm, w)
                add_key(with_legendary_art_prefix(ak), nm, w)
    finally:
        await engine.dispose()

    return sorted((k, v[0], v[1]) for k, v in found.items())


def dump_items(out: Path, *, tiers: list[int]) -> int:
    from waifu_bot.services.item_art_generation import build_item_pixel_art_prompt

    rows = asyncio.run(_fetch_art_keys_from_db())
    source = "database"
    if rows is None:
        rows = _discover_art_keys_from_disk()
        source = "static/game/items/webp + item_templates.json"

    lines: list[str] = [
        "# Item image prompts (pixel art, 1:1)",
        f"# Source: {source}",
        f"# Art keys: {len(rows)}",
        f"# Tiers per key: {', '.join(str(t) for t in tiers)}",
        "",
    ]
    for art_key, display_label, weapon_type in rows:
        lines.append(f"{'=' * 72}")
        lines.append(f"art_key: {art_key}")
        if display_label:
            lines.append(f"display_label: {display_label}")
        if weapon_type:
            lines.append(f"weapon_type: {weapon_type}")
        lines.append(f"Output dir: static/game/items/webp/{art_key}/")
        lines.append("")
        for tier in tiers:
            prompt = build_item_pixel_art_prompt(
                art_key,
                tier,
                weapon_type=weapon_type,
                display_label=display_label,
            )
            lines.append(f"--- tier {tier} -> t{tier}.webp ---")
            lines.append(prompt)
            lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump art generation prompts to info/art_generation_prompts/")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUT_DIR,
        help=f"Output directory (default: {OUT_DIR})",
    )
    parser.add_argument(
        "--skip-expeditions",
        action="store_true",
        help="Skip expedition archetype prompts",
    )
    parser.add_argument(
        "--skip-monsters",
        action="store_true",
        help="Skip monster prompts",
    )
    parser.add_argument(
        "--skip-items",
        action="store_true",
        help="Skip item prompts",
    )
    parser.add_argument(
        "--item-tiers",
        default="1,2,3,4,5,6,7,8,9,10",
        help="Comma-separated item tiers to dump (default: all 1-10)",
    )
    args = parser.parse_args()
    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    tiers = [int(x.strip()) for x in args.item_tiers.split(",") if x.strip()]
    counts: dict[str, int] = {}

    if not args.skip_expeditions:
        n = dump_expeditions(out_dir / "expeditions.txt")
        counts["expeditions"] = n
        print(f"expeditions: {n} prompts -> {out_dir / 'expeditions.txt'}")

    if not args.skip_monsters:
        n = dump_monsters(out_dir / "monsters.txt")
        counts["monsters"] = n
        print(f"monsters: {n} prompts -> {out_dir / 'monsters.txt'}")

    if not args.skip_items:
        n = dump_items(out_dir / "items.txt", tiers=tiers)
        counts["items"] = n
        print(f"items: {n} art keys x {len(tiers)} tiers -> {out_dir / 'items.txt'}")

    readme = out_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Art generation prompts",
                "",
                "Auto-generated by `scripts/dump_art_prompts.py` for manual image generation.",
                "",
                "| File | Contents |",
                "|------|----------|",
                "| `expeditions.txt` | 50 expedition archetype prompts (watercolor, 3:2) |",
                "| `monsters.txt` | 285 monster template prompts (anime, 3:2) |",
                "| `items.txt` | Item prompts per `art_key` and tier (pixel art, 1:1) |",
                "",
                "Monster frames are generated at **3:2 landscape**, but the active dungeon UI crops to the **centered 1:1** square. "
                "Monster prompts therefore keep the head and primary body mass inside that centered 1:1 safe zone.",
                "",
                "Regenerate:",
                "",
                "```bash",
                "python3 scripts/dump_art_prompts.py",
                "```",
                "",
                "Model default: `sourceful/riverflow-v2-fast` (`OPENROUTER_MODEL_IMAGE`).",
                "",
                f"Last run counts: {counts}",
            ]
        ),
        encoding="utf-8",
    )
    print(f"README -> {readme}")


if __name__ == "__main__":
    main()
