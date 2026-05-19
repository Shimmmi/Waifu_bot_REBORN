"""Регрессия: форматирование и отправка полного журнала соло-боя в ЛС."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.solo_battle_log_dm import (
    format_battle_log_entry_ru,
    format_damage_step_ru,
    format_solo_battle_log_messages_ru,
    prepare_solo_battle_log_dm_messages,
    send_solo_battle_log_dm,
)


def test_format_damage_step_base() -> None:
    s = format_damage_step_ru(
        {"kind": "base", "label_ru": "База: урон оружия", "value_after": 100}
    )
    assert "База" in s and "100" in s


def test_format_damage_step_contrib_and_cap() -> None:
    c = format_damage_step_ru(
        {"kind": "contrib", "label_ru": "Пассив «Железная кожа»", "pct_add": 0.18}
    )
    assert "◦" in c and "18.00%" in c
    cap = format_damage_step_ru(
        {"kind": "cap", "label_ru": "Потолок 90%: отброшено 5%"}
    )
    assert "⚠" in cap


def test_format_damage_step_mult() -> None:
    s = format_damage_step_ru(
        {
            "kind": "mult",
            "label_ru": "Коэффициент стикера",
            "value_before": 50,
            "value_after": 45,
            "factor": 0.9,
        }
    )
    assert "50 → 45" in s
    assert "0.9" in s


def test_format_damage_step_add() -> None:
    s = format_damage_step_ru(
        {
            "kind": "add",
            "label_ru": "Урон от СИЛ",
            "value_before": 100,
            "value_after": 120,
            "delta": 20,
        }
    )
    assert "+20" in s


def test_format_battle_log_entry_with_breakdown() -> None:
    entry = {
        "event_type": "damage",
        "log_media_label_ru": "Текст",
        "summary_ru": "Гуль: 42 урона.",
        "message_text": "hello world",
        "damage_breakdown": [
            {"kind": "base", "label_ru": "База", "value_after": 10},
            {
                "kind": "mult",
                "label_ru": "×0.9",
                "value_before": 10,
                "value_after": 9,
                "factor": 0.9,
            },
        ],
        "monster_hp_before": 100,
        "monster_hp_after": 58,
    }
    text = format_battle_log_entry_ru(entry, 1)
    assert "#1" in text
    assert "[Текст]" in text
    assert "hello world" in text
    assert "100 → 58" in text
    assert "База" in text


def test_format_solo_battle_log_splits_long_journal() -> None:
    entries = [
        {
            "event_type": "damage",
            "summary_ru": f"Удар {i}",
            "damage_breakdown": [
                {
                    "kind": "base",
                    "label_ru": "x" * 200,
                    "value_after": i,
                }
            ],
        }
        for i in range(30)
    ]
    parts = format_solo_battle_log_messages_ru(
        entries, dungeon_name="Тестовый данж", max_chars=800
    )
    assert len(parts) >= 2
    assert all("Тестовый данж" in p for p in parts)
    assert any("ч. 2/" in p for p in parts)


@pytest.mark.asyncio
async def test_prepare_returns_none_for_non_admin() -> None:
    session = MagicMock()
    with patch("waifu_bot.services.solo_battle_log_dm.settings") as st:
        st.admin_ids = [111]
        out = await prepare_solo_battle_log_dm_messages(session, 999, 1, "Данж")
    assert out is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_formats_for_admin() -> None:
    session = MagicMock()
    entries = [
        {
            "event_type": "damage",
            "summary_ru": "Удар: 5",
            "log_media_label_ru": "Текст",
            "damage_breakdown": [],
        }
    ]
    with patch("waifu_bot.services.solo_battle_log_dm.settings") as st:
        st.admin_ids = [42]
        with patch(
            "waifu_bot.services.solo_battle_log_dm.fetch_solo_battle_log_entries",
            new_callable=AsyncMock,
            return_value=entries,
        ):
            out = await prepare_solo_battle_log_dm_messages(session, 42, 7, "Пещера")
    assert out is not None
    assert len(out) == 1
    assert "Пещера" in out[0]
    assert "Удар: 5" in out[0]


@pytest.mark.asyncio
async def test_send_solo_battle_log_dm_calls_bot() -> None:
    bot = AsyncMock()
    with patch("waifu_bot.services.solo_battle_log_dm.get_bot", return_value=bot, create=True):
        with patch("waifu_bot.services.webhook.get_bot", return_value=bot):
            await send_solo_battle_log_dm(42, ["part one", "part two"])
    assert bot.send_message.await_count == 2
    bot.send_message.assert_any_await(chat_id=42, text="part one")
    bot.send_message.assert_any_await(chat_id=42, text="part two")


@pytest.mark.asyncio
async def test_send_skips_when_none() -> None:
    with patch("waifu_bot.services.webhook.get_bot") as gb:
        await send_solo_battle_log_dm(1, None)
        gb.assert_not_called()
