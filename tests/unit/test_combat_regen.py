"""Unit tests for in-combat HP regen policies (solo vs Abyss)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from waifu_bot.game.constants import ONLINE_WINDOW_SECONDS
from waifu_bot.services.combat_regen import (
    apply_abyss_regen,
    apply_hp_regen_for_context,
    is_player_online,
)

def _waifu(*, hp: int = 50, max_hp: int = 100, endurance: int = 10) -> SimpleNamespace:
    now = datetime.now(timezone.utc) - timedelta(minutes=10)
    return SimpleNamespace(
        current_hp=hp,
        max_hp=max_hp,
        endurance=endurance,
        hp_updated_at=now,
    )


def _player(seconds_ago: int | None) -> SimpleNamespace:
    if seconds_ago is None:
        return SimpleNamespace(last_combat_action_at=None)
    return SimpleNamespace(
        last_combat_action_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    )


def test_is_player_online_within_window():
    assert is_player_online(_player(120)) is True


def test_is_player_online_outside_window():
    assert is_player_online(_player(ONLINE_WINDOW_SECONDS + 1)) is False


def test_is_player_online_no_prior_action():
    assert is_player_online(_player(None)) is False


def test_solo_regen_accrues_while_offline():
    w = _waifu(hp=50)
    before = int(w.current_hp)
    changed = apply_hp_regen_for_context(
        w, _player(600), context="solo", extra_hp_per_min=0
    )
    assert changed is True
    assert int(w.current_hp) > before


def test_abyss_regen_suppressed_when_offline():
    w = _waifu(hp=50)
    before = int(w.current_hp)
    changed = apply_hp_regen_for_context(
        w, _player(600), context="abyss", extra_hp_per_min=0
    )
    assert changed is True
    assert int(w.current_hp) == before


def test_abyss_regen_applies_when_online():
    w = _waifu(hp=50)
    before = int(w.current_hp)
    changed = apply_hp_regen_for_context(
        w, _player(60), context="abyss", extra_hp_per_min=0
    )
    assert changed is True
    assert int(w.current_hp) > before


def test_abyss_regen_revives_from_zero_when_online():
    w = _waifu(hp=0)
    apply_abyss_regen(w, extra_hp_per_min=0)
    assert int(w.current_hp) > 0


def test_apply_regen_solo_never_uses_suppress_in_context_helper():
    w = _waifu(hp=40)
    apply_hp_regen_for_context(w, None, context="town")
    assert int(w.current_hp) >= 40
