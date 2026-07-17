"""D2-style legendary bonus → item_base_template assignment (316 ↔ 316).

DEPRECATED: bonuses are rolled at drop time via drop_roll.py (migration 0119).
This module remains for historical distribution audits only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from waifu_bot.game.legendary_bonuses.compat import bonuses_compatible, slot_allowed

ROOT = Path(__file__).resolve().parents[2]

# Curated: (name, tier) -> [bonus_key, ...]  (Мистерикл tier 9)
CURATED: dict[tuple[str, int], list[str]] = {
    ("Экскалибур", 10): ["BOSS_SLAYER", "SNIPER_SHOT"],
    ("Теневое жало", 10): ["MYSTIC_SEVEN", "QUICK_REFLEX"],
    ("Звёздный лук", 10): ["TYPE_HUNTER", "HUNT_FRENZY"],
    ("Топор бури", 10): ["WOUND_FURY", "BREAKTHROUGH"],
    ("Рунный меч", 9): ["GOLD_PULSE", "AFFIX_MASTERY"],
    ("Серебряная дуга", 9): ["IMMUNITY_BREAKER", "REVENGE_THIRST"],
    ("Мистерикл", 9): ["PIERCING_SCREAM", "VERBOSITY"],
    ("Кольцо вечности", 10): ["SURVIVOR_SPIRIT", "RARITY_SYNERGY"],
    ("Медальон стражника", 5): ["MORNING_RITUAL", "FIRST_DAILY_DUNGEON"],
}

# Import canon weapon lines from seed script (single source of truth)
import importlib.util

_seed_spec = importlib.util.spec_from_file_location(
    "seed_item_base_grades",
    ROOT / "scripts" / "seed_item_base_grades.py",
)
_seed = importlib.util.module_from_spec(_seed_spec)
assert _seed_spec.loader is not None
_seed_spec.loader.exec_module(_seed)
CANON_WEAPON_LINES = _seed.CANON_WEAPON_LINES


def slot_type_from_template(item_type: str, subtype: str) -> str:
    it = (item_type or "").lower()
    st = (subtype or "").lower()
    if it == "weapon":
        if st == "one_hand":
            return "weapon_1h"
        if st in {"two_hand", "bow", "staff"}:
            return "weapon_2h"
        if st in {"offhand", "orb"}:
            return "offhand"
    if it == "armor":
        return "costume"
    if it == "ring":
        return "ring"
    if it == "amulet":
        return "amulet"
    return "other"


def line_key_for_template(tpl: dict[str, Any]) -> str:
    name = str(tpl.get("name") or "")
    tier = int(tpl.get("tier") or 0)
    it = str(tpl.get("item_type") or "").lower()
    if it == "weapon":
        wline = None
        for li, names in enumerate(CANON_WEAPON_LINES):
            if 1 <= tier <= len(names) and names[tier - 1] == name:
                wline = li
                break
        if wline is not None:
            return f"weapon_line_{wline}"
        return f"rc_weapon_{name}"
    if it == "armor":
        if tpl.get("required_race") or tpl.get("required_class"):
            return f"rc_armor_{name}"
        return f"armor_{tpl.get('subtype')}"
    if it == "ring":
        if tpl.get("required_race") or tpl.get("required_class"):
            return f"rc_ring_{name}"
        return f"ring_{tpl.get('stat1_type')}"
    if it == "amulet":
        if tpl.get("required_race") or tpl.get("required_class"):
            return f"rc_amulet_{name}"
        return f"amulet_{tpl.get('stat1_type')}"
    return f"other_{name}"


TRIGGER_TO_FAMILY: dict[str, str] = {
    "media_type": "media_type",
    "time_calendar": "time_calendar",
    "time_trigger": "time_calendar",
    "tempo": "tempo",
    "text_content": "text_content",
    "message_meta": "text_content",
    "combo_counter": "combo_counter",
    "combo_chain": "combo_counter",
    "crit": "crit",
    "hp_state": "hp_state",
    "hp_threshold": "hp_state",
    "reactive": "reactive",
    "dungeon_progress": "dungeon_progress",
    "dungeon_state": "dungeon_progress",
    "economy": "economy",
    "counter": "economy",
    "meta_inventory": "meta_inventory",
    "unique_passive": "meta_inventory",
    "exotic": "exotic",
}

TIER_BAND_FAMILIES: dict[int, list[str]] = {
    1: ["media_type", "text_content"],
    2: ["media_type", "text_content"],
    3: ["tempo", "time_calendar"],
    4: ["tempo", "time_calendar"],
    5: ["combo_counter", "crit"],
    6: ["combo_counter", "crit"],
    7: ["hp_state", "reactive", "dungeon_progress"],
    8: ["hp_state", "reactive", "dungeon_progress"],
    9: ["exotic", "economy", "meta_inventory"],
    10: ["exotic", "economy", "meta_inventory"],
}

ALL_FAMILIES_ORDER = [
    "media_type",
    "text_content",
    "tempo",
    "time_calendar",
    "combo_counter",
    "crit",
    "hp_state",
    "reactive",
    "dungeon_progress",
    "exotic",
    "economy",
    "meta_inventory",
]

# Bonuses that splash / boss-only fit weapons & armor better than rings
WEAPON_ARMOR_PREFERRED = frozenset(
    {
        "TYPE_HUNTER",
        "PRISM",
        "BOSS_SLAYER",
        "AFFIX_MASTERY",
        "IMMUNITY_BREAKER",
        "DETONATOR",
        "MEDIA_TRIO",
        "CHARGED_DISCHARGE",
    }
)

RING_AMULET_PREFERRED = frozenset(
    {
        "GOLD_PULSE",
        "HUNTER_EXPERIENCE",
        "FIRST_DAILY_DUNGEON",
        "MORNING_RITUAL",
        "MIDNIGHT_STRIKE",
        "RARITY_SYNERGY",
        "SURVIVOR_SPIRIT",
        "PAIN_COLLECTOR",
        "LIVING_ARTIFACT",
    }
)


def _family_for_bonus(bonus: dict[str, Any]) -> str:
    tg = str(bonus.get("trigger_group") or "")
    return TRIGGER_TO_FAMILY.get(tg, tg or "exotic")


def _rotate_families(line_key: str, tier: int) -> list[str]:
    base = list(TIER_BAND_FAMILIES.get(max(1, min(10, tier)), ALL_FAMILIES_ORDER))
    digest = int(hashlib.md5(line_key.encode()).hexdigest(), 16)
    shift = digest % max(1, len(base))
    rotated = base[shift:] + base[:shift]
    # append remaining families as fallback order
    for fam in ALL_FAMILIES_ORDER:
        if fam not in rotated:
            rotated.append(fam)
    return rotated


def _has_splash_effect(bonus: dict[str, Any]) -> bool:
    params = bonus.get("params") or {}
    effects = params.get("effects") or {}
    if effects.get("remaining_monsters_damage_multiplier"):
        return True
    return str(bonus.get("bonus_key") or "") in WEAPON_ARMOR_PREFERRED


def _bonus_fits_slot(bonus: dict[str, Any], slot: str) -> bool:
    key = str(bonus.get("bonus_key") or "")
    if not slot_allowed(key, slot):
        return False
    if _has_splash_effect(bonus) and slot in {"ring", "amulet"}:
        return False
    if key in RING_AMULET_PREFERRED and slot in {"weapon_1h", "weapon_2h", "offhand", "costume"}:
        return False
    return True


@dataclass
class Assignment:
    name: str
    tier: int
    item_type: str
    subtype: str
    line_key: str
    slot_type: str
    bonus_keys: list[str] = field(default_factory=list)


def _pick_bonus_for_template(
    tpl: dict[str, Any],
    pool: list[dict[str, Any]],
) -> dict[str, Any]:
    slot = slot_type_from_template(str(tpl.get("item_type")), str(tpl.get("subtype")))
    tier = int(tpl["tier"])
    lk = line_key_for_template(tpl)
    families = _rotate_families(lk, tier)

    for fam in families:
        candidates = [
            b for b in pool if _family_for_bonus(b) == fam and _bonus_fits_slot(b, slot)
        ]
        if candidates:
            candidates.sort(key=lambda b: str(b["bonus_key"]))
            idx = int(hashlib.md5(f"{lk}:{tier}:{fam}".encode()).hexdigest(), 16) % len(candidates)
            return candidates[idx]

    fallback = [b for b in pool if _bonus_fits_slot(b, slot)] or list(pool)
    if not fallback:
        raise ValueError(f"no bonus left for {tpl['name']} T{tier}")
    fallback.sort(key=lambda b: str(b["bonus_key"]))
    idx = int(hashlib.md5(f"{lk}:{tier}:fb".encode()).hexdigest(), 16) % len(fallback)
    return fallback[idx]


def _apply_curated_pairs(assignments: list[Assignment]) -> None:
    """Expand curated templates to pinned pairs; vacate displaced single assignments."""
    by_key = {(a.name, a.tier): a for a in assignments}
    owner: dict[str, tuple[str, int]] = {}
    for a in assignments:
        if len(a.bonus_keys) == 1:
            owner[a.bonus_keys[0]] = (a.name, a.tier)

    for (name, tier), pair in CURATED.items():
        curated = by_key.get((name, tier))
        if curated is None:
            raise ValueError(f"curated template missing: {name} T{tier}")
        vacated: list[tuple[str, int]] = []
        for bk in pair:
            prev = owner.get(bk)
            if prev and prev != (name, tier):
                vacated.append(prev)
        curated.bonus_keys = list(pair)
        for bk in pair:
            owner[bk] = (name, tier)
        for vn, vt in vacated:
            other = by_key[(vn, vt)]
            other.bonus_keys = []


def assign_bonuses(
    templates: list[dict[str, Any]],
    bonuses: list[dict[str, Any]],
) -> list[Assignment]:
    """Return assignments for all templates; raises on validation failure."""
    bonus_by_key = {str(b["bonus_key"]): b for b in bonuses}
    for pair in CURATED.values():
        for bk in pair:
            if bk not in bonus_by_key:
                raise ValueError(f"curated bonus missing: {bk}")

    ordered = sorted(
        templates,
        key=lambda t: (line_key_for_template(t), int(t["tier"]), str(t["name"])),
    )
    pool = list(bonuses)
    assignments: list[Assignment] = []

    for tpl in ordered:
        name = str(tpl["name"])
        tier = int(tpl["tier"])
        curated_pair = CURATED.get((name, tier))
        if curated_pair:
            candidates = [b for b in pool if str(b["bonus_key"]) in curated_pair]
            chosen = candidates[0] if candidates else _pick_bonus_for_template(tpl, pool)
        else:
            chosen = _pick_bonus_for_template(tpl, pool)
        bk = str(chosen["bonus_key"])
        pool = [b for b in pool if str(b["bonus_key"]) != bk]
        assignments.append(
            Assignment(
                name=str(tpl["name"]),
                tier=int(tpl["tier"]),
                item_type=str(tpl.get("item_type") or ""),
                subtype=str(tpl.get("subtype") or ""),
                line_key=line_key_for_template(tpl),
                slot_type=slot_type_from_template(str(tpl.get("item_type")), str(tpl.get("subtype"))),
                bonus_keys=[bk],
            )
        )

    _apply_curated_pairs(assignments)

    if len(assignments) != len(templates):
        raise ValueError(f"template coverage: {len(assignments)} != {len(templates)}")

    flat_keys: list[str] = []
    for a in assignments:
        flat_keys.extend(a.bonus_keys)
    if len(flat_keys) != len(bonuses):
        raise ValueError(f"bonus usage: {len(flat_keys)} != {len(bonuses)}")
    if len(set(flat_keys)) != len(flat_keys):
        dupes = [k for k in flat_keys if flat_keys.count(k) > 1]
        raise ValueError(f"duplicate bonus keys: {set(dupes)}")

    curated_count = sum(1 for a in assignments if len(a.bonus_keys) == 2)
    vacant_count = sum(1 for a in assignments if len(a.bonus_keys) == 0)
    if curated_count != len(CURATED):
        raise ValueError(f"curated templates: {curated_count} != {len(CURATED)}")
    if vacant_count != len(CURATED):
        raise ValueError(f"vacated templates: {vacant_count} != {len(CURATED)}")

    for a in assignments:
        if len(a.bonus_keys) == 2:
            if not bonuses_compatible(set(a.bonus_keys[:1]), a.bonus_keys[1]):
                raise ValueError(f"incompatible pair on {a.name}: {a.bonus_keys}")
        for bk in a.bonus_keys:
            if not slot_allowed(bk, a.slot_type):
                raise ValueError(f"slot block {bk} on {a.name} ({a.slot_type})")

    return sorted(assignments, key=lambda a: (a.line_key, a.tier, a.name))


def assignments_to_json(assignments: list[Assignment], bonus_by_key: dict[str, dict]) -> list[dict]:
    out = []
    for a in assignments:
        ids = []
        for bk in a.bonus_keys:
            row = bonus_by_key.get(bk)
            if row and row.get("id") is not None:
                ids.append(int(row["id"]))
        out.append(
            {
                "name": a.name,
                "tier": a.tier,
                "base_grade": 0,
                "line_key": a.line_key,
                "slot_type": a.slot_type,
                "bonus_keys": a.bonus_keys,
                "legendary_bonus_ids": ids,
            }
        )
    return out


def export_distribution_md(assignments: list[Assignment], bonus_by_key: dict[str, dict]) -> str:
    lines = [
        "# Распределение легендарных бонусов по шаблонам (316)",
        "",
        "Матрица `item_base_templates` (base_grade=0) → `legendary_bonus_ids`.",
        f"{len(CURATED)} curated-шаблонов × 2 бонуса + "
        f"{len(assignments) - 2 * len(CURATED)} шаблонов × 1 бонус = 316 использований "
        f"({len(CURATED)} шаблонов без бонуса — смещены curated-парами).",
        "",
        "## Сводка",
        "",
        f"- Шаблонов: **{len(assignments)}**",
        f"- Бонусов: **{sum(len(a.bonus_keys) for a in assignments)}**",
        "",
        "## Таблица",
        "",
        "| line_key | name | tier | slot | bonus_keys | trigger_groups |",
        "|----------|------|------|------|------------|----------------|",
    ]
    for a in assignments:
        groups = []
        for bk in a.bonus_keys:
            b = bonus_by_key.get(bk, {})
            groups.append(str(b.get("trigger_group") or ""))
        keys = ", ".join(a.bonus_keys)
        grps = ", ".join(groups)
        lines.append(f"| {a.line_key} | {a.name} | {a.tier} | {a.slot_type} | {keys} | {grps} |")
    return "\n".join(lines) + "\n"


def load_bonuses_from_db() -> list[dict[str, Any]]:
    bonuses = _psql_json_query(
        """
        SELECT COALESCE(json_agg(row_to_json(x) ORDER BY x.id), '[]'::json)
        FROM (
            SELECT id, bonus_key, name, trigger_group, impl_complexity, params, is_active
            FROM legendary_bonuses
            ORDER BY id
        ) x
        """
    )
    if len(bonuses) != 316:
        raise ValueError(f"DB expected 316 bonuses, got {len(bonuses)}")
    return bonuses


def load_bonuses_from_migrations() -> list[dict[str, Any]]:
    """Load 316 bonuses from alembic seed modules (stable ids by insert order)."""
    rows: list[dict[str, Any]] = []

    m91_spec = importlib.util.spec_from_file_location(
        "m0091", ROOT / "alembic/versions/0091_legendary_bonuses_core.py"
    )
    m91 = importlib.util.module_from_spec(m91_spec)
    assert m91_spec.loader is not None
    m91_spec.loader.exec_module(m91)
    bid = 0
    for k, n, d, g, c, p in m91._bonus_rows():
        bid += 1
        rows.append(
            {
                "id": bid,
                "bonus_key": k,
                "name": n,
                "trigger_group": g,
                "impl_complexity": c,
                "params": p,
            }
        )

    m105_spec = importlib.util.spec_from_file_location(
        "m0105", ROOT / "alembic/versions/0105_legendary_bonus_pool.py"
    )
    m105 = importlib.util.module_from_spec(m105_spec)
    assert m105_spec.loader is not None
    m105_spec.loader.exec_module(m105)
    for k, n, d, g, c, p, active in m105._bonus_rows():
        bid += 1
        rows.append(
            {
                "id": bid,
                "bonus_key": k,
                "name": n,
                "trigger_group": g,
                "impl_complexity": c,
                "params": p,
                "is_active": active,
            }
        )
    return rows


def _psql_json_query(sql: str) -> list[dict[str, Any]]:
    import json
    import subprocess

    db = "waifu_bot_reborn"
    proc = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", db, "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = proc.stdout.strip()
    if not raw:
        return []
    return json.loads(raw)


def load_templates_from_db() -> list[dict[str, Any]]:
    """Load base_grade=0 templates from PostgreSQL (canonical for assignment)."""
    templates = _psql_json_query(
        """
        SELECT COALESCE(json_agg(row_to_json(x) ORDER BY x.id), '[]'::json)
        FROM (
            SELECT id, name, item_type, subtype, tier, stat1_type, stat2_type,
                   required_race, required_class
            FROM item_base_templates
            WHERE COALESCE(base_grade, 0) = 0
            ORDER BY id
        ) x
        """
    )
    if len(templates) != 316:
        raise ValueError(f"DB expected 316 templates, got {len(templates)}")
    return templates


def load_templates_from_sql() -> list[dict[str, Any]]:
    """Parse grade-0 templates from item_base_templates_import.sql."""
    import re

    sql = (ROOT / "info/item_base_templates_import.sql").read_text(encoding="utf-8")
    templates: list[dict[str, Any]] = []

    # Weapons with full dmg columns
    wpat = re.compile(
        r"\('([^']*(?:''[^']*)*)','weapon','([^']*)','([^']*)',(\d+),(\d+),(\d+),"
        r"(\d+),(\d+),(\d+),(\d+),'([A-Z]+)',(\d+),(\d+)"
        r"(?:,(\d+),(\d+),(\d+),(\d+),(\d+))?\)"
    )
    for m in wpat.finditer(sql):
        name = m.group(1).replace("''", "'")
        templates.append(
            {
                "name": name,
                "item_type": "weapon",
                "subtype": m.group(2),
                "attack_type": m.group(3),
                "tier": int(m.group(4)),
                "stat1_type": m.group(11),
                "required_race": int(m.group(15)) if m.group(15) else None,
                "required_class": int(m.group(16)) if m.group(16) else None,
            }
        )

    # Armor rows
    apat = re.compile(
        r"\('([^']*(?:''[^']*)*)','armor','([^']*)',NULL,(\d+),(\d+),(\d+),(\d+),'([A-Z]+)',(\d+),(\d+)"
        r"(?:,(\d+),(\d+))?\)"
    )
    for m in apat.finditer(sql):
        name = m.group(1).replace("''", "'")
        templates.append(
            {
                "name": name,
                "item_type": "armor",
                "subtype": m.group(2),
                "tier": int(m.group(3)),
                "stat1_type": m.group(7),
                "required_race": int(m.group(10)) if m.group(10) else None,
                "required_class": int(m.group(11)) if m.group(11) else None,
            }
        )

    # Accessories
    rpat = re.compile(
        r"\('([^']*(?:''[^']*)*)','(ring|amulet)','(ring|amulet)',NULL,(\d+),(\d+),(\d+),"
        r"'([A-Z]+)',(\d+),'?([A-Z]+)?'?,(\d+),(\d+)"
        r"(?:,(\d+),(\d+))?\)"
    )
    for m in rpat.finditer(sql):
        name = m.group(1).replace("''", "'")
        st2 = m.group(8) or None
        templates.append(
            {
                "name": name,
                "item_type": m.group(2),
                "subtype": m.group(3),
                "tier": int(m.group(4)),
                "stat1_type": m.group(7),
                "stat2_type": st2 if st2 else None,
                "required_race": int(m.group(12)) if m.group(12) else None,
                "required_class": int(m.group(13)) if m.group(13) else None,
            }
        )

    if len(templates) != 316:
        raise ValueError(f"SQL parse expected 316 templates, got {len(templates)}")
    return templates


def load_templates() -> list[dict[str, Any]]:
    try:
        return load_templates_from_db()
    except Exception:
        return load_templates_from_sql()


def load_bonuses() -> list[dict[str, Any]]:
    try:
        return load_bonuses_from_db()
    except Exception:
        return load_bonuses_from_migrations()


def run_assignment() -> tuple[list[Assignment], list[dict]]:
    templates = load_templates()
    bonuses = load_bonuses()
    if len(bonuses) != 316:
        raise ValueError(f"expected 316 bonuses, got {len(bonuses)}")
    bonus_by_key = {str(b["bonus_key"]): b for b in bonuses}
    assignments = assign_bonuses(templates, bonuses)
    payload = assignments_to_json(assignments, bonus_by_key)
    return assignments, payload


def write_outputs() -> Path:
    assignments, payload = run_assignment()
    bonus_by_key = {str(b["bonus_key"]): b for b in load_bonuses()}

    json_path = ROOT / "info/legendary_bonus_distribution.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = ROOT / "info/legendary_bonus_distribution.md"
    md_path.write_text(export_distribution_md(assignments, bonus_by_key), encoding="utf-8")
    return json_path
