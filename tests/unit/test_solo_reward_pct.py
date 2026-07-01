"""Unit tests for additive solo dungeon reward percentages."""

from __future__ import annotations

import math

import pytest

from waifu_bot.game.solo_rewards import (
    apply_solo_kill_reward_amounts,
    compute_solo_reward_fractions,
    dungeon_plus_reward_mult,
    guild_reward_fractions,
)


def test_dungeon_plus_reward_mult_zero():
    assert dungeon_plus_reward_mult(0) == pytest.approx(1.0)


def test_dungeon_plus_reward_mult_level_3():
    expected = 1.0 + 3 * 0.15 + math.log1p(3) * 0.10
    assert dungeon_plus_reward_mult(3) == pytest.approx(expected)


def test_consistent_hidden_lvl1_is_three_percent_not_three_hundred():
    """Постоянство lvl1: DB value 3 → +0.03 fraction when /100 applied."""
    exp_frac, _ = compute_solo_reward_fractions(gear_exp_frac=0.03)
    assert exp_frac == pytest.approx(0.03)
    exp_gain, _ = apply_solo_kill_reward_amounts(1000, 0, exp_frac, 0.0)
    assert exp_gain == 1030


def test_hoarder_hidden_lvl1_is_five_percent_gold():
    _, gold_frac = compute_solo_reward_fractions(gear_gold_frac=0.05)
    assert gold_frac == pytest.approx(0.05)
    _, gold_gain = apply_solo_kill_reward_amounts(0, 800, 0.0, gold_frac)
    assert gold_gain == 840


def test_additive_not_multiplicative_gear_int_guild():
    """150 affix (+1.5%) + hidden 3% + INT 40 (+4%) + guild 5% → 1.135, not product."""
    gear = 150 / 10000.0  # 0.015
    hidden = 3 / 100.0  # 0.03
    int_frac = 40 * 0.001  # 0.04
    guild = 0.05
    exp_frac, _ = compute_solo_reward_fractions(
        gear_exp_frac=gear + hidden,
        intelligence_exp_frac=int_frac,
        guild_exp_frac=guild,
    )
    assert exp_frac == pytest.approx(0.015 + 0.03 + 0.04 + 0.05)
    exp_gain, _ = apply_solo_kill_reward_amounts(1000, 0, exp_frac, 0.0)
    assert exp_gain == 1135


def test_boss_bonuses_additive_on_kill():
    exp_frac, gold_frac = compute_solo_reward_fractions(
        gear_exp_frac=0.10,
        boss_exp_frac=0.22 + 0.33,
        gear_gold_frac=0.05,
        boss_gold_frac=0.22 + 0.33,
    )
    assert exp_frac == pytest.approx(0.10 + 0.22 + 0.33)
    assert gold_frac == pytest.approx(0.05 + 0.22 + 0.33)


def test_plus_mult_applied_after_additive_pct():
    exp_frac = 0.20
    plus = dungeon_plus_reward_mult(3)
    exp_gain, _ = apply_solo_kill_reward_amounts(1000, 0, exp_frac, 0.0, plus_reward_mult=plus)
    assert exp_gain == int(round(1000 * 1.20 * plus))


def test_guild_reward_fractions_sums_params():
    exp_f, gold_f = guild_reward_fractions(
        {"dungeon_exp_pct": 0.05, "monster_gold_pct": 0.15, "global_reward_pct": 0.0}
    )
    assert exp_f == pytest.approx(0.05)
    assert gold_f == pytest.approx(0.15)


def test_legendary_gold_mult_separate():
    _, gold_gain = apply_solo_kill_reward_amounts(
        0, 100, 0.0, 0.0, legendary_gold_mult=1.5
    )
    assert gold_gain == 150
