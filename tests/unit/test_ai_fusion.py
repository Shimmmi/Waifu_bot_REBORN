"""Unit tests for RouterAI fusion orchestration."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from waifu_bot.services.ai_fusion import run_fusion, run_fusion_roles
from waifu_bot.services.ai_presets import FusionPreset, FusionRolesJudge, FusionRolesPreset, FusionRoleSpec, PresetDefaults


def _ok_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
    )


class TestAiFusion(unittest.IsolatedAsyncioTestCase):
    async def test_fusion_judge_synthesis(self) -> None:
        preset = FusionPreset(
            experts=["google/gemini-3.5-flash", "z-ai/glm-5.2"],
            judge="z-ai/glm-5.2",
        )
        defaults = PresetDefaults()
        messages = [{"role": "user", "content": "Balance this item"}]

        async def fake_post(client, payload, *, model, caller, use_fusion_semaphore=False):
            if "judge" in caller:
                return _ok_response("Final balanced answer")
            if "gemini" in model:
                return _ok_response("Gemini says increase HP")
            return _ok_response("GLM says reduce damage")

        with patch(
            "waifu_bot.services.ai_fusion.post_chat_completions_routerai",
            new=AsyncMock(side_effect=fake_post),
        ):
            async with httpx.AsyncClient() as client:
                out = await run_fusion(
                    preset,
                    messages,
                    defaults=defaults,
                    caller="test-fusion",
                    client=client,
                )
        self.assertEqual(out, "Final balanced answer")

    async def test_fusion_judge_fallback_to_expert(self) -> None:
        preset = FusionPreset(experts=["google/gemini-3.5-flash"], judge="z-ai/glm-5.2")
        defaults = PresetDefaults()
        messages = [{"role": "user", "content": "Hello"}]

        async def fake_post(client, payload, *, model, caller, use_fusion_semaphore=False):
            if "judge" in caller:
                return httpx.Response(500, json={"error": "fail"})
            return _ok_response("Expert long answer with details")

        with patch(
            "waifu_bot.services.ai_fusion.post_chat_completions_routerai",
            new=AsyncMock(side_effect=fake_post),
        ):
            async with httpx.AsyncClient() as client:
                out = await run_fusion(
                    preset,
                    messages,
                    defaults=defaults,
                    caller="test-fusion-fallback",
                    client=client,
                )
        self.assertEqual(out, "Expert long answer with details")

    async def test_fusion_roles(self) -> None:
        preset = FusionRolesPreset(
            roles={
                "architect": FusionRoleSpec(model="anthropic/claude-sonnet-4.6", system="architect"),
                "engineer": FusionRoleSpec(model="z-ai/glm-5.2", system="engineer"),
            },
            judge=FusionRolesJudge(model="anthropic/claude-sonnet-4.6", system="judge"),
        )
        defaults = PresetDefaults()

        async def fake_post(client, payload, *, model, caller, use_fusion_semaphore=False):
            if "judge" in caller:
                return _ok_response("Synthesized plan")
            return _ok_response(f"Role answer from {model}")

        with patch(
            "waifu_bot.services.ai_fusion.post_chat_completions_routerai",
            new=AsyncMock(side_effect=fake_post),
        ):
            async with httpx.AsyncClient() as client:
                out = await run_fusion_roles(
                    preset,
                    "Design cache layer",
                    defaults=defaults,
                    caller="test-roles",
                    client=client,
                )
        self.assertEqual(out, "Synthesized plan")


if __name__ == "__main__":
    unittest.main()
