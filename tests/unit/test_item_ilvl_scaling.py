"""Ilvl bonus curve vs perfection-aligned T10/A10 anchor."""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from waifu_bot.game.item_ilvl_scaling import (
    CURRENT_SCALE_VER,
    apply_flat_to_int,
    apply_ilvl_scale_to_fresh_item,
    apply_template_fraction,
    flat_scale,
    item_scale_ilvl,
    pct_affix_scale,
    primary_affix_tier_seed_rows,
    primary_catchup_scaled,
    remap_legacy_primary_to_a10,
    scale_affix_raw,
    scale_class,
    scaled_template_armor,
    should_rescale_inventory,
    stamp_ilvl_scale_meta,
    template_fraction_scale,
)
from waifu_bot.services.item_ilvl_rescale import rescale_legacy_plus_item


def test_flat_scale_anchor() -> None:
    assert flat_scale(1) == 1.0
    assert flat_scale(60) == 1.0
    assert flat_scale(200) == pytest.approx(200 / 60)
    assert flat_scale(350) == pytest.approx(350 / 60)


def test_pct_scale_200() -> None:
    expected = 1.0 + 0.40 * math.log(200 / 60)
    assert pct_affix_scale(60) == 1.0
    assert pct_affix_scale(200) == pytest.approx(expected)
    assert pct_affix_scale(200) == pytest.approx(1.4816, rel=0.01)


def test_scale_class_passive_is_none() -> None:
    assert scale_class("passive_node_level_add:w_bash") == "none"
    assert scale_class("passive_all_nodes_level_add") == "none"
    assert scale_class("strength") == "flat"
    assert scale_class("crit_chance_pct") == "pct"
    assert scale_class("melee_damage_flat") == "flat"


def test_expected_table_ilvl_200() -> None:
    assert apply_flat_to_int(5, 200) == 17
    assert scale_affix_raw("strength", 12, 200) == 40
    assert scale_affix_raw("strength", 20, 200) == 67
    assert scale_affix_raw("crit_chance_pct", 120, 200) == 178
    assert scale_affix_raw("passive_node_level_add:w_bash", 2, 200) == 2


def test_item_scale_ilvl_ignores_display_total_level() -> None:
    inv = SimpleNamespace(power_rank=0, plus_level_source=0, total_level=80, level=80)
    assert item_scale_ilvl(inv) == 0
    inv.power_rank = 200
    assert item_scale_ilvl(inv) == 200
    inv.power_rank = 0
    inv.plus_level_source = 15
    assert item_scale_ilvl(inv) == 200


def test_primary_catchup_a2_at_200() -> None:
    assert remap_legacy_primary_to_a10(2, 2) == 12
    assert primary_catchup_scaled(2, 2, 200) == 40


def test_scaled_armor_147_at_200() -> None:
    inv = SimpleNamespace(power_rank=200, plus_level_source=15)
    assert scaled_template_armor(147, inv) == 490


def test_template_fraction_grows_slowly() -> None:
    assert template_fraction_scale(60) == 1.0
    assert apply_template_fraction(0.05, 200) == pytest.approx(0.05 * template_fraction_scale(200))
    assert template_fraction_scale(200) < 1.2


def test_fresh_scale_idempotent() -> None:
    inv = SimpleNamespace(
        base_stat_value=5,
        damage_min=46,
        damage_max=68,
        affixes=[SimpleNamespace(stat="strength", value="12")],
        ilvl_stat_scale_ver=0,
        power_rank=200,
        plus_level_source=15,
    )
    item = SimpleNamespace(damage=68)
    apply_ilvl_scale_to_fresh_item(inv, item, scale_ilvl=200)
    assert inv.base_stat_value == 17
    assert inv.damage_min == 153
    assert inv.affixes[0].value == "40"
    assert inv.ilvl_stat_scale_ver == CURRENT_SCALE_VER
    apply_ilvl_scale_to_fresh_item(inv, item, scale_ilvl=200)
    assert inv.base_stat_value == 17
    assert inv.affixes[0].value == "40"


def test_ilvl_60_does_not_change_a10_numbers() -> None:
    inv = SimpleNamespace(
        base_stat_value=5,
        damage_min=46,
        damage_max=68,
        affixes=[SimpleNamespace(stat="strength", value="12")],
        ilvl_stat_scale_ver=0,
        power_rank=0,
        plus_level_source=0,
    )
    apply_ilvl_scale_to_fresh_item(inv, None, scale_ilvl=60)
    assert inv.base_stat_value == 5
    assert inv.damage_min == 46
    assert inv.affixes[0].value == "12"
    assert inv.ilvl_stat_scale_ver == CURRENT_SCALE_VER


def test_legacy_rescale_catchup_and_no_double() -> None:
    inv = SimpleNamespace(
        base_stat_value=5,
        damage_min=50,
        damage_max=70,
        secondary_fraction_value=0.05,
        plus_level_source=15,
        power_rank=200,
        ilvl_stat_scale_ver=0,
        item=SimpleNamespace(damage=70),
        affixes=[
            SimpleNamespace(stat="strength", value="2", affix_tier=2, tier=2),
            SimpleNamespace(stat="crit_chance_pct", value="120", affix_tier=10, tier=10),
            SimpleNamespace(stat="passive_node_level_add:w_bash", value="1", affix_tier=3, tier=3),
        ],
    )
    assert should_rescale_inventory(inv)
    assert rescale_legacy_plus_item(inv) is True
    assert inv.base_stat_value == 17
    assert inv.affixes[0].value == "40"
    assert inv.affixes[1].value == "178"
    assert inv.affixes[2].value == "1"
    assert inv.ilvl_stat_scale_ver == CURRENT_SCALE_VER
    assert rescale_legacy_plus_item(inv) is False
    assert inv.base_stat_value == 17


def test_campaign_item_not_selected_for_rescale() -> None:
    inv = SimpleNamespace(
        plus_level_source=0,
        power_rank=0,
        total_level=80,
        ilvl_stat_scale_ver=0,
        base_stat_value=5,
        affixes=[],
    )
    assert should_rescale_inventory(inv) is False
    assert rescale_legacy_plus_item(inv) is False


def test_stamp_sets_power_rank_from_generation_ilvl() -> None:
    inv = SimpleNamespace(power_rank=0, plus_level_source=0)
    stamp_ilvl_scale_meta(inv, plus_level=15, scale_ilvl=204)
    assert inv.plus_level_source == 15
    assert inv.power_rank == 204
    low = SimpleNamespace(power_rank=0, plus_level_source=0)
    stamp_ilvl_scale_meta(low, plus_level=5, scale_ilvl=55)
    assert low.power_rank == 55


def test_primary_seed_rows_a10() -> None:
    rows = primary_affix_tier_seed_rows()
    assert len(rows) == 48
    a10 = [r for r in rows if r["affix_tier"] == 10]
    assert len(a10) == 6
    assert all(r["value_min"] == 12 and r["value_max"] == 20 for r in a10)
    assert all(r["min_total_level"] == 46 and r["max_total_level"] == 60 for r in a10)


def test_json_seed_has_primary_a10() -> None:
    import json
    from pathlib import Path

    path = Path("/opt/waifu-bot-REBORN/scripts/data/diablo_affix_family_tiers.json")
    rows = json.loads(path.read_text(encoding="utf-8"))
    strength = [r for r in rows if r["family_id"] == "p_primary_strength"]
    tiers = {int(r["affix_tier"]) for r in strength}
    assert tiers == set(range(1, 11))
    a10 = next(r for r in strength if int(r["affix_tier"]) == 10)
    assert a10["value_min"] == 12
    assert a10["value_max"] == 20
    assert a10["max_total_level"] == 60
