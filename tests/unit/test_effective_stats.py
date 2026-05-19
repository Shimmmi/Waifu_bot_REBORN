"""Юнит-тесты: эффективные статы соло-боя (game/effective_stats.py)."""

from types import SimpleNamespace

import pytest

from waifu_bot.game.effective_stats import (
    accumulate_primary_four_from_gear,
    apply_combined_stat_mult_to_four,
    apply_main_stats_flat_to_four,
    roll_weapon_damage_and_meta,
    stat_multipliers_from_passive_hidden,
)


def test_stat_multipliers_passive_fraction_and_hidden_percent_points() -> None:
    ps = {"all_stats_pct": 0.1}
    hs = {"all_stats_pct": 5}
    pm, hm, cm = stat_multipliers_from_passive_hidden(ps, hs)
    assert pm == pytest.approx(1.1)
    assert hm == pytest.approx(1.05)
    assert cm == pytest.approx(1.155)


def test_stat_multipliers_zero_when_missing() -> None:
    pm, hm, cm = stat_multipliers_from_passive_hidden({}, {})
    assert pm == 1.0 and hm == 1.0 and cm == 1.0


def test_apply_combined_stat_mult_identity_when_one() -> None:
    out = apply_combined_stat_mult_to_four(10, 20, 30, 40, 1.0)
    assert out == (10, 20, 30, 40)


def test_apply_combined_stat_mult_rounds() -> None:
    s, a, i, l = apply_combined_stat_mult_to_four(10, 10, 10, 10, 1.2)
    assert (s, a, i, l) == (12, 12, 12, 12)


def test_apply_main_stats_flat_to_four() -> None:
    assert apply_main_stats_flat_to_four(1, 2, 3, 4, 0) == (1, 2, 3, 4)
    assert apply_main_stats_flat_to_four(1, 2, 3, 4, 100) == (101, 102, 103, 104)


def test_accumulate_primary_four_from_gear_affix() -> None:
    w = SimpleNamespace(strength=10, agility=10, intelligence=10, luck=10)
    aff = SimpleNamespace(stat="strength", value=7)
    inv = SimpleNamespace(base_stat=None, base_stat_value=None, affixes=[aff])
    s, a, i, l, bonuses = accumulate_primary_four_from_gear(w, [inv])
    assert s == 17 and a == 10 and i == 10 and l == 10
    assert bonuses == {}


def test_roll_weapon_damage_unarmed() -> None:
    out = roll_weapon_damage_and_meta([])
    assert out["weapon_damage"] == 1
    assert out["min_chars"] == 1
    assert out["attack_type"] == "melee"


def test_merge_passive_skips_duplicate_asp_when_flag() -> None:
    from waifu_bot.services.passive_skills import merge_passive_into_profile_details

    base = {
        "melee_damage": 100,
        "ranged_damage": 100,
        "magic_damage": 100,
        "armor": 10,
        "hp_max": 100,
        "crit_chance": 5.0,
        "dodge_chance": 5.0,
        "damage_reduction": 0.0,
        "exp_bonus": 0.0,
        "merchant_discount": 0.0,
    }
    ps = {"all_stats_pct": 0.2, "melee_dmg_pct": 0.0}
    with_asp = merge_passive_into_profile_details(dict(base), ps, skip_all_stats_pct_on_damage=False)
    assert with_asp["melee_damage"] == 120
    skip = merge_passive_into_profile_details(dict(base), ps, skip_all_stats_pct_on_damage=True)
    assert skip["melee_damage"] == 100
