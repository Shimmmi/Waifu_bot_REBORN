"""Unit tests for solo dungeon auto-restart preferences."""
from __future__ import annotations

from waifu_bot.db.models.player import Player
from waifu_bot.services.solo_dungeon_auto_prefs import (
    DEFAULT_SOLO_DUNGEON_AUTO_PREFS,
    clamp_min_hp_percent,
    get_prefs,
    merge_patch,
    normalize_prefs,
)


def test_normalize_prefs_defaults():
    assert normalize_prefs(None) == DEFAULT_SOLO_DUNGEON_AUTO_PREFS
    assert normalize_prefs({}) == DEFAULT_SOLO_DUNGEON_AUTO_PREFS


def test_clamp_min_hp_percent():
    assert clamp_min_hp_percent(5) == 10
    assert clamp_min_hp_percent(30) == 30
    assert clamp_min_hp_percent(99) == 50


def test_merge_patch_on_player():
    player = Player(id=1)
    player.solo_dungeon_auto_prefs = dict(DEFAULT_SOLO_DUNGEON_AUTO_PREFS)
    merge_patch(player, {"enabled": True, "min_hp_percent": 45})
    prefs = get_prefs(player)
    assert prefs["enabled"] is True
    assert prefs["min_hp_percent"] == 45
    assert player.solo_dungeon_auto_prefs["enabled"] is True
