"""Hire name+bio JSON parsing and Gemini thinking extras."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from waifu_bot.services.ai_narrative_rewrite import _openrouter_text_extra
from waifu_bot.services.ai_service import _sanitize_single_output
from waifu_bot.services.expedition_events_ai import (
    _parse_name_bio_json,
    generate_hire_waifu_name_and_bio,
)


class TestParseNameBioJson(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(
            _parse_name_bio_json('{"name": "Хлодвига", "bio": "Рубит с плеча."}'),
            ("Хлодвига", "Рубит с плеча."),
        )

    def test_fenced_json(self) -> None:
        raw = '```json\n{"name": "Хлодвига", "bio": "Рубит с плеча."}\n```'
        self.assertEqual(_parse_name_bio_json(raw), ("Хлодвига", "Рубит с плеча."))

    def test_unclosed_fence(self) -> None:
        raw = '```json {"name": "Хлодвига", "bio": "Рубит с плеча."}'
        self.assertEqual(_parse_name_bio_json(raw), ("Хлодвига", "Рубит с плеча."))

    def test_json_with_trailing_prose(self) -> None:
        raw = '{"name": "Хлодвига", "bio": "Рубит с плеча."}\nHope this helps!'
        self.assertEqual(_parse_name_bio_json(raw), ("Хлодвига", "Рубит с плеча."))

    def test_truncated_json_returns_none(self) -> None:
        self.assertIsNone(_parse_name_bio_json('```json {"name": "Хлодви'))

    def test_non_json_returns_none(self) -> None:
        self.assertIsNone(_parse_name_bio_json("ridiculous or edgy.         *"))


class TestSanitizeJsonOutput(unittest.TestCase):
    def test_keeps_json_asterisks(self) -> None:
        raw = '{"name": "Айра", "bio": "Бьёт *с размаху*."}'
        self.assertEqual(_sanitize_single_output(raw), raw)


class TestReasoningExtra(unittest.TestCase):
    def test_minimal_thinking(self) -> None:
        extra = _openrouter_text_extra()
        self.assertEqual(extra["reasoning"]["effort"], "minimal")
        self.assertTrue(extra["reasoning"]["exclude"])


class TestHireNameBioRetry(unittest.IsolatedAsyncioTestCase):
    async def test_retries_when_first_response_is_not_json(self) -> None:
        with patch(
            "waifu_bot.services.expedition_events_ai.has_text_llm_configured",
            return_value=True,
        ), patch(
            "waifu_bot.services.expedition_events_ai._ai_text",
            new=AsyncMock(
                side_effect=[
                    "ridiculous or edgy.",
                    '{"name": "Сильвэ", "bio": "Смеётся в кустах и режет караван."}',
                ]
            ),
        ) as mock_ai:
            out = await generate_hire_waifu_name_and_bio("эльфийка", "ассасин", 3, ["скрытность"])
        self.assertEqual(out, ("Сильвэ", "Смеётся в кустах и режет караван."))
        self.assertEqual(mock_ai.await_count, 2)
        self.assertEqual(mock_ai.await_args_list[0].kwargs["max_tokens"], 700)
        self.assertEqual(mock_ai.await_args_list[1].kwargs["caller"], "hire name+bio retry")


if __name__ == "__main__":
    unittest.main()
