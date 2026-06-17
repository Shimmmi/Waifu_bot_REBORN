"""Unit tests for ai_service.generate()."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from waifu_bot.services.ai_service import generate


class TestAiService(unittest.IsolatedAsyncioTestCase):
    async def test_generate_single_returns_text(self) -> None:
        with patch("waifu_bot.services.ai_service.has_text_llm_configured", return_value=True), patch(
            "waifu_bot.services.ai_service.resolve_preset",
        ) as mock_resolve, patch(
            "waifu_bot.services.ai_service._generate_single",
            new=AsyncMock(return_value="Hello world"),
        ), patch(
            "waifu_bot.services.ai_service.should_offload_llm",
            return_value=False,
        ):
            from waifu_bot.services.ai_presets import PresetDefaults, SinglePreset

            mock_resolve.return_value = (
                SinglePreset(model="google/gemini-3.5-flash", post_process=None),
                PresetDefaults(),
            )
            out = await generate("Say hi", preset="fast", caller="test", post_process_rhythm=False)
        self.assertEqual(out, "Hello world")

    async def test_generate_without_routerai_returns_none(self) -> None:
        with patch("waifu_bot.services.ai_service.has_text_llm_configured", return_value=False):
            out = await generate("x", caller="test")
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
