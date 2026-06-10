"""Legendary static affix profiles: SQL loaders, rule-based picker, LLM prompts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

STAT_TO_PRIMARY: dict[str, str] = {
    "STR": "p_primary_strength",
    "DEX": "p_primary_agility",
    "INT": "p_primary_intelligence",
    "VIT": "p_primary_endurance",
    "CHA": "p_primary_charm",
    "LUK": "p_primary_luck",
}

ATTACK_TO_DMG_PREFIX: dict[str, str] = {
    "melee": "p_dmg_melee",
    "ranged": "p_dmg_ranged",
    "magic": "p_dmg_magic",
}

ATTACK_TO_DMG_SUFFIX: dict[str, str] = {
    "melee": "s_dmg_melee",
    "ranged": "s_dmg_ranged",
    "magic": "s_dmg_magic",
}

MEDIA_TRIGGER_TO_FAMILY: dict[str, str] = {
    "text": "s_media_text",
    "sticker": "p_media_sticker",
    "photo": "p_media_photo",
    "gif": "p_media_gif",
    "audio": "p_media_audio",
    "voice": "p_media_voice",
    "video": "p_media_video",
    "link": "p_media_link",
}


def _kind_for_family_id(family_id: str) -> str:
    return "suffix" if str(family_id).startswith("s_") else "prefix"

TRIGGER_GROUP_MEDIA_HINT: dict[str, str] = {
    "media_type": "sticker",
    "text_content": "text",
    "message_meta": "text",
}

DEFAULT_SUFFIXES = (
    "s_sec_crit_chance_pct",
    "s_sec_hp_max_pct",
    "s_sec_dmg_reduce_pct",
    "s_monster_beast_flat",
    "s_merchant_cut",
)


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


def _psql_json_query(sql: str) -> list[dict[str, Any]]:
    import subprocess

    proc = subprocess.run(
        ["sudo", "-u", "postgres", "psql", "-d", "waifu_bot_reborn", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = proc.stdout.strip()
    if not raw:
        return []
    return json.loads(raw)


def load_legendary_templates() -> list[dict[str, Any]]:
    return _psql_json_query(
        """
        SELECT COALESCE(json_agg(row_to_json(x) ORDER BY x.template_id), '[]'::json)
        FROM (
            SELECT
                ibt.id AS template_id,
                ibt.name,
                ibt.tier,
                ibt.item_type,
                ibt.subtype,
                ibt.attack_type,
                ibt.stat1_type,
                ibt.stat1_value,
                ibt.dmg_min,
                ibt.dmg_max,
                COALESCE(ibt.legendary_static_affixes, '[]'::json) AS legendary_static_affixes,
                json_agg(json_build_object(
                    'key', lb.bonus_key,
                    'name', lb.name,
                    'description', COALESCE(lb.description_tpl, lb.name),
                    'trigger_group', lb.trigger_group
                ) ORDER BY lb.id) AS unique_bonuses
            FROM item_base_templates ibt
            CROSS JOIN LATERAL unnest(COALESCE(ibt.legendary_bonus_ids, '{}')) AS bonus_id
            JOIN legendary_bonuses lb ON lb.id = bonus_id
            WHERE COALESCE(ibt.base_grade, 0) = 0
              AND cardinality(COALESCE(ibt.legendary_bonus_ids, '{}')) > 0
            GROUP BY ibt.id
            ORDER BY ibt.tier, ibt.id
        ) x
        """
    )


def load_affix_catalog_for_tier(tier: int) -> list[dict[str, Any]]:
    tt = max(1, min(10, int(tier)))
    return _psql_json_query(
        f"""
        SELECT COALESCE(json_agg(row_to_json(x) ORDER BY x.family_id), '[]'::json)
        FROM (
            SELECT DISTINCT ON (af.family_id)
                af.id AS catalog_id,
                af.family_id,
                af.kind,
                af.effect_key,
                aft.affix_tier,
                aft.value_min,
                aft.value_max,
                af.allowed_slot_types,
                af.allowed_attack_types,
                af.exclusive_group
            FROM affix_families af
            JOIN affix_family_tiers aft ON aft.family_id = af.id
            WHERE aft.affix_tier <= {tt}
              AND COALESCE(af.is_legendary_aspect, false) = false
              AND af.effect_key NOT ILIKE 'passive_branch_level_add:%'
              AND af.effect_key <> 'passive_all_nodes_level_add'
            ORDER BY af.family_id, aft.affix_tier DESC
        ) x
        """
    )


def weapon_damage_effect_matches(
    effect_key: str,
    slot_type: str,
    attack_type: str | None,
    weapon_subtype: str | None,
) -> bool:
    ek = (effect_key or "").strip().lower()
    if ek not in ("melee_damage_flat", "ranged_damage_flat", "magic_damage_flat"):
        return True
    st = (slot_type or "").lower()
    if "weapon" not in st and st != "offhand":
        return False
    at = (attack_type or "").strip().lower() if attack_type else ""
    if not at:
        wt = (weapon_subtype or "").lower()
        if "bow" in wt:
            at = "ranged"
        elif any(x in wt for x in ("staff", "wand", "orb")):
            at = "magic"
        elif wt:
            at = "melee"
    if at == "melee":
        return ek == "melee_damage_flat"
    if at == "ranged":
        return ek == "ranged_damage_flat"
    if at == "magic":
        return ek == "magic_damage_flat"
    return True


def _media_family_for_template(unique_bonuses: list[dict]) -> str | None:
    for b in unique_bonuses:
        tg = str(b.get("trigger_group") or "")
        key = str(b.get("key") or "").lower()
        hint = TRIGGER_GROUP_MEDIA_HINT.get(tg)
        if hint:
            fam = MEDIA_TRIGGER_TO_FAMILY.get(hint)
            if fam:
                return fam
        for media, fam in MEDIA_TRIGGER_TO_FAMILY.items():
            if media in key:
                return fam
    return None


def rule_based_profile(tpl: dict[str, Any]) -> list[dict[str, str]]:
    """Deterministic 3–4 affix family_id picks coherent with template + unique bonus."""
    stat_code = str(tpl.get("stat1_type") or "STR").upper()
    attack = str(tpl.get("attack_type") or "").lower()
    slot = slot_type_from_template(str(tpl.get("item_type") or ""), str(tpl.get("subtype") or ""))
    bonuses = tpl.get("unique_bonuses") or []
    if isinstance(bonuses, str):
        bonuses = json.loads(bonuses)

    picks: list[dict[str, str]] = []
    primary = STAT_TO_PRIMARY.get(stat_code, "p_primary_strength")
    picks.append({"family_id": primary, "kind": "prefix"})

    if slot in {"weapon_1h", "weapon_2h", "offhand"} and attack:
        dmg_p = ATTACK_TO_DMG_PREFIX.get(attack)
        if dmg_p:
            picks.append({"family_id": dmg_p, "kind": "prefix"})

    media_fam = _media_family_for_template(bonuses)
    if media_fam and len(picks) < 4:
        if not any(p["family_id"] == media_fam for p in picks):
            picks.append({"family_id": media_fam, "kind": _kind_for_family_id(media_fam)})

    # One weapon-damage line per exclusive_group (prefix XOR suffix damage)

    tid = int(tpl.get("template_id") or 0)
    tier = int(tpl.get("tier") or 1)
    suffix_idx = int(hashlib.md5(f"{tid}:{tier}".encode()).hexdigest(), 16) % len(DEFAULT_SUFFIXES)
    suffix = DEFAULT_SUFFIXES[suffix_idx]
    if not any(p["family_id"] == suffix for p in picks):
        picks.append({"family_id": suffix, "kind": "suffix"})

    while len(picks) < 3:
        extra = "s_sec_hp_max_pct" if picks[-1]["family_id"] != "s_sec_hp_max_pct" else "s_sec_crit_chance_pct"
        picks.append({"family_id": extra, "kind": "suffix"})

    return picks[:4]


def validate_profile(
    affixes: list[dict[str, str]],
    tpl: dict[str, Any],
    catalog_family_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not 3 <= len(affixes) <= 4:
        errors.append(f"affix count {len(affixes)} not in 3..4")
    seen_fam: set[str] = set()
    seen_excl: set[str] = set()
    slot = slot_type_from_template(str(tpl.get("item_type") or ""), str(tpl.get("subtype") or ""))
    attack = tpl.get("attack_type")
    subtype = tpl.get("subtype")
    catalog_by_fid = {str(c["family_id"]): c for c in (tpl.get("_catalog") or [])}

    prefixes = sum(1 for a in affixes if str(a.get("kind") or "").lower() == "prefix")
    suffixes = sum(1 for a in affixes if str(a.get("kind") or "").lower() == "suffix")
    if prefixes < 1 or suffixes < 1:
        errors.append("need at least 1 prefix and 1 suffix")

    for a in affixes:
        fid = str(a.get("family_id") or "")
        if fid not in catalog_family_ids:
            errors.append(f"unknown family_id {fid}")
        if fid in seen_fam:
            errors.append(f"duplicate family_id {fid}")
        seen_fam.add(fid)
        cat = catalog_by_fid.get(fid, {})
        ek = str(cat.get("effect_key") or "")
        if ek and not weapon_damage_effect_matches(ek, slot, attack, subtype):
            errors.append(f"{fid} incompatible with attack_type={attack}")
        excl = str(cat.get("exclusive_group") or "")
        if excl:
            if excl in seen_excl:
                errors.append(f"duplicate exclusive_group {excl}")
            seen_excl.add(excl)
    return errors


def build_system_prompt() -> str:
    return (
        "Ты дизайнер легендарных предметов в стиле Diablo. "
        "Для каждого предмета выбери ровно 3 или 4 статических бонуса из приложенного каталога. "
        "Бонусы должны согласовываться с уникальным бонусом, attack_type, stat1 и slot_type. "
        "Melee-оружие: не magic_damage_flat. Magic staff: не melee_damage_flat. "
        "Текстовые/media бонусы: prefer media_damage_* или подходящий primary stat. "
        "Верни ТОЛЬКО JSON: {\"profiles\": {\"<template_id>\": {\"affixes\": [{\"family_id\": \"...\", \"kind\": \"prefix|suffix\"}], "
        "\"rationale\": \"...\"}}}. "
        "Используй только family_id из каталога. Не указывай числовые values. "
        "Минимум 1 prefix и 1 suffix. Один exclusive_group — не более одного раза."
    )


def build_user_prompt(items: list[dict[str, Any]], catalog: list[dict[str, Any]], tier: int) -> str:
    compact_cat = []
    for c in catalog:
        compact_cat.append(
            {
                "family_id": c["family_id"],
                "kind": c["kind"],
                "effect_key": c["effect_key"],
                "value_range": [c.get("value_min"), c.get("value_max")],
            }
        )
    payload = {
        "affix_catalog_tier": tier,
        "affix_catalog": compact_cat,
        "items": [
            {
                "template_id": it["template_id"],
                "name": it["name"],
                "tier": it["tier"],
                "slot_type": slot_type_from_template(it.get("item_type", ""), it.get("subtype", "")),
                "attack_type": it.get("attack_type"),
                "stat1": it.get("stat1_type"),
                "unique_bonuses": it.get("unique_bonuses"),
            }
            for it in items
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_profiles_response(raw: str, expected_ids: list[int]) -> dict[int, list[dict[str, str]]]:
    text = raw.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    data = json.loads(text)
    profiles_raw = data.get("profiles") or data
    out: dict[int, list[dict[str, str]]] = {}
    for tid in expected_ids:
        key = str(tid)
        block = profiles_raw.get(key) or profiles_raw.get(tid)
        if not block:
            raise ValueError(f"missing profile for template_id {tid}")
        affixes = block.get("affixes") if isinstance(block, dict) else block
        if not isinstance(affixes, list):
            raise ValueError(f"bad affixes for {tid}")
        out[tid] = [
            {"family_id": str(a["family_id"]), "kind": str(a.get("kind") or "prefix")}
            for a in affixes
        ]
    return out


def load_profiles_json(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles") or data
    return {str(k): v for k, v in profiles.items()}


def save_profiles_json(path: Path, profiles: dict[str, list[dict[str, str]]], meta: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"version": 1, "profiles": profiles}
    if meta:
        payload.update(meta)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_profiles_md(
    profiles: dict[str, list[dict[str, str]]],
    templates: list[dict[str, Any]] | None = None,
) -> str:
    """Human-readable matrix template_id → static affix family_ids."""
    by_id = {int(t["template_id"]): t for t in (templates or load_legendary_templates())}
    lines = [
        "# Legendary static affix profiles",
        "",
        "Детерминированный набор `family_id` на шаблон (`item_base_templates.legendary_static_affixes`). "
        "Числовые `value` роллятся при спавне из `affix_family_tiers` по tier шаблона.",
        "",
        "| template_id | name | tier | affixes |",
        "|-------------|------|------|---------|",
    ]
    for tid_str in sorted(profiles.keys(), key=lambda x: int(x)):
        tid = int(tid_str)
        tpl = by_id.get(tid, {})
        name = tpl.get("name") or "?"
        tier = tpl.get("tier") or "?"
        aff = ", ".join(f"{a['kind']}:{a['family_id']}" for a in profiles[tid_str])
        lines.append(f"| {tid} | {name} | {tier} | {aff} |")
    lines.append("")
    return "\n".join(lines)
