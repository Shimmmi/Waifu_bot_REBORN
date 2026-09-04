"""WebP item identities: one name across tiers 1–10, extra slugs from disk."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from waifu_bot.paths import static_game_directory
from waifu_bot.services.item_art import (
    derive_item_art_key,
    slugify_item_base_name,
)

WEBP_ROOT_REL = Path("items") / "webp"
IDENTITY_MAP_REL = Path("scripts") / "data" / "item_art_identity_map.json"

REFINE_SLUG_TOKENS = (
    "vozvysh",
    "iskazheniya",
    "iskazhenie",
    "iskazhen",
    "apogey",
    "preispodney",
)

CATEGORY_META: dict[str, dict[str, str | None]] = {
    "weapon_sword_1h": {"item_type": "weapon", "subtype": "one_hand", "attack_type": "melee"},
    "weapon_sword_2h": {"item_type": "weapon", "subtype": "two_hand", "attack_type": "melee"},
    "weapon_axe_1h": {"item_type": "weapon", "subtype": "one_hand", "attack_type": "melee"},
    "weapon_axe_2h": {"item_type": "weapon", "subtype": "two_hand", "attack_type": "melee"},
    "weapon_bow": {"item_type": "weapon", "subtype": "bow", "attack_type": "ranged"},
    "weapon_staff": {"item_type": "weapon", "subtype": "staff", "attack_type": "magic"},
    "orb": {"item_type": "weapon", "subtype": "orb", "attack_type": "magic"},
    "shield": {"item_type": "weapon", "subtype": "offhand", "attack_type": "melee"},
    "armor": {"item_type": "armor", "subtype": "medium", "attack_type": None},
    "ring": {"item_type": "ring", "subtype": "ring", "attack_type": None},
    "amulet": {"item_type": "amulet", "subtype": "amulet", "attack_type": None},
    "generic": {"item_type": "weapon", "subtype": "one_hand", "attack_type": "melee"},
}

_ARMOR_ROBE = ("mantiya", "plasch", "shelk", "odeyanie", "rubaha", "tkan", "pokrov", "nakidka")
_ARMOR_HEAVY = ("laty", "dospeh", "pantsir", "koloss", "adamant")
_ARMOR_LIGHT = ("kozha", "kozhan", "stegan")

_LATIN_TO_CYR: tuple[tuple[str, str], ...] = (
    ("sch", "щ"),
    ("zh", "ж"),
    ("kh", "х"),
    ("ts", "ц"),
    ("ch", "ч"),
    ("sh", "ш"),
    ("yu", "ю"),
    ("ya", "я"),
    ("yo", "ё"),
    ("yi", "ї"),
    ("ye", "е"),
    ("a", "а"),
    ("b", "б"),
    ("v", "в"),
    ("g", "г"),
    ("d", "д"),
    ("e", "е"),
    ("z", "з"),
    ("i", "и"),
    ("j", "й"),
    ("k", "к"),
    ("l", "л"),
    ("m", "м"),
    ("n", "н"),
    ("o", "о"),
    ("p", "п"),
    ("r", "р"),
    ("s", "с"),
    ("t", "т"),
    ("u", "у"),
    ("f", "ф"),
    ("h", "х"),
    ("y", "ы"),
    ("c", "к"),
    ("w", "в"),
    ("x", "кс"),
    ("q", "к"),
)


def webp_root() -> Path:
    return static_game_directory() / WEBP_ROOT_REL


def identity_map_path(repo_root: Path | None = None) -> Path:
    if repo_root is None:
        from waifu_bot.paths import repository_root

        repo_root = repository_root()
    return repo_root / IDENTITY_MAP_REL


def is_refine_variant_slug(slug: str) -> bool:
    s = str(slug or "").lower()
    return any(tok in s for tok in REFINE_SLUG_TOKENS)


def armor_subtype_from_slug(slug: str) -> str:
    s = str(slug or "").lower()
    if any(tok in s for tok in _ARMOR_ROBE):
        return "robe"
    if any(tok in s for tok in _ARMOR_HEAVY):
        return "heavy"
    if any(tok in s for tok in _ARMOR_LIGHT):
        return "light"
    return "medium"


def category_meta(category: str, *, slug: str = "") -> dict[str, str | None]:
    meta = dict(CATEGORY_META.get(category) or {})
    if not meta:
        return {"item_type": "weapon", "subtype": "one_hand", "attack_type": "melee"}
    if category == "armor":
        meta["subtype"] = armor_subtype_from_slug(slug)
    return meta


def slot_type_from_category(category: str) -> str:
    if category in {"weapon_sword_1h", "weapon_axe_1h", "generic"}:
        return "weapon_1h"
    if category in {"weapon_sword_2h", "weapon_axe_2h", "weapon_bow", "weapon_staff"}:
        return "weapon_2h"
    if category in {"orb", "shield"}:
        return "offhand"
    if category == "armor":
        return "costume"
    if category == "ring":
        return "ring"
    if category == "amulet":
        return "amulet"
    return "other"


def _unslug_token(token: str, word_map: dict[str, str]) -> str:
    t = str(token or "").strip().lower()
    if not t:
        return ""
    if t in word_map:
        return word_map[t]
    out: list[str] = []
    i = 0
    while i < len(t):
        matched = False
        for lat, cyr in _LATIN_TO_CYR:
            if t.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                matched = True
                break
        if not matched:
            out.append(t[i])
            i += 1
    return "".join(out)


def unslugify_name(slug: str, *, word_map: dict[str, str] | None = None) -> str:
    """Best-effort RU name from ASCII slug (catalog word map first)."""
    wm = word_map or {}
    parts = [p for p in str(slug or "").split("_") if p]
    words: list[str] = []
    for part in parts:
        w = _unslug_token(part, wm)
        if not w:
            continue
        words.append(w)
    if not words:
        return "Предмет"
    titled = [words[0][:1].upper() + words[0][1:] if words[0] else words[0]]
    titled.extend(words[1:])
    return " ".join(titled)


def catalog_word_map(names: Iterable[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in names:
        for word in re.split(r"[\s\-—]+", str(name or "").strip()):
            w = word.strip()
            if not w:
                continue
            slug = slugify_item_base_name(w)
            if slug and slug not in out:
                out[slug] = w
    return out


def scan_webp_identities(root: Path | None = None) -> list[dict[str, Any]]:
    """Return disk identities: category/slug with present tiers (skip legendary/flat)."""
    base = root or webp_root()
    if not base.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for cat_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        category = cat_dir.name
        if category == "legendary":
            continue
        if category not in CATEGORY_META:
            # leftover unknown folders — skip unless they contain slug children
            pass
        slug_dirs = [p for p in cat_dir.iterdir() if p.is_dir()]
        if not slug_dirs:
            # flat category/tN.webp
            continue
        for slug_dir in sorted(slug_dirs, key=lambda p: p.name):
            slug = slug_dir.name
            if is_refine_variant_slug(slug):
                continue
            if slug == category:
                continue
            tiers: list[int] = []
            for n in range(1, 11):
                if (slug_dir / f"t{n}.webp").is_file():
                    tiers.append(n)
            if not tiers:
                continue
            found.append(
                {
                    "category": category,
                    "slug": slug,
                    "art_key": f"{category}/{slug}",
                    "tiers": tiers,
                    "kind": "refine_skip" if is_refine_variant_slug(slug) else "identity",
                }
            )
    return found


def slot_type_from_template_row(item_type: str | None, subtype: str | None) -> str:
    it = (item_type or "").lower()
    st = (subtype or "").lower()
    if it == "weapon":
        if st == "one_hand":
            return "weapon_1h"
        if st in {"two_hand", "bow", "staff"}:
            return "weapon_2h"
        if st in {"offhand", "orb"}:
            return "offhand"
        return "weapon_1h"
    if it == "armor":
        return "costume"
    if it == "ring":
        return "ring"
    if it == "amulet":
        return "amulet"
    return "other"


def expected_art_key_for_catalog_row(row: dict[str, Any]) -> str:
    item_type = str(row.get("item_type") or "")
    subtype = str(row.get("subtype") or "")
    name = str(row.get("name") or "")
    slot = slot_type_from_template_row(item_type, subtype)
    return derive_item_art_key(slot, subtype, name, display_name=name)


def classify_identities(
    disk: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Match catalog names to disk folders; leftover disk slugs are extra identities."""
    word_map = catalog_word_map(str(r.get("name") or "") for r in catalog_rows)
    by_key = {str(d["art_key"]): d for d in disk}
    by_slug: dict[str, list[str]] = {}
    for d in disk:
        by_slug.setdefault(str(d["slug"]), []).append(str(d["art_key"]))

    in_catalog: list[dict[str, Any]] = []
    aliases: dict[str, str] = {}
    missing_art: list[dict[str, Any]] = []
    catalog_slugs: set[str] = set()

    for row in catalog_rows:
        name = str(row.get("name") or "").strip()
        slug = slugify_item_base_name(name)
        catalog_slugs.add(slug)
        expected = expected_art_key_for_catalog_row(row)
        entry = {
            "name": name,
            "slug": slug,
            "expected_art_key": expected,
            "catalog_id": row.get("id"),
            "item_type": row.get("item_type"),
            "subtype": row.get("subtype"),
            "tier": row.get("tier"),
        }
        if expected in by_key:
            entry["disk_art_key"] = expected
            in_catalog.append(entry)
            continue
        alts = by_slug.get(slug) or []
        if len(alts) == 1:
            aliases[expected] = alts[0]
            entry["disk_art_key"] = alts[0]
            in_catalog.append(entry)
            continue
        if alts:
            # Prefer same trailing slug; pick first stable
            aliases[expected] = alts[0]
            entry["disk_art_key"] = alts[0]
            in_catalog.append(entry)
            continue
        missing_art.append(entry)

    extras: list[dict[str, Any]] = []
    used_disk = {str(e.get("disk_art_key")) for e in in_catalog if e.get("disk_art_key")}
    used_disk.update(aliases.values())
    existing_names = {str(r.get("name") or "").strip() for r in catalog_rows}

    for d in disk:
        key = str(d["art_key"])
        slug = str(d["slug"])
        if key in used_disk:
            continue
        if slug in catalog_slugs:
            # catalog owns this slug under a different classification; skip duplicate extra
            continue
        meta = category_meta(str(d["category"]), slug=slug)
        name = unslugify_name(slug, word_map=word_map)
        if name in existing_names:
            name = f"{name} ({d['category']})"
        extras.append(
            {
                "name": name,
                "slug": slug,
                "art_key": key,
                "category": d["category"],
                "item_type": meta.get("item_type"),
                "subtype": meta.get("subtype"),
                "attack_type": meta.get("attack_type"),
                "family_key": slug[:64],
                "tiers": d.get("tiers") or [],
            }
        )
        existing_names.add(name)

    return {
        "in_catalog": in_catalog,
        "extra_identities": extras,
        "aliases": aliases,
        "missing_art": missing_art,
        "disk_count": len(disk),
        "catalog_count": len(catalog_rows),
    }


@lru_cache(maxsize=1)
def load_identity_map() -> dict[str, Any]:
    path = identity_map_path()
    if not path.is_file():
        return {"aliases": {}, "extra_identities": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"aliases": {}, "extra_identities": []}
    if not isinstance(data, dict):
        return {"aliases": {}, "extra_identities": []}
    return data


def art_key_aliases() -> dict[str, str]:
    raw = load_identity_map().get("aliases") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if k and v}


# Extra identities are stored as a single catalog row at this native tier (stats scaled at drop).
EXTRA_IDENTITY_NATIVE_TIER = 5

_ATTACK_SPEED_BY_SUBTYPE: dict[str, int] = {
    "one_hand": 3,
    "two_hand": 4,
    "bow": 4,
    "staff": 5,
    "orb": 4,
    "offhand": 0,
}

_STAT1_BY_SUBTYPE: dict[str, str] = {
    "one_hand": "DEX",
    "two_hand": "STR",
    "bow": "DEX",
    "staff": "INT",
    "orb": "INT",
    "offhand": "STR",
    "ring": "LUK",
    "amulet": "LUK",
    "light": "DEX",
    "medium": "VIT",
    "heavy": "STR",
    "robe": "INT",
}


def extra_identity_seed_rows() -> list[dict[str, Any]]:
    """SQL-ready item_base_templates rows for webp slugs missing from the catalog."""
    from waifu_bot.game.item_tier_stats import level_band_for_tier, median_anchor_stats

    extras = load_identity_map().get("extra_identities") or []
    native = EXTRA_IDENTITY_NATIVE_TIER
    lo, hi = level_band_for_tier(native)
    rows: list[dict[str, Any]] = []
    for ex in extras:
        if not isinstance(ex, dict):
            continue
        name = str(ex.get("name") or "").strip()
        if not name:
            continue
        item_type = str(ex.get("item_type") or "weapon")
        subtype = str(ex.get("subtype") or "one_hand")
        stats = median_anchor_stats(item_type, subtype, tier=native)
        attack_speed = int(_ATTACK_SPEED_BY_SUBTYPE.get(subtype, 0))
        if item_type in {"ring", "amulet", "armor"}:
            attack_speed = 0
        stat1 = _STAT1_BY_SUBTYPE.get(subtype)
        if not stat1:
            if item_type == "weapon":
                stat1 = "STR"
            elif item_type in {"ring", "amulet"}:
                stat1 = "LUK"
            else:
                stat1 = "VIT"
        atk_type = ex.get("attack_type")
        rows.append(
            {
                "name": name[:128],
                "item_type": item_type[:32],
                "subtype": subtype[:32],
                "attack_type": (str(atk_type)[:16] if atk_type else None),
                "tier": native,
                "level_min": lo,
                "level_max": hi,
                "dmg_min": int(stats.get("dmg_min") or 0),
                "dmg_max": int(stats.get("dmg_max") or 0),
                "attack_speed": attack_speed,
                "armor_base": int(stats.get("armor_base") or 0),
                "stat1_type": stat1,
                "stat1_value": max(1, int(stats.get("stat1_value") or 1)),
                "stat2_type": None,
                "stat2_value": 0,
                "base_price": max(1, int(stats.get("base_price") or 10)),
                "boss_allowed": True,
                "weight": 100,
                "base_grade": 0,
                "family_key": str(ex.get("family_key") or ex.get("slug") or "")[:64],
            }
        )
    return rows


def sql_join_inventory_identity(
    inv_alias: str = "inv",
    item_alias: str = "i",
    tpl_alias: str = "ibt",
) -> str:
    """Join an inventory row to its identity template (id first, else name / grade 0)."""
    inv = inv_alias
    item = item_alias
    tpl = tpl_alias
    return f"""
JOIN LATERAL (
  SELECT t.*
  FROM item_base_templates t
  WHERE ({inv}.base_template_id IS NOT NULL AND t.id = {inv}.base_template_id)
     OR (
       {inv}.base_template_id IS NULL
       AND btrim(t.name) = btrim({item}.name)
       AND COALESCE(t.base_grade, 0) = 0
     )
  ORDER BY t.id
  LIMIT 1
) {tpl} ON TRUE
"""


def apply_art_key_alias(art_key: str) -> str:
    k = str(art_key or "").strip()
    if not k:
        return k
    aliases = art_key_aliases()
    if k in aliases:
        return aliases[k]
    # legendary-prefixed
    prefix = "legendary/"
    if k.startswith(prefix):
        rest = k[len(prefix) :]
        if rest in aliases:
            return prefix + aliases[rest]
    return k
