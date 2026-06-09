"""Unit tests for guild raid leave / abort."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.guild_raid_service import leave_raid
from waifu_bot.services.guild_raid_v2_service import leader_cancel_raid


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _participant(pid: int):
    return SimpleNamespace(raid_id=10, player_id=pid)


def _setup_leave(
    *,
    player_id: int,
    is_leader: bool = False,
    remaining_after_delete: int = 2,
    raid_version: int = 2,
):
    mem = SimpleNamespace(guild_id=1, player_id=player_id, is_leader=is_leader)
    guild = SimpleNamespace(id=1, tag="TST", raid_active_id=10, telegram_chat_id=-100)
    raid = SimpleNamespace(
        id=10,
        status="active",
        raid_version=raid_version,
        party_snapshot_json=[],
    )
    session = AsyncMock()
    session.get = AsyncMock(
        side_effect=lambda model, pk: guild if pk == 1 else raid if pk == 10 else None
    )
    session.execute = AsyncMock(
        side_effect=[
            _scalar_result(mem),
            _scalar_result(_participant(player_id)),
            _scalars_result([201, 202][:remaining_after_delete]),
        ]
    )
    session.scalar = AsyncMock(return_value=remaining_after_delete)
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session, guild, raid, mem


def test_leave_aborts_when_leader_leaves():
    async def _run():
        session, guild, raid, _mem = _setup_leave(player_id=100, is_leader=True, remaining_after_delete=2)
        with patch(
            "waifu_bot.services.guild_raid_v2_service.cancel_guild_raid",
            new_callable=AsyncMock,
        ) as cancel_mock:
            out = await leave_raid(session, 100)
        cancel_mock.assert_awaited_once()
        assert cancel_mock.await_args.kwargs["reason"] == "leader_left"
        assert out == {"success": True, "raid_cancelled": True, "reason": "leader_left"}
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_leave_aborts_when_last_participant():
    async def _run():
        session, guild, raid, _mem = _setup_leave(
            player_id=100, is_leader=False, remaining_after_delete=0
        )
        with patch(
            "waifu_bot.services.guild_raid_v2_service.cancel_guild_raid",
            new_callable=AsyncMock,
        ) as cancel_mock:
            out = await leave_raid(session, 100)
        cancel_mock.assert_awaited_once()
        assert cancel_mock.await_args.kwargs["reason"] == "no_participants"
        assert out == {"success": True, "raid_cancelled": True, "reason": "no_participants"}

    asyncio.run(_run())


def test_leave_keeps_raid_when_member_leaves():
    async def _run():
        session, guild, raid, _mem = _setup_leave(
            player_id=100, is_leader=False, remaining_after_delete=2
        )
        snapshot = [{"player_id": 201, "name": "A"}, {"player_id": 202, "name": "B"}]
        with patch(
            "waifu_bot.services.guild_raid_v2_service.cancel_guild_raid",
            new_callable=AsyncMock,
        ) as cancel_mock, patch(
            "waifu_bot.services.guild_raid_v2_service._build_party_snapshot",
            new_callable=AsyncMock,
            return_value=snapshot,
        ) as snap_mock:
            out = await leave_raid(session, 100)
        cancel_mock.assert_not_awaited()
        snap_mock.assert_awaited_once_with(session, [201, 202])
        assert raid.party_snapshot_json == snapshot
        assert guild.raid_active_id == 10
        assert out == {"success": True, "raid_cancelled": False}

    asyncio.run(_run())


def test_leave_not_participant_returns_error():
    async def _run():
        mem = SimpleNamespace(guild_id=1, player_id=100, is_leader=False)
        guild = SimpleNamespace(id=1, tag="TST", raid_active_id=10)
        raid = SimpleNamespace(id=10, status="active", raid_version=2)
        session = AsyncMock()
        session.get = AsyncMock(
            side_effect=lambda model, pk: guild if pk == 1 else raid if pk == 10 else None
        )
        session.execute = AsyncMock(
            side_effect=[_scalar_result(mem), _scalar_result(None)]
        )
        out = await leave_raid(session, 100)
        assert out == {"error": "not_in_raid"}
        session.commit.assert_not_awaited()

    asyncio.run(_run())


def test_leader_cancel_raid_success():
    async def _run():
        mem = SimpleNamespace(guild_id=1, player_id=100, is_leader=True)
        guild = SimpleNamespace(id=1, tag="TST", raid_active_id=10, telegram_chat_id=-100)
        raid = SimpleNamespace(id=10, status="active")
        session = AsyncMock()
        session.get = AsyncMock(
            side_effect=lambda model, pk: guild if pk == 1 else raid if pk == 10 else None
        )
        session.execute = AsyncMock(return_value=_scalar_result(mem))
        session.commit = AsyncMock()
        with patch(
            "waifu_bot.services.guild_raid_v2_service.cancel_guild_raid",
            new_callable=AsyncMock,
        ) as cancel_mock:
            out = await leader_cancel_raid(session, 100)
        cancel_mock.assert_awaited_once()
        assert cancel_mock.await_args.kwargs["reason"] == "leader_cancel"
        assert out == {"success": True, "raid_id": 10}
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_leader_cancel_raid_forbidden():
    async def _run():
        mem = SimpleNamespace(guild_id=1, player_id=100, is_leader=False)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalar_result(mem))
        out = await leader_cancel_raid(session, 100)
        assert out == {"error": "forbidden"}
        session.commit.assert_not_awaited()

    asyncio.run(_run())


def test_leader_cancel_raid_no_active():
    async def _run():
        mem = SimpleNamespace(guild_id=1, player_id=100, is_leader=True)
        guild = SimpleNamespace(id=1, tag="TST", raid_active_id=None)
        session = AsyncMock()
        session.get = AsyncMock(return_value=guild)
        session.execute = AsyncMock(return_value=_scalar_result(mem))
        out = await leader_cancel_raid(session, 100)
        assert out == {"error": "no_active_raid"}
        session.commit.assert_not_awaited()

    asyncio.run(_run())
