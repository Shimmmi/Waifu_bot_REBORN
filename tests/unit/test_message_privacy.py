"""Privacy edge: no user message bodies in logs/persist structures."""

from __future__ import annotations

import pytest

from waifu_bot.game.constants import MediaType
from waifu_bot.services.message_privacy import (
    assert_no_user_message_text,
    extract_from_telegram_message,
    strip_forbidden_text_keys,
)


class _FakeChat:
    id = -100
    type = "supergroup"


class _FakeMessage:
    def __init__(self, text: str | None = None, caption: str | None = None) -> None:
        self.text = text
        self.caption = caption
        self.chat = _FakeChat()


def test_extract_signals_and_ephemeral() -> None:
    view = extract_from_telegram_message(_FakeMessage(text="привет мир"), MediaType.TEXT)
    assert view.signals.length == len("привет мир")
    assert view.signals.has_text is True
    assert view.ephemeral.value == "привет мир"


def test_assert_rejects_message_text_key() -> None:
    with pytest.raises(AssertionError, match="message_text"):
        assert_no_user_message_text({"event_data": {"message_text": "secret"}})


def test_assert_allows_length_only() -> None:
    assert_no_user_message_text(
        {"event_data": {"message_length": 12, "summary_ru": "Атака отменена: ≥6, было 5."}}
    )


def test_strip_forbidden_keys() -> None:
    cleaned = strip_forbidden_text_keys(
        {"text": "leak", "message_length": 4, "nested": {"text_preview": "x", "ok": 1}}
    )
    assert "text" not in cleaned
    assert cleaned["message_length"] == 4
    assert "text_preview" not in cleaned["nested"]
    assert cleaned["nested"]["ok"] == 1


def test_slot_summary_has_no_chat_fragments() -> None:
    from waifu_bot.services.guild_raid_narrative_ai import _slot_summary

    text = _slot_summary(
        [
            {
                "slot_label": "00:00–03:59 МСК",
                "rest": False,
                "active_players": ["Alice (2)"],
                "messages": 2,
                "previews": ["should not appear"],
            }
        ]
    )
    assert "Фрагменты чата" not in text
    assert "should not appear" not in text
    assert "сообщений: 2" in text
