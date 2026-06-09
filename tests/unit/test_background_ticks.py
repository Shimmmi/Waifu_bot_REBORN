"""Unit tests: background tick registry and Dramatiq actor map."""

from __future__ import annotations

from waifu_bot.services.background_ticks import get_background_tick_registry
from waifu_bot.worker.actors.gameplay import TICK_ACTORS


def test_registry_covers_all_tick_actors():
    specs = {s.name for s in get_background_tick_registry()}
    actors = set(TICK_ACTORS.keys())
    assert specs == actors


def test_registry_has_gd_v1_round():
    names = [s.name for s in get_background_tick_registry()]
    assert "gd_v1_round" in names
    assert "chat_rewards_flush" in names
    assert "chat_rewards_daily_claim" in names
