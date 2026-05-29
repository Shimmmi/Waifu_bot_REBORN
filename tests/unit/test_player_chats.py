"""Unit tests for player group chat tracking."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.services.player_chats import (
    resolve_player_group_chats,
    touch_player_chat_seen,
)


@pytest.mark.asyncio
async def test_touch_player_chat_seen_ignores_private_chat():
    session = AsyncMock()
    await touch_player_chat_seen(session, 42, 12345)
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_touch_player_chat_seen_inserts_group_chat():
    session = AsyncMock()
    await touch_player_chat_seen(session, 42, -100123)
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_player_group_chats_merges_sources():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.all.return_value = [(-1001,), (-1002,), (-1001,)]
    session.execute = AsyncMock(return_value=result_mock)

    chat_ids = await resolve_player_group_chats(session, 99)

    assert chat_ids == [-1002, -1001]
    session.execute.assert_awaited_once()
