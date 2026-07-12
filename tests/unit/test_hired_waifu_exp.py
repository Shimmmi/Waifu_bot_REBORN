"""Unit tests: hired waifu experience (exp_current / exp_to_next)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from waifu_bot.services.expedition import _apply_exp_to_hired_unit, exp_to_next_level_hired


def test_exp_to_next_level_hired_formula() -> None:
    assert exp_to_next_level_hired(1) == 50
    assert exp_to_next_level_hired(2) == 105
    assert exp_to_next_level_hired(3) == 170
    assert exp_to_next_level_hired(5) == 330


def test_apply_exp_to_hired_unit_within_level() -> None:
    unit = SimpleNamespace(
        level=1,
        exp_current=0,
        perk_upgrade_points=0,
        max_hp=65,
        current_hp=65,
    )
    leveled, lvl = _apply_exp_to_hired_unit(unit, 30)
    assert not leveled
    assert lvl == 1
    assert unit.exp_current == 30


def test_apply_exp_to_hired_unit_level_up() -> None:
    unit = SimpleNamespace(
        level=1,
        exp_current=40,
        perk_upgrade_points=0,
        max_hp=65,
        current_hp=65,
    )
    with patch("waifu_bot.services.hired_waifu_state.refresh_hired_power"):
        leveled, lvl = _apply_exp_to_hired_unit(unit, 20)
    assert leveled
    assert lvl == 2
    assert unit.exp_current == 10
    assert unit.perk_upgrade_points == 1
    assert unit.max_hp == 50 + 2 * 15


def test_build_damage_summary_finish_blocked() -> None:
    from waifu_bot.services.combat_damage_trace import build_damage_summary_ru

    s = build_damage_summary_ru(
        damage=10000,
        is_crit=True,
        monster_dodged=False,
        monster_name="Статуя",
        finish_blocked=True,
    )
    assert "Добивание заблокировано" in s
    assert "1 HP" in s
