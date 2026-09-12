"""RouterAI-only image model configuration."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from waifu_bot.services.llm_client import (
    DEFAULT_IMAGE_MODEL,
    IMAGE_MODALITY_ATTEMPTS,
    chat_payload_to_images_body,
    get_image_model,
    has_image_llm_configured,
    image_provider_chain,
    images_response_as_chat,
    post_chat_completions,
    uses_images_endpoint,
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

    def test_uses_images_endpoint_for_gpt_image(self) -> None:
        self.assertTrue(uses_images_endpoint("openai/gpt-image-2.5-sunburst"))
        self.assertTrue(uses_images_endpoint("openai/gpt-image-1"))
        self.assertFalse(uses_images_endpoint("google/gemini-3.1-flash-lite-image"))
        self.assertFalse(uses_images_endpoint("img-routerai"))

    def test_chat_payload_to_images_body(self) -> None:
        body = chat_payload_to_images_body(
            {
                "model": "openai/gpt-image-2.5-sunburst",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "draw bear"},
                            {
                                "type": "image_url",
                                "image_url": {"url": "data:image/png;base64,abc"},
                            },
                        ],
                    }
                ],
                "image_config": {"aspect_ratio": "3:2", "image_size": "1K"},
            }
        )
        self.assertEqual(body["model"], "openai/gpt-image-2.5-sunburst")
        self.assertEqual(body["prompt"], "draw bear")
        self.assertEqual(body["aspect_ratio"], "3:2")
        self.assertEqual(body["resolution"], "1K")
        self.assertEqual(body["n"], 1)
        self.assertEqual(
            body["input_references"],
            [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
        )

    def test_images_response_as_chat(self) -> None:
        wrapped = images_response_as_chat({"data": [{"b64_json": "QUJD"}], "usage": {"cost": 1}})
        images = wrapped["choices"][0]["message"]["images"]
        self.assertEqual(images[0]["image_url"]["url"], "data:image/png;base64,QUJD")


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

    async def test_gpt_image_posts_to_images_endpoint(self) -> None:
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            import json

            payload = json.loads(request.content.decode())
            self.assertEqual(payload.get("model"), "openai/gpt-image-2.5-sunburst")
            self.assertEqual(payload.get("prompt"), "draw a polar bear")
            self.assertEqual(payload.get("aspect_ratio"), "3:2")
            self.assertNotIn("messages", payload)
            return httpx.Response(200, json={"data": [{"b64_json": "QUJD"}]})

        transport = httpx.MockTransport(handler)
        payload = {
            "model": "openai/gpt-image-2.5-sunburst",
            "messages": [{"role": "user", "content": "draw a polar bear"}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": "3:2", "image_size": "1K"},
        }

        with patch("waifu_bot.services.llm_client.settings") as mock_settings:
            mock_settings.openrouter_api_key = None
            mock_settings.routerai_api_key = "ra-k"
            mock_settings.routerai_base_url = "https://routerai.ru/api/v1"
            mock_settings.routerai_model = None
            mock_settings.routerai_model_image = "openai/gpt-image-2.5-sunburst"
            mock_settings.llm_worker_enabled = False

            async with httpx.AsyncClient(transport=transport) as client:
                r = await post_chat_completions(
                    client,
                    payload,
                    caller="test-gpt-image",
                    use_image_model=True,
                )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(paths, ["/api/v1/images"])
        data = r.json()
        url = data["choices"][0]["message"]["images"][0]["image_url"]["url"]
        self.assertEqual(url, "data:image/png;base64,QUJD")


if __name__ == "__main__":
    unittest.main()
