"""Unit tests for solo dungeon DM notifications."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.dungeon_notify import (
    build_auto_restart_skip_line,
    build_solo_dungeon_outcome_text,
    build_solo_dungeon_retry_keyboard,
    build_solo_dungeon_start_line,
    notify_solo_dungeon_outcome,
    parse_solo_dungeon_retry_callback,
    solo_dungeon_retry_callback_data,
    start_dungeon_error_message,
)
from waifu_bot.services.solo_dungeon_auto_restart import AutoRestartResult, AutoRestartTarget


def test_build_solo_dungeon_outcome_text_success_with_item_and_hp():
    text = build_solo_dungeon_outcome_text(
        completed=True,
        dungeon_name="Пещера",
        plus_level=2,
        gold=500,
        exp=120,
        item_dropped={"name": "Меч", "level": 5},
        waifu_current_hp=847,
        waifu_max_hp=1200,
    )
    assert "Пещера»+2 пройдено" in text
    assert "500" in text
    assert "120" in text
    assert "Меч" in text
    assert "❤ HP вайфу: 847 / 1200" in text
    assert "веб-приложении" not in text


def test_build_solo_dungeon_outcome_text_fail_caps_and_hp():
    text = build_solo_dungeon_outcome_text(
        completed=False,
        dungeon_name="Лес",
        plus_level=0,
        gold=40,
        exp=10,
        reason="dot",
        waifu_current_hp=1,
        waifu_max_hp=500,
    )
    assert "ПОРАЖЕНИЕ В ПОДЗЕМЕЛЬЕ «Лес»" in text
    assert "урон со временем" in text
    assert "40" in text
    assert "10" in text
    assert "✨ Опыт: 10" in text
    assert "❤ HP вайфу: 1 / 500" in text
    assert "веб-приложении" not in text


def test_solo_dungeon_retry_callback_data_roundtrip():
    assert solo_dungeon_retry_callback_data(42, 2) == "sd_retry_42_2"
    assert parse_solo_dungeon_retry_callback("sd_retry_42_2") == (42, 2)
    assert parse_solo_dungeon_retry_callback("invalid") is None
    assert parse_solo_dungeon_retry_callback("sd_retry_x_1") is None


def test_build_solo_dungeon_retry_keyboard():
    kb = build_solo_dungeon_retry_keyboard(99, 3)
    btn = kb.inline_keyboard[0][0]
    assert btn.text == "🔄 Войти снова"
    assert btn.callback_data == "sd_retry_99_3"


def test_start_dungeon_error_message_known_and_unknown():
    assert "активное подземелье" in start_dungeon_error_message("dungeon_already_active")
    assert "Бездны" in start_dungeon_error_message("abyss_session_active")
    assert start_dungeon_error_message("unknown_code") == "Не удалось начать подземелье."


def test_build_solo_dungeon_start_line():
    line = build_solo_dungeon_start_line({"monster_name": "Goblin", "monster_hp": 42})
    assert "Goblin" in line
    assert "42" in line
    assert build_solo_dungeon_start_line({"error": "x"}) is None


def test_build_auto_restart_skip_line_low_hp():
    result = AutoRestartResult(status="skipped_low_hp", min_hp_percent=40)
    assert "40%" in (build_auto_restart_skip_line(result) or "")


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_auto_started_no_keyboard():
    session = AsyncMock()
    bot = AsyncMock()
    auto_result = AutoRestartResult(
        status="started",
        target=AutoRestartTarget(12, 1, 2, 3),
        start_payload={"monster_name": "Boss", "monster_hp": 50},
    )
    with (
        patch("waifu_bot.services.webhook.get_bot", return_value=bot),
        patch(
            "waifu_bot.services.player_notification_prefs.should_send_dm",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.try_auto_restart_solo_dungeon",
            new_callable=AsyncMock,
            return_value=auto_result,
        ),
    ):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=True,
            dungeon_name="Test",
            dungeon_id=12,
            plus_level=1,
            gold=10,
            exp=5,
            waifu_current_hp=100,
            waifu_max_hp=200,
        )
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["reply_markup"] is None
    assert "Подземелье начато" in kwargs["text"]


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_sends_dm_with_keyboard():
    session = AsyncMock()
    bot = AsyncMock()
    with (
        patch("waifu_bot.services.webhook.get_bot", return_value=bot),
        patch(
            "waifu_bot.services.player_notification_prefs.should_send_dm",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.try_auto_restart_solo_dungeon",
            new_callable=AsyncMock,
            return_value=AutoRestartResult(status="disabled"),
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.resolve_retry_target_for_outcome",
            new_callable=AsyncMock,
            return_value=(12, 1),
        ),
    ):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=True,
            dungeon_name="Test",
            dungeon_id=12,
            plus_level=1,
            gold=10,
            exp=5,
            waifu_current_hp=100,
            waifu_max_hp=200,
        )
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 777
    assert kwargs["reply_markup"] is not None
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == "sd_retry_12_1"


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_skips_when_pref_disabled():
    session = AsyncMock()
    bot = AsyncMock()
    with (
        patch("waifu_bot.services.webhook.get_bot", return_value=bot),
        patch(
            "waifu_bot.services.player_notification_prefs.should_send_dm",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.try_auto_restart_solo_dungeon",
            new_callable=AsyncMock,
            return_value=AutoRestartResult(status="disabled"),
        ) as auto_mock,
    ):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=True,
            dungeon_name="Test",
            dungeon_id=12,
            gold=10,
            exp=5,
        )
    auto_mock.assert_awaited_once()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_solo_dungeon_outcome_swallows_send_errors():
    session = AsyncMock()
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("blocked")
    with (
        patch("waifu_bot.services.webhook.get_bot", return_value=bot),
        patch(
            "waifu_bot.services.player_notification_prefs.should_send_dm",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.try_auto_restart_solo_dungeon",
            new_callable=AsyncMock,
            return_value=AutoRestartResult(status="disabled"),
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.resolve_retry_target_for_outcome",
            new_callable=AsyncMock,
            return_value=(5, 0),
        ),
    ):
        await notify_solo_dungeon_outcome(
            session,
            777,
            completed=False,
            dungeon_name="Test",
            dungeon_id=5,
            reason="death",
        )
