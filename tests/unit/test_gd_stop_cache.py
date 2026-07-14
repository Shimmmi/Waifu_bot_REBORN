"""GD stop bypasses Redis negative cache; get_active heals poisoned sentinel."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_active_v1_cycle_ignores_negative_sentinel_and_hits_db():
    from waifu_bot.services.gd_cycle_service import GDCycleService

    redis = MagicMock()
    gd = GDCycleService(redis)
    cycle = SimpleNamespace(id=42, status="active", chat_id=-1001)
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: cycle)
    )

    with patch(
        "waifu_bot.services.gd_cycle_service.gd_active_cache_mod.get_cached_active_cycle_id",
        new=AsyncMock(return_value=None),  # poisoned "none"
    ), patch(
        "waifu_bot.services.gd_cycle_service.gd_active_cache_mod.set_active_cycle_cache",
        new=AsyncMock(),
    ) as set_cache, patch(
        "waifu_bot.services.gd_cycle_service.gd_active_cache_mod.invalidate_active_cycle_cache",
        new=AsyncMock(),
    ):
        got = await gd.get_active_v1_cycle(session, -1001)

    assert got is cycle
    set_cache.assert_awaited()
    assert set_cache.await_args.args[2] == 42


@pytest.mark.asyncio
async def test_stop_gd_by_cycle_id_bypasses_redis():
    from waifu_bot.services.gd_webapp_service import stop_gd_for_player

    session = AsyncMock()
    cycle = SimpleNamespace(
        id=7, status="active", chat_id=-1001, battle_state_json={}
    )
    session.get = AsyncMock(return_value=cycle)
    session.scalar = AsyncMock(return_value=99)
    gd = MagicMock()
    gd.cancel_active_cycle = AsyncMock(
        return_value={"success": True, "cycle_id": 7, "chat_id": -1001, "reason": "player_stop"}
    )

    with patch(
        "waifu_bot.services.gd_webapp_service.get_game_config_map",
        new=AsyncMock(return_value={"gd_stop_enabled": "1"}),
    ):
        result = await stop_gd_for_player(
            session, 1, gd, None, cycle_id=7
        )

    assert result.get("success") is True
    gd.cancel_active_cycle.assert_awaited_once()
    gd.get_active_v1_cycle.assert_not_called()
