"""Unit tests for LLM usage context and recording."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from waifu_bot.services.llm_client import post_chat_completions_routerai
from waifu_bot.services.llm_usage import (
    bind_llm_http,
    http_trigger,
    llm_player_id,
    llm_source,
    llm_trigger,
    record_llm_http,
    reset_llm_context,
    set_llm_player_id,
    telegram_trigger_from_text,
    usage_tokens_from_response,
)


class TestLlmUsageHelpers(unittest.TestCase):
    def test_http_trigger_strips_api_and_ids(self) -> None:
        self.assertEqual(
            http_trigger("POST", "/api/tavern/living/cards/42/chat"),
            "POST /tavern/living/cards/{id}/chat",
        )

    def test_telegram_slash(self) -> None:
        self.assertEqual(telegram_trigger_from_text("/gd_start@bot extra"), "/gd_start")
        self.assertIsNone(telegram_trigger_from_text("hello"))

    def test_bind_http_context(self) -> None:
        tokens = bind_llm_http("GET", "/api/delve/line")
        try:
            self.assertEqual(llm_source(), "webapp")
            self.assertEqual(llm_trigger(), "GET /delve/line")
            set_llm_player_id(123)
            self.assertEqual(llm_player_id(), 123)
        finally:
            reset_llm_context(tokens)
        self.assertIsNone(llm_player_id())
        self.assertEqual(llm_source(), "background")


class TestUsageTokens(unittest.TestCase):
    def test_reads_usage_block(self) -> None:
        resp = httpx.Response(
            200,
            json={"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 4}},
        )
        self.assertEqual(usage_tokens_from_response(resp), (11, 4))


class TestRecordSkipWithoutEngine(unittest.IsolatedAsyncioTestCase):
    async def test_record_is_noop_without_session(self) -> None:
        with patch("waifu_bot.db.session.SessionLocal", None):
            await record_llm_http(
                caller="test",
                modality="text",
                provider="routerai",
                model="m",
                http_status=200,
                ok=True,
                latency_ms=1,
            )


class TestRouteraiRecords(unittest.IsolatedAsyncioTestCase):
    async def test_success_records_roundtrip(self) -> None:
        recorded: dict = {}

        async def _capture(**kwargs):
            recorded.update(kwargs)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                },
            )

        transport = httpx.MockTransport(handler)
        with patch("waifu_bot.services.llm_client._routerai_provider") as mock_prov, patch(
            "waifu_bot.services.llm_usage.record_llm_http", _capture
        ):
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
        self.assertEqual(recorded.get("caller"), "test-routerai-direct")
        self.assertEqual(recorded.get("ok"), True)
        self.assertEqual(recorded.get("http_status"), 200)
        self.assertEqual(recorded.get("prompt_tokens"), 3)
        self.assertEqual(recorded.get("completion_tokens"), 5)
        self.assertEqual(recorded.get("modality"), "text")

    async def test_timeout_records_not_ok(self) -> None:
        recorded: dict = {}

        async def _capture(**kwargs):
            recorded.update(kwargs)

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        transport = httpx.MockTransport(handler)
        with patch("waifu_bot.services.llm_client._routerai_provider") as mock_prov, patch(
            "waifu_bot.services.llm_usage.record_llm_http", _capture
        ):
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
            with self.assertRaises(httpx.ReadTimeout):
                async with httpx.AsyncClient(transport=transport) as client:
                    await post_chat_completions_routerai(
                        client,
                        {"messages": [{"role": "user", "content": "ping"}]},
                        model="google/gemini-3.5-flash",
                        caller="test-timeout",
                    )
        self.assertEqual(recorded.get("caller"), "test-timeout")
        self.assertEqual(recorded.get("ok"), False)
        self.assertIsNone(recorded.get("http_status"))


class TestAdminRouteWired(unittest.TestCase):
    def test_usage_path_registered(self) -> None:
        from waifu_bot.api.armory_routes import router

        paths = {getattr(r, "path", None) for r in router.routes}
        self.assertIn("/armory/admin/llm/usage", paths)

    def test_non_admin_gets_403(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from waifu_bot.api import armory_deps as ad
        from waifu_bot.api.armory_deps import require_armory_user
        from waifu_bot.api.armory_routes import router
        from waifu_bot.api.deps import get_db

        app = FastAPI()
        app.include_router(router)

        async def as_player() -> int:
            return 424242

        async def fake_db():
            yield None

        app.dependency_overrides[require_armory_user] = as_player
        app.dependency_overrides[get_db] = fake_db
        with patch.object(ad.settings, "admin_ids", []):
            resp = TestClient(app).get("/armory/admin/llm/usage")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("detail"), "admin access required")


if __name__ == "__main__":
    unittest.main()
