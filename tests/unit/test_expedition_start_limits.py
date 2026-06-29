"""Unit tests: expedition start (v2 path + legacy config guard)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.expedition import ExpeditionService


@pytest.fixture
def service() -> ExpeditionService:
    return ExpeditionService()


def test_start_rejects_missing_config_without_v2(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        result = await service.start(session, 123, None, [1], 60)
        assert result == {"error": "missing_expedition_config"}

    asyncio.run(_run())


def test_start_v2_bypasses_legacy_slot_requirement(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        expected = {"success": True, "active_id": 7, "reward_type": "gold", "depth_tier": 1}
        with patch(
            "waifu_bot.services.expedition_v2_start.start_expedition_v2",
            new_callable=AsyncMock,
            return_value=expected,
        ) as mock_v2:
            result = await service.start(
                session,
                123,
                None,
                [1, 2],
                60,
                reward_type="gold",
                depth_tier=1,
            )
        assert result == expected
        mock_v2.assert_awaited_once()

    asyncio.run(_run())


def test_start_legacy_daily_slot_when_no_v2_params(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        player = AsyncMock()
        expected = {"success": True, "active_id": 7}
        with (
            patch.object(service, "_lock_player_for_update", new_callable=AsyncMock, return_value=player),
            patch.object(service, "_start_daily_slot_v13", new_callable=AsyncMock, return_value=expected) as mock_start,
        ):
            result = await service.start(session, 123, 99, [1, 2], 60, difficulty_level=3)
        assert result == expected
        mock_start.assert_awaited_once_with(session, 123, 99, [1, 2], 60, 3)

    asyncio.run(_run())


def test_commit_start_or_slot_conflict_maps_integrity_error(service: ExpeditionService):
    async def _run():
        from sqlalchemy.exc import IntegrityError

        session = AsyncMock()
        session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))
        session.rollback = AsyncMock()
        result = await service._commit_start_or_slot_conflict(session)
        assert result == {"error": "already_started"}
        session.rollback.assert_awaited_once()

    asyncio.run(_run())
