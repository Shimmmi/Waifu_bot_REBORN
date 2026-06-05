"""Unit tests: expedition start limits (daily cap, constructor block, slot conflict)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from waifu_bot.game.constants import EXPEDITION_SLOTS_PER_DAY
from waifu_bot.services.expedition import ExpeditionService


@pytest.fixture
def service() -> ExpeditionService:
    return ExpeditionService()


def test_start_rejects_constructor_without_slot(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        result = await service.start(
            session,
            123,
            None,
            [1, 2],
            60,
            affix_template_id=6,
            affix_level=3,
            display_base_location="Ruins",
        )
        assert result == {"error": "constructor_disabled"}

    asyncio.run(_run())


def test_start_rejects_missing_daily_slot_config(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        result = await service.start(session, 123, 42, [1], 60)
        assert result == {"error": "missing_expedition_config"}

    asyncio.run(_run())


def test_start_rejects_when_daily_limit_reached(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        player = MagicMock()
        with (
            patch.object(
                service,
                "_lock_player_for_update",
                new_callable=AsyncMock,
                return_value=player,
            ),
            patch.object(
                service,
                "_check_daily_start_limit",
                new_callable=AsyncMock,
                return_value={"error": "daily_limit_reached", "max": EXPEDITION_SLOTS_PER_DAY},
            ),
        ):
            result = await service.start(
                session,
                123,
                99,
                [1],
                60,
                difficulty_level=2,
            )
        assert result["error"] == "daily_limit_reached"
        assert result["max"] == EXPEDITION_SLOTS_PER_DAY

    asyncio.run(_run())


def test_start_delegates_to_daily_slot_when_config_valid(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        player = MagicMock()
        expected = {"success": True, "active_id": 7}
        with (
            patch.object(
                service,
                "_lock_player_for_update",
                new_callable=AsyncMock,
                return_value=player,
            ),
            patch.object(
                service,
                "_check_daily_start_limit",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(
                service,
                "_start_daily_slot_v13",
                new_callable=AsyncMock,
                return_value=expected,
            ) as mock_start,
        ):
            result = await service.start(
                session,
                123,
                99,
                [1, 2],
                60,
                difficulty_level=3,
            )
        assert result == expected
        mock_start.assert_awaited_once_with(session, 123, 99, [1, 2], 60, 3)

    asyncio.run(_run())


def test_commit_start_or_slot_conflict_maps_integrity_error(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        session.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception()))
        session.rollback = AsyncMock()
        result = await service._commit_start_or_slot_conflict(session)
        assert result == {"error": "already_started"}
        session.rollback.assert_awaited_once()

    asyncio.run(_run())


def test_check_daily_start_limit_blocks_at_cap(service: ExpeditionService):
    async def _run():
        session = AsyncMock()
        with patch.object(
            service,
            "_count_starts_today",
            new_callable=AsyncMock,
            return_value=EXPEDITION_SLOTS_PER_DAY,
        ):
            result = await service._check_daily_start_limit(session, 123)
        assert result == {"error": "daily_limit_reached", "max": EXPEDITION_SLOTS_PER_DAY}

    asyncio.run(_run())


def test_parallel_start_only_one_commits(service: ExpeditionService):
    """Simulate race: second commit hits unique index and returns already_started."""

    async def _run():
        session = AsyncMock()
        commit_calls = 0

        async def fake_commit():
            nonlocal commit_calls
            commit_calls += 1
            if commit_calls > 1:
                raise IntegrityError("stmt", {}, Exception())

        session.commit = fake_commit
        session.rollback = AsyncMock()

        first = await service._commit_start_or_slot_conflict(session)
        second = await service._commit_start_or_slot_conflict(session)

        assert first is None
        assert second == {"error": "already_started"}

    asyncio.run(_run())
