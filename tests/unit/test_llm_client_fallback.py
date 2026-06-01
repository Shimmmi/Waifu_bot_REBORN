"""Unit tests for OpenRouter → RouterAI fallback on HTTP 402."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from waifu_bot.services.llm_client import (
    LlmProvider,
    llm_provider_chain,
    post_chat_completions,
)

_OR = LlmProvider(
    name="openrouter",
    base_url="https://openrouter.ai/api/v1",
    api_key="or-key",
    text_model="openai/gpt-4o-mini",
    image_model="img/a",
)
_RA = LlmProvider(
    name="routerai",
    base_url="https://routerai.ru/api/v1",
    api_key="ra-key",
    text_model="google/gemini-3.1-flash-lite-preview",
    image_model="google/gemini-3.1-flash-image-preview",
)


class TestLlmClientFallback(unittest.IsolatedAsyncioTestCase):
    async def test_402_on_openrouter_retries_routerai(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            host = str(request.url.host or "")
            calls.append(host)
            auth = request.headers.get("Authorization", "")
            if "openrouter" in host:
                self.assertEqual(auth, "Bearer or-key")
                return httpx.Response(402, json={"error": "insufficient credits"})
            self.assertIn("routerai", host)
            self.assertEqual(auth, "Bearer ra-key")
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "fallback ok"}}]},
            )

        transport = httpx.MockTransport(handler)
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": "ping"}],
        }

        with patch(
            "waifu_bot.services.llm_client.llm_provider_chain",
            return_value=[_OR, _RA],
        ):
            async with httpx.AsyncClient(transport=transport) as client:
                r = await post_chat_completions(client, payload, caller="test-fallback")

        self.assertEqual(r.status_code, 200)
        self.assertEqual(calls, ["openrouter.ai", "routerai.ru"])
        data = r.json()
        self.assertEqual(
            data["choices"][0]["message"]["content"],
            "fallback ok",
        )

    async def test_402_without_fallback_provider_returns_402(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json={"error": "insufficient credits"})

        transport = httpx.MockTransport(handler)
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": [{"role": "user", "content": "ping"}],
        }

        with patch(
            "waifu_bot.services.llm_client.llm_provider_chain",
            return_value=[_OR],
        ):
            async with httpx.AsyncClient(transport=transport) as client:
                r = await post_chat_completions(client, payload, caller="test-no-fallback")

        self.assertEqual(r.status_code, 402)

    def test_llm_provider_chain_includes_routerai_when_key_set(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "or-k"
            mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
            mock_settings.openrouter_model = "m1"
            mock_settings.openrouter_model_image = "img1"
            mock_settings.openrouter_model_hire = None
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model = "m2"
            mock_settings.routerai_model_image = "img2"

            chain = llm_provider_chain()
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0].name, "openrouter")
        self.assertEqual(chain[1].name, "routerai")

    def test_llm_provider_chain_routerai_only(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = None
            mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
            mock_settings.openrouter_model = "m1"
            mock_settings.openrouter_model_image = "img1"
            mock_settings.openrouter_model_hire = None
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model = None
            mock_settings.routerai_model_image = None

            chain = llm_provider_chain()
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].name, "routerai")


if __name__ == "__main__":
    unittest.main()
