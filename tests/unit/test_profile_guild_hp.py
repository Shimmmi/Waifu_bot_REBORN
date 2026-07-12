"""Tests for guild HP in profile details and compute."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.passive_skills import apply_guild_hp_to_profile_details
from waifu_bot.services.waifu_hp import compute_effective_max_hp


def test_apply_guild_hp_to_profile_details():
    out = apply_guild_hp_to_profile_details({"hp_max": 1000}, {"max_hp_pct": 0.07})
    assert out["hp_max"] == 1070


def test_apply_guild_hp_to_profile_details_no_guild():
    out = apply_guild_hp_to_profile_details({"hp_max": 1000}, {})
    assert out["hp_max"] == 1000


def test_compute_effective_max_hp_applies_guild_pct():
    async def _run():
        waifu = SimpleNamespace(
            level=10,
            endurance=10,
            strength=10,
        )
        session = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=empty_result)

        with patch(
            "waifu_bot.services.passive_skills.get_passive_skill_bonuses",
            new_callable=AsyncMock,
            return_value={},
        ):
            with patch(
                "waifu_bot.services.guild_skill_effects.effect_values_for_player",
                new_callable=AsyncMock,
                return_value={},
            ):
                base = await compute_effective_max_hp(session, 42, waifu)
            with patch(
                "waifu_bot.services.guild_skill_effects.effect_values_for_player",
                new_callable=AsyncMock,
                return_value={"max_hp_pct": 0.07},
            ):
                boosted = await compute_effective_max_hp(session, 42, waifu)
        assert boosted == int(round(base * 1.07))

    asyncio.run(_run())
