"""Unit tests for guild max_hp_pct in waifu HP sync."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from waifu_bot.services.waifu_hp import sync_waifu_max_hp


def test_sync_waifu_max_hp_applies_guild_vitality():
    async def _run():
        waifu = SimpleNamespace(
            level=10,
            endurance=10,
            strength=10,
            max_hp=1000,
            current_hp=900,
        )
        session = AsyncMock()
        with patch(
            "waifu_bot.services.waifu_hp.compute_effective_max_hp",
            new_callable=AsyncMock,
            return_value=1070,
        ) as compute_mock:
            await sync_waifu_max_hp(session, 42, waifu)
        compute_mock.assert_awaited_once_with(session, 42, waifu)
        assert waifu.max_hp == 1070
        assert waifu.current_hp == 900

    asyncio.run(_run())
