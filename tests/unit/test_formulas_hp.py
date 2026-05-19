"""Регрессия: calculate_max_hp (game/formulas.py)."""

from waifu_bot.game.constants import BASE_HP_PER_LEVEL, HP_K_COEFFICIENT, STR_HP_COEFFICIENT
from waifu_bot.game.formulas import calculate_max_hp


def test_calculate_max_hp_known_snapshot() -> None:
    level, end_, str_ = 5, 12, 14
    expected = BASE_HP_PER_LEVEL * level + end_ * HP_K_COEFFICIENT + str_ * STR_HP_COEFFICIENT
    assert calculate_max_hp(level, end_, str_) == expected
