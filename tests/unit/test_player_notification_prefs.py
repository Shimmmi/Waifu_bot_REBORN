"""Unit tests for DM notification preferences."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.services.player_notification_prefs import (
    DEFAULT_DM_NOTIFICATION_PREFS,
    get_prefs,
    merge_patch,
    normalize_prefs,
    should_send_dm,
)


def test_normalize_prefs_defaults():
    assert normalize_prefs(None) == DEFAULT_DM_NOTIFICATION_PREFS
    assert normalize_prefs({}) == DEFAULT_DM_NOTIFICATION_PREFS


def test_normalize_prefs_partial():
    out = normalize_prefs({"solo_dungeon": False, "unknown": True})
    assert out["solo_dungeon"] is False
    assert out["expedition_result"] is True
    assert "unknown" not in out


def test_merge_patch():
    player = MagicMock()
    player.dm_notification_prefs = dict(DEFAULT_DM_NOTIFICATION_PREFS)
    result = merge_patch(player, {"group_dungeon": False})
    assert result["group_dungeon"] is False
    assert player.dm_notification_prefs["group_dungeon"] is False


@pytest.mark.asyncio
async def test_should_send_dm_false():
    session = AsyncMock()
    player = MagicMock()
    player.dm_notification_prefs = {**DEFAULT_DM_NOTIFICATION_PREFS, "solo_dungeon": False}
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=player))
    )
    assert await should_send_dm(session, 123, "solo_dungeon") is False


@pytest.mark.asyncio
async def test_should_send_dm_true_when_no_player():
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    assert await should_send_dm(session, 123, "solo_dungeon") is True


def test_get_prefs_from_player():
    player = MagicMock()
    player.dm_notification_prefs = {"raid": False}
    prefs = get_prefs(player)
    assert prefs["raid"] is False
    assert prefs["solo_dungeon"] is True
