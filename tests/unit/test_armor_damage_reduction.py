"""Тесты формулы снижения урона от брони A/(A+K(L))."""

from waifu_bot.game.constants import ARMOR_DR_CAP, ARMOR_K_BASE, ARMOR_K_PER_LEVEL
from waifu_bot.game.formulas import calculate_armor_damage_reduction


def test_zero_armor_returns_zero() -> None:
    assert calculate_armor_damage_reduction(0, 30) == 0.0


def test_dr_increases_with_armor() -> None:
    low = calculate_armor_damage_reduction(50, 30)
    high = calculate_armor_damage_reduction(150, 30)
    assert high > low > 0.0


def test_dr_decreases_with_waifu_level_at_same_armor() -> None:
    low_level = calculate_armor_damage_reduction(100, 10)
    high_level = calculate_armor_damage_reduction(100, 50)
    assert low_level > high_level


def test_dr_respects_cap() -> None:
    huge = calculate_armor_damage_reduction(10_000, 1)
    assert huge == ARMOR_DR_CAP


def test_calibration_examples_from_plan() -> None:
    k10 = ARMOR_K_BASE + ARMOR_K_PER_LEVEL * 10
    dr_10_30 = calculate_armor_damage_reduction(30, 10)
    assert abs(dr_10_30 - (30 / (30 + k10))) < 1e-9

    k60 = ARMOR_K_BASE + ARMOR_K_PER_LEVEL * 60
    dr_60_250 = calculate_armor_damage_reduction(250, 60)
    assert abs(dr_60_250 - (250 / (250 + k60))) < 1e-9
