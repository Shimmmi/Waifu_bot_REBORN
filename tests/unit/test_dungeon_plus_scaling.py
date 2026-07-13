"""Unit tests for Dungeon+ TTK-anchored HP / decoupled DMG scaling."""

from __future__ import annotations

import math

import pytest

from waifu_bot.game.dungeon_plus_scaling import (
    REF_MSG_DAMAGE,
    dungeon_plus_budget_mult,
    dungeon_plus_difficulty_params,
    dungeon_plus_dmg_mult,
    dungeon_plus_extra_monsters,
    dungeon_plus_hp_mult_for_rolled,
    dungeon_plus_hp_target,
    dungeon_plus_reward_mult,
    dungeon_plus_ttk_normal,
)
from waifu_bot.game.solo_rewards import dungeon_plus_reward_mult as solo_reward_mult


@pytest.mark.parametrize(
    "n, expected_ttk",
    [
        (1, 3.4),
        (5, 5.0),
        (10, 7.0),
        (30, 15.0),
    ],
)
def test_ttk_normal_anchors(n: int, expected_ttk: float) -> None:
    assert dungeon_plus_ttk_normal(n) == pytest.approx(expected_ttk)
    assert dungeon_plus_hp_target(n) == pytest.approx(REF_MSG_DAMAGE * expected_ttk)


@pytest.mark.parametrize("n", [1, 5, 10, 30])
def test_hp_mult_lands_near_target(n: int) -> None:
    # Typical tier-5 mid-roll base before plus scale (illustrative).
    rolled_hp = 1000
    hp_m = dungeon_plus_hp_mult_for_rolled(n, rolled_hp)
    final = int(round(rolled_hp * hp_m))
    target = dungeon_plus_hp_target(n)
    assert final == pytest.approx(target, rel=0.01)
    assert hp_m >= 1.0


@pytest.mark.parametrize(
    "n, expected",
    [
        (1, 1.08),
        (5, 1.40),
        (10, 1.80),
        (30, 3.40),
    ],
)
def test_dmg_mult_anchors(n: int, expected: float) -> None:
    assert dungeon_plus_dmg_mult(n) == pytest.approx(expected)


@pytest.mark.parametrize("n", [1, 5, 10, 30])
def test_dmg_mult_less_than_hp_mult(n: int) -> None:
    rolled_hp = 800
    assert dungeon_plus_dmg_mult(n) < dungeon_plus_hp_mult_for_rolled(n, rolled_hp)


@pytest.mark.parametrize(
    "n, expected",
    [
        (0, 0),
        (1, 0),
        (3, 0),
        (4, 1),
        (8, 2),
        (10, 2),
        (30, 7),
    ],
)
def test_extra_monsters(n: int, expected: int) -> None:
    assert dungeon_plus_extra_monsters(n) == expected


@pytest.mark.parametrize("n", [0, 1, 3, 10, 30])
def test_reward_mult_formula(n: int) -> None:
    expected = 1.0 + n * 0.22 + math.log1p(n) * 0.15
    assert dungeon_plus_reward_mult(n) == pytest.approx(expected)
    assert solo_reward_mult(n) == pytest.approx(expected)


def test_reward_mult_higher_than_legacy_at_plus_10() -> None:
    legacy = 1.0 + 10 * 0.15 + math.log1p(10) * 0.10
    assert dungeon_plus_reward_mult(10) > legacy


def test_zero_plus_is_noop() -> None:
    assert dungeon_plus_ttk_normal(0) == pytest.approx(1.0)
    assert dungeon_plus_hp_target(0) == pytest.approx(0.0)
    assert dungeon_plus_hp_mult_for_rolled(0, 500) == pytest.approx(1.0)
    assert dungeon_plus_dmg_mult(0) == pytest.approx(1.0)
    assert dungeon_plus_extra_monsters(0) == 0
    assert dungeon_plus_budget_mult(0) == pytest.approx(1.0)


def test_difficulty_params_keys() -> None:
    p = dungeon_plus_difficulty_params(5)
    assert p["hp_target"] == pytest.approx(25000.0)
    assert p["dmg_mult"] == pytest.approx(1.40)
    assert p["budget_mult"] == pytest.approx(5.0)
    assert p["extra_monsters"] == 1
    assert p["item_level_bonus"] == 5
    assert p["rarity_floor"] == "rare"
    assert p["elite_chance_bonus"] == pytest.approx(0.10)


def test_ref_msg_damage_is_5000() -> None:
    assert REF_MSG_DAMAGE == 5000
