"""Unit tests for post_chat_completions_routerai explicit model slug."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from waifu_bot.services.llm_client import post_chat_completions_routerai


class TestLlmClientRouteraiDirect(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_model_sent_in_payload(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            body = json.loads(request.content.decode())
            seen["model"] = body.get("model", "")
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

        transport = httpx.MockTransport(handler)
        with patch("waifu_bot.services.llm_client._routerai_provider") as mock_prov:
            mock_prov.return_value = type(
                "P",
                (),
                {
                    "name": "routerai",
                    "base_url": "https://routerai.ru/api/v1",
                    "api_key": "ra-key",
                    "text_model": "default-model",
                    "image_model": "img",
                },
            )()
            async with httpx.AsyncClient(transport=transport) as client:
                r = await post_chat_completions_routerai(
                    client,
                    {"messages": [{"role": "user", "content": "ping"}]},
                    model="google/gemini-3.5-flash",
                    caller="test-routerai-direct",
                )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(seen["model"], "google/gemini-3.5-flash")


if __name__ == "__main__":
    unittest.main()
