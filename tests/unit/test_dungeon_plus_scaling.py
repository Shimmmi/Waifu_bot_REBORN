"""Unit tests for Dungeon+ nonlinear HP / decoupled DMG scaling."""

from __future__ import annotations

import math

import pytest

from waifu_bot.game.dungeon_plus_scaling import (
    ENTRY_REF_MSG_DAMAGE,
    HP_EXP,
    HP_FLAT,
    HP_SCALE,
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


def _expected_hp(n: int) -> float:
    return HP_FLAT + HP_SCALE * (n ** HP_EXP)


@pytest.mark.parametrize(
    "n, approx_hp",
    [
        (1, 2400),
        (5, 5480),
        (10, 16400),
        (30, 152000),
    ],
)
def test_hp_target_anchors(n: int, approx_hp: float) -> None:
    hp = dungeon_plus_hp_target(n)
    assert hp == pytest.approx(_expected_hp(n))
    assert hp == pytest.approx(approx_hp, rel=0.02)


def test_soft_entry_and_steep_late() -> None:
    assert dungeon_plus_hp_target(1) < 4000
    assert dungeon_plus_hp_target(30) > 2 * 75000  # steeper than old linear 75k


@pytest.mark.parametrize("n", [1, 5, 10, 30])
def test_ttk_derived_from_entry_ref(n: int) -> None:
    assert dungeon_plus_ttk_normal(n) == pytest.approx(
        dungeon_plus_hp_target(n) / ENTRY_REF_MSG_DAMAGE
    )


@pytest.mark.parametrize("n", [1, 5, 10, 30])
def test_hp_mult_lands_near_target(n: int) -> None:
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
        (4, 0),
        (7, 0),
        (8, 1),
        (10, 1),
        (11, 1),
        (12, 2),
        (30, 6),
    ],
)
def test_extra_monsters(n: int, expected: int) -> None:
    assert dungeon_plus_extra_monsters(n) == expected


@pytest.mark.parametrize("n", [0, 1, 3, 10, 30])
def test_reward_mult_formula(n: int) -> None:
    expected = 1.0 + n * 0.22 + math.log1p(n) * 0.15
    assert dungeon_plus_reward_mult(n) == pytest.approx(expected)
    assert solo_reward_mult(n) == pytest.approx(expected)


def test_zero_plus_is_noop() -> None:
    assert dungeon_plus_ttk_normal(0) == pytest.approx(1.0)
    assert dungeon_plus_hp_target(0) == pytest.approx(0.0)
    assert dungeon_plus_hp_mult_for_rolled(0, 500) == pytest.approx(1.0)
    assert dungeon_plus_dmg_mult(0) == pytest.approx(1.0)
    assert dungeon_plus_extra_monsters(0) == 0
    assert dungeon_plus_budget_mult(0) == pytest.approx(1.0)


def test_budget_mult_sqrt_of_hp_ratio() -> None:
    assert dungeon_plus_budget_mult(1) == pytest.approx(1.0)
    ratio = dungeon_plus_hp_target(30) / dungeon_plus_hp_target(1)
    assert dungeon_plus_budget_mult(30) == pytest.approx(ratio ** 0.5)
    assert dungeon_plus_budget_mult(30) < ratio  # damped vs raw HP growth


def test_difficulty_params_keys() -> None:
    p = dungeon_plus_difficulty_params(5)
    assert p["hp_target"] == pytest.approx(_expected_hp(5))
    assert p["dmg_mult"] == pytest.approx(1.40)
    assert p["budget_mult"] == pytest.approx(
        (dungeon_plus_hp_target(5) / dungeon_plus_hp_target(1)) ** 0.5
    )
    assert p["extra_monsters"] == 0
    assert p["item_level_bonus"] == 5
    assert p["rarity_floor"] == "rare"
    assert p["elite_chance_bonus"] == pytest.approx(0.10)


def test_entry_ref_is_1000() -> None:
    assert ENTRY_REF_MSG_DAMAGE == 1000
