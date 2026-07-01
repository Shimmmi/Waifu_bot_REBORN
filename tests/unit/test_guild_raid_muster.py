"""Unit tests for guild raid muster callbacks."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.guild_raid_v2_service import (
    MUSTER_STATUS_CANCELLED,
    MUSTER_STATUS_COMPLETED,
    MUSTER_STATUS_PENDING,
    respond_muster,
)


def _pending_muster(*, responses=None, pids=None, muster_id=1):
    return SimpleNamespace(
        id=muster_id,
        guild_id=10,
        initiator_player_id=100,
        status=MUSTER_STATUS_PENDING,
        participant_ids_json=pids or [100, 200],
        responses_json=dict(responses or {}),
        raid_id=None,
        deadline_at=datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc),
    )


def test_respond_muster_accept_one_of_two_pending():
    async def _run():
        muster = _pending_muster()
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)
        session.commit = AsyncMock()

        out = await respond_muster(session, 100, 1, True)

        assert out["status"] == "pending"
        assert muster.responses_json["100"] == "accepted"
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_respond_muster_accept_second_starts_raid():
    async def _run():
        muster = _pending_muster(responses={"100": "accepted"})
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)

        started = {"success": True, "status": "started", "raid_id": 99}

        with patch(
            "waifu_bot.services.guild_raid_v2_service._complete_muster_and_start_raid",
            AsyncMock(return_value=started),
        ) as complete_mock:
            out = await respond_muster(session, 200, 1, True)

        complete_mock.assert_awaited_once_with(session, muster)
        assert out["status"] == "started"
        assert out["raid_id"] == 99

    asyncio.run(_run())


def test_respond_muster_idempotent_accept():
    async def _run():
        muster = _pending_muster(responses={"100": "accepted"})
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)
        session.commit = AsyncMock()

        out = await respond_muster(session, 100, 1, True)

        assert out["status"] == "pending"
        assert out.get("idempotent") is True
        session.commit.assert_not_awaited()

    asyncio.run(_run())


def test_respond_muster_idempotent_accept_all_triggers_complete():
    async def _run():
        muster = _pending_muster(responses={"100": "accepted", "200": "accepted"})
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)

        started = {"success": True, "status": "started", "raid_id": 42}

        with patch(
            "waifu_bot.services.guild_raid_v2_service._complete_muster_and_start_raid",
            AsyncMock(return_value=started),
        ) as complete_mock:
            out = await respond_muster(session, 100, 1, True)

        complete_mock.assert_awaited_once_with(session, muster)
        assert out["status"] == "started"

    asyncio.run(_run())


def test_respond_muster_decline_cancels():
    async def _run():
        muster = _pending_muster()
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)
        session.commit = AsyncMock()

        out = await respond_muster(session, 100, 1, False)

        assert out["status"] == "cancelled"
        assert muster.status == MUSTER_STATUS_CANCELLED
        assert muster.responses_json["100"] == "declined"
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_respond_muster_not_invited():
    async def _run():
        muster = _pending_muster()
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)

        out = await respond_muster(session, 999, 1, True)

        assert out == {"error": "not_invited"}

    asyncio.run(_run())


def test_respond_muster_not_found_when_completed():
    async def _run():
        muster = _pending_muster()
        muster.status = MUSTER_STATUS_COMPLETED
        session = AsyncMock()
        session.get = AsyncMock(return_value=muster)

        out = await respond_muster(session, 100, 1, True)

        assert out == {"error": "muster_not_found"}

    asyncio.run(_run())


def test_complete_muster_schedules_prologue_in_background():
    async def _run():
        from waifu_bot.services.guild_raid_v2_service import _complete_muster_and_start_raid

        muster = _pending_muster(responses={"100": "accepted", "200": "accepted"})
        guild = SimpleNamespace(
            id=10,
            raid_active_id=None,
            telegram_chat_id=-100555,
            name="Test Guild",
            tag="TEST",
        )
        tpl = SimpleNamespace(id=1, gxp_reward=100)
        raid = SimpleNamespace(id=77)

        session = AsyncMock()
        session.get = AsyncMock(side_effect=lambda model, pk: guild if pk == 10 else None)
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        async def _flush_side_effect():
            session.add.call_args_list  # raid added via session.add

        session.flush.side_effect = _flush_side_effect

        with patch(
            "waifu_bot.services.guild_raid_v2_service._best_template",
            AsyncMock(return_value=tpl),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service._build_party_snapshot",
            AsyncMock(return_value=[{"name": "A"}]),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.pick_random_raid_setting",
            return_value=("forest", 1),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.GuildRaid",
            side_effect=lambda **kwargs: SimpleNamespace(id=77, **kwargs),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service._schedule_raid_prologue",
        ) as schedule_mock:
            out = await _complete_muster_and_start_raid(session, muster)

        assert out["status"] == "started"
        assert out["raid_id"] == 77
        assert muster.status == MUSTER_STATUS_COMPLETED
        schedule_mock.assert_called_once_with(77)

    asyncio.run(_run())
