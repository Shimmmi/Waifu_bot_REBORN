"""Unit tests for legendary static affix profile logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib.legendary_static_affix_llm import (
    parse_profiles_response,
    rule_based_profile,
    validate_profile,
    weapon_damage_effect_matches,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILES_JSON = ROOT / "scripts/data/legendary_static_affixes.json"


def test_weapon_damage_melee_blocks_magic():
    assert weapon_damage_effect_matches("magic_damage_flat", "weapon_1h", "melee", "one_hand") is False
    assert weapon_damage_effect_matches("melee_damage_flat", "weapon_1h", "melee", "one_hand") is True


def test_rule_based_profile_has_three_to_four_affixes():
    tpl = {
        "template_id": 999,
        "tier": 1,
        "item_type": "weapon",
        "subtype": "one_hand",
        "attack_type": "melee",
        "stat1_type": "STR",
        "unique_bonuses": [{"key": "CAPS_SIEGE", "trigger_group": "text_content"}],
    }
    prof = rule_based_profile(tpl)
    assert 3 <= len(prof) <= 4
    fids = [p["family_id"] for p in prof]
    assert "p_primary_strength" in fids


def test_profiles_json_exists():
    assert PROFILES_JSON.is_file()
    data = json.loads(PROFILES_JSON.read_text(encoding="utf-8"))
    profiles = data.get("profiles") or data
    assert len(profiles) >= 300


def test_parse_profiles_response():
    raw = json.dumps(
        {
            "profiles": {
                "42": {
                    "affixes": [
                        {"family_id": "p_primary_strength", "kind": "prefix"},
                        {"family_id": "p_dmg_melee", "kind": "prefix"},
                        {"family_id": "s_sec_crit_chance_pct", "kind": "suffix"},
                    ]
                }
            }
        }
    )
    parsed = parse_profiles_response(raw, [42])
    assert len(parsed[42]) == 3


def test_validate_profile_rejects_duplicate_exclusive():
    tpl = {
        "item_type": "weapon",
        "subtype": "one_hand",
        "attack_type": "melee",
        "_catalog": [
            {
                "family_id": "p_dmg_melee",
                "effect_key": "melee_damage_flat",
                "exclusive_group": "weapon_damage_affinity",
            },
            {
                "family_id": "s_dmg_melee",
                "effect_key": "melee_damage_flat",
                "exclusive_group": "weapon_damage_affinity",
            },
            {"family_id": "p_primary_strength", "effect_key": "strength", "exclusive_group": None},
            {"family_id": "s_sec_crit_chance_pct", "effect_key": "crit_chance_pct", "exclusive_group": "secondary_bonus"},
        ],
    }
    affixes = [
        {"family_id": "p_primary_strength", "kind": "prefix"},
        {"family_id": "p_dmg_melee", "kind": "prefix"},
        {"family_id": "s_dmg_melee", "kind": "suffix"},
        {"family_id": "s_sec_crit_chance_pct", "kind": "suffix"},
    ]
    errs = validate_profile(affixes, tpl, {c["family_id"] for c in tpl["_catalog"]})
    assert any("exclusive_group" in e for e in errs)
