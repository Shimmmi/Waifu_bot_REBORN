"""Amulet fixed-bonus matrix: catalog loaders, LLM prompts, validation, markdown export."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQL = ROOT / "info" / "item_base_templates_import.sql"
DEFAULT_SECONDARY_SQL = ROOT / "info" / "item_secondary_migration.sql"
DEFAULT_LEGENDARY_JSON = ROOT / "info" / "legendary_bonus_distribution.json"
DEFAULT_OUT_JSON = ROOT / "info" / "amulet_bonus_matrix_draft.json"
DEFAULT_OUT_MD = ROOT / "info" / "AMULET_BONUS_MATRIX.md"

MONSTER_FAMILIES = (
    "beast",
    "construct",
    "demon",
    "dragon",
    "elemental",
    "fae",
    "humanoid",
    "slime",
    "undead",
)

MEDIA_KEYS = (
    "media_damage_text_percent",
    "media_damage_sticker_percent",
    "media_damage_photo_percent",
    "media_damage_gif_percent",
    "media_damage_audio_percent",
    "media_damage_voice_percent",
    "media_damage_video_percent",
    "media_damage_link_percent",
)

FLAT_STAT_KEYS = (
    "strength",
    "agility",
    "intelligence",
    "endurance",
    "charm",
    "luck",
    "hp_flat",
    "defense_flat",
)

FRACTION_KEYS = frozenset(
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

FLAT_DAMAGE_KEYS = frozenset(
    {
        "melee_damage_flat",
        "ranged_damage_flat",
        "magic_damage_flat",
        "damage_flat",
    }
)

LINE_KEYS = ("vit_str", "int_dex", "cha_luk", "restricted")

# Per-line bonus pools for rule-based fallback (10 unique keys each).
LINE_BONUS_POOLS: dict[str, list[str]] = {
    "vit_str": [
        "hp_max_pct",
        "dmg_reduce_pct",
        "melee_damage_flat",
        "defense_flat",
        "endurance",
        "damage_vs_monster_type_flat:undead",
        "evade_pct",
        "strength",
        "damage_vs_monster_type_flat:construct",
        "crit_chance_pct",
    ],
    "int_dex": [
        "exp_bonus_pct",
        "magic_damage_flat",
        "media_damage_text_percent",
        "crit_chance_pct",
        "intelligence",
        "media_damage_sticker_percent",
        "damage_vs_monster_type_flat:elemental",
        "magic_find_pct",
        "media_damage_gif_percent",
        "ranged_damage_flat",
    ],
    "cha_luk": [
        "gold_bonus_pct",
        "magic_find_pct",
        "charm",
        "luck",
        "merchant_discount_flat",
        "media_damage_voice_percent",
        "evade_pct",
        "damage_vs_monster_type_flat:fae",
        "crit_chance_pct",
        "media_damage_photo_percent",
    ],
    "restricted": [
        "hp_max_pct",
        "magic_damage_flat",
        "gold_bonus_pct",
        "dmg_reduce_pct",
    ],
}

_AMULET_ROW_RE = re.compile(
    r"\('([^']*(?:''[^']*)*)','amulet','amulet',NULL,(\d+),(\d+),(\d+),"
    r"'([A-Z]+)',(\d+),(?:'([A-Z]+)'|NULL),(\d+),(\d+)"
    r"(?:,(NULL|\d+),(NULL|\d+))?\)"
)

_SECONDARY_UPDATE_RE = re.compile(
    r"secondary_bonus_type='([^']+)', secondary_bonus_value=([\d.]+) "
    r"WHERE name='([^']*(?:''[^']*)*)' AND tier=(\d+)"
)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _unescape_sql_name(name: str) -> str:
    return name.replace("''", "'")


def load_secondary_map(path: Path | None = None) -> dict[tuple[str, int], dict[str, Any]]:
    """Parse item_secondary_migration.sql UPDATE rows for amulets."""
    text = (path or DEFAULT_SECONDARY_SQL).read_text(encoding="utf-8")
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for m in _SECONDARY_UPDATE_RE.finditer(text):
        sec_type, sec_val, name, tier = m.group(1), float(m.group(2)), m.group(3), int(m.group(4))
        out[(_unescape_sql_name(name), tier)] = {
            "secondary_bonus_type": sec_type,
            "secondary_bonus_value": sec_val,
        }
    return out


def load_legendary_map(path: Path | None = None) -> dict[tuple[str, int], dict[str, Any]]:
    data = json.loads((path or DEFAULT_LEGENDARY_JSON).read_text(encoding="utf-8"))
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for row in data:
        if str(row.get("slot_type") or "").lower() != "amulet":
            continue
        if int(row.get("base_grade") or 0) != 0:
            continue
        key = (str(row["name"]), int(row["tier"]))
        out[key] = {
            "bonus_keys": list(row.get("bonus_keys") or []),
            "legendary_bonus_ids": list(row.get("legendary_bonus_ids") or []),
            "line_key": row.get("line_key"),
        }
    return out


def infer_line_key(amulet: dict[str, Any]) -> str:
    if amulet.get("required_race") or amulet.get("required_class"):
        return "restricted"
    stat1 = str(amulet.get("stat1_type") or "").upper()
    if stat1 == "VIT":
        return "vit_str"
    if stat1 == "INT":
        return "int_dex"
    return "cha_luk"


def load_amulet_catalog(
    sql_path: Path | None = None,
    secondary_path: Path | None = None,
    legendary_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Load all 34 amulet base templates from SQL with secondary + legendary metadata."""
    sql = (sql_path or DEFAULT_SQL).read_text(encoding="utf-8")
    secondary = load_secondary_map(secondary_path)
    legendary = load_legendary_map(legendary_path)
    amulets: list[dict[str, Any]] = []
    for m in _AMULET_ROW_RE.finditer(sql):
        name = _unescape_sql_name(m.group(1))
        tier = int(m.group(2))
        level_min = int(m.group(3))
        level_max = int(m.group(4))
        stat1_type = m.group(5)
        stat1_value = int(m.group(6))
        stat2_type = m.group(7)
        stat2_value = int(m.group(8))
        base_price = int(m.group(9))
        def _opt_int(raw: str | None) -> int | None:
            if raw is None or raw == "NULL":
                return None
            return int(raw)

        required_race = _opt_int(m.group(10))
        required_class = _opt_int(m.group(11))
        sec = secondary.get((name, tier), {})
        leg = legendary.get((name, tier), {})
        row: dict[str, Any] = {
            "name": name,
            "tier": tier,
            "level_min": level_min,
            "level_max": level_max,
            "stat1_type": stat1_type,
            "stat1_value": stat1_value,
            "stat2_type": stat2_type,
            "stat2_value": stat2_value,
            "base_price": base_price,
            "required_race": required_race,
            "required_class": required_class,
            "current_secondary_type": sec.get("secondary_bonus_type"),
            "current_secondary_value": sec.get("secondary_bonus_value"),
            "legendary_bonus_keys": leg.get("bonus_keys") or [],
            "legendary_bonus_ids": leg.get("legendary_bonus_ids") or [],
            "line_key": infer_line_key(
                {
                    "stat1_type": stat1_type,
                    "required_race": required_race,
                    "required_class": required_class,
                }
            ),
        }
        amulets.append(row)
    amulets.sort(key=lambda x: (x["line_key"], x["tier"], x["name"]))
    return amulets


def group_amulets_by_line(amulets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {k: [] for k in LINE_KEYS}
    for a in amulets:
        groups.setdefault(a["line_key"], []).append(a)
    for key in groups:
        groups[key].sort(key=lambda x: (x["tier"], x["name"]))
    return groups


def whitelist_bonus_keys() -> list[str]:
    keys: list[str] = []
    keys.extend(sorted(FRACTION_KEYS))
    keys.extend(sorted(FLAT_DAMAGE_KEYS))
    keys.extend(MEDIA_KEYS)
    keys.extend(FLAT_STAT_KEYS)
    keys.append("merchant_discount_flat")
    for fam in MONSTER_FAMILIES:
        keys.append(f"damage_vs_monster_type_flat:{fam}")
    return keys


def implementation_tier(bonus_key: str) -> str:
    base = bonus_key.split(":", 1)[0]
    if base in FRACTION_KEYS:
        return "sql_only"
    return "needs_code"


def scaling_formula_for_key(bonus_key: str) -> str:
    base = bonus_key.split(":", 1)[0]
    if base in FRACTION_KEYS:
        return "tier × 0.005"
    if base in FLAT_DAMAGE_KEYS or base == "damage_flat":
        return "tier × 2"
    if base.startswith("media_damage_"):
        return "tier × 1"
    if base.startswith("damage_vs_monster_type_flat"):
        return "tier × 2"
    if base in FLAT_STAT_KEYS or base == "merchant_discount_flat":
        return "⌊(tier+1)/2⌋"
    return "tier × 1"


def compute_bonus_value(bonus_key: str, tier: int, *, boosted: bool = False) -> float:
    tier = max(1, min(10, int(tier)))
    base = bonus_key.split(":", 1)[0]
    if base in FRACTION_KEYS:
        val = tier * 0.005
    elif base in FLAT_DAMAGE_KEYS or base == "damage_flat":
        val = float(tier * 2)
    elif base.startswith("media_damage_"):
        val = float(tier)
    elif base.startswith("damage_vs_monster_type_flat"):
        val = float(tier * 2)
    elif base in FLAT_STAT_KEYS or base == "merchant_discount_flat":
        val = float((tier + 1) // 2)
    else:
        val = float(tier)
    if boosted:
        val *= 1.25
    if base in FRACTION_KEYS:
        return round(val, 4)
    return float(int(round(val)) if base not in FRACTION_KEYS else val)


def format_bonus_display(bonus_key: str, value: float) -> str:
    base = bonus_key.split(":", 1)[0]
    if base in FRACTION_KEYS:
        return f"+{value * 100:.1f}%"
    if base.startswith("media_damage_"):
        return f"+{value:.0f}%"
    if base.endswith("_flat") or base in FLAT_STAT_KEYS:
        return f"+{int(round(value))}"
    if base.startswith("damage_vs_monster_type_flat"):
        fam = bonus_key.split(":", 1)[-1]
        return f"+{int(round(value))} vs {fam}"
    return f"+{value:g}"


def build_system_prompt() -> str:
    keys = whitelist_bonus_keys()
    return (
        "Ты game balance designer для RPG waifu-bot. "
        "Назначь каждому амулету уникальный фиксированный бонус из whitelist. "
        "Бонус дополняет stat1, не заменяет его. "
        "Тематика имени должна совпадать с типом бонуса "
        "(Амулет архимага → magic_damage_flat, Медальон воина → melee_damage_flat или dmg_reduce_pct). "
        "Внутри одной линии из 10 амулетов bonus_key не повторяется. "
        "Числа bonus_value должны соответствовать scaling_formula для данного ключа. "
        "Restricted аmulets (race/class): value на 25% выше стандарта того же tier. "
        "Верни ТОЛЬКО JSON:\n"
        '{"profiles": [{"name": "...", "tier": N, "bonus_key": "...", '
        '"bonus_value": number, "scaling_formula": "...", "rationale_ru": "..."}]}\n'
        f"Whitelist bonus_key ({len(keys)}): {', '.join(keys)}"
    )


def build_user_prompt(line_key: str, amulets: list[dict[str, Any]]) -> str:
    payload = {
        "line_key": line_key,
        "line_description": {
            "vit_str": "VIT primary, STR secondary — танк/выживание",
            "int_dex": "INT primary, DEX secondary — магия/знания",
            "cha_luk": "CHA→LUK primary — торговля/удача",
            "restricted": "Race/class restricted усиленные варианты",
        }.get(line_key, line_key),
        "scaling_rules": {
            "fraction_pct": "value = tier × 0.005 (0.005 = +0.5%)",
            "flat_damage": "value = tier × 2",
            "media_percent": "value = tier × 1 (целое, процентные пункты)",
            "flat_stat": "value = floor((tier+1)/2)",
            "monster_slayer": "value = tier × 2",
            "restricted_boost": "×1.25 к value",
        },
        "amulets": [
            {
                "name": a["name"],
                "tier": a["tier"],
                "level_range": [a["level_min"], a["level_max"]],
                "stat1": f"{a['stat1_type']}+{a['stat1_value']}",
                "stat2": (
                    f"{a['stat2_type']}+{a['stat2_value']}"
                    if a.get("stat2_type")
                    else None
                ),
                "current_secondary": (
                    f"{a['current_secondary_type']}={a['current_secondary_value']}"
                    if a.get("current_secondary_type")
                    else None
                ),
                "legendary_keys": a.get("legendary_bonus_keys") or [],
                "restricted": bool(a.get("required_race") or a.get("required_class")),
            }
            for a in amulets
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def rule_based_profile(
    amulet: dict[str, Any],
    *,
    used_keys: set[str] | None = None,
) -> dict[str, Any]:
    line = str(amulet.get("line_key") or infer_line_key(amulet))
    pool = list(LINE_BONUS_POOLS.get(line, LINE_BONUS_POOLS["vit_str"]))
    taken = used_keys or set()
    available = [k for k in pool if k not in taken]
    if not available:
        available = [k for k in whitelist_bonus_keys() if k not in taken]
    h = int(hashlib.md5(f"{amulet['name']}:{amulet['tier']}".encode()).hexdigest(), 16)
    bonus_key = available[h % len(available)]
    boosted = bool(amulet.get("required_race") or amulet.get("required_class"))
    bonus_value = compute_bonus_value(bonus_key, int(amulet["tier"]), boosted=boosted)
    return {
        "name": amulet["name"],
        "tier": int(amulet["tier"]),
        "bonus_key": bonus_key,
        "bonus_value": bonus_value,
        "scaling_formula": scaling_formula_for_key(bonus_key),
        "rationale_ru": f"Rule-based: тематика линии {line}, ключ из пула.",
        "implementation_tier": implementation_tier(bonus_key),
        "source": "rule_based",
    }


def validate_profile(
    profile: dict[str, Any],
    amulet: dict[str, Any],
    *,
    used_keys: set[str],
    whitelist: set[str],
) -> list[str]:
    errors: list[str] = []
    name = str(profile.get("name") or "")
    tier = int(profile.get("tier") or 0)
    if name != amulet["name"]:
        errors.append(f"name mismatch: {name!r} != {amulet['name']!r}")
    if tier != int(amulet["tier"]):
        errors.append(f"tier mismatch for {name}")
    bonus_key = str(profile.get("bonus_key") or "")
    base_key = bonus_key.split(":", 1)[0]
    if bonus_key not in whitelist and not any(
        bonus_key == w or bonus_key.startswith("damage_vs_monster_type_flat:")
        for w in whitelist
    ):
        if not (base_key.startswith("damage_vs_monster_type") and ":" in bonus_key):
            errors.append(f"bonus_key not in whitelist: {bonus_key}")
    elif bonus_key not in whitelist:
        fam = bonus_key.split(":", 1)[-1]
        if fam not in MONSTER_FAMILIES:
            errors.append(f"unknown monster family: {fam}")
    if bonus_key in used_keys and amulet.get("line_key") != "restricted":
        errors.append(f"duplicate bonus_key in line: {bonus_key}")
    try:
        bonus_value = float(profile.get("bonus_value") or 0)
    except (TypeError, ValueError):
        errors.append("bonus_value not numeric")
        bonus_value = 0
    if bonus_value <= 0:
        errors.append("bonus_value must be > 0")
    boosted = bool(amulet.get("required_race") or amulet.get("required_class"))
    expected = compute_bonus_value(bonus_key, tier, boosted=boosted)
    if base_key in FRACTION_KEYS:
        if abs(bonus_value - expected) > 0.002:
            errors.append(f"value {bonus_value} != expected {expected} for fraction")
    else:
        if abs(bonus_value - expected) > 1.5:
            errors.append(f"value {bonus_value} != expected {expected}")
    return errors


def _extract_json_blob(text: str) -> str:
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def parse_profiles_response(raw: str, amulets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _extract_json_blob(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Truncated array: try wrapping partial profiles list
        if '"profiles"' in text and text.count("{") > text.count("}"):
            text = text.rstrip(", \n\t") + "]}"
        data = json.loads(text)
    profiles_raw = data.get("profiles") or data
    if isinstance(profiles_raw, dict):
        profiles_list = list(profiles_raw.values())
    else:
        profiles_list = list(profiles_raw)
    by_key = {(str(p["name"]), int(p["tier"])): p for p in profiles_list if "name" in p and "tier" in p}
    out: list[dict[str, Any]] = []
    for amulet in amulets:
        key = (amulet["name"], int(amulet["tier"]))
        block = by_key.get(key)
        if not block:
            raise ValueError(f"missing profile for {key[0]} tier {key[1]}")
        out.append(block)
    return out


def normalize_profiles(
    profiles: list[dict[str, Any]],
    amulets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    whitelist = set(whitelist_bonus_keys())
    used_keys: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for profile, amulet in zip(profiles, amulets, strict=True):
        errs = validate_profile(profile, amulet, used_keys=used_keys, whitelist=whitelist)
        if errs:
            fb = rule_based_profile(amulet, used_keys=used_keys)
            normalized.append(
                {
                    "name": amulet["name"],
                    "tier": int(amulet["tier"]),
                    "line_key": amulet["line_key"],
                    "bonus_key": fb["bonus_key"],
                    "bonus_value": fb["bonus_value"],
                    "scaling_formula": fb["scaling_formula"],
                    "rationale_ru": fb["rationale_ru"],
                    "implementation_tier": fb["implementation_tier"],
                    "source": "rule_based",
                    "validation_errors": errs,
                }
            )
        else:
            bonus_key = str(profile["bonus_key"])
            boosted = bool(amulet.get("required_race") or amulet.get("required_class"))
            normalized.append(
                {
                    "name": amulet["name"],
                    "tier": int(amulet["tier"]),
                    "line_key": amulet["line_key"],
                    "bonus_key": bonus_key,
                    "bonus_value": float(profile["bonus_value"]),
                    "scaling_formula": str(
                        profile.get("scaling_formula") or scaling_formula_for_key(bonus_key)
                    ),
                    "rationale_ru": str(profile.get("rationale_ru") or ""),
                    "implementation_tier": implementation_tier(bonus_key),
                    "source": "llm",
                    "validation_errors": None,
                }
            )
        used_keys.add(normalized[-1]["bonus_key"])
    return normalized


def merge_catalog_with_profiles(
    amulets: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    profile_map = {(p["name"], p["tier"]): p for p in profiles}
    merged: list[dict[str, Any]] = []
    for a in amulets:
        p = profile_map[(a["name"], a["tier"])]
        merged.append(
            {
                **a,
                "proposed_bonus_key": p["bonus_key"],
                "proposed_bonus_value": p["bonus_value"],
                "proposed_bonus_display": format_bonus_display(p["bonus_key"], p["bonus_value"]),
                "scaling_formula": p["scaling_formula"],
                "rationale_ru": p["rationale_ru"],
                "implementation_tier": p["implementation_tier"],
                "profile_source": p.get("source", "unknown"),
            }
        )
    return merged


def save_matrix_json(path: Path, rows: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "amulet_count": len(rows),
        "profiles": rows,
    }
    if meta:
        payload["meta"] = meta
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_matrix_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(rows: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> str:
    lines: list[str] = [
        "# Матрица уникальных бонусов амулетов (draft)",
        "",
        "Expert fusion-анализ (preset `expert`). На согласование перед внедрением в БД/код.",
        "",
    ]
    if meta:
        lines.append(f"- Preset: `{meta.get('preset', 'expert')}`")
        lines.append(f"- Источник: `{meta.get('source', 'llm')}`")
        lines.append(f"- Амулетов: **{len(rows)}**")
        lines.append("")

    lines.extend(
        [
            "## Легенда",
            "",
            "| implementation_tier | Значение |",
            "|-------------------|----------|",
            "| `sql_only` | Достаточно UPDATE `secondary_bonus_type/value` в шаблоне |",
            "| `needs_code` | Нужно расширение системы (implicit affix / template effect) |",
            "",
        ]
    )

    groups = group_amulets_by_line(rows)
    line_titles = {
        "vit_str": "Линия VIT/STR (выживание)",
        "int_dex": "Линия INT/DEX (магия и знания)",
        "cha_luk": "Линия CHA/LUK (торговля и удача)",
        "restricted": "Race/class restricted",
    }
    for line_key in LINE_KEYS:
        group = groups.get(line_key) or []
        if not group:
            continue
        lines.append(f"## {line_titles.get(line_key, line_key)}")
        lines.append("")
        lines.append(
            "| Tier | Имя | stat1 | Текущий secondary | Предложенный bonus | T1/T5/T10 | impl |"
        )
        lines.append("|------|-----|-------|-------------------|--------------------|-----------|------|")
        for row in group:
            tier = int(row["tier"])
            t1 = format_bonus_display(
                row["proposed_bonus_key"],
                compute_bonus_value(row["proposed_bonus_key"], 1, boosted=bool(row.get("required_race"))),
            )
            t5 = format_bonus_display(
                row["proposed_bonus_key"],
                compute_bonus_value(row["proposed_bonus_key"], 5, boosted=bool(row.get("required_race"))),
            )
            t10 = format_bonus_display(
                row["proposed_bonus_key"],
                compute_bonus_value(row["proposed_bonus_key"], 10, boosted=bool(row.get("required_race"))),
            )
            cur = row.get("current_secondary_type") or "—"
            stat1 = f"{row['stat1_type']}+{row['stat1_value']}"
            lines.append(
                f"| {tier} | {row['name']} | {stat1} | `{cur}` | "
                f"`{row['proposed_bonus_key']}` ({row['proposed_bonus_display']}) | "
                f"{t1} / {t5} / {t10} | `{row['implementation_tier']}` |"
            )
        lines.append("")

    lines.append("## Rationale по амулетам")
    lines.append("")
    for row in rows:
        lines.append(f"### {row['name']} (T{row['tier']})")
        lines.append(f"- **Bonus:** `{row['proposed_bonus_key']}` = {row['proposed_bonus_display']}")
        lines.append(f"- **Formula:** {row['scaling_formula']}")
        lines.append(f"- **Impl:** `{row['implementation_tier']}` · source: `{row.get('profile_source', '?')}`")
        if row.get("rationale_ru"):
            lines.append(f"- {row['rationale_ru']}")
        lines.append("")

    sql_count = sum(1 for r in rows if r["implementation_tier"] == "sql_only")
    code_count = sum(1 for r in rows if r["implementation_tier"] == "needs_code")
    lines.extend(
        [
            "## Сводка",
            "",
            f"- `sql_only`: {sql_count} амулетов",
            f"- `needs_code`: {code_count} амулетов",
            "",
            "Этап 2 (внедрение) — только после согласования этой матрицы.",
            "",
        ]
    )
    return "\n".join(lines)


def save_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
