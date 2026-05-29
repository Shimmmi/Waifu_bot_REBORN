"""Unit tests for solo dungeon DM notifications."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.dungeon_notify import (
    build_solo_dungeon_outcome_text,
    notify_solo_dungeon_outcome,
)


def test_build_solo_dungeon_outcome_text_success_with_item():
    text = build_solo_dungeon_outcome_text(
        completed=True,
        dungeon_name="Пещера",
        plus_level=2,
        gold=500,
        exp=120,
        item_dropped={"name": "Меч", "level": 5},
    )
    assert "Пещера»+2 пройдено" in text
    assert "500" in text
    assert "120" in text
    assert "Меч" in text


def test_build_solo_dungeon_outcome_text_fail():
    text = build_solo_dungeon_outcome_text(
        completed=False,
        dungeon_name="Лес",
        plus_level=0,
        gold=40,
        exp=10,
        reason="dot",
    )
    assert "проиграно" in text
    assert "урон со временем" in text
    assert "40" in text


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_sends_dm():
    session = AsyncMock()
    bot = AsyncMock()
    with patch("waifu_bot.services.webhook.get_bot", return_value=bot):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=True,
            dungeon_name="Test",
            gold=10,
            exp=5,
        )
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 777


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_swallows_send_errors():
    session = AsyncMock()
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("blocked")
    with patch("waifu_bot.services.webhook.get_bot", return_value=bot):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=False,
            dungeon_name="Test",
            reason="death",
        )
