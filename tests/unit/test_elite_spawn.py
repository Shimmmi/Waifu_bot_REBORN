"""Elite spawn chance: no luck, uniform base, Dungeon+ bonus."""

from __future__ import annotations

import pytest

from waifu_bot.game.constants import (
    ELITE_SPAWN_BONUS_MAX,
    ELITE_SPAWN_CHANCE_BASE,
    elite_spawn_bonus_for_plus_level,
)


def _p(plus_level: int) -> float:
    b = elite_spawn_bonus_for_plus_level(plus_level)
    p = float(ELITE_SPAWN_CHANCE_BASE) + b
    return max(0.0, min(1.0, p))


def test_bonus_zero_at_standard_difficulty() -> None:
    assert elite_spawn_bonus_for_plus_level(0) == pytest.approx(0.0)


def test_bonus_scales_per_plus_level() -> None:
    assert elite_spawn_bonus_for_plus_level(1) == pytest.approx(0.02)
    assert elite_spawn_bonus_for_plus_level(10) == pytest.approx(0.20)


def test_bonus_capped_at_40_percent() -> None:
    assert elite_spawn_bonus_for_plus_level(20) == pytest.approx(ELITE_SPAWN_BONUS_MAX)
    assert elite_spawn_bonus_for_plus_level(30) == pytest.approx(ELITE_SPAWN_BONUS_MAX)


def test_monotonic_probability_with_plus_level() -> None:
    assert _p(0) < _p(1) < _p(5) < _p(20)
    assert _p(20) == pytest.approx(ELITE_SPAWN_CHANCE_BASE + ELITE_SPAWN_BONUS_MAX)


def test_standard_difficulty_is_uniform_base() -> None:
    """All pl=0 dungeons use base only (no template/luck in formula)."""
    assert _p(0) == pytest.approx(ELITE_SPAWN_CHANCE_BASE)
