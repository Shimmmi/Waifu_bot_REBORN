"""RouterAI-only image model configuration."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from waifu_bot.services.llm_client import (
    DEFAULT_IMAGE_MODEL,
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    image_provider_chain,
    post_chat_completions,
)


class TestLlmImageModel(unittest.TestCase):
    def test_image_modality_attempts_prefer_image_and_text(self) -> None:
        self.assertEqual(IMAGE_MODALITY_ATTEMPTS[0], ("image", "text"))
        self.assertIn(("image",), IMAGE_MODALITY_ATTEMPTS)

    def test_get_image_model_from_routerai_env(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.routerai_model_image = "google/gemini-3.1-flash-lite-image"
            self.assertEqual(get_image_model(), "google/gemini-3.1-flash-lite-image")

    def test_get_image_model_default(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.routerai_model_image = ""
            self.assertEqual(get_image_model(), DEFAULT_IMAGE_MODEL)

    def test_image_provider_chain_routerai_only(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "or-k"
            mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
            mock_settings.openrouter_model = "m1"
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model = None
            mock_settings.routerai_model_image = "img-routerai"

            chain = image_provider_chain()
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].name, "routerai")
        self.assertEqual(chain[0].image_model, "img-routerai")

    def test_has_image_llm_configured_requires_routerai(self) -> None:
        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "or-k"
            mock_settings.routerai_api_key = None
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model_image = "img"
            self.assertFalse(has_image_llm_configured())

        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model_image = "img"
            self.assertTrue(has_image_llm_configured())


class TestLlmImageRouting(unittest.IsolatedAsyncioTestCase):
    async def test_image_request_uses_routerai_not_openrouter(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            host = str(request.url.host or "")
            calls.append(host)
            body = httpx.Request(
                "POST",
                "http://test/",
                content=request.content,
                headers=request.headers,
            )
            import json

            payload = json.loads(body.content.decode())
            self.assertEqual(payload.get("model"), "img-routerai")
            return httpx.Response(200, json={"choices": [{"message": {}}]})

        transport = httpx.MockTransport(handler)
        payload = {
            "model": "img-routerai",
            "messages": [{"role": "user", "content": "draw"}],
            "modalities": ["image"],
        }

        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = "or-k"
            mock_settings.openrouter_base_url = "https://openrouter.ai/api/v1"
            mock_settings.openrouter_model = "m1"
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model = None
            mock_settings.routerai_model_image = "img-routerai"
            mock_settings.llm_worker_enabled = False

            async with httpx.AsyncClient(transport=transport) as client:
                r = await post_chat_completions(
                    client,
                    payload,
                    caller="test-image",
                    use_image_model=True,
                )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(calls, ["routerai.ru"])


if __name__ == "__main__":
    unittest.main()
